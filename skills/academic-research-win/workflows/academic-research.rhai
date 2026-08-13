// ═══════════════════════════════════════════════════════════════════════════════
// academic-research-win — Windows-adapted, hybrid-MCP variant of the
// academic-research workflow.
//
// Hybrid model (Option C):
//   * paper-search-mcp  — search (Stage 2) + metadata/abstract (Stage 4) + PDF.
//     Native launch on Windows:  uvx paper-search-mcp   (native stdio, no container).
//   * academic-mcp (vendored python stdio server) — OpenAlex citation-graph
//     walk (Stage 3). paper-search-mcp has NO citation-chain equivalent, so the
//     unique capability is preserved by keeping this one tool.
//
// Field remap (paper-search-mcp Paper.to_dict() -> workflow unified schema),
// mirrored in mappings/paper_search_mapping.py (+ tests/test_mapping.py):
//   doi_or_arxiv_id <- doi (fallback paper_id, then url)
//   title           <- title
//   first_author    <- first token of authors ("; "-joined)
//   year            <- int(published_date[:4])  (0 if blank)
//   citation_count  <- citations (int)
//   is_open_access  <- bool(pdf_url)   (heuristic — see module docstring)
//   abstract        <- abstract  (available from search; removes Stage 4 fetch)
// ═══════════════════════════════════════════════════════════════════════════════

let meta = #{
    name: "academic-research-win",
    description: "Windows-adapted, hybrid-MCP academic literature research pipeline: decompose question into bounded sub-questions, fan-out paper-search-mcp search_papers across 22 scholarly sources, use the vendored academic-mcp OpenAlex citation walk for Stage 3 (no paper-search-mcp equivalent), extract evidence per paper from search abstracts, verify claims against sources, synthesize a cited report with gap marking. Keyless, Windows-native.",
};

// ── Args (injected by caller or defaults) ──────────────────────────────
// args.question          — the research question (required)
// args.seed_ids          — list of known-relevant paper ids (optional, default [])
// args.freshness_years   — prefer papers within N years (default 5)
// args.max_subquestions  — cap on bounded sub-questions (default 5)
// args.output_path       — where to write the report (auto-generated if absent)

let question = args.get("question", "");
let seed_ids = args.get("seed_ids", []);
let freshness_years = args.get("freshness_years", 5);
let max_subquestions = args.get("max_subquestions", 5);

// paper-search-mcp has no timestamp helper; caller sets path when invoking.
let output_path = args.get("output_path", ".scratch/research/academic-research-win-OUTPUT.md");

// ── MCP tool helper ─────────────────────────────────────────────────────
// The parent agent has both MCP servers registered (paper-search-mcp + academic-mcp)
// under those exact names. Sub-agents spawned via agent() inherit the same session.
// We qualify tool calls as <server>__<tool>. Always call search_tool first to
// confirm the current schema before use_tool.

print("============================================================");
print("  academic-research-win workflow (hybrid MCP)");
print("  search: paper-search-mcp | citation chain: academic-mcp");
print("============================================================");
print("  Question: " + question);
print("  Seeds:    " + seed_ids.len());
print("  Freshness: " + freshness_years + " years");
print("  Max sub-Q: " + max_subquestions);
print("");

// ══════════════════════════════════════════════════════════════════════
// STAGE 1 — SCOPE
//   Turn the user's question into bounded sub-questions (max N, per A2).
//   If seed_ids provided, each becomes an anchor sub-question.
// ══════════════════════════════════════════════════════════════════════
print("[STAGE 1] SCOPE — decomposing question into bounded sub-questions");

