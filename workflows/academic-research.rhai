let meta = #{
    name: "academic-research",
    description: "Scoped academic literature research pipeline: decompose question into bounded sub-questions, fan-out academic_search across OpenAlex/arXiv/Crossref/PubMed, citation-chain top hits, extract evidence per paper, verify claims against sources, synthesize cited report with gap marking. Keyless, academic-sourced only.",
};

// ── Args (injected by caller or defaults) ──────────────────────────────
// args.question        — the research question (required)
// args.seed_ids        — list of known-relevant paper ids (optional, default [])
// args.freshness_years — prefer papers within N years (default 5)
// args.max_subquestions — cap on bounded sub-questions (default 5)
// args.output_path     — where to write the report (auto-generated if absent)

let question = args.get("question", "");
let seed_ids = args.get("seed_ids", []);
let freshness_years = args.get("freshness_years", 5);
let max_subquestions = args.get("max_subquestions", 5);

// Generate default output path if not provided
let timestamp = `date +%Y%m%d-%H%M%S`.trim();  // note: workflows can't shell out; caller sets path
let output_path = args.get("output_path", ".scratch/research/academic-research-OUTPUT.md");

// ── MCP tool helper ─────────────────────────────────────────────────────
// Workflows run as the parent agent which has MCP access. Sub-agents spawned
// via `agent()` inherit MCP access in the same session. We instruct each
// sub-agent to call the academic-mcp tools via use_tool + search_tool.

print("============================================================");
print("  academic-research workflow");
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
# Academic Research — Stage 1: Scope

You are the **Scope** stage of an academic research pipeline. Your job is to turn the user's question into at most ` + max_subquestions + ` bounded sub-questions that can each be answered by searching academic literature.

## Rules
- Each sub-question MUST be answerable via scholarly databases (OpenAlex, arXiv, Crossref, PubMed).
- Sub-questions should cover DISTINCT facets of the topic (not rephrasings of each other).
- If the user provided seed paper ids (` + seed_ids.join(", ") + `), include sub-questions that explore what cites them and what they reference.
- Mark each sub-question with a `search_query` string suitable for the `academic_search` tool.
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
      "search_query": "<query string for academic_search>",
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
// STAGE 2 — SEARCH WAVE
//   Fan out academic_search per sub-question (parallel).
//   Dedup + ranking is handled by the server.
// ══════════════════════════════════════════════════════════════════════
print("[STAGE 2] SEARCH WAVE — fanning out academic_search per sub-question");

let search_prompt = `
# Academic Research — Stage 2: Search Wave

You are the **Search Wave** stage. Call `academic_search` for EACH sub-question below. Use `search_tool` first to confirm the current schema, then `use_tool` to call `academic-mcp__academic_search`.

## Sub-questions (from Stage 1)
` + scope_result + `

## Instructions
For EACH sub-question, call:
  use_tool("academic-mcp__academic_search", {query: <search_query>, sources: <sources_hint or omit for all>, limit: 10})

Collect ALL results. Then produce a deduplicated merged list (the server already dedups across sources, but sub-questions may overlap). For each unique paper, record:
- doi_or_arxiv_id (the most resolvable id)
- title, first_author, year, citation_count
- which sub-question(s) it answered
- is_open_access (true/false)

## Output format (JSON only)
{
  "papers": [
    {
      "id": "<DOI or arXiv id>",
      "title": "...",
      "first_author": "...",
      "year": 2024,
      "citation_count": 123,
      "answered_subquestions": ["sq1", "sq2"],
      "is_open_access": true
    }
  ],
  "subquestion_coverage": {
    "sq1": {"n_results": 5, "top_citation_count": 3934},
    "sq2": {"n_results": 0, "note": "no academic results"}
  }
}

Output ONLY the JSON object.`;

let search_result = agent(search_prompt);
print("[STAGE 2] Search wave complete");
print("");

// ══════════════════════════════════════════════════════════════════════
// STAGE 3 — CHAIN
//   academic_citation_chain 1–2 hops on top hits + seed ids (parallel).
//   Forward (cites) for "who builds on this", backward (refs) for "prior art".
// ══════════════════════════════════════════════════════════════════════
print("[STAGE 3] CHAIN — citation chaining on top hits and seeds");

let chain_prompt = `
# Academic Research — Stage 3: Citation Chain

You are the **Citation Chain** stage. For the top-cited papers from Stage 2 AND the seed ids, walk the citation graph 1 hop in BOTH directions to find related work.

## Papers to chain (top 5 by citation count from Stage 2)
` + search_result + `

## Seed ids to chain
` + seed_ids.join(", ") + `

## Instructions
For EACH paper id (top 5 + seeds), call BOTH:
  use_tool("academic-mcp__citation_chain", {work_id: <id>, direction: "refs", depth: 1})
  use_tool("academic-mcp__citation_chain", {work_id: <id>, direction: "cites", depth: 1})

(Use `search_tool` first to confirm the tool name — it may be `academic-mcp__academic_citation_chain`.)

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
print("[STAGE 3] Chain complete");
print("");

// ══════════════════════════════════════════════════════════════════════
// STAGE 4 — EVIDENCE SHARDS
//   Parallel agents extract claims+evidence per paper (abstract via
//   academic_get_paper). Top-K papers only (default 10 by citation count).
// ══════════════════════════════════════════════════════════════════════
print("[STAGE 4] EVIDENCE SHARDS — extracting claims+evidence per paper");

let evidence_prompt = `
# Academic Research — Stage 4: Evidence Shards

You are the **Evidence Shard** stage. For each of the TOP 10 papers (by citation count) from the merged Stage 2 + Stage 3 results, fetch the full metadata + abstract and extract structured evidence.

## Papers to process (top 10)
` + search_result + `
(plus any new papers from Stage 3 that rank in the top 10 by citation count)

## Instructions
For EACH paper:
1. Call `academic_get_paper` to get full metadata + abstract.
   (Use `search_tool` first to confirm the tool name: `academic-mcp__academic_get_paper`.)
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
  "unavailable": ["<id where get_paper failed>"]
}

Output ONLY the JSON object.`;

let evidence_result = agent(evidence_prompt);
print("[STAGE 4] Evidence shards complete");
print("");

// ══════════════════════════════════════════════════════════════════════
// STAGE 5 — VERIFIER
//   Independent cross-check: each claim must be traceable to a paper id.
//   Drop unsupported claims. Flag contradictions.
// ══════════════════════════════════════════════════════════════════════
print("[STAGE 5] VERIFIER — cross-checking claims against sources");

let verify_prompt = `
# Academic Research — Stage 5: Verifier

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
# Academic Research — Stage 6: Synthesis

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
- Sources: OpenAlex, arXiv, Crossref, PubMed (via academic-mcp)
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
print("  academic-research workflow — COMPLETE");
print("============================================================");
print("  Report: " + output_path);
print("  Stages: scope → search → chain → evidence → verify → synthesis");
print("============================================================");
