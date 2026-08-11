# SEARCH-PIVOT — Linux research search path (searxng-aware)

**Problem:** Research sub-agents used to be pointed at a searxng MCP server that is
**not installed on this machine** (no process, no Docker, no package; the registered
MCP servers in `~/.grok/mcpServers.json` point at Windows paths). Any sub-agent that
followed the old `web_search` → searxng instructions hit a dead end.

**Fix:** `scripts/search_pivot.py` — a single, MCP-independent search tool with
graceful degradation. Run it with the venv interpreter (shebang handles this):

```bash
~/.grok/skills/academic-research/scripts/search_pivot.py probe
```

## Pivot order

1. **searxng** (probed on `SEARXNG_URL` or `127.0.0.1:8888 / :4004 / localhost:8888`)
   → general web search via JSON API, if reachable.
2. **DuckDuckGo HTML** (`html.duckduckgo.com`) → keyless general web fallback.
3. **Keyless scholarly APIs** (OpenAlex / arXiv / Crossref / PubMed via the vendored
   `server/academic_mcp.py`) → for academic-shaped queries.
4. **Honest failure** — exit 1 with the reason on stderr; never fabricate results.

Every invocation emits JSON and reports the path taken in the `"pivot"` field, so
downstream screening can audit provenance.

## Commands

| Command | Purpose |
|---------|---------|
| `probe` | Health check: is searxng up? are the academic APIs reachable? |
| `web "<q>" [--limit N]` | General web (searxng → duckduckgo). |
| `academic "<q>" [--sources openalex,arxiv,crossref,pubmed] [--limit N] [--focus general\|ml]` | Scholarly search. |
| `chain <id-or-doi> [--direction cites\|refs] [--depth 1\|2]` | OpenAlex citation-graph walk. |
| `paper <id-or-doi>` | Metadata + abstract + OA PDF link. |
| `tldr <id> [<id> ...]` | Best-effort Semantic Scholar TLDRs (degrades on 429). |
| `auto "<q>" [--limit N]` | Web-first with academic fallback (collection sub-agents). |

## Web-search reality check (2026-08-09 — from this machine's IP)

Probing every keyless engine on 2026-08-09 showed this host's IP is **flagged for
general web scraping**:

| Engine | Result | Meaning |
|--------|--------|---------|
| DuckDuckGo HTML | HTTP **202** + challenge page | shadow-ban (burst of queries tripped it) |
| Bing HTML | HTTP 200 + **captcha** | bot detection |
| Mojeek | HTTP 200 + **challenge** | bot detection |
| Qwant API | HTTP **403** | blocked |
| Wikipedia API | works, narrow scope | definitional lookups only |
| OpenAlex / arXiv / Crossref / PubMed | **HTTP 200** | scholarly search unaffected |

**Mitigations (built into the pivot):** `web` rotates through searxng → ddg-html →
bing-html → mojeek → ddg-lite → wikipedia, with a 90s per-engine cooldown after
empty/blocked responses, and reports `engine_statuses` for audit.

**Recommended fixes (system-level):**
1. **Run searxng in Docker** (`docker run -d -p 8888:8080 searxng/searxng`) — it
   aggregates ~20 engines with per-engine failure handling and is the natural
   home for API keys (Brave, Google CSE) later. The pivot auto-detects it at
   `127.0.0.1:8888` (or set `SEARXNG_URL`).
2. **Brave Search API** (free tier, ~2000 queries/mo) — the most reliable keyed
   option; add the key to the searxng config or the pivot via env.

**Advice for sub-agents:** for scholarly queries always prefer the `academic`
path (reliable from this IP). The `web` path is best-effort — if every engine
reports blocked, note it in your output and do not fabricate results.

## Notes for sub-agents (Phase 1 collection)

- **Prefer quoted phrases** for academic queries — unquoted natural language makes
  OpenAlex match on high-citation off-topic records (e.g. "atomic" → materials science).
- **Citation walks:** seed `chain` from the **published DOI** when known. OpenAlex
  splits preprint vs. published records; a bare arXiv id often yields 0 citing works
  even though the published version has hundreds.
- **Never fabricate:** if every path fails, report the JSON with `"ok": false` and the
  `"reason"` — do not invent results.
- Academic APIs are reachable on this machine (verified: OpenAlex + arXiv HTTP 200);
  searxng is NOT installed (verified).

## Files

- `scripts/search_pivot.py` — the tool (run with the skill's `.venv/bin/python`).
- `../server/academic_mcp.py` — vendored keyless scholarly search (same logic as the
  academic-mcp MCP server; imported as a plain module, no MCP transport needed).
- Venv: `.venv/` (Python 3.12, `mcp==1.8.0` pinned — newer `mcp` broke the server API).
