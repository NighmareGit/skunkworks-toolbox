#!/usr/bin/env python3
"""
search_pivot.py — searxng-aware research search with graceful degradation (Linux).

WHY THIS EXISTS
    Research sub-agents used to be pointed at a searxng MCP server that is NOT
    installed on this machine (no searxng process, no Docker container, no pip
    package; the registered MCP servers in ~/.grok/mcpServers.json point at
    Windows paths). This tool replaces that dead path with a pivot:

      1. searxng reachable   -> use its JSON API for general web search
      2. searxng unreachable -> rotate through keyless web engines
             (duckduckgo-html -> bing-html -> mojeek -> duckduckgo-lite),
             each with a per-engine cooldown after empty/blocked responses
             (DuckDuckGo shadow-bans after bursts — rotation + cooldown
             keeps the web path alive)
      3. keyless scholarly APIs (OpenAlex / arXiv / Crossref / PubMed)
             via the vendored academic_mcp.py (same logic as the academic-mcp
             MCP server, callable without any MCP transport)
      4. honest "no results / unavailable" report — never fabricate

    Every invocation reports which path it took (field "pivot"), so sub-agents
    and orchestrators can audit where results came from.

USAGE
    search_pivot.py probe                            # what is reachable right now
    search_pivot.py web  "<query>" [--limit N]       # general web (searxng -> ddg)
    search_pivot.py academic "<query>" [--sources openalex,arxiv,crossref,pubmed]
                                  [--limit N] [--focus general|ml]
    search_pivot.py chain <id-or-doi> [--direction cites|refs] [--depth 1|2]
    search_pivot.py paper <id-or-doi>
    search_pivot.py tldr <id> [<id> ...]
    search_pivot.py auto "<query>" [--limit N]       # web-first, academic fallback

ENV
    SEARXNG_URL   comma/space-separated base URLs to probe, e.g.
                  "http://127.0.0.1:8888 http://localhost:4004"
                  Defaults: http://127.0.0.1:8888, http://127.0.0.1:4004,
                            http://localhost:8888
    OPENALEX_MAILTO, UNPAYWALL_EMAIL   polite-pool identifiers (passed through).

EXIT CODES
    0  success (results returned, even if empty-but-valid)
    1  hard failure / nothing reachable (reason on stderr, JSON on stdout)

OUTPUT
    JSON on stdout:  {"pivot": "<path>", "query": "...", ..., "results": [...]}
    Every result carries "source" so downstream screening can cite provenance.
"""

from __future__ import annotations

import argparse
import html as _html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

# ---------------------------------------------------------------------------
# Vendored academic_mcp (same keyless scholarly logic as the academic-mcp MCP
# server — imported as a plain module; no MCP transport required).
# ---------------------------------------------------------------------------
_SERVER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server")
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

try:
    import academic_mcp as _am
except Exception as _e:  # pragma: no cover - env setup failure
    _am = None
    _IMPORT_ERROR = str(_e)
else:
    _IMPORT_ERROR = None

# ---------------------------------------------------------------------------
# Quality layer (domain-trust filter) — route the anchor's results through
# src/anchor_filter.py so bing junk drops and high-quality results rise.
# Imported as a module (same pattern as academic_mcp); if unavailable the
# pivot falls back to unfiltered anchor results (reversible, safe).
# ---------------------------------------------------------------------------
_MESH_SRC = os.environ.get(
    "SEARX_MESH_SRC",
    os.path.join(os.path.expanduser("~"), "projects", "searx-mesh", "src"))
if _MESH_SRC not in sys.path:
    sys.path.insert(0, _MESH_SRC)

try:
    import anchor_filter as _af
except Exception as _e:  # pragma: no cover - env setup failure
    _af = None
    _AF_IMPORT_ERROR = str(_e)
else:
    _AF_IMPORT_ERROR = None

# High-weight engines per the Q3 relevance sample (anchor_filter.ENGINE_WEIGHT):
# duckduckgo web (100%) and mwmbl (100%). A query has "collapsed" when the
# anchor returns no result from either of these (bing-only junk) — the
# coverage problem the quality layer cannot fix by re-ranking alone.
HIGH_WEIGHT_ENGINES = frozenset(
    e for e, w in (_af.ENGINE_WEIGHT.items() if _af is not None else {})
    if w >= 100
) or frozenset({"duckduckgo web", "mwmbl"})

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEFAULT_SEARXNG_URLS = [
    "http://127.0.0.1:8888",
    "http://127.0.0.1:4004",
    "http://localhost:8888",
]
PROBE_TIMEOUT = 2      # seconds per searxng probe
HTTP_TIMEOUT = 15      # seconds per real HTTP call
# R4b fail-fast: short timeout for the SINGLE cheap fallback (wikipedia) tried
# when the anchor collapses. Bounds the degraded path to <3s instead of walking
# the full 15s/engine ladder (R4 measured degraded p95 14-65s).
DEGRADED_FALLBACK_TIMEOUT = 2.5
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

