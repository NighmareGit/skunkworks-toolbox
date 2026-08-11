---
name: academic-research-win
description: >
  Windows-adapted, hybrid-MCP variant of academic-research. Deep multi-source
  literature research via paper-search-mcp (22 scholarly sources + PDF), with the
  OpenAlex citation-graph walk preserved by keeping the vendored academic-mcp
  server for Stage 3 only. Native on Windows — no Docker. Use when the user asks
  for a literature review, paper lookup, citation walk, or prior-art search.
when-to-use: >
  "research the literature on <topic>", "pull papers on <topic>", "citation chain for <paper>",
  "who cites <paper>", "what does <paper> reference", "literature review on <topic>",
  "find prior art for <technique>", "verify paper entry in the research base",
  "update the research base on <topic>"
allowed-tools: use_tool, search_tool, read_file, write, grep, workflow
user-invocable: true
disable-model-invocation: false
metadata:
  short-description: "Windows-native, paper-search-mcp-backed academic literature search + citation chain"
  author: "windows-variant (academic-research-win)"
  version: "0.1.0"
  compatibility: >
    requires BOTH `paper-search-mcp` (primary: search/metadata/PDF) and `academic-mcp`
    (Stage 3 citation-graph walk) MCP servers registered in ~/.grok/mcpServers.
    Both launch as native stdio Python processes on Windows — no Docker required.
    Set PAPER_SEARCH_MCP_LOCAL_DIR to launch paper-search-mcp from a local checkout
    (e.g. <paper-search-mcp-dir>) instead of uvx; default stays uvx.
---

# `/academic-research-win` — Windows-Adapted Academic Literature Research

A local Windows variant of the `academic-research` skill. It does **not** modify
`skunkworks-toolbox`; instead it composes two already-installed MCP servers into
the same six-stage funnel, swapping in the richer, Windows-native
`paper-search-mcp` for search/metadata/PDF while retaining the vendored
`academic-mcp` **only** for the citation-graph walk that paper-search-mcp cannot
replicate.

## Why a variant (and why hybrid)

