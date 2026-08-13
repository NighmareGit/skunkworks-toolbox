# Grok Role Architecture — Model Routing & Scoped System Prompts

> How the orchestration layer is wired: which model plays which role, why,
> and how the rails keep LongCat from looping.
> Applies to: `~/.grok/config.toml` + `~/.grok/prompts/*.md` + `~/.grok/personas/*.toml`

---

## The Model-Role Matrix

| Tier | Role | Model | Capability | Why this model |
|------|------|-------|------------|----------------|
| **Orchestrator** | `orchestrator` | `deepseek-v4-flash` | all | Coordination = state machine + dispatch + verify + log. Light cognitive load, high frequency. Flash is correct, not a compromise. |
| **Fork** | (session fork) | `deepseek-v4-flash` | — | `fork_secondary_model` → forks inherit the orchestrator model. |
| **Worker** | `researcher` | `longcat` | read-only | Heavy reading + synthesis. 256K context is the asset. |
| **Worker** | `implementer` | `longcat` | all | Code changes, test-running. Deep work. |
| **Worker** | `general` | `longcat` | all | Well-scoped execution tasks. |
| **Worker** | `planner` | `longcat` | read-only | Architecture/planning reads lots of files. |
| **Sentinel** | `verifier` | `deepseek-v4-flash` | read-only | Contract checking is mechanical + cheap. Different model than implementer = correlated-error protection. |
| **Utility** | `math-enforcer` | `deepseek-v4-flash` | execute | Validation tasks. (Also: path bug fixed from Windows → Linux.) |
| **Explore** | (built-in explore) | `local-gemma-4-e4b` | read-only | `[subagents.models]` routing — free local AI (127.0.0.1:8080, this machine) |

## Local AI validation (127.0.0.1:8080)

Validated 2026-08-08. Model: `gemma-4-E4B-Gemini-3.1-Pro-Reasoning-Distill-Q6_K.gguf`
(7.5B params, 6.2 GB, Q6_K, 131K ctx, 4 parallel slots, llama.cpp server on this host).

| Capability | Result | Note |
|-----------|--------|------|
| Speed | **~100-107 tok/s** | Fast enough for explore/recon |
| Logic | **Strong** | Clean syllogistic reasoning |
| Math | **Works, needs token budget** | Reasoning-distill model: emits chain-of-thought into `reasoning_content` FIRST; `content` stays empty if `max_tokens` is small. "Can't do math" = budget artifact. Give ≥512 tokens. |
| Tool calls | **WORK** | Proper `finish_reason: tool_calls` + JSON args (tested get_weather) |
| Windows tool-call flakiness | Known | Server runs on Windows (model_path `D:\Models\...`); tool-call formatting can glitch. Verifier should re-check explore outputs. |

**Suitability verdict:** ✅ Good for explore (fast recon: read/grep/list; strong logic for interpretation; free).
**Caveats:** (1) Do NOT route math-heavy tasks to it — reasoning eats the budget, content returns empty.
(2) Give adequate `max_tokens` (config has 32768 — good). (3) Server binds loopback only; Grok on this
host reaches it via 127.0.0.1:8080.

## Why this split works

```
                ┌─────────────────────────────┐
                │  ORCHESTRATOR (ds-4-flash)   │  ← coordination, NOT execution
                │  dispatch · verify · recover │
                └──────┬──────────┬────────────┘
                       │ delegate │
        ┌──────────────▼──┐  ┌────▼─────────────┐
        │ LONG-CAT WORKERS │  │ VERIFIER (ds-4)   │
        │ researcher      │  │ independent check │
        │ implementer     │  │ contract-focused  │
        │ general / planner│  └───────────────────┘
        └─────────────────┘
```

- **Cost**: coordination is cheap (flash), deep work is expensive (longcat) — money spent where reasoning actually happens.
- **Correlated errors**: implementer (longcat) and verifier (ds-4-flash) are different models, so the verifier doesn't share the implementer's blind spots.
- **Context preservation**: the orchestrator's context stays lean because it never does execution work (the coordination-ratio rule from campaign-orchestrator: <20% orchestration).

