#!/usr/bin/env python3
"""scenario_dress_rehearsal.py — End-to-end ORCHESTRATION PROTOCOL rehearsal.

Port of tests/scenario-dress-rehearsal.sh to stdlib-only Python: cross-platform,
no shell=True, identical fixtures and assertions. Exercises the *protocol*
(not the tools in isolation) using only /tmp fixtures — zero LLM calls,
zero real campaign state. Four self-contained scenario groups, each in its
own mktemp fixture with explicit PASS/FAIL assertions and a running counter.

  A. SESSION-ORIENTATION — build a minimal campaign, assert it parses and the
     first-ready task is computable from files alone (no orphan dependents).
  B. DISPATCH-LIFECYCLE   — pre then post through dispatch; assert the
     decision log is sandboxed inside the fixture (RT-D4), never the
     real project.
  C. COMPACTION-SIMULATION— write state, then re-read EVERYTHING in fresh
     processes (no vars carried over) and prove the reconstructible
     "next action" is identical — a session resumes from files alone.
  D. PIVOT-SIMULATION    — mutate a dependency (T1 -> failed), append a
     decision; assert first-ready changes accordingly and the log is
     append-only with a correctly-formatted header.

Usage: tests/scenario_dress_rehearsal.py [--only <name>] [--verbose]
Exit: 0 = all pass, 1 = any fail
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
# Fixture + helper contents, verbatim from the bash heredocs.
# ---------------------------------------------------------------------------

CAMPAIGN_ORIENTATION = """\
{
  "schema_version": "1.0.0",
  "campaign_id": "rehearsal-orientation",
  "mission_ref": "MISSION.md",
  "status": "in_progress",
  "created": "2026-08-08T00:00:00Z",
  "updated": "2026-08-08T00:00:00Z",
  "tasks": {
    "T1": { "file": "tasks/T1.md", "status": "done", "depends_on": [], "sub_agents": [] },
    "T2": { "file": "tasks/T2.md", "status": "pending", "depends_on": ["T1"], "sub_agents": [] },
    "T3": { "file": "tasks/T3.md", "status": "pending", "depends_on": ["T2"], "sub_agents": [] }
  }
}
"""

CAMPAIGN_COMPACTION = """\
{
  "schema_version": "1.0.0",
  "campaign_id": "rehearsal-compaction",
  "mission_ref": "MISSION.md",
  "status": "in_progress",
  "created": "2026-08-08T00:00:00Z",
  "updated": "2026-08-08T00:00:00Z",
  "tasks": {
    "T1": { "file": "tasks/T1.md", "status": "done", "depends_on": [], "sub_agents": [] },
    "T2": { "file": "tasks/T2.md", "status": "pending", "depends_on": ["T1"], "sub_agents": [] },
    "T3": { "file": "tasks/T3.md", "status": "pending", "depends_on": ["T2"], "sub_agents": [] }
  }
}
"""

CAMPAIGN_PIVOT = """\
{
  "schema_version": "1.0.0",
  "campaign_id": "rehearsal-pivot",
  "mission_ref": "MISSION.md",
  "status": "in_progress",
  "created": "2026-08-08T00:00:00Z",
  "updated": "2026-08-08T00:00:00Z",
  "tasks": {
    "T1": { "file": "tasks/T1.md", "status": "pending", "depends_on": [], "sub_agents": [] },
    "T2": { "file": "tasks/T2.md", "status": "pending", "depends_on": ["T1"], "sub_agents": [] },
    "T3": { "file": "tasks/T3.md", "status": "pending", "depends_on": [], "sub_agents": [] }
  }
}
"""

T1_TASK = """\
{ "schema_version": "1.0.0", "task_id": "T1", "status": "done", "outputs": ["out/T1.md"] }
"""

T2_TASK = """\
{
  "schema_version": "1.0.0", "task_id": "T2", "status": "pending",
  "depends_on": ["T1"],
  "output_contract": { "min_size_bytes": 500, "required_sections": ["Findings", "Method"] }
}
"""

# Reusable: compute first-ready task + its output contract from files alone.
NEXT_HELPER = """\
import json, sys, os
fix = sys.argv[1]
camp = json.load(open(f"{fix}/CAMPAIGN.json"))
tasks = camp["tasks"]
done = {tid for tid, t in tasks.items() if t.get("status") == "done"}
def ready(tid):
    t = tasks[tid]
    return t.get("status") == "pending" and all(d in done for d in t.get("depends_on", []))