`paper-search-mcp` (https://github.com/openags/paper-search-mcp) is a far better
**search + full-text** provider — 22 sources (arXiv, PubMed, Crossref, OpenAlex,
Semantic Scholar, CORE, Europe PMC, CiteSeerX, DOAJ, BASE, Zenodo, HAL, SSRN,
Unpaywall, IEEE, ACM, …), PDF download, and PDF text extraction. It installs and
runs natively on Windows via `uvx paper-search-mcp` — **no Docker**.

But it has **no citation-graph traversal** tool. The original `academic-mcp`
`academic_citation_chain` walks the OpenAlex graph forward/backward 1–2 hops, and
Stage 3 of this pipeline depends on it. Rather than drop capability, the variant
keeps both servers registered and routes by stage:

| Stage | Provider | Tool |
|-------|----------|------|
| SCOPED search, evidence, report | `paper-search-mcp` | `search_papers`, `get_crossref_paper_by_doi` |
| Citation graph walk | `academic-mcp` (vendored) | `academic_citation_chain` |

> **On the "no Docker" premise:** the vendored `academic_mcp.py` is *also* a
> native stdio Python server (deps: `mcp`/`fastmcp` only) — it never needed
> Docker either. Both servers run on Windows without a container runtime. The
> pivot here is for *capability* (broader sources + PDF), not for Docker
> avoidance.

## Scope Discipline (hard rule)

**Academic sources ONLY.** paper-search-mcp pulls exclusively from scholarly
databases.

| Tool | Backend | What it returns |
|------|---------|-----------------|
| `search_papers` (`paper-search-mcp__search_papers`) | 22 sources above | Deduped, per-source-breakdown paper results (title, authors, year, citations, abstract, DOI, pdf_url) |
| `get_crossref_paper_by_doi` (`paper-search-mcp__get_crossref_paper_by_doi`) | Crossref | Full metadata for a DOI |
| `academic_citation_chain` (`academic-mcp__citation_chain`) | OpenAlex citation graph | Backward (refs) or forward (cites) neighbors, 1–2 hops |

**NOT available here:** general web search, news, blogs, GitHub, non-scholarly
sources. `academic_tld` (Semantic Scholar TL;DRs) is also unavailable —
paper-search-mcp has no equivalent; rely on abstracts instead.

**Keyless & local.** No API tokens required for the core path. Set
`PAPER_SEARCH_MCP_UNPAYWALL_EMAIL` (Unpaywall polite pool); CORE/Semantic-Scholar
keys are optional. No paid SaaS.

## Output-schema mapping (paper-search-mcp → workflow)

paper-search-mcp's `Paper.to_dict()` uses different field names than the original
`academic-mcp` `academic_search` result. Stage-2 sub-agents must remap so Stages
4–6 stay stable:

| Workflow expects | paper-search-mcp source | Rule |
|---|---|---|
| `doi_or_arxiv_id` | `doi` (fallback `paper_id`, then `url`) | prefer DOI |
| `title` | `title` | direct |
| `first_author` | `authors` (`"; "`-joined string) | first token |
| `year` | `published_date` (ISO str) | `int(date[:4])`; `0` if blank |
| `citation_count` | `citations` (int) | direct |
| `is_open_access` | `pdf_url` | `bool(pdf_url)` — **heuristic**: means "PDF locatable", not legal-OA (paper-search-mcp has no explicit OA flag) |
| `abstract` | `abstract` | direct — Stage 4 uses this, no extra fetch needed |

A reference implementation of this mapping lives in
`mappings/paper_search_mapping.py` (with tests in `tests/test_mapping.py`). The
workflow prompts follow exactly this contract.

## Intent → Tool Routing Table

Route the user's request to the minimal tool set.

| User intent | Tool(s) to call | Notes |
|-------------|-----------------|-------|
| "Find papers on topic X" / "research the literature on X" | `paper-search-mcp__search_papers` | `sources` = comma string or omit for all; `max_results_per_source=10`. Remap to unified schema (table above). |
| "Who cites paper Y" / "what builds on Y" | `academic-mcp__citation_chain(direction="cites")` | Start from DOI/arXiv id; Stage 3 handles it. |
| "What does paper Y reference" / "prior art for Y" | `academic-mcp__citation_chain(direction="refs")` | |
| "Get details on paper Z" / "abstract of Z" | `paper-search-mcp__get_crossref_paper_by_doi` (DOI only) **or** use the abstract already returned by `search_papers` | paper-search-mcp has no arXiv/OpenAlex-id resolver; prefer the search-result abstract. |
| Deep literature review / multi-facet investigation | **invoke the workflow** (see below) | scope → search → chain → evidence → collect → verify → synthesis. |
| Verify/refresh an entry in the research base | `search_papers` (title) + abstract check | Confirm id resolves, abstract matches. |

### Routing rules

1. **Dedup+ranking is in the server** (`search_papers` returns `papers` already
   deduped across sources). Do not re-rank/re-dedup downstream.
2. **Prefer precision:** `max_results_per_source=10`. Raise only on explicit
   breadth requests.
3. **Chain depth 1 unless asked.** `depth=1`; `depth=2` only on "broader context".
4. **Always call `search_tool` first** to confirm the current schema before
   `use_tool` — server tool names can evolve.

### Known caveat (citation-chain seed)

Seed `academic_citation_chain` from a **published DOI** when one is known, not an
arXiv id — OpenAlex treats the preprint and published versions as separate work
records, so an arXiv-only seed surfaces only citations to the preprint (often
3–13) vs. hundreds for the published version. `search_papers` results carry the
DOI when available; prefer it for chaining.

## When to invoke the workflow vs. direct tool calls

**Direct tool calls (you, in-session):**
- Single paper lookup, one-shot search, quick citation check.
- Verifying/refreshing a specific research-base entry.
- ≤ 2 tool calls answer the question.

**Invoke the `academic-research-win` Rhai workflow:**
- The user asks for a literature review, multi-facet investigation, or "deep dive".
- The question requires synthesis across > 2 sub-questions.
- You need evidence extraction + cross-verification + cited report.

### Invoking the workflow

```
workflow(name: "academic-research-win", args: #{ question: "<the user's question>", seed_ids: ["DOI-or-arXiv-id", ...], freshness_years: 5, max_subquestions: 5 })
```

| Arg | Type | Default | Purpose |
|-----|------|---------|---------|
| `question` | string | required | The research question. |
| `seed_ids` | list[str] | [] | Known-relevant paper ids to anchor citation chains. |
| `freshness_years` | int | 5 | Prefer papers within this many years. |
| `max_subquestions` | int | 5 | Cap on bounded sub-questions (A2 discipline: 3–5). |
| `output_path` | string | auto | Where to write the report. |
| `research_root` | string | `research` | Root folder for the per-topic research collection (Stage 4b). Defaults to `<cwd>/research`; point it at the project being researched. |

## Research workspace layout

Stage 4b (`COLLECT`) materialises the search results + citation chain into a neat,
organised folder so downstream stages and the next AI agent can find everything.
The layout is produced by `mappings/research_workspace.py` (helpers:
`system_tmp_dir`, `init_topic`, `place_download`, `write_map_md`,
`CollectedPaper.from_unified`).

**Temp download buffer → system standard temp folder.** Transient PDFs are
fetched into `research_workspace.system_tmp_dir()`, which returns Python's
`tempfile.gettempdir()` — on Windows that is the user's `Local\Temp` (the OS
standard `TMP`/`TEMP`), *never* a hard-coded path. After staging, each PDF is
**moved** (not copied) into the permanent collection, so the temp folder stays
the single transient scratch space.

