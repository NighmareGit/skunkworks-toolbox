#!/usr/bin/env python3
"""
academic-mcp — keyless, local MCP server for academic research.

Tools:
  academic_search         — fan-out search across OpenAlex/arXiv/Crossref/PubMed
                            dual-mode via focus="general"|"ml" (default general)
  academic_citation_chain — OpenAlex citation-graph traversal (the gap)
  academic_get_paper       — metadata + abstract + OA PDF link
  academic_tldr            — best-effort TLDRs from Semantic Scholar

All sources are keyless REST. Stdlib urllib for HTTP (zero extra deps beyond mcp).
Uses the canonical mcp.server low-level API for reliable stdio transport.
"""

import asyncio
import json
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

POLITE_TIMEOUT = 10  # seconds per HTTP call
MAX_WORKERS = 3  # parallel source fan-out
RETRY_STATUSES = {429, 500, 502, 503, 504}

OPENALEX_MAILTO = os.environ.get("OPENALEX_MAILTO", "research@example.org")
UNPAYWALL_EMAIL = os.environ.get("UNPAYWALL_EMAIL", "research@example.org")

# ---------------------------------------------------------------------------
# ML-focus weighting tables (for focus="ml" mode)
# ---------------------------------------------------------------------------

# Venues whose (lowercased) name contains any of these tokens get the max
# venue sub-score. Covers the major ML-systems / DL conferences and journals.
ML_VENUE_TOKENS = {
    "neurips", "nips", "icml", "iclr", "mlsys",
    "cvpr", "iccv", "eccv",
    "acl", "emnlp", "naacl",
    "tmlr", "jmlr",
    "tpami", "ijcv", "tip", "tmm",
    "transactions on machine learning research",
    "transactions on pattern analysis",
    "machine learning", "knowledge and information",
    "neural computation", "neurocomputing",
    "artificial intelligence", "journal of machine learning",
    "international conference on learning representations",
    "conference on neural information processing",
    "computer vision and pattern recognition",
    "association for computational linguistics",
    "empirical methods in natural language",
    "north american association for computational",
    "conference on language modeling", "colm",
    "uncertainty in artificial intelligence", "uai",
    "algorithmic learning theory", "colt",
    "international conference on artificial intelligence", "ijcai",
    "association for the advancement of aa", "aaai",
    "conference on empirical methods",
    "neural information processing systems",
    "international conference on machine learning",
    "learning representations",
}

# OpenAlex concept display_names (lowercased) that signal ML relevance.
# A paper's concept sub-score = min(matches / 3, 1.0) — saturates at 3 hits.
ML_CONCEPT_NAMES = {
    "machine learning", "artificial intelligence",
    "natural language processing", "computer vision",
    "theoretical computer science", "deep learning",
    "reinforcement learning", "neural network",
    "language model", "large language model",
    "mixture of experts", "attention mechanism",
    "generative adversarial network", "representation learning",
    "transfer learning", "multi-task learning",
    "self-supervised learning", "contrastive learning",
    "transformer", "convolutional neural network",
    "recurrent neural network", "graph neural network",
    "generative pre-training", "prompt engineering",
    "in-context learning", "instruction tuning",
    "reinforcement learning from human",
    "text generation", "image generation",
    "diffusion model", "variational autoencoder",
    "bayesian inference", "probabilistic graphical model",
    "kernel method", "gaussian process",
    "optimization", "stochastic gradient descent",
    "parallel computing", "distributed computing",
    "software engineering", "programming language",
    "data structure", "algorithm",
    "computation and language", "computer science",
}

# arXiv primary categories that count as ML-ish — used for the source
# sub-score when the result came from the arXiv adapter.
ARXIV_ML_CATEGORIES = {
    "cs.LG", "cs.CL", "cs.AI", "cs.CV", "cs.NE",
    "cs.MA", "cs.DC", "cs.AR", "cs.SE", "cs.PL",
    "stat.ML", "stat.TH",
}

# Weights for the four focus sub-scores → total.
FOCUS_W_SOURCE = 0.20
FOCUS_W_VENUE = 0.25
FOCUS_W_CONCEPT = 0.30
FOCUS_W_RECENCY = 0.25

# Recency: papers within RECENCY_FULL_YEARS get score 1.0, then linear
# decay to 0 at RECENCY_ZERO_YEARS.
RECENCY_FULL_YEARS = 2
RECENCY_ZERO_YEARS = 7

# How strongly the focus total re-weights the citation ranking.
# effective_score = citation_count * (1 + FOCUS_LIFT * focus_total)
FOCUS_LIFT = 1.5


