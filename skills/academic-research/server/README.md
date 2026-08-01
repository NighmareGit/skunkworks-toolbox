# academic-mcp

Keyless, local MCP server for academic research. Four tools, all backed by keyless REST APIs — no API tokens required.

## Tools

| Tool | What it does | Backend |
|------|--------------|---------|
| `academic_search(query, sources, limit, focus)` | Fan-out search, DOI/title dedup, rank by citation count + recency. Dual-mode via `focus`: `"general"` (default, ML-agnostic) or `"ml"` (lateral ML/LLM-systems bias — boosts ML venues, arXiv cs.*, ML concepts; cross-domain papers still surface but rank lower; adds transparent `focus_score` breakdown) | OpenAlex, arXiv, Crossref, PubMed |
| `academic_citation_chain(work_id, direction, depth)` | Walk OpenAlex citation graph 1–2 hops (the capability no other MCP has) | OpenAlex |
| `academic_get_paper(id_or_doi)` | Full metadata + abstract + OA PDF link | OpenAlex + Unpaywall |
| `academic_tldr(paper_ids)` | Best-effort TLDRs, tolerant of rate limits | Semantic Scholar |

## Setup

```bash
cd ~/programs/academic-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

Stdio mode (for MCP clients):

```bash
source .venv/bin/activate
python academic_mcp.py
```

## Configuration

Optional env vars for polite-pool compliance:

| Var | Default | Purpose |
|-----|---------|---------|
| `OPENALEX_MAILTO` | `research@example.org` | OpenAlex polite pool (use your real email for higher rate limits) |
| `UNPAYWALL_EMAIL` | `research@example.org` | Unpaywall polite pool |

These are API parameters, not fake heartbeats — OpenAlex and Unpaywall operate a "polite pool" with better rate limits when you supply a contact email. The default is a neutral test value; set your own for production use.

## Register in ~/.grok

```json
{
  "academic-mcp": {
    "command": "bash",
    "args": ["-c", "source <MCP_VENV>/bin/activate && python <REPO_ROOT>/mcp/academic-mcp/academic_mcp.py"]
  }
}
```

## Dual-mode (`focus`)

`academic_search` accepts an optional `focus` parameter (default `"general"`):

- **`focus="general"`** (default) — ML-agnostic ranking by citation count + recency. Unchanged behavior; safe for non-ML domains (finance, biology, etc.).
- **`focus="ml"`** — lateral ML/LLM-systems bias. Computes a per-result `focus_score` (source / venue / concept / recency sub-scores, each 0.0–1.0, + weighted total) and re-ranks by `citation_count × (1 + 1.5 × total)`. Biases toward:
  - arXiv `cs.*` categories (cs.LG, cs.CL, cs.AI, cs.CV, cs.NE, stat.ML, …)
  - ML-systems venues (NeurIPS, ICML, ICLR, MLSys, CVPR, ACL, EMNLP, TMLR, JMLR, …)
  - OpenAlex concepts matching ML keywords (transformers, mixture of experts, RL, …)
  - Recent papers (full score ≤2 years old, linear decay to 0 at 7 years)

  **Cross-domain papers are never filtered out** — a highly-cited storage-engine or theory paper matching the query still appears, just ranked below ML-relevant hits. The `focus_score` breakdown is exposed per result so the bias is transparent.

## Design

See `.scratch/specs/academic-research-skill-design.md` for the full architecture.