> **⚠ Persistence: Temp is transient — move before you finish.** The OS-standard
> temp folder is volatile: it is wiped on reboot and by system/disk-cleanup runs
> (Windows Disk Cleanup, Storage Sense, anti-virus temp sweeps). A downloaded PDF
> is **not safe** until it has been moved into `<topic>/pdfs/` via
> `place_download` / `place_and_index` and the destination has been confirmed to
> exist. Treat the temp file as pure scratch; `map.md` (written into the
> permanent collection) is the durable index every downstream stage/agent must
> re-read — never assume a temp path survives. If a stage is interrupted after
> download but before the move, re-run the download; do **not** rely on leftover
> Temp files. Downstream code should ALWAYS read from `map.md` + `pdfs/`, never
> from a remembered temp path.

**Per-topic collection.** Each research run writes under the project root:

```
<project-root>/
  research/                         # <-- research_root (default "research"; overridable via args.research_root)
    <topic-slug>/                   # slug = research_workspace._slug(<question>)
      map.md                        # <-- AI-readable index of everything below (see schema)
      pdfs/                         # downloaded PDFs, named after the paper id
        2201_00978v1.pdf
        10_1000_xyz.pdf
      ...
```

**`map.md` — the index an AI agent reads first.** Written/refreshed after every
collection action. It always contains: a header table (topic, slug, collection
path, `pdfs/` location, and — when the chain ran — the citation-chain run:
direction/depth/hop1), plus a **Collected papers** table
(`#` · id · title · first author · year · search-cites · OA PDF · chain cites · pdf)
and a collapsible **Abstracts** per paper so the full text an agent needs is
already in-band. The per-paper record is built from the *same* unified schema the
workflow uses (`doi_or_arxiv_id`, `title`, `first_author`, `year`,
`citation_count`, `is_open_access`, `abstract`), plus `chain_cites`/`chain_refs`
from Stage 3 and the relative `pdfs/` path. A fresh `map.md` is created on
`init_topic` even before any paper is collected, so the folder is never empty.

**Failure tolerance.** If a paper's `pdf_url` is missing (e.g. Semantic Scholar /
some OpenAlex hits), it is still indexed in `map.md` from its `abstract` — the
collection degrades gracefully rather than failing.

## Windows MCP registration

Both servers are registered in `~/.grok/mcpServers` (a JSON map of
server-name → `{command, args, env}`). The server **names must be exactly**
`paper-search-mcp` and `academic-mcp` — the workflow qualifies tool calls as
`paper-search-mcp__<tool>` and `academic-mcp__<tool>`.

```jsonc
{
  "paper-search-mcp": {
    "command": "uvx",
    "args": ["paper-search-mcp"],
    "env": { "PAPER_SEARCH_MCP_UNPAYWALL_EMAIL": "you@example.org" }
  },
  "academic-mcp": {
    "command": "D:\\projects\\pool\\skills\\academic-research-win\\mcp\\.venv\\Scripts\\python.exe",
    "args": ["D:\\projects\\skunkworks-toolbox\\skills\\academic-research\\server\\academic_mcp.py"]
  }
}
```

Run `mcp/register-mcp-servers.ps1` to (re)create the `academic-mcp` venv and
(safely, with backup) write this JSON. Restart the agent runtime afterwards.

## Quick reference — MCP tool call pattern

Tools are accessed via `use_tool` with the qualified name
`<server>__<tool>`. Call `search_tool` first to confirm the schema.

```
search_tool(query: "search_papers")
use_tool("paper-search-mcp__search_papers", {query: "mixture of experts", sources: "arxiv,openalex", max_results_per_source: 10})
use_tool("academic-mcp__citation_chain", {work_id: "<DOI>", direction: "cites", depth: 1})
```

If a server is not registered, fail fast: *"The paper-search-mcp / academic-mcp
MCP server is not reachable. Check registration in ~/.grok/mcpServers and that
the server process is running (uvx / venv python)."*

## Maintenance operations

1. **Verify an entry** — `search_papers` the title; confirm the abstract + DOI match the base. Flag mismatches.
2. **Refresh community status** — `academic-mcp__citation_chain(direction="cites", depth=1)` on the DOI to spot new citing papers.
3. **Add a new verified paper** — `search_papers` to find it, read its abstract, then append to the base with full provenance (DOI/arXiv id, title, first author, venue, abstract summary).

## Failure modes

| Mode | Response |
|------|----------|
| `paper-search-mcp` unreachable | Fail fast with registration check. |
| `academic-mcp` unreachable | Stage 2 proceeds; Stage 3 (chain) aborts — report the gap, continue with search-evidence only. |
| All sources 429 | Report partial results + which source failed; suggest retry in 30s. |
| No results for query | "No academic results found for `<query>`" — do NOT fabricate. |
| `academic_citation_chain` resolves no DOI/arXiv/OpenAlex id | Say "No citation neighbors found for `<id>`"; do NOT fabricate. |
