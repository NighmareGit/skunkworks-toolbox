let meta = #{
    name: "campaign-template",
    description: "Template for systematic multi-target fix campaigns. Copy this file and customize the targets array, paths, and prompts.",
};

// ── Model routing note ─────────────────────────────────────────────────
// agent() sub-agents inherit the parent model (frontier with web access).
// If dispatching to a local model, add: "if you need internet, reply NEED_ONLINE: <query>"
// The parent handles the web_search and returns results.

// ── Constants (CUSTOMIZE) ──────────────────────────────────────────────
let data_dir = ".scratch/data/historical/5yr_50names";
let benchmark_dir = ".scratch/benchmarks";
let research_dir = ".scratch/research/<campaign-slug>";
let spec_dir = ".scratch/plans/<campaign-slug>";

let targets = [
    // CUSTOMIZE: one entry per missed metric
    #{id: "ID1", name: "target-name", metric: "Metric X current < target", detail: "What's wrong in one sentence"},
    #{id: "ID2", name: "target-name", metric: "Metric Y current < target", detail: "What's wrong in one sentence"},
];

print("Campaign: <name> — " + targets.len() + " targets");

// ══════════════════════════════════════════════════════════════════════
// Phase 0: Triage
// ══════════════════════════════════════════════════════════════════════
print("[PHASE 0] Triage...");

let triage_prompt = `...`;  // See fix-missed-targets.rhai for full prompt
let triage = agent(triage_prompt);

// ══════════════════════════════════════════════════════════════════════
// Phase 1-4: Per-target loop
// ══════════════════════════════════════════════════════════════════════
for target in targets {
    // Wayfinder
    print("Wayfinder: " + target.id);
    let wf = agent(`...`);

    // Research
    print("Research: " + target.id);
    let rs = agent(`...`);

    // Grill + Red-team
    print("Grill: " + target.id);
    let gr = agent(`...`);

    // Spec + Implement
    print("Implement: " + target.id);
    let sp = agent(`...`);
}

// ══════════════════════════════════════════════════════════════════════
// Phase 5: Verify
// ══════════════════════════════════════════════════════════════════════
print("[PHASE 5] Verify...");
let verify = agent(`...`);

// ══════════════════════════════════════════════════════════════════════
// Phase 6: Code review + Commit
// ══════════════════════════════════════════════════════════════════════
print("[PHASE 6] Code review...");
let cr = agent(`...`);

print("Campaign complete.");