let scope_prompt = `
# Academic Research (win) — Stage 1: Scope

You are the **Scope** stage of the Windows-adapted academic research pipeline.
Your job is to turn the user's question into at most ` + max_subquestions + ` bounded sub-questions that can each be answered by searching scholarly literature.

## Rules
- Each sub-question MUST be answerable via scholarly databases (paper-search-mcp sources: arxiv, pubmed, biorxiv, medrxiv, google_scholar, iacr, semantic, crossref, openalex, pmc, core, europepmc, dblp, openaire, citeseerx, doaj, base, zenodo, hal, ssrn, unpaywall, ieee, acm).
- Sub-questions should cover DISTINCT facets of the topic (not rephrasings of each other).
- If the user provided seed paper ids (` + seed_ids.join(", ") + `), include sub-questions that explore what cites them and what they reference (Stage 3 handles the chain).
- Mark each sub-question with a `search_query` string suitable for paper-search-mcp `search_papers`.
- Mark each with `facet`: one of {foundational, methods, recent_advances, applications, limitations, related_work}.

## User question
` + question + `

## Freshness window
Prefer papers within the last ` + freshness_years + ` years unless the question asks for historical/seminal work.

## Output format (JSON only, no prose)
{
  "subquestions": [
    {
      "id": "sq1",
      "question": "<one sentence sub-question>",
      "search_query": "<query string for search_papers>",
      "facet": "<facet label>",
      "sources_hint": ["openalex", "arxiv"]
    }
  ],
  "seeds_to_chain": ["<id from seed_ids that should be citation-chained, or empty>"],
  "notes": "<any scope assumptions you made>"
}

Output ONLY the JSON object. No markdown, no explanation.`;

let scope_result = agent(scope_prompt);
print("[STAGE 1] Scope complete");
print("");

// ══════════════════════════════════════════════════════════════════════
// STAGE 2 — SEARCH WAVE  (paper-search-mcp)
//   Fan out paper-search-mcp__search_papers per sub-question (parallel).
//   Dedup + ranking is handled by the server. Then MAP the output into the
//   workflow's unified schema so Stages 4-6 stay stable.
// ══════════════════════════════════════════════════════════════════════
print("[STAGE 2] SEARCH WAVE — fanning out paper-search-mcp__search_papers");

let search_prompt = `
# Academic Research (win) — Stage 2: Search Wave

You are the **Search Wave** stage. Call `search_papers` for EACH sub-question below.
Use `search_tool` first to confirm the current schema, then `use_tool` to call
`paper-search-mcp__search_papers`.

## Sub-questions (from Stage 1)
` + scope_result + `

## Instructions
For EACH sub-question, call:
  use_tool("paper-search-mcp__search_papers", {query: <search_query>, sources: <comma-join sources_hint, or omit/"all">, max_results_per_source: 10})

Collect ALL results. The server already dedups across sources and per-sub-question; merge the
per-sub-question runs and report a single deduplicated list. For each unique paper, record a
UNIFIED record (map paper-search-mcp Paper.to_dict() fields):

- doi_or_arxiv_id: prefer `doi`; if blank, use `paper_id` (arXiv-style); else `url`.
- title: from `title`.
- first_author: first token of `authors` (papers join authors with "; ").
- year: int(published_date[:4]); 0 if blank.
- citation_count: `citations` (int).
- is_open_access: bool(pdf_url) — heuristic; paper-search-mcp has no explicit OA flag, so this
  means "a PDF URL is locatable", not "legally open access".
- abstract: from `abstract` (keep it — Stage 4 uses it directly, no extra fetch needed).
- answered_subquestions: which sub-question id(s) it answered.

## Output format (JSON only)
{
  "papers": [
    {
      "doi_or_arxiv_id": "10.48550/arXiv.1706.03762",
      "title": "...",
      "first_author": "...",
      "year": 2017,
      "citation_count": 104000,
      "is_open_access": true,
      "abstract": "...",
      "answered_subquestions": ["sq1", "sq2"]
    }
  ],
  "subquestion_coverage": {
    "sq1": {"n_results": 5, "top_citation_count": 3934},
    "sq2": {"n_results": 0, "note": "no academic results"}
  }
}

Output ONLY the JSON object.`;

let search_result = agent(search_prompt);
print("[STAGE 2] Search wave complete (paper-search-mcp)");
print("");

// ══════════════════════════════════════════════════════════════════════
// STAGE 3 — CHAIN  (academic-mcp — the one capability paper-search-mcp lacks)
//   OpenAlex citation graph, 1–2 hops, both directions. This tool is NOT
//   in paper-search-mcp, so we deliberately keep the vendored academic-mcp server
//   registered for this stage only.
// ══════════════════════════════════════════════════════════════════════
print("[STAGE 3] CHAIN — citation chaining via academic-mcp (OpenAlex graph)");