def _compute_focus_score(paper: dict, current_year: int) -> dict:
    """Compute the per-result focus_score breakdown for focus="ml".

    Returns a dict with source/venue/concept/recency sub-scores (each 0.0–1.0)
    and a weighted total. Pure function of the paper dict + current_year.
    """
    # --- source sub-score ---
    source = paper.get("source", "")
    arxiv_cat = paper.get("_arxiv_category", "")
    if source == "arxiv" and arxiv_cat in ARXIV_ML_CATEGORIES:
        source_score = 1.0
    elif source == "arxiv":
        source_score = 0.4
    elif source == "openalex":
        source_score = 0.3
    else:
        source_score = 0.0

    # --- venue sub-score ---
    venue = (paper.get("venue") or "").lower()
    venue_score = 0.0
    if venue:
        for token in ML_VENUE_TOKENS:
            if token in venue:
                venue_score = 1.0
                break
        if venue_score == 0.0 and ("arxiv" in venue or "preprint" in venue):
            venue_score = 0.3

    # --- concept sub-score ---
    concepts = paper.get("_concepts", [])
    concept_names = {
        c.get("display_name", "").lower() for c in concepts
        if c.get("display_name")
    }
    if concept_names:
        matches = 0
        for ml_name in ML_CONCEPT_NAMES:
            for cn in concept_names:
                if ml_name in cn or cn in ml_name:
                    matches += 1
                    break
        concept_score = min(matches / 3.0, 1.0)
    else:
        concept_score = 0.0

    # --- recency sub-score ---
    year = paper.get("year", 0) or 0
    age = current_year - year
    if age <= RECENCY_FULL_YEARS:
        recency_score = 1.0
    elif age >= RECENCY_ZERO_YEARS:
        recency_score = 0.0
    else:
        span = RECENCY_ZERO_YEARS - RECENCY_FULL_YEARS
        recency_score = (RECENCY_ZERO_YEARS - age) / span if span > 0 else 0.0

    total = (
        FOCUS_W_SOURCE * source_score
        + FOCUS_W_VENUE * venue_score
        + FOCUS_W_CONCEPT * concept_score
        + FOCUS_W_RECENCY * recency_score
    )
    return {
        "source": round(source_score, 2),
        "venue": round(venue_score, 2),
        "concept": round(concept_score, 2),
        "recency": round(recency_score, 2),
        "total": round(total, 3),
    }


# ---------------------------------------------------------------------------
# HTTP helper (stdlib only)
# ---------------------------------------------------------------------------


def http_get(url: str, timeout: int = POLITE_TIMEOUT) -> tuple[int, bytes]:
    """GET url, return (status, body). Never raises — returns (0, b'') on failure."""
    req = urllib.request.Request(url, headers={"User-Agent": "academic-mcp/1.0 (mailto:" + OPENALEX_MAILTO + ")"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception:
        return 0, b""


def http_get_json(url: str, timeout: int = POLITE_TIMEOUT) -> dict | list | None:
    """GET JSON, retry once on 429/5xx. Returns parsed JSON or None."""
    status, body = http_get(url, timeout)
    if status in RETRY_STATUSES:
        import time
        time.sleep(1.5)
        status, body = http_get(url, timeout)
    if status == 200 and body:
        try:
            return json.loads(body.decode("utf-8", errors="replace"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
    return None


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation/diacritics/double-space for dedup keys."""
    if not title:
        return ""
    t = title.lower().strip()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def normalize_doi(doi: str) -> str:
    """Strip resolver prefix + lowercase for comparison."""
    if not doi:
        return ""
    d = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    return d.strip()


def strip_html(text: str) -> str:
    """Strip HTML tags + decode common entities (titles leak <scp>, <sup>, etc.)."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    # Numeric entities (decimal + hex)
    text = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), text)
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    # Named entities
    for ent, ch in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                    ("&quot;", '"'), ("&#39;", "'"), ("&apos;", "'"),
                    ("&nbsp;", " "), ("&mdash;", "—"), ("&ndash;", "–"),
                    ("&hellip;", "…")):
        text = text.replace(ent, ch)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _is_placeholder_doi(doi: str) -> bool:
    """Detect placeholder/fake DOIs (e.g. ACM's 10.1145/nnnnnnn.nnnnnnn)."""
    if not doi:
        return False
    return bool(re.search(r"nnnnnn|xxxxxx|000000|placeholder|example\.doi", doi.lower()))


# ---------------------------------------------------------------------------
# Source adapters
# ---------------------------------------------------------------------------


def search_openalex(query: str, limit: int) -> list[dict]:
    """Search OpenAlex works. Returns list of unified-schema dicts."""
    params = urllib.parse.urlencode({"search": query, "per-page": limit, "mailto": OPENALEX_MAILTO})
    data = http_get_json(f"https://api.openalex.org/works?{params}")
    if not data or "results" not in data:
        return []
    papers = []
    for w in data["results"]:
        doi = normalize_doi(w.get("doi") or "")
        title = strip_html(w.get("title") or "")
        authors = []
        for a in w.get("authorships", [])[:10]:
            au = a.get("author", {}) or {}
            name = au.get("display_name")
            if name:
                authors.append(name)
        venue = ""
        loc = (w.get("primary_location") or {}) or {}
        src = loc.get("source") or {}
        venue = src.get("display_name") or loc.get("raw_venue_name") or ""
        oa_url = ""
        oa = w.get("open_access") or {}
        if oa.get("is_oa"):
            oa_url = oa.get("oa_url") or ""
        # Capture OpenAlex concepts for focus="ml" weighting.
        raw_concepts = w.get("concepts") or []
        concepts = [
            {"display_name": c.get("display_name", "")}
            for c in raw_concepts
            if c.get("display_name")
        ]
        year = w.get("publication_year") or 0
        abstract = ""
        inv = w.get("abstract_inverted_index")
        if inv:
            parts = []
            for word, positions in inv.items():
                for p in positions:
                    while len(parts) <= p:
                        parts.append("")
                    parts[p] = word
            abstract = " ".join(parts)
            if len(abstract) > 1500:
                abstract = abstract[:1497] + "..."
        papers.append(
            {
                "id": w.get("id", "").replace("https://", ""),
                "title": title,
                "authors": authors,
                "year": year,
                "venue": venue,
                "doi": doi,
                "arxiv_id": _extract_arxiv_id(w) or "",
                "citation_count": w.get("cited_by_count", 0) or 0,
                "abstract": abstract if abstract else "(no abstract available)",
                "source": "openalex",
                "url": w.get("doi") or w.get("id", ""),
                "open_access_url": oa_url,
                "_norm_title": normalize_title(title),
                "_norm_doi": doi,
                "_concepts": concepts,
            }
        )
    return papers


def _extract_arxiv_id(work: dict) -> str:
    """Try to find an arxiv id in a OpenAlex work record."""
    for loc in work.get("locations", []) or []:
        landing = (loc.get("landing_page_url") or "").lower()
        if "arxiv.org" in landing:
            m = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9]+\.[0-9v]+)", landing)
            if m:
                return m.group(1)
    ids = work.get("ids") or {}
    for k, v in ids.items():
        if "arxiv" in k.lower() and v:
            m = re.search(r"([0-9]{4}\.[0-9]{4,5})", v)
            if m:
                return m.group(1)
    return ""


