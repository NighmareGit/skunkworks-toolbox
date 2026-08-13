let meta = #{
    name: "role-routing-smoke",
    description: "Smoke-test the agent type routing: the researcher type (longcat) reads a file, the verifier type (ds-4-flash) checks the notes. Validates ~/.grok/agents/ type definitions end-to-end.",
    when_to_use: "After editing ~/.grok/agents/*.md type definitions or role prompts, to confirm agent_type routing + rails work.",
    phases: [
        #{ title: "Research", detail: "researcher type reads the target, writes structured notes" },
        #{ title: "Verify", detail: "verifier type checks the notes meet contract" },
    ],
};

// Guard args: args.target is required
let target = if args == () { () } else { args.target };
if target == () {
    pause("verification", "Pass args.target — absolute path of the file to read (e.g. a MISSION.md or report).");
}

let notes_schema = #{
    "type": "object", "required": ["path", "key_insights"],
    "properties": #{
        "path": #{ "type": "string" },
        "key_insights": #{ "type": "array", "maxItems": 10, "items": #{ "type": "string" } },
        "summary": #{ "type": "string" },
    },
};
let verdict_schema = #{
    "type": "object", "required": ["verified", "reason"],
    "properties": #{
        "verified": #{ "type": "boolean" },
        "reason": #{ "type": "string" },
        "evidence": #{ "type": "string" },
    },
};

phase("Research");
let research = agent(
    "You are a Researcher running on LongCat-2.0. RAILS (mandatory — anti-loop constraints): "
    + "R1 state your single goal in one sentence before acting; R2 hard tool-call budget of 12 — "
    + "at 80% start writing, at 100% stop; R3 follow numbered steps in order; R4 if you repeat an "
    + "action twice with no new result, STOP and report LOOP DETECTED; R5 done ONLY when output "
    + "contract met; R6 NO DERIVATION — you must actually READ the target file, never invent its "
    + "content from memory; R7 no scope creep; R8 if ambiguous, report AMBIGUOUS and proceed "
    + "conservatively; R9 write a heartbeat to .scratch/task-state/smoke-researcher.json.\n\n"
    + "GOAL: Read the file at " + target + " and produce structured notes.\n\n"
    + "Steps:\n"
    + "1. Verify the target file exists (read_file or ls). If missing, report the exact path and STOP.\n"
    + "2. Read the file in full.\n"
    + "3. Extract key insights (bulleted), a one-paragraph summary, and any action items.\n"
    + "4. Report findings as {path, key_insights[], summary}.\n\n"
    + "Use read-only tools only. Do not create files.",
    #{
        label: "researcher:longcat",
        agent_type: "researcher",
        output_schema: notes_schema,
    }
);

if research == () || !research.success || research.output == () || research.output.path == () {
    complete(#{
        summary: "Research agent failed or returned unusable output — role routing not confirmed for longcat.",
        research_agent_id: research.agent_id,
        failed: true,
    });
}

let notes_path = research.output.path;
let insights = research.output.key_insights;
log("Researcher (longcat) read " + notes_path + " and extracted " + insights.len().to_string() + " insights");

phase("Verify");
let verification = agent(
    "You are a Verifier running on DeepSeek-V4-Flash. You are a DIFFERENT model than the "
    + "implementer on purpose (correlated-error protection). Your job: independently verify "
    + "that the research output meets its contract. You verify; you do not repair.\n\n"
    + "GOAL: Check that the notes path reported below exists and the insights are grounded in it.\n\n"
    + "Steps:\n"
    + "1. Confirm the reported path " + notes_path + " actually exists on disk (read_file or ls).\n"
    + "2. Spot-check the notes content: does it actually reflect the source file, or does it look "
    + "fabricated/generic (hallucination red flags)?\n"
    + "3. Report {verified: true} ONLY with concrete evidence you independently inspected. "
    + "Otherwise {verified: false} with the reason.\n\n"
    + "Read-only tools only. Do not edit anything.",
    #{
        label: "verifier:deepseek-v4-flash",
        agent_type: "verifier",
        output_schema: verdict_schema,
    }
);

let verified = verification != () && verification.success
    && verification.output != () && verification.output.verified == true;

log("Verifier (ds-4-flash) verdict: " + (if verified { "PASS" } else { "FAIL" }));
log("Verifier reason: " + (if verification.output != () { verification.output.reason } else { "agent failed" }));

complete(#{
    summary: (if verified {
        "Role routing CONFIRMED: longcat researcher produced notes, ds-4-flash verifier confirmed them."
    } else {
        "Role routing check incomplete: verifier did not confirm. Inspect transcripts."
    }),
    notes_path: notes_path,
    insight_count: insights.len(),
    verified: verified,
    verifier_reason: (if verification.output != () { verification.output.reason } else { "n/a" }),
    research_agent_id: research.agent_id,
    verifier_agent_id: verification.agent_id,
});
