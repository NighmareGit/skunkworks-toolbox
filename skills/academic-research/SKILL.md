---
name: academic-research
description: >
  Hybrid academic literature research: paper-search-mcp (22 scholarly sources + PDF) for search/metadata/full-text,
  the vendored academic-mcp for the OpenAlex citation-graph walk, and search_pivot.py for general-web fallback.
  Use when the user says "research the literature on X", "pull papers on Y", "citation chain for Z",
  "update the research base on W", "find prior art for V", or asks for a literature review / paper lookup / citation walk.
  Academic sources are the primary path; general web is an explicit fallback only. If the request needs
  non-academic sources, the web fallback is used and flagged — otherwise say so and stop.
  Orchestrates the `academic-research` Rhai workflow for deep multi-source runs; for single lookups call the MCP tools directly.
when-to-use: >
  "research the literature on <topic>", "pull papers on <topic>", "citation chain for <paper>",
  "what does the academic literature say about X", "find prior art for <technique>",
  "verify paper entry in the research base", "update the research base on <topic>",
  "who cites <paper>", "what does <paper> reference", "literature review on <topic>"
allowed-tools: use_tool, search_tool, read_file, write, grep, workflow
user-invocable: true
disable-model-invocation: false
metadata:
  short-description: "Scoped academic literature search via keyless scholarly APIs"
  author: "prototype-auto M3 build"
  version: "0.1.0"
  compatibility: >
    requires BOTH `paper-search-mcp` (primary: search/metadata/PDF) and `academic-mcp`
    (citation-graph walk) MCP servers registered in ~/.grok/mcpServers; paper-search-mcp
    installs via `uvx paper-search-mcp` (cross-platform, keyless core path).
---

# `/academic-research` — Hybrid Academic Literature Research

Research the academic literature using a **hybrid MCP** stack. This skill routes intents to two MCP servers and a web-fallback script, then orchestrates the `academic-research` Rhai workflow for deep multi-source investigations:

| Stage | Provider | Tool | Role |
|-------|----------|------|------|
| Search / metadata / PDF | `paper-search-mcp` | `paper-search-mcp__search_papers`, `paper-search-mcp__get_crossref_paper_by_doi` | Primary — 22 scholarly sources + PDF download/extract |
| Citation-graph walk | `academic-mcp` (vendored) | `academic-mcp__academic_citation_chain` | The capability paper-search-mcp lacks (OpenAlex graph) |
| General-web fallback | `search_pivot.py` (vendored) | CLI: `web` / `auto` | Non-academic sources only, flagged when used |