## The LongCat Looping Problem → Rails

LongCat **loops** when given open-ended tasks, broad scopes, or ambiguous goals.
Every LongCat role therefore ships with the **Rail Core** (`~/.grok/prompts/longcat-rails.md`)
as a mandatory preamble:

| Rail | What it prevents |
|------|------------------|
| R1 SINGLE GOAL | Wandering across multiple goals |
| R2 TOOL BUDGET | Infinite exploration (hard cap, default 20) |
| R3 NUMBERED STEPS | Improvising new work |
| R4 STOP-AND-REPORT | Retry loops (max 2 retries, then LOOP DETECTED) |
| R5 DEFINITION OF DONE | Premature or gold-plated completion |
| R6 NO DERIVATION | Fabricating file content instead of reading |
| R7 NO SCOPE CREEP | Adjacent-work creep |
| R8 ASK FOR CLARITY | Guessing on ambiguity |
| R9 HEARTBEAT | Silent stalls (state file = observability) |

The orchestrator ENFORCES these via the dispatch toolchain (scope-guard.py sets
budgets, dispatch-wrapper runs pre/post gates, recovery-playbook catches loops).

## Role prompt files

| File | Role | Model | Rails |
|------|------|-------|-------|
| `~/.grok/prompts/orchestrator.md` | Orchestrator | ds-4-flash | dispatch discipline, longcat-handling |
| `~/.grok/prompts/researcher.md` | Researcher | longcat | R1-R9 + no-derivation reinforced |
| `~/.grok/prompts/implementer.md` | Implementer | longcat | R1-R9 + scope-creep reinforced |
| `~/.grok/prompts/general.md` | General | longcat | R1-R9 + single-goal reinforced |
| `~/.grok/prompts/planner.md` | Planner | longcat | R1-R9 + planner-doesn't-execute |
| `~/.grok/prompts/verifier.md` | Verifier | ds-4-flash | independent check, no repair |
| `~/.grok/prompts/longcat-rails.md` | (shared) | — | the rail core, referenced by all longcat roles |
| `~/.grok/personas/longcat-rails.toml` | (persona) | longcat | reusable anti-loop overlay for ad-hoc longcat spawns |

## Skills by role (what each role loads)

| Role | Skills |
|------|--------|
| Orchestrator | `campaign-orchestrator`, `orchestration-dispatch`, `task-state`, `agent-monitor`, `worktree-guard` (for dispatch) |
| Researcher | `academic-research`, `research`, `research-pipeline` |
| Implementer | `implement`, `tdd`, `worktree-guard`, `prototype`, `check-work` |
| General | (task-dependent; defaults apply) |
| Plan | `codebase-design`, `create-workflow` (if planning workflows) |
| Verifier | `check-work`, `perf-verification`, `review` |

## Dispatch recipe (orchestrator → longcat worker)

Every dispatch to a LongCat role MUST include in the prompt:
1. The **one-sentence goal** (R1)
2. The **tool-call budget** (R2) — default 20
3. **Numbered steps** in order (R3)
4. The **output contract**: exact path, min bytes, format, required sections (R5)
5. The **input file list** with absolute paths (R6 — prevent derivation)
6. Reference to `~/.grok/prompts/longcat-rails.md` (read first)

Use `toolchain.py dispatch --mode pre` to validate before spawning, and
`--mode post` to verify after. The `sanitize-prompt.py --brief` builder generates
this structure automatically.

## Change log

| Date | Change |
|------|--------|
| 2026-08-08 | Added 6 sub-agent roles (orchestrator/researcher/implementer/general/planner/verifier). Set fork model → ds-4-flash. Routed explore → ds-4-flash. Fixed math-enforcer prompt path (Windows → Linux). Added rail core + persona overlay. |

## Reverting

Backup: `~/.grok/config.toml.bak-20260808-172316`
Restore: `cp ~/.grok/config.toml.bak-20260808-172316 ~/.grok/config.toml`
Then delete `~/.grok/prompts/*.md` (role prompts) + `~/.grok/personas/longcat-rails.toml`.