def search_arxiv(query: str, limit: int) -> list[dict]:
    """Search arXiv via export API."""
    params = urllib.parse.urlencode({"search_query": f"all:{query}", "start": 0, "max_results": limit, "sortBy": "relevance"})
    status, body = http_get(f"http://export.arxiv.org/api/query?{params}")
    if status != 200 or not body:
        return []
    import xml.etree.ElementTree as ET
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    try:
        root = ET.fromstring(body.decode("utf-8", errors="replace"))
    except ET.ParseError:
        return []
    papers = []
    for entry in root.findall("a:entry", ns):
        title_el = entry.find("a:title", ns)
        title = strip_html(title_el.text or "").replace("\n", " ") if title_el is not None else ""
        authors = [el.find("a:name", ns).text for el in entry.findall("a:author", ns) if el.find("a:name", ns) is not None]
        pub = entry.find("a:published", ns)
        year = 0
        if pub is not None and pub.text:
            m = re.search(r"\d{4}", pub.text)
            if m:
                year = int(m.group(0))
        id_el = entry.find("a:id", ns)
        arxiv_id = ""
        if id_el is not None and id_el.text:
            m = re.search(r"arxiv\.org/abs/([0-9]+\.[0-9v]+)", id_el.text)
            if m:
                arxiv_id = m.group(1)
        doi_el = entry.find("arxiv:doi", ns)
        doi = (doi_el.text or "").strip() if doi_el is not None else ""
        # Capture primary arXiv category for focus="ml" source weighting.
        arxiv_primary_cat = ""
        cat_el = entry.find("arxiv:primary_category", ns)
        if cat_el is not None:
            arxiv_primary_cat = cat_el.get("term", "") or ""
        summary_el = entry.find("a:summary", ns)
        abstract = ""
        if summary_el is not None and summary_el.text:
            abstract = re.sub(r"\s+", " ", summary_el.text).strip()
            if len(abstract) > 1500:
                abstract = abstract[:1497] + "..."
        url = ""
        for link in entry.findall("a:link", ns):
            if link.get("title") == "pdf":
                url = link.get("href", "")
                break
        if not url and id_el is not None:
            url = id_el.text or ""
        papers.append(
            {
                "id": f"arxiv:{arxiv_id}" if arxiv_id else (id_el.text or "").replace("http://arxiv.org/abs/", "arxiv:"),
                "title": title,
                "authors": authors[:10],
                "year": year,
                "venue": "arXiv",
                "doi": doi,
                "arxiv_id": arxiv_id,
                "citation_count": 0,
                "abstract": abstract if abstract else "(no abstract available)",
                "source": "arxiv",
                "url": url,
                "open_access_url": url if url.endswith(".pdf") else (f"https://arxiv.org/pdf/{arxiv_id}.pdf" if arxiv_id else ""),
                "_norm_title": normalize_title(title),
                "_norm_doi": normalize_doi(doi),
                "_arxiv_category": arxiv_primary_cat,
                "_concepts": [],
            }
        )
    return papers


def search_crossref(query: str, limit: int) -> list[dict]:
    """Search Crossref works."""
    params = urllib.parse.urlencode({"query": query, "rows": limit, "mailto": OPENALEX_MAILTO})
    data = http_get_json(f"https://api.crossref.org/works?{params}")
    if not data or "message" not in data:
        return []
    items = data["message"].get("items", [])
    papers = []
    for item in items:
        title_list = item.get("title") or []
        title = strip_html(title_list[0]) if title_list else ""
        authors = []
        for a in item.get("author", [])[:10]:
            given = a.get("given", "")
            family = a.get("family", "")
            name = f"{given} {family}".strip()
            if name:
                authors.append(name)
        year = 0
        for key in ("published-print", "published-online", "issued", "created"):
            v = item.get(key, {})
            if v and "date-parts" in v and v["date-parts"]:
                year = (v["date-parts"][0] or [0])[0]
                if year:
                    break
        venue_list = item.get("container-title") or []
        venue = venue_list[0] if venue_list else ""
        doi = item.get("DOI", "")
        arxiv_id = ""
        for rel in (item.get("relation") or {}).values():
            for entry in rel if isinstance(rel, list) else []:
                if isinstance(entry, dict) and "arxiv" in str(entry.get("id-type", "")).lower():
                    arxiv_id = entry.get("id", "")
        abstract = item.get("abstract", "") or ""
        if abstract.startswith("<jats:"):
            abstract = re.sub(r"<[^>]+>", "", abstract)
        if len(abstract) > 1500:
            abstract = abstract[:1497] + "..."
        url = item.get("URL") or (f"https://doi.org/{doi}" if doi else "")
        citation_count = item.get("is-referenced-by-count", 0) or 0
        oa_url = ""
        for lic in item.get("link", []) or []:
            if lic.get("content-type") in ("application/pdf", "text/html"):
                oa_url = lic.get("URL", "")
                break
        papers.append(
            {
                "id": f"doi:{doi}" if doi else url,
                "title": title,
                "authors": authors,
                "year": year,
                "venue": venue,
                "doi": doi.lower(),
                "arxiv_id": arxiv_id,
                "citation_count": citation_count,
                "abstract": abstract if abstract else "(no abstract available)",
                "source": "crossref",
                "url": url,
                "open_access_url": oa_url,
                "_norm_title": normalize_title(title),
                "_norm_doi": normalize_doi(doi),
                "_arxiv_category": "",
                "_concepts": [],
            }
        )
    return papers