`paper-search-mcp` (https://github.com/openags/paper-search-mcp) is the better **search + full-text** provider but has **no citation-graph traversal** tool. Rather than drop capability, this skill keeps both servers registered and routes by stage. The vendored `academic_mcp.py` is a native stdio Python server (deps: `fastmcp` only) — no container runtime needed.

## Scope Discipline (hard rule)

**Academic sources ONLY.** The hybrid stack pulls exclusively from scholarly databases for the primary path:

| Tool | Backend | What it returns |
|------|---------|-----------------|
| `paper-search-mcp__search_papers` | 22 sources (arXiv, PubMed, Crossref, OpenAlex, Semantic Scholar, CORE, Europe PMC, CiteSeerX, DOAJ, BASE, Zenodo, HAL, SSRN, Unpaywall, IEEE, ACM, …) | Deduped, per-source-breakdown paper results (title, authors, year, citations, abstract, DOI, pdf_url) |
| `paper-search-mcp__get_crossref_paper_by_doi` | Crossref | Full metadata for a DOI |
| `academic-mcp__academic_citation_chain` | OpenAlex citation graph | Backward (refs) or forward (cites) neighbors, 1–2 hops |
| `academic-mcp__academic_search` | OpenAlex + arXiv + Crossref + PubMed | Deduped, ranked paper results (still available as a secondary scholarly channel) |
| `academic-mcp__academic_get_paper` | OpenAlex + Unpaywall + arXiv API | Full metadata + abstract + open-access PDF link |
| `academic-mcp__academic_tldr` | Semantic Scholar (best-effort) | One-sentence summaries; degrades gracefully on 429 |

**NOT available on the academic path:** general web search, news, blogs, company docs, GitHub, non-scholarly sources. A **general-web fallback** exists (`search_pivot.py`) and is used ONLY when the user explicitly needs non-academic sources — it is always flagged as such in the output. Otherwise say: *"This skill is scoped to academic literature only — the request needs general web search, which is out of scope here."* Then stop.

**Keyless & local (core path).** No API tokens required for the core path — `paper-search-mcp` runs keyless via `uvx paper-search-mcp`, and `academic-mcp` hits public scholarly APIs (polite pools respected). Optional keys only raise rate limits: set `PAPER_SEARCH_MCP_UNPAYWALL_EMAIL` (Unpaywall polite pool); CORE/Semantic-Scholar keys are optional. No paid SaaS.

## Output-schema mapping (paper-search-mcp → workflow)

paper-search-mcp's `Paper.to_dict()` uses different field names than the workflow's unified schema. Stage-2 sub-agents must remap so downstream stages stay stable:

| Workflow expects | paper-search-mcp source | Rule |
|---|---|---|
| `doi_or_arxiv_id` | `doi` (fallback `paper_id`, then `url`) | prefer DOI |
| `title` | `title` | direct |
| `first_author` | `authors` (`"; "`-joined string) | first token |
| `year` | `published_date` (ISO str) | `int(date[:4])`; `0` if blank |
| `citation_count` | `citations` (int) | direct |
| `is_open_access` | `pdf_url` | `bool(pdf_url)` — **heuristic**: means "PDF locatable", not legal-OA |
| `abstract` | `abstract` | direct — no extra fetch needed |

A reference implementation lives in `mappings/paper_search_mapping.py`. The workflow prompts follow exactly this contract.

## Citation Discipline (mandatory)

Every factual claim in your output **must** carry a source anchor:

- **Preferred:** DOI (e.g., `10.48550/arXiv.1706.03762`) or arXiv id (e.g., `2312.12456`).
- **Acceptable:** OpenAlex work id (e.g., `W2626778328`) when DOI unavailable.
- **Flag as unverified:** Any claim you cannot anchor to a specific paper id. Prefix with `[unverified — no source found]`.

**No citation = flagged claim.** Do not present unsourced findings as established fact. If the search returned nothing for a sub-question, say so explicitly — that is a *gap*, not a negative result.

## Intent → Tool Routing Table

Route the user's request to the minimal tool set. Do NOT call all four tools for every request.

| User intent | Tool(s) to call | Notes |
|-------------|-----------------|-------|
| "Find papers on topic X" / "research the literature on X" | `paper-search-mcp__search_papers` | `sources` = comma string or omit for all; `max_results_per_source=10`. Remap to unified schema (see output-schema mapping). |
| "Who cites paper Y" / "what builds on Y" | `academic-mcp__academic_citation_chain(direction="cites")` | Forward chain. Start from DOI/arXiv id; otherwise `search_papers` first to find the seed. |
| "What does paper Y reference" / "prior art for Y" | `academic-mcp__academic_citation_chain(direction="refs")` | Backward chain. |
| "Get details on paper Z" / "abstract of Z" | `paper-search-mcp__get_crossref_paper_by_doi` (DOI only) **or** use the abstract already returned by `search_papers` | paper-search-mcp has no arXiv/OpenAlex-id resolver; prefer the search-result abstract. For full metadata resolution, fall back to `academic-mcp__academic_get_paper`. |
| "Summarize these papers" / "TL;DR on X, Y, Z" | `academic-mcp__academic_tldr` | Batch endpoint — pass up to 10 ids per call. Graceful on 429. |
| "Find non-academic info on X" / general web | `search_pivot.py web "X"` (flagged fallback) | Non-academic only; flagged in output as a web fallback. |
| Deep literature review / multi-facet investigation | **invoke the workflow** (see below) | Bounded sub-questions → search wave → chain → evidence → verify → synthesize. |
| Verify/refresh an entry in the research base | `search_papers` (title) + abstract check | Confirm id resolves, abstract matches. |

### Routing rules

1. **Dedup + ranking is in the server.** `search_papers` returns `papers` already deduped across sources. Do not re-rank/re-dedup downstream.
2. **Prefer precision over recall.** Default `max_results_per_source=10`. Raise only on explicit breadth requests.
3. **Chain depth 1 unless asked.** `depth=1`; `depth=2` only on "broader context" or "2-hop".
4. **Batch TLDRs.** If summarizing N papers, one `academic_tldr` call with all ids, not N calls.
5. **Always call `search_tool` first** to confirm the current schema before `use_tool` — server tool names can evolve.
6. **Web fallback is flagged.** When `search_pivot.py` is used, the results are explicitly tagged as non-academic web sources.

### Known caveats (read before chaining)

1. **arXiv-id resolution is transparent on the academic-mcp side.** Bare arXiv ids (`2312.11514`) are accepted by `academic_citation_chain` and `academic_get_paper` — the server normalizes them to DOI form (`10.48550/arXiv.2312.11514`) internally. You do NOT need to pre-convert them. (paper-search-mcp itself does NOT resolve bare arXiv ids — it has no get_paper.)
2. **OpenAlex splits preprint vs. published version — seed chains from the published DOI for full yield.** A single arXiv preprint and its published journal/conference version are *different OpenAlex work records*. Seeding `academic_citation_chain` from a preprint id only surfaces citations **to the preprint** (often 3–13). The published version typically has hundreds of citations. **`search_papers` results carry the DOI when available — prefer it for chaining**, not the arXiv id, to get the full forward-citation set.
3. **`academic_get_paper` citation counts are real.** The server enriches arXiv-sourced lookups with OpenAlex (keyless) so `citation_count` and `venue` reflect the published record, falling back gracefully to `citation_count: 0` / `venue: "arXiv"` only when no OpenAlex record exists.
4. **`is_open_access` is a heuristic on the paper-search-mcp path.** paper-search-mcp exposes no explicit OA flag, so the mapping treats a non-empty `pdf_url` as "PDF locatable" — an over-approximation (some pdf_urls are paywalled landing pages). Treat the OA column accordingly; arXiv/PubMed PDFs may be openly hosted even when semantics differ per source.

## When to invoke the workflow vs. direct tool calls

**Direct tool calls (you, in-session):**
- Single paper lookup, one-shot search, quick citation check.
- Verifying/refreshing a specific research-base entry.
- ≤ 2 tool calls answer the question.

**Invoke the `academic-research` Rhai workflow:**
- The user asks for a literature review, multi-facet investigation, or "deep dive".
- The question requires synthesis across > 2 sub-questions.
- You need evidence extraction + cross-verification + cited report.
- The user says "use the workflow" or "run the full research pipeline".

### Invoking the workflow

```
workflow(name: "academic-research", args: #{ question: "<the user's question>", seed_ids: ["DOI-or-arXiv-id", ...], freshness_years: 5, max_subquestions: 5 })
```

**Args the workflow accepts:**

| Arg | Type | Default | Purpose |
|-----|------|---------|---------|
| `question` | string | required | The research question. |
| `seed_ids` | list[str] | [] | Known-relevant paper ids to anchor citation chains. |
| `freshness_years` | int | 5 | Prefer papers within this many years (older flagged as "seminal/context"). |
| `max_subquestions` | int | 5 | Cap on bounded sub-questions (A2 discipline: 3–5). |
| `output_path` | string | auto | Where to write the report. Default: `.scratch/research/academic-research-<timestamp>.md` |

### Reading the workflow output

The workflow writes a single Markdown report with this structure:

```
# Academic Research Report — <question>

## Sub-questions investigated
1. ...
2. ...

## Findings (by claim)

### Claim: <one-sentence finding>
- **Source:** <DOI or arXiv id> — <authors> (<year>), <title>
- **Evidence:** <direct abstract quote or paraphrase>
- **Confidence:** high/medium/low (based on study consensus + source count)

### Claim: ...
...

## Gaps (Partial)
- <sub-question with no academic coverage — marked Partial>

## Sources
| # | DOI/arXiv | Title | Year | Citations |
```

**Key things to check when you receive the workflow report:**
- Every `### Claim:` block has a `**Source:**` line with a resolvable id. If not, flag it.
- `## Gaps` section is present — absence of evidence is reported, not silently dropped.
- The `## Sources` table has ≥ 1 entry per claim. Cross-check.

## First live workload — maintaining the research base

The project's lateral research base lives at:

> the project's research base (e.g. `.scratch/research/lateral-research-base.md`, relative to the repo root)

**Maintenance operations (use this skill):**

1. **Verify an entry** — `search_papers` the title; confirm the abstract + DOI match the base. Flag mismatches.
2. **Refresh community status** — `academic-mcp__academic_citation_chain(direction="cites", depth=1)` on the DOI to spot new citing papers since last update.
3. **Add a new verified paper** — `search_papers` to find it, read its abstract, then append to the base with full provenance (DOI/arXiv id, title, first author, venue, abstract summary).
4. **Dedup check** — before adding, `search_papers` the title to confirm it's not already in the base under a different id.

**Convention for base entries:**

```
| [arXiv:<id>](https://arxiv.org/abs/<id>) | <Title> | <First author> | <Venue> | <One-line abstract summary + mission link> |
```

Every entry MUST have a resolvable arXiv id or DOI. Entries without one are flagged for verification.

## MCP registration (Linux — ~/.grok/mcpServers)

Both servers are registered in `~/.grok/mcpServers` (a JSON map of server-name → `{command, args, env}`). The server **names must be exactly** `paper-search-mcp` and `academic-mcp` — the workflow qualifies tool calls as `paper-search-mcp__<tool>` and `academic-mcp__<tool>`.

```jsonc
// ~/.grok/mcpServers.json  (Linux)
{
  "paper-search-mcp": {
    "command": "uvx",
    "args": ["paper-search-mcp"],
    "env": { "PAPER_SEARCH_MCP_UNPAYWALL_EMAIL": "you@example.org" }
  },
  "academic-mcp": {
    "command": "bash",
    "args": ["-c", "source <SKILL_ROOT>/.venv/bin/activate && python <SKILL_ROOT>/server/academic_mcp.py"]
  }
}
```

- **paper-search-mcp** installs and runs via `uvx paper-search-mcp` (cross-platform, keyless core path). No local checkout required. Set `PAPER_SEARCH_MCP_LOCAL_DIR` to launch from a local clone instead of `uvx`; default stays `uvx`.
- **academic-mcp** is the vendored `server/academic_mcp.py` — a native stdio Python server (dep: `fastmcp` only). Create its venv with `python3 -m venv <SKILL_ROOT>/.venv && <SKILL_ROOT>/.venv/bin/pip install -r <SKILL_ROOT>/server/requirements.txt`. Replace `<SKILL_ROOT>` with the absolute path to this skill directory.
- Restart the agent runtime after (re)writing registration.

## Quick reference — MCP tool call pattern

Tools are accessed via `use_tool` with the qualified name `<server>__<tool>`. **Always call `search_tool` first** to confirm the current schema (server tool names can evolve). Examples:

```
search_tool(query: "search_papers")
use_tool("paper-search-mcp__search_papers", {query: "mixture of experts", sources: "arxiv,openalex", max_results_per_source: 10})
use_tool("academic-mcp__academic_citation_chain", {work_id: "<DOI>", direction: "cites", depth: 1})
```

If a server is not registered, fail fast: *"The paper-search-mcp / academic-mcp MCP server is not reachable. Check registration in ~/.grok/mcpServers and that the server process is running (uvx / venv python)."*

### Keyless & optional-keys note

The core path is keyless: `uvx paper-search-mcp` runs without tokens, and `academic-mcp` hits public scholarly APIs. Optional environment variables only raise rate limits — `PAPER_SEARCH_MCP_UNPAYWALL_EMAIL` (Unpaywall polite pool), plus optional CORE/Semantic-Scholar keys. No paid SaaS is required.

## Output format for direct (non-workflow) responses

For single tool calls, respond to the user with:

```
## Results — <question>

| # | Title | Year | Citations | DOI/arXiv | Open Access |
|---|-------|------|-----------|-----------|-------------|
| 1 | ... | ... | ... | [arXiv:2312.12456](https://arxiv.org/abs/2312.12456) | ✅/❌ |

**Key findings:**
- <Claim anchored to source DOI> — <brief evidence>
- ...

**Coverage note:** <any sub-question with no results, flagged>
```

## Failure modes

| Mode | Response |
|------|----------|
| `paper-search-mcp` unreachable | Fail fast with registration check (uvx / `~/.grok/mcpServers`). |
| `academic-mcp` unreachable | Search proceeds; citation-chain stage aborts — report the gap, continue with search-evidence only. |
| All sources 429 | Report partial results + which source failed; suggest retry in 30s. |
| No results for query | Say "No academic results found for `<query>`" — do NOT fabricate. |
| User asks for non-academic source | Use the `search_pivot.py` web fallback and flag the results as non-academic web sources; if web also fails, scope refusal. |
| `academic_tldr` degrades | Note "(TLDR unavailable — Semantic Scholar rate-limited)"; proceed with abstracts. |
