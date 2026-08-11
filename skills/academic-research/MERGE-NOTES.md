# MERGE-NOTES — ACAD-MERGE

Merge of the `academic-research-win` variant's alternative source-gathering
(`paper-search-mcp`) into the Linux `academic-research` skill. Result: a **HYBRID**
skill — paper-search-mcp for search/metadata/PDF, the vendored academic-mcp for the
OpenAlex citation-graph walk, and `search_pivot.py` for general-web fallback.

## What was merged (capability table)

| Capability | Provider | Tool | Source |
|---|---|---|---|
| Scoped search across 22 scholarly sources | `paper-search-mcp` | `paper-search-mcp__search_papers` | win variant |
| Per-DOI metadata lookup | `paper-search-mcp` | `paper-search-mcp__get_crossref_paper_by_doi` | win variant |
| PDF download + text extraction | `paper-search-mcp` | (built into `search_papers` results) | win variant |
| OpenAlex citation-graph walk (1–2 hops) | `academic-mcp` (vendored) | `academic-mcp__academic_citation_chain` | pre-existing Linux |
| General-web fallback (non-academic) | `search_pivot.py` (vendored) | `web` / `auto` CLI | pre-existing Linux |
| Field remap (paper-search-mcp → workflow schema) | `mappings/paper_search_mapping.py` | `normalize_paper`, `normalize_search_papers_results`, `best_work_id_for_openalex` | win variant |
| Research-workspace layout (per-topic `map.md` + `pdfs/`) | `mappings/research_workspace.py` | `init_topic`, `place_and_index`, `write_map_md`, `CollectedPaper` | win variant |
| Hybrid workflow orchestration | `workflows/academic-research.rhai` | 6-stage funnel (scope → search → chain → evidence → collect → verify → synthesis) | win variant |

### Sections merged into `SKILL.md`

- Hybrid stage routing table (search/PDF → paper-search-mcp; chain → academic-mcp; web → search_pivot).
- `Output-schema mapping (paper-search-mcp → workflow)` table + reference to `mappings/paper_search_mapping.py`.
- Rewritten `Intent → Tool Routing Table` routing search to `search_papers`, chain to `academic_citation_chain`, web to `search_pivot`.
- `MCP registration (Linux — ~/.grok/mcpServers)` snippet with `uvx paper-search-mcp` + vendored `academic_mcp.py` (bash/venv) — **not** the Windows `.ps1`.
- `Keyless & optional-keys note` (core path keyless; Unpaywall/CORE/SS keys optional).
- Updated `Failure modes` (paper-search-mcp unreachable vs academic-mcp unreachable handled differently).
- Updated `Maintenance operations` to use `search_papers`.

### What was excluded, and why

| Excluded | Why |
|---|---|
| `mcp/register-mcp-servers.ps1` | Windows-only PowerShell registration; the Linux skill uses `~/.grok/mcpServers.json` directly. |
| Windows paths in the registration snippet (`D:\...`, `Scripts\python.exe`) | Replaced with portable `<SKILL_ROOT>` placeholders + `bash -c "source ... && python ..."`. |
| `mcp/` directory (e2e_smoke.py, verify_fixes.py, README.md) | Win-variant MCP harness; out of scope for the Linux merge. |
| `tests/` directory | Win-variant test suite; not part of this merge (smoke test is separate). |
| `CODE-REVIEW.md`, `WAYFINDER-plan.md` | Win-variant planning/review docs; not skill content. |
| `__pycache__/` | Build artifact; never copied. |

## Delta vs the pre-merge Linux skill

- **Pre-merge:** single-provider (`academic-mcp` only), 4 tools (`academic_search`, `academic_citation_chain`, `academic_get_paper`, `academic_tldr`), search via OpenAlex/arXiv/Crossref/PubMed only, no PDF extraction, web fallback was `search_pivot.py` only.
- **Post-merge (hybrid):** paper-search-mcp is the **primary** search/metadata/PDF channel (22 sources + PDF); academic-mcp is retained **specifically** for the citation-chain walk it alone provides (plus `academic_get_paper`/`academic_tldr` as secondary scholarly channels); `search_pivot.py` remains the flagged general-web fallback. The vendored `academic_mcp.py` server is unchanged in capability — only its role in the routing narrowed to "citation chain + scholarly secondary."
- **Scope discipline preserved:** academic sources are still the primary path; web fallback is explicit and flagged. Citation discipline (DOI/arXiv anchors, `[unverified]` flagging) unchanged.
- **New files:** `mappings/` (3 .py), `workflows/academic-research.rhai`, `MERGE-NOTES.md`.