def search_pubmed(query: str, limit: int) -> list[dict]:
    """Search PubMed via E-utilities (esearch → esummary)."""
    params = urllib.parse.urlencode({"db": "pubmed", "term": query, "retmax": limit, "retmode": "json"})
    search_data = http_get_json(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?{params}")
    if not search_data:
        return []
    idlist = (search_data.get("esearchresult") or {}).get("idlist", []) or []
    if not idlist:
        return []
    ids = ",".join(idlist)
    sum_data = http_get_json(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={ids}&retmode=json")
    if not sum_data:
        return []
    result = sum_data.get("result") or {}
    papers = []
    for pmid in idlist:
        rec = result.get(pmid)
        if not rec:
            continue
        title = strip_html(rec.get("title") or "")
        authors = [a.get("name", "") for a in (rec.get("authors") or [])[:10] if a.get("name")]
        year = 0
        pubdate = rec.get("pubdate") or rec.get("sortpubdate") or ""
        m = re.search(r"\d{4}", pubdate)
        if m:
            year = int(m.group(0))
        venue = rec.get("fulljournalname") or rec.get("source") or ""
        doi = ""
        for aid in (rec.get("articleids") or []):
            if aid.get("idtype") == "doi":
                doi = aid.get("value", "")
        abstract = "(abstract unavailable via esummary)"
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        papers.append(
            {
                "id": f"pmid:{pmid}",
                "title": title,
                "authors": authors,
                "year": year,
                "venue": venue,
                "doi": doi.lower() if doi else "",
                "arxiv_id": "",
                "citation_count": 0,
                "abstract": abstract,
                "source": "pubmed",
                "url": url,
                "open_access_url": "",
                "_norm_title": normalize_title(title),
                "_norm_doi": normalize_doi(doi),
                "_arxiv_category": "",
                "_concepts": [],
            }
        )
    return papers


# ---------------------------------------------------------------------------
# Dedup + ranking
# ---------------------------------------------------------------------------


def dedup_and_rank(papers: list[dict], limit: int, focus: str = "general") -> list[dict]:
    """Dedup by DOI (preferred) then title; rank by citation_count desc, year desc.

    When focus="ml", re-rank with a focus-aware lift: each result gets a
    focus_score (source/venue/concept/recency sub-scores + weighted total)
    and the sort key becomes citation_count * (1 + FOCUS_LIFT * total).
    Cross-domain papers are NOT filtered out — they just sort lower. The
    per-result focus_score breakdown is exposed in the output schema.
    """
    from datetime import datetime

    seen_doi: set[str] = set()
    seen_title: set[str] = set()
    unique: list[dict] = []
    for p in papers:
        # Drop junk matches with placeholder/fake DOIs (e.g. ACM 10.1145/nnnnnnn.nnnnnnn)
        if _is_placeholder_doi(p.get("_norm_doi", "")):
            continue
        nd = p.get("_norm_doi", "")
        nt = p.get("_norm_title", "")
        if nd:
            if nd in seen_doi:
                continue
            seen_doi.add(nd)
            if nt:
                seen_title.add(nt)
            unique.append(p)
        elif nt and nt not in seen_title:
            seen_title.add(nt)
            unique.append(p)
        elif not nt:
            unique.append(p)

    if focus == "ml":
        current_year = datetime.now().year
        for p in unique:
            p["_focus_score"] = _compute_focus_score(p, current_year)
        unique.sort(
            key=lambda x: (
                x.get("citation_count", 0) * (1 + FOCUS_LIFT * x.get("_focus_score", {}).get("total", 0)),
                x.get("year", 0),
            ),
            reverse=True,
        )
    else:
        unique.sort(key=lambda x: (x.get("citation_count", 0), x.get("year", 0)), reverse=True)

    out = []
    for p in unique[:limit]:
        q = {k: v for k, v in p.items() if not k.startswith("_")}
        if focus == "ml" and "_focus_score" in p:
            q["focus_score"] = p["_focus_score"]
        out.append(q)
    return out


# ---------------------------------------------------------------------------
# Citation chain helpers
# ---------------------------------------------------------------------------


def _normalize_arxiv_id(raw: str) -> str:
    """If raw looks like a bare arXiv id (2312.11514 or 2312.11514v2),
    return the DOI form 10.48550/arXiv.<id> (version stripped). Otherwise
    return raw unchanged."""
    m = re.match(r"^(\d{4}\.\d{4,5})(v\d+)?$", raw.strip())
    if m:
        return f"10.48550/arXiv.{m.group(1)}"
    return raw


def _resolve_to_openalex_id(work_id: str) -> str:
    """Resolve a user-supplied id to an OpenAlex work id.

    Accepts: OpenAlex W-id, DOI (incl. 10.48550/arXiv.xxxx), bare arXiv id
    (2312.11514), or a title-ish string as a last-resort fallback.
    """
    w = _normalize_arxiv_id(work_id)
    # Strip common prefixes
    for prefix in ("https://api.openalex.org/works/", "https://openalex.org/works/", "openalex.org/", "openalex.org/works/"):
        if w.startswith(prefix):
            w = w[len(prefix):]
            break
    if w.startswith("W") and w[1:].isdigit():
        return f"https://api.openalex.org/works/{w}"
    if "." in w and "/" in w and not w.startswith("http"):
        url = f"https://api.openalex.org/works/doi:{urllib.parse.quote(w, safe='/:')}"
        data = http_get_json(url)
        if data and "id" in data:
            return data["id"]
    # Last resort: title search
    url = f"https://api.openalex.org/works?filter=title.search:{urllib.parse.quote(w)}&per-page=1"
    data = http_get_json(url)
    if data and data.get("results"):
        return data["results"][0].get("id", "")
    return ""


def _fetch_citation_page(work_id: str, endpoint: str, page_size: int = 50) -> list[dict]:
    """Fetch one page of referenced_works or cites for an OpenAlex work.

    For "refs" (backward): uses /{id}/referenced_works endpoint, then batch-resolves.
    For "cites" (forward): uses ?filter=cites:{id} endpoint directly.
    """
    # Extract short W-id from work_id
    m = re.search(r"W\d+", work_id)
    short_id = m.group(0) if m else work_id

    if endpoint == "cites":
        # Forward: papers that cite this one — use filter
        filter_url = f"https://api.openalex.org/works?filter=cites:{short_id}&per-page={page_size}"
        data = http_get_json(filter_url)
        if not data or "results" not in data:
            return []
        return data["results"]

    # Backward: referenced_works endpoint returns the full work object
    url = f"{work_id}/{endpoint}?per-page={page_size}"
    data = http_get_json(url)
    if not data:
        return []
    raw_ids = data.get(endpoint) or []
    if not raw_ids:
        return []
    # Extract short W-ids
    short_ids = []
    for wid in raw_ids[:page_size]:
        wm = re.search(r"W\d+", wid)
        if wm:
            short_ids.append(wm.group(0))
    if not short_ids:
        return []
    # Batch resolve via filter (single HTTP call)
    ids_str = "|".join(short_ids)
    batch_url = f"https://api.openalex.org/works?filter=ids.openalex:{ids_str}&per-page={len(short_ids)}"
    batch_data = http_get_json(batch_url)
    if not batch_data or "results" not in batch_data:
        return []
    return batch_data["results"]


def _work_to_unified(w: dict, hop: int = 0) -> dict:
    """Convert an OpenAlex work record to our unified schema."""
    doi = normalize_doi(w.get("doi") or "")
    title = strip_html(w.get("title") or "")
    authors = []
    for a in w.get("authorships", [])[:10]:
        au = a.get("author", {}) or {}
        name = au.get("display_name")
        if name:
            authors.append(name)
    venue = ""
    loc = (w.get("primary_location") or {}) or {}
    src = loc.get("source") or {}
    venue = src.get("display_name") or ""
    year = w.get("publication_year") or 0
    abstract = ""
    inv = w.get("abstract_inverted_index")
    if inv:
        parts = []
        for word, positions in inv.items():
            for p in positions:
                while len(parts) <= p:
                    parts.append("")
                parts[p] = word
        abstract = " ".join(parts)
        if len(abstract) > 800:
            abstract = abstract[:797] + "..."
    raw_id = w.get("id", "")
    # Strip any openalex.org prefix to get short W-id
    short_id = re.sub(r"https?://(api\.)?openalex\.org/works?/", "", raw_id)
    if short_id == raw_id:
        # Try without /works/ (e.g. https://openalex.org/W...)
        short_id = re.sub(r"https?://(api\.)?openalex\.org/", "", raw_id)
    return {
        "id": short_id if short_id else raw_id,
        "title": title,
        "authors": authors,
        "year": year,
        "venue": venue,
        "doi": doi,
        "citation_count": w.get("cited_by_count", 0) or 0,
        "abstract": abstract if abstract else "(no abstract available)",
        "source": "openalex",
        "url": w.get("doi") or w.get("id", ""),
        "hop": hop,
    }


# ---------------------------------------------------------------------------
# MCP server (low-level mcp.server API)
# ---------------------------------------------------------------------------

server = Server("academic-mcp")

# Thread pool for blocking IO
_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)


def _run_search(query: str, sources: list[str] | None, limit: int, focus: str = "general") -> dict:
    if sources is None:
        sources = ["openalex", "arxiv", "crossref", "pubmed"]
    sources = [s.lower().strip() for s in sources]
    focus = "ml" if focus == "ml" else "general"
    source_map = {
        "openalex": search_openalex,
        "arxiv": search_arxiv,
        "crossref": search_crossref,
        "pubmed": search_pubmed,
    }
    all_papers: list[dict] = []
    errors: list[str] = []

    def _call(name: str):
        fn = source_map.get(name)
        if not fn:
            return name, [], f"unknown source: {name}"
        try:
            return name, fn(query, limit * 2), None
        except Exception as e:
            return name, [], str(e)

    futures = [_executor.submit(_call, s) for s in sources if s in source_map]
    for fut in futures:
        name, papers, err = fut.result()
        if err:
            errors.append(f"{name}: {err}")
        else:
            all_papers.extend(papers)

    results = dedup_and_rank(all_papers, limit, focus=focus)
    return {
        "query": query,
        "focus": focus,
        "sources_queried": sources,
        "total_raw": len(all_papers),
        "total_unique": len(results),
        "errors": errors if errors else None,
        "results": results,
    }


def _run_citation_chain(work_id: str, direction: str, depth: int) -> dict:
    if depth not in (1, 2):
        return {"error": "depth must be 1 or 2"}
    oa_id = _resolve_to_openalex_id(work_id)
    if not oa_id:
        return {"error": f"could not resolve {work_id!r} to an OpenAlex work id"}
    endpoint = "referenced_works" if direction == "refs" else "cites"
    papers_by_hop: dict[int, list[dict]] = {1: [], 2: []}
    seen_ids: set[str] = {oa_id}
    hop1 = _fetch_citation_page(oa_id, endpoint, page_size=50)
    for p in hop1:
        wid = p.get("id", "")
        if wid and wid not in seen_ids:
            seen_ids.add(wid)
            papers_by_hop[1].append(_work_to_unified(p, hop=1))
    if depth >= 2:
        for parent in papers_by_hop[1][:5]:
            pid = parent.get("id", "")
            if not pid:
                continue
            # Ensure full URL for the citation endpoint
            if pid.startswith("W"):
                pid_url = f"https://api.openalex.org/works/{pid}"
            elif pid.startswith("http"):
                pid_url = pid
            else:
                continue
            hop2 = _fetch_citation_page(pid_url, endpoint, page_size=20)
            for p in hop2:
                wid = p.get("id", "")
                if wid and wid not in seen_ids:
                    seen_ids.add(wid)
                    papers_by_hop[2].append(_work_to_unified(p, hop=2))
    return {
        "start_work_id": oa_id,
        "direction": direction,
        "depth": depth,
        "hop_1_count": len(papers_by_hop[1]),
        "hop_2_count": len(papers_by_hop[2]),
        "hop_1": papers_by_hop[1][:25],
        "hop_2": papers_by_hop[2][:25] if depth >= 2 else [],
    }


def _run_get_paper(id_or_doi: str) -> dict:
    raw = id_or_doi.strip()
    # Strip common prefixes
    for prefix in ("https://api.openalex.org/works/", "https://openalex.org/works/", "openalex.org/", "openalex.org/works/"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break
    oa_url = None
    oa_data = None
    if raw.startswith("http") and "openalex.org/works" in raw:
        oa_url = raw
    elif raw.upper().startswith("W") and raw[1:].isdigit():
        oa_url = f"https://api.openalex.org/works/{raw}"
    elif re.match(r"^\d{4}\.\d{4,5}", raw):
        # Try OpenAlex search by arxiv id (full-text search)
        search_url = f"https://api.openalex.org/works?search={raw}&per-page=10"
        search_data = http_get_json(search_url)
        if search_data and search_data.get("results"):
            for r in search_data["results"]:
                for loc in r.get("locations", []) or []:
                    if raw in (loc.get("landing_page_url") or ""):
                        return _format_paper(r)
        # Fallback: arXiv API directly, then enrich with OpenAlex
        arxiv_data = _fetch_arxiv_metadata(raw)
        if arxiv_data:
            return _enrich_with_openalex(arxiv_data)
    if oa_data is None and "." in raw and "/" in raw:
        # Try DOI first
        oa_url = f"https://api.openalex.org/works/doi:{urllib.parse.quote(raw, safe='/:')}"
        oa_data = http_get_json(oa_url)
        if oa_data and "id" in oa_data:
            return _format_paper(oa_data)
        # If it looks like an arXiv DOI (10.48550/arXiv.*), extract arxiv id
        if "arxiv" in raw.lower():
            arxiv_m = re.search(r"(\d{4}\.\d{4,5})", raw)
            if arxiv_m:
                arxiv_id = arxiv_m.group(1)
                # Try OpenAlex search by arxiv id
                search_url = f"https://api.openalex.org/works?search={arxiv_id}&per-page=10"
                search_data = http_get_json(search_url)
                if search_data and search_data.get("results"):
                    for r in search_data["results"]:
                        for loc in r.get("locations", []) or []:
                            if arxiv_id in (loc.get("landing_page_url") or ""):
                                return _format_paper(r)
                # Fallback: arXiv API directly, then enrich with OpenAlex
                arxiv_data = _fetch_arxiv_metadata(arxiv_id)
                if arxiv_data:
                    return _enrich_with_openalex(arxiv_data)
        oa_data = None
    if oa_url and oa_data is None:
        oa_data = http_get_json(oa_url)
    if not oa_data:
        return {"error": f"could not resolve {id_or_doi!r}", "id_or_doi": id_or_doi}
    return _format_paper(oa_data)


def _fetch_arxiv_metadata(arxiv_id: str) -> dict | None:
    """Fetch metadata from arXiv API directly."""
    import xml.etree.ElementTree as ET
    ns = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}&max_results=1"
    status, body = http_get(url)
    if status != 200 or not body:
        return None
    try:
        root = ET.fromstring(body.decode("utf-8", errors="replace"))
    except ET.ParseError:
        return None
    entry = root.find("a:entry", ns)
    if entry is None:
        return None
    title_el = entry.find("a:title", ns)
    title = strip_html(title_el.text or "").replace("\n", " ") if title_el is not None else ""
    authors = [el.find("a:name", ns).text for el in entry.findall("a:author", ns) if el.find("a:name", ns) is not None]
    pub = entry.find("a:published", ns)
    year = 0
    if pub is not None and pub.text:
        m = re.search(r"\d{4}", pub.text)
        if m:
            year = int(m.group(0))
    summary_el = entry.find("a:summary", ns)
    abstract = ""
    if summary_el is not None and summary_el.text:
        abstract = strip_html(summary_el.text).strip()
    # DOI from arxiv:doi
    doi_el = entry.find("arxiv:doi", ns)
    doi = (doi_el.text or "").strip() if doi_el is not None else ""
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    return {
        "id": f"arxiv:{arxiv_id}",
        "title": title,
        "authors": authors[:25],
        "year": year,
        "venue": "arXiv",
        "doi": doi.lower() if doi else "",
        "arxiv_id": arxiv_id,
        "citation_count": 0,
        "abstract": abstract if abstract else "(no abstract available)",
        "source": "arxiv",
        "url": f"https://arxiv.org/abs/{arxiv_id}",
        "open_access_url": pdf_url,
        "is_open_access": True,
    }


def _enrich_with_openalex(paper: dict) -> dict:
    """Enrich an arXiv-sourced paper dict with OpenAlex citation_count + venue.

    Tries DOI lookup first, then title search. Returns the OpenAlex-formatted
    paper if a match is found; otherwise returns the original arXiv paper
    unchanged (graceful fallback — citation_count stays 0, venue stays arXiv).
    """
    doi = normalize_doi(paper.get("doi") or "")
    # Path 1: DOI → OpenAlex (most reliable when arXiv record has a DOI)
    if doi and not doi.startswith("arxiv:"):
        oa_url = f"https://api.openalex.org/works/doi:{urllib.parse.quote(doi, safe='/:')}"
        oa_data = http_get_json(oa_url)
        if oa_data and "id" in oa_data:
            return _format_paper(oa_data)
    # Path 2: title search → best OpenAlex match
    title = paper.get("title", "")
    if title:
        search_url = f"https://api.openalex.org/works?search={urllib.parse.quote(title[:200])}&per-page=5"
        search_data = http_get_json(search_url)
        if search_data and search_data.get("results"):
            norm_title = normalize_title(title)
            # Prefer an exact-ish title match
            for r in search_data["results"]:
                if normalize_title(r.get("title") or "") == norm_title:
                    return _format_paper(r)
            # Otherwise take the top result (highest relevance per OpenAlex)
            return _format_paper(search_data["results"][0])
    return paper


def _format_unpaywall(uw_data: dict) -> dict:
    """Format an Unpaywall response into our unified schema."""
    title = strip_html(uw_data.get("title") or "")
    authors = []
    for a in (uw_data.get("z_authors") or [])[:25]:
        given = a.get("given", "")
        family = a.get("family", "")
        name = f"{given} {family}".strip()
        if name:
            authors.append(name)
    year = uw_data.get("published_date", "") or ""
    year_num = 0
    if year:
        m = re.search(r"\d{4}", str(year))
        if m:
            year_num = int(m.group(0))
    venue = uw_data.get("journal_name") or ""
    doi = normalize_doi(uw_data.get("doi") or "")
    oa_url_pdf = ""
    best = uw_data.get("best_oa_location") or {}
    oa_url_pdf = best.get("url_for_pdf") or best.get("url") or ""
    if not oa_url_pdf:
        for loc in uw_data.get("oa_locations", []) or []:
            u = loc.get("url_for_pdf") or loc.get("url") or ""
            if u:
                oa_url_pdf = u
                break
    return {
        "id": uw_data.get("doi") or "",
        "title": title,
        "authors": authors,
        "year": year_num,
        "venue": venue,
        "doi": doi,
        "citation_count": 0,
        "abstract": "(abstract unavailable via Unpaywall — use academic_search for OpenAlex abstract)",
        "source": "unpaywall",
        "url": uw_data.get("doi") or "",
        "open_access_url": oa_url_pdf,
        "is_open_access": bool(oa_url_pdf) or uw_data.get("is_oa", False),
    }


def _format_paper(oa_data: dict) -> dict:
    """Format an OpenAlex work record + Unpaywall into unified schema."""
    doi = normalize_doi(oa_data.get("doi") or "")
    title = strip_html(oa_data.get("title") or "")
    authors = []
    for a in oa_data.get("authorships", [])[:25]:
        au = a.get("author", {}) or {}
        name = au.get("display_name")
        if name:
            authors.append(name)
    venue = ""
    loc = (oa_data.get("primary_location") or {}) or {}
    src = loc.get("source") or {}
    venue = src.get("display_name") or ""
    year = oa_data.get("publication_year") or 0
    abstract = ""
    inv = oa_data.get("abstract_inverted_index")
    if inv:
        parts = []
        for word, positions in inv.items():
            for p in positions:
                while len(parts) <= p:
                    parts.append("")
                parts[p] = word
        abstract = " ".join(parts)
    oa_url_pdf = ""
    if doi:
        uw_data = http_get_json(f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi, safe='/:')}?email={urllib.parse.quote(UNPAYWALL_EMAIL)}")
        if uw_data:
            best = uw_data.get("best_oa_location") or {}
            oa_url_pdf = best.get("url_for_pdf") or best.get("url") or ""
            if not oa_url_pdf:
                for loc in uw_data.get("oa_locations", []) or []:
                    u = loc.get("url_for_pdf") or loc.get("url") or ""
                    if u:
                        oa_url_pdf = u
                        break
    return {
        "id": oa_data.get("id", "").replace("https://api.openalex.org/works/", "W"),
        "title": title,
        "authors": authors,
        "year": year,
        "venue": venue,
        "doi": doi,
        "citation_count": oa_data.get("cited_by_count", 0) or 0,
        "abstract": abstract if abstract else "(no abstract available)",
        "source": "openalex+unpaywall",
        "url": oa_data.get("doi") or oa_data.get("id", ""),
        "open_access_url": oa_url_pdf,
        "is_open_access": bool(oa_url_pdf) or (oa_data.get("open_access", {}) or {}).get("is_oa", False),
    }


