"""
paper-search-mcp -> academic-research workflow output mapping.

`paper-search-mcp` (https://github.com/openags/paper-search-mcp) returns its
`Paper.to_dict()` shape from `search_papers` / the per-source `search_*` tools:

    paper_id, title, authors ("; "-joined str), abstract, doi,
    published_date (ISO str), pdf_url, url, source, citations (int), ...

The academic-research workflow (Stages 2-6) was written against the *original*
`academic-mcp` `academic_search` schema, which speaks:

    doi_or_arxiv_id, title, first_author, year, citation_count,
    is_open_access, abstract(...)

This module is the **reference normalizer** that bridges the two. It is the
executable spec that the workflow's Stage-2 sub-agent prompts are written to
follow. Keep these rules and the tests in `tests/test_mapping.py` in lockstep.

Notes / limitations (documented honestly so the workflow prompts can too):
- `is_open_access` is a *heuristic*: paper-search-mcp exposes no explicit OA
  flag, so we treat a non-empty `pdf_url` as "open-access PDF available."
  This is an over-approximation (some pdf_urls are paywalled landing pages)
  and under-represents arXiv/PubMed where the PDF is openly hosted but
  pdf_url semantics differ per source. The workflow flags OA per the Sources
  table; treat this column as "PDF locatable" rather than legal-OA.
- arXiv ids are returned in `paper_id` (e.g. "2312.12456") and DOIs in `doi`.
  We prefer DOI; arXiv id is the fallback identifier the workflow can resolve.
  See `best_work_id_for_openalex()` for the Stage-3 citation-chain seed rule
  (DOI first, arXiv id second, a bare URL deliberately excluded -- OpenAlex
  cannot map a landing-page URL to a Work id without fragile title matching).
"""

from __future__ import annotations

from typing import Any


# Fields the workflow's unified paper schema expects (see academic-research.rhai
# Stage 2 "Output format" block). This constant is the single source of truth
# for what Stage 4/5/6 read; tests assert against it.
UNIFIED_FIELDS = (
    "doi_or_arxiv_id",
    "title",
    "first_author",
    "year",
    "citation_count",
    "is_open_access",
    "abstract",
)


def _to_int(value: Any, default: int = 0) -> int:
    """Coerce a value that may be int/str/None into an int."""
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _pick_id(raw: dict) -> str:
    """Prefer DOI, then paper_id (arxiv-style), then url."""
    doi = (raw.get("doi") or "").strip()
    if doi:
        return doi
    pid = (raw.get("paper_id") or "").strip()
    if pid:
        return pid
    url = (raw.get("url") or "").strip()
    return url


def _first_author(authors_field: Any) -> str:
    """paper-search-mcp joins authors with '; '. Take the first."""
    if not authors_field:
        return ""
    # Normalize: authors may already be a string or a list.
    if isinstance(authors_field, (list, tuple)):
        tokens = [str(a).strip() for a in authors_field if a]
    else:
        tokens = [t.strip() for t in str(authors_field).split(";") if t.strip()]
    return tokens[0] if tokens else ""


def _year(published_date: Any) -> int:
    """Extract the year from an ISO date string; 0 when absent/invalid."""
    if not published_date:
        return 0
    text = str(published_date).strip()
    if len(text) < 4:
        return 0
    try:
        return int(text[:4])
    except ValueError:
        return 0


def _is_open_access(pdf_url: Any) -> bool:
    """Heuristic: a non-empty pdf_url implies a locatable PDF. See module docstring."""
    return bool(pdf_url)


def normalize_paper(raw: dict) -> dict:
    """Map one paper-search-mcp Paper.to_dict() record to the workflow schema."""
    return {
        "doi_or_arxiv_id": _pick_id(raw),
        "title": (raw.get("title") or "").strip(),
        "first_author": _first_author(raw.get("authors")),
        "year": _year(raw.get("published_date")),
        "citation_count": _to_int(raw.get("citations"), default=0),
        "is_open_access": _is_open_access(raw.get("pdf_url")),
        "abstract": raw.get("abstract") or "",
    }


def normalize_search_papers_results(papers: list[dict]) -> list[dict]:
    """
    Map the `papers` list returned by paper-search-mcp `search_papers`
    into the unified schema, preserving order and count.

    This is the function the Stage-2 sub-agent should conceptually produce
    when it maps `paper-search-mcp__search_papers` output for downstream
    stages. It is intentionally a *reference* implementation: the real
    execution is LLM-driven via `agent()` prompts, but these tests pin the
    contract the prompts must follow.
    """
    return [normalize_paper(p) for p in papers]


def best_work_id_for_openalex(paper: dict) -> str:
    """Identifier to hand to Stage-3 `academic_citation_chain` (OpenAlex).

    A *stronger* version of the workflow's `doi_or_arxiv_id` rule (see
    `academic-research.rhai` Stage-3 routing: "prefer doi; if blank, use
    paper_id (arXiv-style); else url") -- tuned for the citation graph:

    * prefer the DOI: OpenAlex resolves it in a single hop;
    * otherwise the arXiv-style `paper_id`: OpenAlex resolves arXiv ids via
      its arXiv-to-work lookup;
    * a bare `url` is **deliberately NOT returned**: OpenAlex cannot map a
      landing-page URL to a Work id directly and would fall back to (fragile)
      title matching, risking the wrong work.

    Returns ``""`` when neither a DOI nor a `paper_id` is present; callers
    apply their own last-resort seed (the live E2E falls back to a known-good
    DOI). This mirrors exactly what the `.rhai` Stage-3 sub-agent is
    instructed to feed into `citation_chain(work_id=...)`.
    """
    doi = (paper.get("doi") or "").strip()
    if doi:
        return doi
    return (paper.get("paper_id") or "").strip()