let chain_prompt = `
# Academic Research (win) — Stage 3: Citation Chain

You are the **Citation Chain** stage. For the top-cited papers from Stage 2 AND the seed ids, walk the
OpenAlex citation graph 1 hop in BOTH directions to find related work.

## Papers to chain (top 5 by citation count from Stage 2)
` + search_result + `

## Seed ids to chain
` + seed_ids.join(", ") + `

## Instructions
For EACH paper id (top 5 + seeds), call BOTH:
  use_tool("academic-mcp__citation_chain", {work_id: <id>, direction: "refs", depth: 1})
  use_tool("academic-mcp__citation_chain", {work_id: <id>, direction: "cites", depth: 1})

(Use `search_tool` first to confirm the tool name — it may be
`academic-mcp__academic_citation_chain`.)

Merge all neighbors. For each new paper found, record:
- id, title, first_author, year, citation_count
- discovered_via: {seed_id, direction, hop}

Then run a SECOND dedup pass against the Stage 2 papers. Only keep genuinely new papers.

## Output format (JSON only)
{
  "new_papers": [
    {
      "id": "<DOI or arXiv id>",
      "title": "...",
      "first_author": "...",
      "year": 2024,
      "citation_count": 50,
      "discovered_via": {"seed": "...", "direction": "cites", "hop": 1}
    }
  ],
  "total_unique_after_chain": 42
}

Output ONLY the JSON object.`;

let chain_result = agent(chain_prompt);
print("[STAGE 3] Chain complete (academic-mcp)");
print("");

// ══════════════════════════════════════════════════════════════════════
// STAGE 4 — EVIDENCE SHARDS  (paper-search-mcp)
//   The `abstract` field is already present in Stage 2 results, so NO separate
//   paper-fetch is required. If fuller Crossref metadata is needed for a DOI,
//   call paper-search-mcp__get_crossref_paper_by_doi. paper-search-mcp has no
//   unified get_paper that resolves arXiv/OpenAlex ids — it only offers the
//   Crossref DOI lookup above, so Stage 4 leans on the abstracts Stage 2 already
//   returned.
// ══════════════════════════════════════════════════════════════════════
print("[STAGE 4] EVIDENCE SHARDS — extracting claims+evidence per paper");

let evidence_prompt = `
# Academic Research (win) — Stage 4: Evidence Shards

You are the **Evidence Shard** stage. For each of the TOP 10 papers (by citation count) from the
merged Stage 2 + Stage 3 results, extract structured evidence. The abstract is already attached
to each paper from Stage 2 (a separate fetch is NOT required). If you need fuller Crossref metadata
for a DOI, call `get_crossref_paper_by_doi` (confirm via search_tool first).

## Papers to process (top 10)
` + search_result + `
(plus any new papers from Stage 3 that rank in the top 10 by citation count)

## Instructions
For EACH paper:
1. Use the `abstract` already on the record (from Stage 2). If it is empty, call
   use_tool("paper-search-mcp__get_crossref_paper_by_doi", {doi: <doi_or_arxiv_id>})
   when a DOI is available; if only an arXiv id, the abstract is unavailable — mark as such.
2. Extract a structured evidence record:
   - **claim**: the ONE most relevant finding to the user's question
   - **evidence**: direct quote or close paraphrase from the abstract
   - **method**: study type if inferable (e.g., "empirical", "theoretical", "survey", "benchmark")
   - **confidence**: high/medium/low based on sample/scope cues in the abstract
   - **paper_id**: the DOI or arXiv id

## User question (for relevance judging)
` + question + `

## Output format (JSON only)
{
  "evidence": [
    {
      "paper_id": "10.48550/arXiv.2312.12456",
      "title": "...",
      "claim": "<one sentence>",
      "evidence": "<abstract quote>",
      "method": "empirical",
      "confidence": "high",
      "year": 2023
    }
  ],
  "unavailable": ["<id where abstract was missing and DOI not resolvable>"]
}

Output ONLY the JSON object.`;

let evidence_result = agent(evidence_prompt);
print("[STAGE 4] Evidence shards complete (paper-search-mcp)");
print("");