def _run_tldr(paper_ids: list[str]) -> dict:
    import time
    if not paper_ids:
        return {"error": "paper_ids must be non-empty"}
    # S2 batch endpoint expects {"ids": ["arXiv:...", "DOI:...", "CorpusId:..."]}
    # Prefix IDs appropriately for best resolution
    s2_ids = []
    for pid in paper_ids[:100]:
        p = pid.strip()
        if p.startswith("10.") and "/" in p and ":" not in p:
            s2_ids.append(f"DOI:{p}")
        elif re.match(r"^\d{4}\.\d{4,5}", p):
            s2_ids.append(f"arXiv:{p}")
        elif p.isdigit():
            s2_ids.append(f"CorpusId:{p}")
        else:
            s2_ids.append(p)
    ids_json = json.dumps({"ids": s2_ids})
    url = "https://api.semanticscholar.org/graph/v1/paper/batch?fields=title,year,citationCount,abstract,tldr,externalIds"
    summaries: list[dict] = []
    status = 0

    def _do_request():
        nonlocal status
        req = urllib.request.Request(url, data=ids_json.encode("utf-8"), headers={"Content-Type": "application/json", "User-Agent": "academic-mcp/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=POLITE_TIMEOUT) as resp:
                status = resp.status
                return resp.read()
        except urllib.error.HTTPError as e:
            status = e.code
            return b""
        except Exception:
            status = 0
            return b""

    body = _do_request()
    if status in RETRY_STATUSES:
        time.sleep(2)
        body = _do_request()
    if status == 200 and body:
        try:
            items = json.loads(body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            items = []
        for item in (items if isinstance(items, list) else []):
            if not item:
                continue
            tldr_text = ""
            t = item.get("tldr")
            if isinstance(t, dict):
                tldr_text = t.get("text", "") or ""
            elif isinstance(t, str):
                tldr_text = t
            summaries.append(
                {
                    "id": item.get("paperId") or "",
                    "external_ids": item.get("externalIds") or {},
                    "title": item.get("title") or "",
                    "year": item.get("year") or 0,
                    "citation_count": item.get("citationCount", 0) or 0,
                    "abstract": (item.get("abstract") or "")[:600],
                    "tldr": tldr_text if tldr_text else "(unavailable)",
                    "source": "semanticscholar",
                }
            )
    else:
        for pid in paper_ids:
            summaries.append(
                {
                    "id": pid,
                    "external_ids": {},
                    "title": "",
                    "year": 0,
                    "citation_count": 0,
                    "abstract": "",
                    "tldr": "(unavailable — Semantic Scholar returned HTTP " + str(status) + ")",
                    "source": "semanticscholar",
                }
            )
    return {
        "requested": len(paper_ids),
        "returned": len([s for s in summaries if s.get("title")]),
        "degraded": status != 200,
        "s2_status": status,
        "results": summaries,
    }


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="academic_search",
            description=(
                "Fan-out search across academic sources (OpenAlex, arXiv, Crossref, PubMed), "
                "dedup by DOI/title, rank by citation count + recency, return unified schema. "
                "Two modes via the `focus` parameter: "
                "focus=\"general\" (default) is ML-agnostic — pure citation+recency ranking. "
                "focus=\"ml\" biases (never excludes) toward ML-systems venues "
                "(NeurIPS/ICML/ICLR/MLSys/CVPR/ACL/EMNLP/TMLR/JMLR etc.), arXiv cs.* categories, "
                "and ML concepts — lateral cross-domain papers still surface but rank lower. "
                "focus=\"ml\" adds a transparent per-result `focus_score` breakdown "
                "(source/venue/concept/recency sub-scores + weighted total)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Free-text search query."},
                    "sources": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Subset of [\"openalex\",\"arxiv\",\"crossref\",\"pubmed\"]. Defaults to all four.",
                    },
                    "limit": {"type": "integer", "description": "Max results after dedup/ranking. Default 10."},
                    "focus": {
                        "type": "string",
                        "enum": ["general", "ml"],
                        "description": (
                            "\"general\" (default): ML-agnostic citation+recency ranking. "
                            "\"ml\": lateral ML/LLM-systems bias — boosts ML venues, arXiv cs.*, "
                            "and ML concepts; cross-domain papers still included but ranked lower. "
                            "Adds a transparent focus_score breakdown per result."
                        ),
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="academic_citation_chain",
            description="Walk the OpenAlex citation graph from a starting work. direction=refs (backward) or cites (cites). depth 1-2 hops.",
            inputSchema={
                "type": "object",
                "properties": {
                    "work_id": {"type": "string", "description": "OpenAlex id, DOI, or arXiv id to start from."},
                    "direction": {"type": "string", "enum": ["refs", "cites"], "description": "\"refs\" for referenced works (backward), \"cites\" for citing works (forward)."},
                    "depth": {"type": "integer", "description": "1 or 2 hops. Default 1."},
                },
                "required": ["work_id"],
            },
        ),
        Tool(
            name="academic_get_paper",
            description="Resolve a DOI, arXiv id, or OpenAlex id to full metadata + abstract + open-access PDF link.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id_or_doi": {"type": "string", "description": "DOI, arXiv id, or OpenAlex work id."},
                },
                "required": ["id_or_doi"],
            },
        ),
        Tool(
            name="academic_tldr",
            description="Best-effort TLDRs from Semantic Scholar (batch endpoint). Tolerant of 429s — retries with backoff, degrades gracefully.",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_ids": {"type": "array", "items": {"type": "string"}, "description": "DOIs, arXiv ids, or S2 paper ids."},
                },
                "required": ["paper_ids"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "academic_search":
            result = await asyncio.get_event_loop().run_in_executor(
                _executor, _run_search, arguments.get("query", ""),
                arguments.get("sources"), arguments.get("limit", 10),
                arguments.get("focus", "general")
            )
        elif name == "academic_citation_chain":
            result = await asyncio.get_event_loop().run_in_executor(
                _executor, _run_citation_chain, arguments.get("work_id", ""), arguments.get("direction", "refs"), arguments.get("depth", 1)
            )
        elif name == "academic_get_paper":
            result = await asyncio.get_event_loop().run_in_executor(
                _executor, _run_get_paper, arguments.get("id_or_doi", "")
            )
        elif name == "academic_tldr":
            result = await asyncio.get_event_loop().run_in_executor(
                _executor, _run_tldr, arguments.get("paper_ids", [])
            )
        else:
            result = {"error": f"unknown tool: {name}"}
        return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e), "tool": name}, indent=2))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
