---
name: fireplace
description: Multi-perspective brainstorming that deliberately looks at a problem from several different frames before converging. Use when a problem feels stuck, one-dimensional, or needs richer options than the current framing allows.
---

# Fireplace

Sit with the problem and turn it over. Generate divergent views first; only then converge.

## Core rule

Do **not** jump to a solution. The goal is better frames and better options, not the first clever answer.

## Process

1. **Name the problem** in one or two sentences as currently understood.
2. **Rotate through perspectives** (use as many as useful):
   - User / beneficiary
   - Implementer / future maintainer
   - Operator / on-call
   - Adversary / red-team
   - Simplicity maximalist
   - Performance / scale maximalist
   - Constraint play (what if budget, time, or tech was radically different)
   - Reverse (how could this fail spectacularly, then invert)
   - Analogy from another domain
3. For each useful perspective, generate 2–4 distinct observations or options. Keep them short and concrete.
4. **Cluster and contrast** — show where the perspectives agree, where they violently disagree, and which tensions are load-bearing.
5. **Converge lightly** — surface the 2–4 most interesting directions that survived the multi-vector look. Do not force a single winner unless the user asks for one.
6. Hand the richest options back for grilling, red-teaming, or wayfinding.

This skill is divergent by design. It pairs well with `grill-with-docs` (after) and `red-team` (on the surviving options).
