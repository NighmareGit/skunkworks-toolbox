---
name: academic-research
description: >
  Scoped academic literature research via keyless scholarly APIs (OpenAlex, arXiv, Crossref, PubMed, Semantic Scholar).
  Use when the user says "research the literature on X", "pull papers on Y", "citation chain for Z",
  "update the research base on W", "find prior art for V", or asks for a literature review / paper lookup / citation walk.
  Does NOT do general web search — if the request needs non-academic sources, say so and stop.
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
  compatibility: "requires `academic-mcp` MCP server registered in ~/.grok/mcpServers"
---

# `/academic-research` — Scoped Academic Literature Research

Research the academic literature using **keyless scholarly APIs only**. This skill routes intents to the `academic-mcp` MCP server tools and orchestrates the `academic-research` Rhai workflow for deep multi-source investigations.

## Scope Discipline (hard rule)

**Academic sources ONLY.** The four MCP tools pull exclusively from scholarly databases:

| Tool | Backend | What it returns |
|------|---------|-----------------|
| `academic_search` | OpenAlex + arXiv + Crossref + PubMed | Deduped, ranked paper results (title, authors, year, citations, abstract, DOI) |
| `academic_citation_chain` | OpenAlex citation graph | Backward (refs) or forward (cites) neighbors, 1–2 hops |
| `academic_get_paper` | OpenAlex + Unpaywall + arXiv API | Full metadata + abstract + open-access PDF link |
| `academic_tldr` | Semantic Scholar (best-effort) | One-sentence summaries; degrades gracefully on 429 |

**NOT available here:** general web search, news, blogs, company docs, GitHub, non-scholarly sources. If the user needs those, say: *"This skill is scoped to academic literature only — the request needs general web search, which is out of scope here."* Then stop. Do NOT silently substitute `searxng` or `web_search`.

**Keyless & local.** No API tokens required. Runs against public scholarly APIs (polite pools respected). No paid SaaS.

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
| "Find papers on topic X" / "research the literature on X" | `academic_search` | Single call per sub-question; use `sources` to scope if user specifies (e.g., "only arXiv"). |
| "Who cites paper Y" / "what builds on Y" | `academic_citation_chain(direction="cites")` | Forward chain. Start from DOI/arXiv id if user gives one; otherwise `academic_search` first to find the seed. |
| "What does paper Y reference" / "prior art for Y" | `academic_citation_chain(direction="refs")` | Backward chain. |
| "Get details on paper Z" / "abstract of Z" | `academic_get_paper` | Resolves DOI, arXiv id, or OpenAlex id. |
| "Summarize these papers" / "TL;DR on X, Y, Z" | `academic_tldr` | Batch endpoint — pass up to 10 ids per call. Graceful on 429. |
| Deep literature review / multi-facet investigation | **invoke the workflow** (see below) | Bounded sub-questions → search wave → chain → evidence → verify → synthesize. |
| Verify/refresh an entry in the research base | `academic_get_paper` + `academic_search` | Confirm arXiv id resolves, abstract matches, citation count current. |

### Routing rules

1. **Dedup + ranking is in the server.** Do NOT re-rank or re-dedup results in the skill. The server already normalizes titles, merges by DOI, and sorts by citation count desc then year desc.
2. **Prefer precision over recall.** Default `limit=10`. Only raise if the user explicitly wants breadth.
3. **Chain depth 1 unless asked.** `depth=1` is the default; `depth=2` only when the user asks for "broader context" or "2-hop".
4. **Batch TLDRs.** If summarizing N papers, one `academic_tldr` call with all ids, not N calls.

### Known caveats (read before chaining)

1. **arXiv-id resolution is now transparent.** Bare arXiv ids (`2312.11514`) are accepted by `academic_citation_chain` and `academic_get_paper` — the server normalizes them to DOI form (`10.48550/arXiv.2312.11514`) internally. You do NOT need to pre-convert them.
2. **OpenAlex splits preprint vs. published version — seed chains from the published DOI for full yield.** A single arXiv preprint and its published journal/conference version are *different OpenAlex work records*. Seeding `academic_citation_chain` from a preprint id only surfaces citations **to the preprint** (often 3–13). The published version typically has hundreds of citations. **When a published DOI is known (e.g. from `academic_search` results, or `academic_get_paper` which enriches the published version), always seed the chain from that published DOI** — not the arXiv id — to get the full forward-citation set. The skill's `get_paper` now enriches arXiv-sourced records with the OpenAlex published-version metadata (citation count + venue) when a match is found.
3. **`academic_get_paper` citation counts are now real.** The server enriches arXiv-sourced lookups with OpenAlex (keyless) so `citation_count` and `venue` reflect the published record, falling back gracefully to `citation_count: 0` / `venue: "arXiv"` only when no OpenAlex record exists.

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

1. **Verify an entry** — `academic_get_paper` with the arXiv id; confirm title, first author, abstract summary match the base entry. Flag mismatches.
2. **Refresh community status** — `academic_citation_chain(direction="cites", depth=1)` to check for new citing papers since last update.
3. **Add a new verified paper** — `academic_search` to find it, `academic_get_paper` to confirm metadata, then append to the base with full provenance (arXiv id, title, first author, venue, abstract summary, mission link).
4. **Dedup check** — before adding, `academic_search` the title to confirm it's not already in the base under a different id.

**Convention for base entries:**

```
| [arXiv:<id>](https://arxiv.org/abs/<id>) | <Title> | <First author> | <Venue> | <One-line abstract summary + mission link> |
```

Every entry MUST have a resolvable arXiv id or DOI. Entries without one are flagged for verification.

## Quick reference — MCP tool call pattern

Tools are accessed via the `use_tool` tool with the qualified name `academic-mcp__<tool>`. Always call `search_tool` first to confirm the current schema (the server may be updated). Example:

```
search_tool(query: "academic_search")   // returns schema
use_tool(tool_name: "academic-mcp__academic_search", tool_input: {query: "mixture of experts", limit: 5})
```

If the MCP server is not registered or tools are unavailable, fail fast with: *"The academic-mcp MCP server is not reachable. Check registration in ~/.grok/mcpServers and that the server process is running."*

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
| MCP server unreachable | Fail fast with registration check instructions. |
| All sources 429 | Report partial results + which source failed; suggest retry in 30s. |
| No results for query | Say "No academic results found for `<query>`" — do NOT fabricate. |
| User asks for non-academic source | Scope refusal: "Out of scope — use general web search for that." |
| `academic_tldr` degrades | Note "(TLDR unavailable — Semantic Scholar rate-limited)"; proceed with abstracts. |