DDG_HTML_URL = "https://html.duckduckgo.com/html/"
DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"
BING_URL = "https://www.bing.com/search"
MOJEEK_URL = "https://www.mojeek.com/search"

# Per-engine cooldown (seconds) after an empty/failed response — rotation skips
# an engine that recently returned nothing so we stop hammering a rate-limited
# provider (observed: DuckDuckGo HTML shadow-bans after a burst of queries).
ENGINE_COOLDOWN_SECONDS = 90
_ENGINE_COOLDOWN_UNTIL: dict[str, float] = {}

# scholarly-shaped query hint (used by auto mode to decide fallback target)
_SCHOLARLY_HINTS = re.compile(
    r"\b(arxiv|paper|doi|literature|survey|citation|publication|"
    r"proceedings|preprint|journal|benchmark|work|agent|llm|model)\b",
    re.I,
)


# ---------------------------------------------------------------------------
# searxng
# ---------------------------------------------------------------------------
def _searxng_urls() -> list[str]:
    env = os.environ.get("SEARXNG_URL", "").strip()
    if env:
        return [u for u in re.split(r"[\s,]+", env) if u]
    return list(DEFAULT_SEARXNG_URLS)


def probe_searxng() -> dict:
    """Return {'ok': bool, 'url': str|None, 'detail': str} for the first live searxng."""
    for base in _searxng_urls():
        url = f"{base.rstrip('/')}/search?q=test&format=json"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as resp:
                body = resp.read(200_000)
                data = json.loads(body)
                if isinstance(data, dict) and "results" in data:
                    return {"ok": True, "url": base, "detail": f"{base} answered with JSON"}
                return {"ok": False, "url": base, "detail": f"{base} returned non-search JSON"}
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
    return {"ok": False, "url": None, "detail": f"no searxng reachable ({last})"}


def _apply_quality_layer(results: list[dict], top_n: int) -> tuple[list[dict], str | None]:
    """Run anchor results through the domain-trust quality layer.

    Returns (filtered, note). If the layer module is unavailable, the results
    pass through untouched (with a note) so the pivot still works — the layer
    is an enhancement, not a hard dependency.
    """
    if _af is None:
        return results[:top_n], f"quality layer unavailable ({_AF_IMPORT_ERROR})"
    filtered, note = _af.filter_results(
        results, _af.DEFAULT_JUNK_DOMAINS, _af.DEFAULT_TRUSTED_DOMAINS,
        _af.TRUSTED_TLDS, top_n)
    return filtered, note


def _has_highweight(results: list[dict]) -> bool:
    """True if any result comes from a high-weight engine (ddg web / mwmbl)."""
    return any(r.get("engine") in HIGH_WEIGHT_ENGINES for r in results)