// ══════════════════════════════════════════════════════════════════════
// STAGE 4b — COLLECT (materialise the organised research folder)
//   Win-variant layout contract (keyless, no container):
//     * transient PDFs are downloaded to the OS-standard TEMP folder
//       (Python `tempfile.gettempdir()`) — never a hard-coded path.
//     * the per-topic collection lives at <research_root>/research/<slug>/
//       with a `pdfs/` sub-folder and a `map.md` index an AI agent can read.
//     * `research_workspace` (mappings/research_workspace.py on the agent's
//       PYTHONPATH) performs the moves and writes/refreshes `map.md`.
//   Default research root is `research` (cwd-relative); pass args.research_root
//   to point collection at the project actually being researched.
// ══════════════════════════════════════════════════════════════════════
let research_root = args.get("research_root", "research");
let research_topic = question;            // human-readable; sub-agent slugifies via _slug()
print("[STAGE 4b] COLLECT — organising papers into the research folder");
print("  Research root:  " + research_root + "/research/<slug>/");
print("  Temp download buffer: system temp (Python tempfile.gettempdir()) — VOLATILE:");
print("    cleared on reboot/cleanup; PDFs are MOVED into <topic>/pdfs/ before finish.");
print("");

let collect_prompt = `
# Academic Research (win) — Stage 4b: Collect & Index

You are the **Collect** stage. Materialise the search results + citation chain
into a neat, organised folder so downstream stages (and the next AI agent) can
find everything. The `research_workspace` helper (the `mappings` package on
your PYTHONPATH = the skill root) does the file layout and writes `map.md`.

## What you have in hand
- Stage 2 papers (`search_result`): top-ranked papers, each already normalised
  to the unified schema (doi_or_arxiv_id, title, first_author, year,
  citation_count, is_open_access, abstract) and carrying a `pdf_url` when the
  source exposes one.
- Stage 3 chain (`chain_result`): citation-chain neighbours + per-id hop counts.

## Instructions (do these exactly)
> **Persistence contract (read first).** Downloads stage in the OS-standard TEMP
> folder via research_workspace.system_tmp_dir(), which is VOLATILE: it is cleared
> on reboot and by system/disk-cleanup runs. You MUST MOVE (not copy) every PDF
> into the topic's pdfs/ sub-folder through place_and_index before finishing, and
> confirm the destination exists. The Temp file is scratch only; map.md is the
> durable index downstream stages trust.
1. topic_dir = research_workspace.init_topic(research_topic)   # creates
   <research_root>/research/<slug>/pdfs/ and an initial map.md.
   slug = research_workspace._slug(research_topic)
2. Merge & dedup (by doi_or_arxiv_id) Stage 2 top-10 + new Stage-3 papers.
3. For each collected paper:
   a. transient download — if `pdf_url` present: fetch it to a file named by
      `research_workspace._filename_for(id, pdf_url)` INSIDE
      research_workspace.system_tmp_dir() (the OS-standard temp folder;
      DO NOT hard-code any path).
   b. permanently collect — research_workspace.place_and_index(
        tmp_pdf, research_topic, paper_dict,
        chain_cites=<hop-1 cites for this id from chain_result, else 0>,
        chain_refs=<hop-1 refs for this id, else 0>,
        chain_stats={"direction":"both","depth":1,"hop1":<total hop-1>})
      which moves the temp PDF into topic_dir/pdfs/ and refreshes map.md.
   c. if no pdf_url: still index the paper in map.md (abstract only).
4. Emit the final absolute paths so the next stage can find the artefacts.

## Variables available to you
- research_root = ` + research_root + `
- research_topic = ` + research_topic + `

## Output format (JSON only)
{
  "topic_slug": "<slug>",
  "topic_dir": "<absolute path to <research_root>/research/<slug>>",
  "map_md": "<absolute path to map.md>",
  "pdfs_collected": <int>,
  "papers_indexed": <int>,
  "chain_hop1_total": <int>
}
Output ONLY the JSON object.`;

let collect_result = agent(collect_prompt);
print("[STAGE 4b] Collect complete — research folder organised (map.md written)");
print("");

// ══════════════════════════════════════════════════════════════════════
// STAGE 5 — VERIFIER
//   Independent cross-check: each claim must be traceable to a paper id.
//   Drop unsupported claims. Flag contradictions.
// ══════════════════════════════════════════════════════════════════════
print("[STAGE 5] VERIFIER — cross-checking claims against sources");