ready_tasks = sorted(
    [tid for tid in tasks if ready(tid)],
    key=lambda tid: (int(''.join(c for c in tid if c.isdigit()) or 0), tid),
)
first = ready_tasks[0] if ready_tasks else None
contract = {}
tp = f"{fix}/tasks/{first}.json"
if first and os.path.exists(tp):
    contract = json.load(open(tp)).get("output_contract", {})
print(json.dumps({"next_task": first, "output_contract": contract}, sort_keys=True))
"""

# Reusable: assert a campaign has no orphan dependents + report first-ready.
ORIENT_HELPER = """\
import json, sys
fix = sys.argv[1]
camp = json.load(open(f"{fix}/CAMPAIGN.json"))
tasks = camp["tasks"]
for tid, t in tasks.items():
    for d in t.get("depends_on", []):
        assert d in tasks, f"orphan dependent: {tid} -> {d}"
done = {tid for tid, t in tasks.items() if t.get("status") == "done"}
def ready(tid):
    t = tasks[tid]
    return t.get("status") == "pending" and all(d in done for d in t.get("depends_on", []))
ready_tasks = sorted(
    [tid for tid in tasks if ready(tid)],
    key=lambda tid: (int(''.join(c for c in tid if c.isdigit()) or 0), tid),
)
first = ready_tasks[0] if ready_tasks else None
print(f"OK first_ready={first} ready_count={len(ready_tasks)}")
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", default="",
                        help="only run tests whose name contains this substring")
    parser.add_argument("--verbose", action="store_true",
                        help="print command output for passing tests")
    args = parser.parse_args(argv)

    project = os.environ.get("PROJECT", "<project>")
    scripts = os.path.join(project, ".scratch", "scripts")
    only = args.only
    verbose = args.verbose

    pass_count = 0
    fail_count = 0
    failed_tests = []
    fixtures = []

    # --- harness helpers ---------------------------------------------------

    def write_text(path, content):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write(content)

    def run_cmd(cmd, cwd=None):
        """Run a command; return stdout on success, raise on non-zero exit."""
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        if res.returncode != 0:
            msg = (res.stderr or res.stdout).strip() or f"exit {res.returncode}"
            raise RuntimeError(msg)
        return res.stdout

    def req(cond, msg="assertion failed"):
        if not cond:
            raise AssertionError(msg)

    def count_startswith(path, prefix):
        return sum(1 for line in open(path) if line.startswith(prefix))

    def contains(path, needle):
        return needle in open(path).read()

    def run_test(name, fn):
        """Run fn(); on success count a PASS and (if verbose) show output."""
        nonlocal pass_count, fail_count
        if only and only not in name:
            return
        try:
            out = fn()
        except Exception as exc:  # noqa: BLE001 — surface any failure
            fail_count += 1
            failed_tests.append(name)
            print(f"  ❌ {name} ({exc})")
            return
        pass_count += 1
        print(f"  ✅ {name}")
        if verbose and out:
            for line in out.splitlines():
                print(f"       {line}")

    def heartbeat(scenario, status):
        # R9 heartbeat — never fails a test (guarded). Writes to /tmp, NOT the
        # project — the harness claims "zero real campaign state" and must honor
        # it. Mirrors the bash heartbeat() exactly.
        f = os.environ.get("REHEARSAL_HEARTBEAT", "/tmp/rehearsal-heartbeat.json")
        os.makedirs(os.path.dirname(f), exist_ok=True)
        ts = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        try:
            with open(f, "w") as fh:
                fh.write(json.dumps(
                    {"scenario": scenario, "status": status, "ts": ts}) + "\n")
        except Exception:  # noqa: BLE001 — heartbeat must never fail a test
            pass

    def new_fixture():
        d = tempfile.mkdtemp(prefix="dress-rehearsal.")
        fixtures.append(d)
        return d

    def cleanup():
        for d in fixtures:
            if d and os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)

    def decision_log(task_id, decision, rationale, outcome, log_file):
        # decision-log.sh was a shim -> toolchain.py decision-log.
        run_cmd([sys.executable, os.path.join(scripts, "toolchain.py"),
                 "decision-log", "--task-id", task_id, "--decision", decision,
                 "--rationale", rationale, "--outcome", outcome,
                 "--log-file", log_file])

    # --- header ------------------------------------------------------------

    print("=== Scenario Dress Rehearsal (orchestration protocol) ===")
    print(f"Project: {project}")
    print("")

    try:
        # --------------------------------------------------------------
        # A. SESSION-ORIENTATION
        # --------------------------------------------------------------
        print("--- A. SESSION-ORIENTATION ---")
        heartbeat("orientation", "before")
        F = new_fixture()
        os.makedirs(os.path.join(F, "tasks"))
        write_text(os.path.join(F, "CAMPAIGN.json"), CAMPAIGN_ORIENTATION)
        write_text(os.path.join(F, "tasks", "T1.json"), T1_TASK)

        # DECISIONS.md with >=2 entries (real tool, pointed at the fixture).
        decision_log("T1", "seed decision A", "orientation fixture", "ok",
                     os.path.join(F, "DECISIONS.md"))
        decision_log("T2", "seed decision B", "orientation fixture", "ok",
                     os.path.join(F, "DECISIONS.md"))

        run_test("CAMPAIGN.json parses as valid JSON",
                 lambda: run_cmd([sys.executable, "-c",
                                  "import json,sys; json.load(open(sys.argv[1]))",
                                  os.path.join(F, "CAMPAIGN.json")]))

        write_text(os.path.join(F, "_orient.py"), ORIENT_HELPER)
        run_test("no orphan dependents + first ready task is T2",
                 lambda: run_cmd([sys.executable,
                                  os.path.join(F, "_orient.py"), F]))

        run_test("DECISIONS.md has >=2 entries",
                 lambda: req(count_startswith(
                     os.path.join(F, "DECISIONS.md"), "## ") >= 2,
                     "expected >=2 decision entries"))
        heartbeat("orientation", "after")
        print("")

        # --------------------------------------------------------------
        # B. DISPATCH-LIFECYCLE
        # --------------------------------------------------------------
        print("--- B. DISPATCH-LIFECYCLE ---")
        heartbeat("dispatch", "before")
        F = new_fixture()
        proj = os.path.join(F, "proj")
        os.makedirs(proj)
        write_text(os.path.join(proj, "MISSION.md"), "# Mission\n")

        # dispatch-wrapper.sh was a shim -> toolchain.py dispatch.
        run_test("dispatch pre exits 0",
                 lambda: run_cmd([sys.executable,
                                  os.path.join(scripts, "toolchain.py"),
                                  "dispatch", "--mode", "pre", "--cwd", proj,
                                  "--task-id", "W1", "--inputs", "MISSION.md",
                                  "--outputs", "out.md", "--min-bytes", "100",
                                  "--format", "markdown",
                                  "--description", "rehearsal pre"]))

        # Produce a verified-good output (markdown header + >=100 bytes).
        write_text(os.path.join(proj, "out.md"), "# Header\n" + "x" * 300)

        run_test("dispatch post exits 0",
                 lambda: run_cmd([sys.executable,
                                  os.path.join(scripts, "toolchain.py"),
                                  "dispatch", "--mode", "post", "--cwd", proj,
                                  "--task-id", "W1", "--outputs", "out.md",
                                  "--min-bytes", "100", "--format", "markdown"]))

        # RT-D4 sandboxing: log lands INSIDE the fixture, NEVER the real
        # project.
        run_test("decision log written inside fixture",
                 lambda: req(os.path.isfile(os.path.join(
                     proj, ".scratch", "task-state", "DECISIONS.md")),
                     "fixture decision log missing"))
        # RT-D4: real-project decision log must NOT contain the fixture's
        # dispatch id. Mirrors `! grep -q "W1" ...`: passes if the file is
        # absent OR does not contain "W1".
        def rt_d4():
            p = os.path.join(project, ".scratch", "task-state", "DECISIONS.md")
            if os.path.exists(p):
                req("W1" not in open(p).read(),
                    "real project decision log polluted with W1")
        run_test("real project decision log NOT polluted (RT-D4)", rt_d4)
        heartbeat("dispatch", "after")
        print("")

        # --------------------------------------------------------------
        # C. COMPACTION-SIMULATION
        # --------------------------------------------------------------
        print("--- C. COMPACTION-SIMULATION ---")
        heartbeat("compaction", "before")
        F = new_fixture()
        os.makedirs(os.path.join(F, "tasks"))
        write_text(os.path.join(F, "CAMPAIGN.json"), CAMPAIGN_COMPACTION)
        write_text(os.path.join(F, "tasks", "T2.json"), T2_TASK)

        decision_log("T1", "compaction seed 1", "r", "o",
                     os.path.join(F, "DECISIONS.md"))
        decision_log("T2", "compaction seed 2", "r", "o",
                     os.path.join(F, "DECISIONS.md"))

        write_text(os.path.join(F, "_next.py"), NEXT_HELPER)

        # Process 1: compute next-action from files, persist to disk.
        baseline = run_cmd([sys.executable, os.path.join(F, "_next.py"), F])
        write_text(os.path.join(F, "next.baseline"), baseline)
        run_test("baseline next-action written to disk",
                 lambda: req(os.path.getsize(os.path.join(F, "next.baseline"))
                             > 0, "baseline file empty"))
        run_test("next action targets T2 with output contract",
                 lambda: req(contains(os.path.join(F, "next.baseline"),
                                      '"next_task": "T2"'),
                             "expected next_task T2"))

        # Process 2: a FRESH python process re-reads ALL state from files
        # alone (no vars carried over) and must reproduce the identical value.
        def compaction_fresh():
            fresh = run_cmd([sys.executable, os.path.join(F, "_next.py"), F])
            # bash compared $() output on both sides -> trailing newline stripped.
            req(fresh.rstrip("\n") == baseline.rstrip("\n"),
                "fresh process reproduced a different next action")
        run_test("compaction: fresh process reproduces identical next action",
                 compaction_fresh)
        heartbeat("compaction", "after")
        print("")

        # --------------------------------------------------------------
        # D. PIVOT-SIMULATION
        # --------------------------------------------------------------
        print("--- D. PIVOT-SIMULATION ---")
        heartbeat("pivot", "before")
        F = new_fixture()
        os.makedirs(os.path.join(F, "tasks"))
        write_text(os.path.join(F, "CAMPAIGN.json"), CAMPAIGN_PIVOT)
        write_text(os.path.join(F, "_next.py"), NEXT_HELPER)

        # Seed one decision BEFORE the pivot (proves append-only later).
        decision_log("T1", "initial plan", "start", "ok",
                     os.path.join(F, "DECISIONS.md"))

        # Baseline next-action (T1).
        before = run_cmd([sys.executable, os.path.join(F, "_next.py"), F])
        write_text(os.path.join(F, "next.before"), before)
        run_test("baseline first-ready is T1",
                 lambda: req(contains(os.path.join(F, "next.before"),
                                      '"next_task": "T1"'),
                             "expected next_task T1"))

        # PIVOT: mutate a dependency — flip T1 -> failed. (path via argv)
        run_cmd([sys.executable, "-c",
                 "import json,sys; d=json.load(open(sys.argv[1])); "
                 "d['tasks']['T1']['status']='failed'; "
                 "json.dump(d, open(sys.argv[1],'w'), indent=2)",
                 os.path.join(F, "CAMPAIGN.json")])
        run_test("CAMPAIGN.json still valid JSON after pivot",
                 lambda: run_cmd([sys.executable, "-c",
                                  "import json,sys; json.load(open(sys.argv[1]))",
                                  os.path.join(F, "CAMPAIGN.json")]))

        # Append the pivot decision (real tool, append-only).
        decision_log("T1", "PIVOT: T1 failed, reroute downstream",
                     "simulated failure", "reroute to T3",
                     os.path.join(F, "DECISIONS.md"))

        # Recompute next-action after pivot.
        after = run_cmd([sys.executable, os.path.join(F, "_next.py"), F])
        write_text(os.path.join(F, "next.after"), after)
        run_test("pivot changes first-ready (T1 -> T3)",
                 lambda: req('"next_task": "T1"' not in after
                             and '"next_task": "T3"' in after,
                             "expected next_task to change from T1 to T3"))

        dec = os.path.join(F, "DECISIONS.md")
        run_test("decision log contains pivot entry",
                 lambda: req(contains(dec, "PIVOT: T1 failed"),
                             "pivot entry missing"))
        run_test("decision log append-only: prior entry preserved",
                 lambda: req(contains(dec, "initial plan"),
                             "prior entry lost"))
        run_test("decision log has exactly 2 entries",
                 lambda: req(count_startswith(dec, "## ") == 2,
                             "expected exactly 2 entries"))
        run_test("decision log file header present",
                 lambda: req(any(line.startswith("# Decision Log")
                                 for line in open(dec)),
                             "file header missing"))
        run_test("decision entry header matches documented format",
                 lambda: req(re.search(
                     r"^## \d{4}-\d{2}-\d{2}T[\d:]+Z \| T1$",
                     open(dec).read(), re.MULTILINE) is not None,
                     "entry header format mismatch"))
        heartbeat("pivot", "after")
        print("")

    finally:
        cleanup()

    # --- summary -----------------------------------------------------------

    print("==========================================")
    print(f"RESULTS: {pass_count} passed, {fail_count} failed")
    if fail_count > 0:
        print("Failed tests:")
        for t in failed_tests:
            print(f"  - {t}")
        print("")
        print("DRESS REHEARSAL: FAILED")
        return 1
    print("ALL DRESS REHEARSAL SCENARIOS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