def searxng_web(query: str, limit: int) -> dict:
    """Anchor path: query searxng, route results through the quality layer,
    and recover from coverage collapse via one retry.

    Coverage collapse = the anchor returned results but none from a high-weight
    engine (duckduckgo web / mwmbl) — i.e. bing-only junk, the Q3 failure mode.
    On collapse we retry once (engines fluctuate run-to-run); if it persists we
    return an HONEST degraded signal rather than serving junk as if good (K1).
    """
    def _fetch() -> dict:
        base = probe_searxng()
        if not base["ok"] or not base["url"]:
            return {"ok": False, "reason": base["detail"]}
        url = (f"{base['url'].rstrip('/')}/search?q={urllib.parse.quote(query)}"
               f"&format=json&pageno=1")
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            data = json.loads(resp.read(1_000_000))
        # Give the filter room to drop junk and re-rank: fetch more than `limit`.
        raw = data.get("results", [])[:max(limit * 2, 20)]
        results = []
        for rank, r in enumerate(raw, start=1):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", "") or r.get("snippet", ""),
                "engine": r.get("engine", "searxng"),
                "source": "searxng",
                "rank": r.get("rank", rank),
            })
        return {"ok": True, "results": results, "base": base}

    # R4b FAIL-FAST: a single anchor attempt, no retry. R4 measured the degraded
    # path at p95 14-65s because a collapsed query burned a 2.5s retry sleep +
    # a second full fetch, THEN walked the slow 15s/engine ladder. We now return
    # the honest degraded signal on the FIRST collapse so web_rotated() can try
    # only one cheap fallback instead of the slow ladder. K1 preserved: the
    # signal is still ok:false/degraded:true, never junk.
    fetched = _fetch()
    if not fetched["ok"]:
        # Anchor unreachable — not a collapse; let the ladder fall through.
        return {"ok": False, "reason": fetched["reason"]}

    filtered, note = _apply_quality_layer(fetched["results"], limit)

    # Healthy: we have filtered results anchored by a high-weight engine.
    if filtered and _has_highweight(filtered):
        return {"ok": True, "pivot": "searxng", "results": filtered,
                "total": len(filtered), "engine": "searxng",
                "quality_note": note}

    # Collapse: 0 results after filter, OR no high-weight engine (bing-only).
    # Fail fast — honest degraded signal (K1: never fabricate, never serve junk
    # as if good). ok:false so web_rotated() can try a cheap fallback; the
    # degraded flag + reason tell the caller why.
    degraded_note = (
        "coverage degraded: anchor returned no high-weight engine "
        "(duckduckgo web / mwmbl) — bing-only junk refused as results"
    )
    if note:
        degraded_note += f"; quality-layer note: {note}"
    return {"ok": False, "pivot": "searxng", "degraded": True,
            "reason": degraded_note,
            "results": filtered, "total": len(filtered), "engine": "searxng"}