let verify_prompt = `
# Academic Research (win) — Stage 5: Verifier

You are the **Verifier** stage. Your job is to validate every claim from Stage 4 against its cited source. Be ruthless.

## Evidence records to verify
` + evidence_result + `

## Verification rules
1. **Traceability**: every claim MUST have a `paper_id` that resolves to a real paper. If not, DROP the claim.
2. **Fidelity**: the `evidence` field must actually support the `claim`. If the abstract doesn't contain the finding, FLAG as [claim exceeds evidence].
3. **Contradiction check**: if two claims from different papers directly contradict, mark both with [contradiction — see <other_paper_id>].
4. **Confidence calibration**: downgrade confidence if the evidence is from a single low-citation paper or a non-empirical study.

## Output format (JSON only)
{
  "verified_claims": [
    {
      "paper_id": "...",
      "claim": "...",
      "evidence": "...",
      "verdict": "supported | partial | exceeds_evidence",
      "confidence": "high | medium | low",
      "contradicts": "<other_paper_id or null>"
    }
  ],
  "dropped_claims": [
    {
      "paper_id": "...",
      "reason": "untraceable | exceeds_evidence | duplicate"
    }
  ]
}

Output ONLY the JSON object.`;

let verify_result = agent(verify_prompt);
print("[STAGE 5] Verification complete");
print("");

// ══════════════════════════════════════════════════════════════════════
// STAGE 6 — SYNTHESIS
//   Report with every claim cited (DOI/arXiv); Partial marking on gaps.
// ══════════════════════════════════════════════════════════════════════
print("[STAGE 6] SYNTHESIS — writing cited report");

let synth_prompt = `
# Academic Research (win) — Stage 6: Synthesis

You are the **Synthesis** stage. Write the final academic research report. Every claim MUST carry a source anchor.

## Verified claims
` + verify_result + `

## Dropped claims (do NOT include in report)
(already excluded above)

## Original user question
` + question + `

## Sub-questions investigated (from Stage 1)
` + scope_result + `

## Output format — write this Markdown report to: ` + output_path + `

# Academic Research Report

## Question
` + question + `

## Sub-questions investigated
1. <sub-question 1>
2. <sub-question 2>
...

## Findings

### <Claim — one sentence>
- **Source:** [<paper_id>](https://doi.org/<paper_id> or https://arxiv.org/abs/<paper_id>) — <authors> (<year>), <title>
- **Evidence:** <direct quote or close paraphrase>
- **Confidence:** high/medium/low
- **Method:** <study type>

### <Claim — next>
...

## Gaps (Partial)
- <sub-question with no academic coverage — marked Partial>
- <sub-question where claims were dropped by verifier — marked Partial>

## Sources
| # | ID | Title | Year | Citations | Open Access |
|---|----|-------|------|-----------|-------------|
| 1 | [<id>](https://arxiv.org/abs/<id>) | ... | 2024 | 123 | ✅ |

## Methodology note
- Search provider: paper-search-mcp (22 scholarly sources: arxiv, pubmed, biorxiv, medrxiv, google_scholar, iacr, semantic, crossref, openalex, pmc, core, europepmc, dblp, openaire, citeseerx, doaj, base, zenodo, hal, ssrn, unpaywall, ieee, acm)
- Citation chain: academic-mcp (OpenAlex graph) — retained because paper-search-mcp has no citation-chain tool
- Freshness window: ` + freshness_years + ` years
- Citation chaining: 1-hop forward + backward from top hits and seeds
- Verification: independent cross-check; unsupported claims dropped
- Coverage: <N> sub-questions, <M> papers examined, <K> claims verified

Write the report to ` + output_path + `. Output ONLY the file path when done.`;

let final_report = agent(synth_prompt);
print("[STAGE 6] Synthesis complete");
print("");

// ══════════════════════════════════════════════════════════════════════
// Final summary
// ══════════════════════════════════════════════════════════════════════
print("");
print("============================================================");
print("  academic-research-win workflow — COMPLETE");
print("  (search: paper-search-mcp | chain: academic-mcp)");
print("============================================================");
print("  Report: " + output_path);
print("  Stages: scope -> search -> chain -> evidence -> collect -> verify -> synthesis");
print("  Research collection: " + research_root + "/research/<topic-slug>/  (see Stage 4b map.md)");
print("============================================================");