# ---------------------------------------------------------------------------
# DuckDuckGo HTML fallback (keyless general web)
# ---------------------------------------------------------------------------
def _ddg_fetch(url: str, query: str) -> str:
    req = urllib.request.Request(
        url, data=urllib.parse.urlencode({"q": query}).encode(),
        headers={"User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return resp.read(2_000_000).decode("utf-8", "replace")


def _ddg_extract(html: str, limit: int) -> list[dict]:
    results = []
    # HTML endpoint: result links carry class="result__a", snippets "result__snippet"
    blocks = re.split(r'class="result', html)[1:]
    for block in blocks:
        if len(results) >= limit:
            break
        m_link = re.search(r'__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not m_link:
            continue
        href, title = m_link.group(1), _html.unescape(re.sub(r"<[^>]+>", "", m_link.group(2))).strip()
        real_url = _uddg_target(href)
        m_snip = re.search(r'__snippet"[^>]*>(.*?)</a>', block, re.S)
        snippet = _html.unescape(re.sub(r"<[^>]+>", "", m_snip.group(1))).strip() if m_snip else ""
        results.append({
            "title": title or real_url,
            "url": real_url,
            "content": snippet,
            "engine": "duckduckgo-html",
            "source": "duckduckgo-html",
        })
    return results


def _uddg_target(href: str) -> str:
    """DDG wraps targets as //duckduckgo.com/l/?uddg=<enc>&rut=... — unwrap."""
    if "uddg=" in href:
        m = re.search(r"[?&]uddg=([^&]+)", href)
        if m:
            return urllib.parse.unquote(m.group(1))
    if href.startswith("//"):
        href = "https:" + href
    return href


def ddg_web(query: str, limit: int) -> dict:
    try:
        html = _ddg_fetch(DDG_HTML_URL, query)
        results = _ddg_extract(html, limit)
    except Exception as e:
        # second try against the lite endpoint
        try:
            html = _ddg_fetch(DDG_LITE_URL, query)
            results = _ddg_extract(html, limit)
        except Exception as e2:
            return {"ok": False, "reason": f"duckduckgo unavailable: {e2}"}
    return {"ok": True, "pivot": "duckduckgo-html", "results": results,
            "total": len(results), "engine": "duckduckgo"}


# ---------------------------------------------------------------------------
# Bing HTML + Mojeek (additional keyless web engines for rotation)
# ---------------------------------------------------------------------------
def _strip_tags(s: str) -> str:
    return _html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def bing_web(query: str, limit: int) -> dict:
    url = f"{BING_URL}?q={urllib.parse.quote(query)}&count={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "en-US,en;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            html = resp.read(2_000_000).decode("utf-8", "replace")
    except Exception as e:
        return {"ok": False, "reason": f"bing unavailable: {e}"}
    results = []
    # Bing wraps result links in <li class="b_algo"> with <h2><a href="...">title</a>
    for block in re.split(r'<li class="b_algo"', html)[1:]:
        if len(results) >= limit:
            break
        m = re.search(r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not m:
            continue
        url2, title = m.group(1), _strip_tags(m.group(2))
        m_snip = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
        snippet = _strip_tags(m_snip.group(1)) if m_snip else ""
        results.append({"title": title or url2, "url": url2, "content": snippet,
                        "engine": "bing-html", "source": "bing-html"})
    if not results:
        return {"ok": False, "reason": "bing returned no parseable results (possible block)"}
    return {"ok": True, "pivot": "bing-html", "results": results,
            "total": len(results), "engine": "bing-html"}


def wikipedia_web(query: str, limit: int, timeout: int = HTTP_TIMEOUT) -> dict:
    """Last-resort general-knowledge engine: Wikipedia opensearch (keyless, rarely blocked)."""
    url = ("https://en.wikipedia.org/w/api.php?action=opensearch&search="
           + urllib.parse.quote(query) + f"&limit={limit}&format=json")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read(200_000))
    except Exception as e:
        return {"ok": False, "reason": f"wikipedia unavailable: {e}"}
    titles, urls = data[1] or [], data[3] or []
    results = [{"title": t, "url": u, "content": "", "engine": "wikipedia",
                "source": "wikipedia"} for t, u in zip(titles, urls)][:limit]
    if not results:
        return {"ok": False, "reason": "wikipedia returned no matches"}
    return {"ok": True, "pivot": "wikipedia", "results": results,
            "total": len(results), "engine": "wikipedia"}


def mojeek_web(query: str, limit: int) -> dict:
    url = f"{MOJEEK_URL}?q={urllib.parse.quote(query)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA,
                                               "Accept-Language": "en-US,en;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            html = resp.read(2_000_000).decode("utf-8", "replace")
    except Exception as e:
        return {"ok": False, "reason": f"mojeek unavailable: {e}"}
    results = []
    # Mojeek: <ul class="results-standard"><li><h2><a href="...">title</a></h2><p class="s">snippet</p>
    for block in re.split(r'<li class="r">', html)[1:]:
        if len(results) >= limit:
            break
        m = re.search(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not m:
            continue
        url2, title = m.group(1), _strip_tags(m.group(2))
        m_snip = re.search(r'<p class="s"[^>]*>(.*?)</p>', block, re.S)
        snippet = _strip_tags(m_snip.group(1)) if m_snip else ""
        results.append({"title": title or url2, "url": url2, "content": snippet,
                        "engine": "mojeek", "source": "mojeek"})
    if not results:
        return {"ok": False, "reason": "mojeek returned no parseable results"}
    return {"ok": True, "pivot": "mojeek", "results": results,
            "total": len(results), "engine": "mojeek"}


# ---------------------------------------------------------------------------
# Engine rotation (the anti-shadow-ban path)
# ---------------------------------------------------------------------------
def _engine_ready(name: str) -> bool:
    until = _ENGINE_COOLDOWN_UNTIL.get(name, 0.0)
    return time.time() >= until


def _mark_cooldown(name: str) -> None:
    _ENGINE_COOLDOWN_UNTIL[name] = time.time() + ENGINE_COOLDOWN_SECONDS


def web_rotated(query: str, limit: int) -> dict:
    """Try engines in order until one returns results. Report per-engine status.

    Order: searxng (if reachable) -> duckduckgo-html -> bing-html -> mojeek ->
    duckduckgo-lite. Engines in cooldown are skipped (and reported as skipped).
    """
    engines = ["searxng", "duckduckgo-html", "bing-html", "mojeek", "duckduckgo-lite", "wikipedia"]
    statuses: dict[str, str] = {}
    # Carries the anchor-collapse signal through the ladder so the caller sees
    # it even when a later engine (e.g. ddg-html) recovers the query.
    degraded: str | None = None
    for name in engines:
        if not _engine_ready(name):
            statuses[name] = "skipped (cooldown)"
            continue
        try:
            if name == "searxng":
                out = searxng_web(query, limit)
            elif name == "duckduckgo-html":
                out = ddg_web(query, limit)
            elif name == "bing-html":
                out = bing_web(query, limit)
            elif name == "mojeek":
                out = mojeek_web(query, limit)
            elif name == "wikipedia":
                out = wikipedia_web(query, limit)
            else:
                out = ddg_web(query, limit)  # lite fallback handled inside ddg_web
        except Exception as e:
            out = {"ok": False, "reason": str(e)}
        # Anchor collapsed (quality, not a block): don't cooldown it (it isn't
        # rate-limited — it's just bing-only right now).
        if name == "searxng" and out.get("degraded"):
            # R4b FAIL-FAST: do NOT walk the slow 15s/engine ladder for a
            # known-collapsed anchor (R4 measured that ladder at p95 14-65s).
            # Try only ONE cheap, fast, keyless fallback (wikipedia opensearch)
            # with a short timeout; if it fails, return the honest degraded
            # signal immediately. Bounds the degraded path to <3s.
            degraded = out.get("reason", "coverage degraded")
            statuses[name] = "degraded (no high-weight engine)"
            try:
                cheap = wikipedia_web(query, limit, timeout=DEGRADED_FALLBACK_TIMEOUT)
            except Exception as e:
                cheap = {"ok": False, "reason": str(e)}
            if cheap.get("ok") and cheap.get("results"):
                cheap["engine_statuses"] = statuses
                cheap["engine_statuses"]["wikipedia"] = (
                    f"ok ({len(cheap['results'])}) [cheap-degraded]")
                cheap["degraded"] = True
                cheap["degraded_note"] = (
                    f"anchor (searxng) coverage degraded: {degraded}; "
                    f"recovered via wikipedia (cheap fallback)")
                return cheap
            # Cheap fallback failed too — return the honest degraded signal now
            # (K1: never fabricate, never serve junk as if good).
            statuses["wikipedia"] = (
                f"cheap-degraded failed ({cheap.get('reason', 'no results')[:50]})")
            return {"ok": False, "pivot": "none", "engine_statuses": statuses,
                    "degraded": True,
                    "reason": (f"anchor (searxng) coverage degraded: {degraded}; "
                               f"cheap fallback (wikipedia) also failed; "
                               f"no engine recovered"),
                    "results": []}
        if out.get("ok") and out.get("results"):
            out["engine_statuses"] = statuses
            out["engine_statuses"][name] = f"ok ({len(out['results'])})"
            if degraded is not None:
                out["degraded"] = True
                out["degraded_note"] = (
                    f"anchor (searxng) coverage degraded: {degraded}; "
                    f"recovered via {name}")
            return out
        reason = out.get("reason", "no results")
        statuses[name] = f"failed ({reason[:60]})"
        _mark_cooldown(name)
    out = {"ok": False, "pivot": "none", "engine_statuses": statuses,
           "reason": "all web engines failed or in cooldown", "results": []}
    if degraded is not None:
        out["degraded"] = True
        out["degraded_note"] = (
            f"anchor (searxng) coverage degraded: {degraded}; no engine recovered")
    return out


# ---------------------------------------------------------------------------
# Academic (keyless scholarly APIs via vendored academic_mcp)
# ---------------------------------------------------------------------------
def _require_academic():
    if _am is None:
        raise RuntimeError(f"academic_mcp unavailable ({_IMPORT_ERROR}) — run with "
                           "~/.grok/skills/academic-research/.venv/bin/python")


def academic_search(query: str, sources: list[str] | None, limit: int, focus: str) -> dict:
    _require_academic()
    out = _am._run_search(query, sources, limit, focus)
    # tag each result with provenance
    for r in out.get("results", []):
        r["source"] = r.get("source") or "academic-api"
    return {"ok": True, "pivot": "academic-api", **out}


def academic_chain(work_id: str, direction: str, depth: int) -> dict:
    _require_academic()
    out = _am._run_citation_chain(work_id, direction, depth)
    if "error" in out:
        return {"ok": False, "reason": out["error"]}
    return {"ok": True, "pivot": "academic-api", **out}


def academic_paper(id_or_doi: str) -> dict:
    _require_academic()
    out = _am._run_get_paper(id_or_doi)
    if not out:
        return {"ok": False, "reason": f"no record for {id_or_doi!r}"}
    return {"ok": True, "pivot": "academic-api", **out}


def academic_tldr(paper_ids: list[str]) -> dict:
    _require_academic()
    out = _am._run_tldr(paper_ids)
    return {"ok": True, "pivot": "academic-api", **out}


def probe_academic() -> dict:
    checks = {}
    for name, fn in (("openalex", _probe_openalex), ("arxiv", _probe_arxiv)):
        try:
            checks[name] = fn()
        except Exception as e:
            checks[name] = {"ok": False, "detail": str(e)}
    return checks


def _probe_openalex() -> dict:
    url = "https://api.openalex.org/works/W2741809807"
    with urllib.request.urlopen(url, timeout=PROBE_TIMEOUT) as resp:
        return {"ok": resp.status == 200, "detail": f"HTTP {resp.status}"}


def _probe_arxiv() -> dict:
    url = "https://export.arxiv.org/api/query?search_query=all:test&max_results=1"
    with urllib.request.urlopen(url, timeout=PROBE_TIMEOUT) as resp:
        return {"ok": resp.status == 200, "detail": f"HTTP {resp.status}"}


# ---------------------------------------------------------------------------
# auto mode
# ---------------------------------------------------------------------------
def auto(query: str, limit: int) -> dict:
    """web-first (engine rotation): searxng -> ddg -> bing -> mojeek -> academic."""
    w = web_rotated(query, limit)
    if w["ok"] and w.get("results"):
        return w
    if _SCHOLARLY_HINTS.search(query) or _am is not None:
        a = academic_search(query, None, limit, "general")
        if a.get("total_unique", 0) > 0:
            return a
    return {"ok": False, "pivot": "none",
            "reason": f"no search path produced results (web: {w.get('reason', 'n/a')})",
            "results": []}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _emit(obj: dict, exit_code: int = 0) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))
    sys.exit(exit_code)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="search_pivot.py", description=__doc__.split("\n")[1])
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("probe", help="health check: searxng + academic APIs")
    sp.set_defaults(func=cmd_probe)

    sp = sub.add_parser("web", help="general web search (searxng -> duckduckgo)")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(func=cmd_web)

    sp = sub.add_parser("academic", help="scholarly search via keyless APIs")
    sp.add_argument("query")
    sp.add_argument("--sources", default="openalex,arxiv,crossref,pubmed")
    sp.add_argument("--limit", type=int, default=10)
    sp.add_argument("--focus", choices=["general", "ml"], default="general")
    sp.set_defaults(func=cmd_academic)

    sp = sub.add_parser("chain", help="OpenAlex citation graph walk")
    sp.add_argument("work_id")
    sp.add_argument("--direction", choices=["cites", "refs"], default="cites")
    sp.add_argument("--depth", type=int, choices=[1, 2], default=1)
    sp.set_defaults(func=cmd_chain)

    sp = sub.add_parser("paper", help="metadata + abstract + OA link for an id/DOI")
    sp.add_argument("id_or_doi")
    sp.set_defaults(func=cmd_paper)

    sp = sub.add_parser("tldr", help="best-effort TLDRs from Semantic Scholar")
    sp.add_argument("paper_ids", nargs="+")
    sp.set_defaults(func=cmd_tldr)

    sp = sub.add_parser("auto", help="web-first with academic fallback")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(func=cmd_auto)

    args = p.parse_args(argv)
    args.func(args)


def cmd_probe(args: argparse.Namespace) -> None:
    searx = probe_searxng()
    acad = probe_academic()
    _emit({"pivot": "probe",
           "searxng": searx,
           "academic_apis": acad,
           "note": ("searxng NOT installed on this machine — general web falls back "
                    "to duckduckgo-html; scholarly falls back to keyless APIs")})


def cmd_web(args: argparse.Namespace) -> None:
    out = web_rotated(args.query, args.limit)
    if not out["ok"]:
        _emit(out, exit_code=1)
    _emit(out)


def cmd_academic(args: argparse.Namespace) -> None:
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    try:
        out = academic_search(args.query, sources, args.limit, args.focus)
    except Exception as e:
        _emit({"ok": False, "pivot": "academic-api", "reason": str(e)}, exit_code=1)
    _emit(out)


def cmd_chain(args: argparse.Namespace) -> None:
    try:
        out = academic_chain(args.work_id, args.direction, args.depth)
    except Exception as e:
        _emit({"ok": False, "pivot": "academic-api", "reason": str(e)}, exit_code=1)
    _emit(out)


def cmd_paper(args: argparse.Namespace) -> None:
    try:
        out = academic_paper(args.id_or_doi)
    except Exception as e:
        _emit({"ok": False, "pivot": "academic-api", "reason": str(e)}, exit_code=1)
    _emit(out)


def cmd_tldr(args: argparse.Namespace) -> None:
    try:
        out = academic_tldr(args.paper_ids)
    except Exception as e:
        _emit({"ok": False, "pivot": "academic-api", "reason": str(e)}, exit_code=1)
    _emit(out)


def cmd_auto(args: argparse.Namespace) -> None:
    out = auto(args.query, args.limit)
    _emit(out, exit_code=0 if out.get("ok") else 1)


if __name__ == "__main__":
    main()
