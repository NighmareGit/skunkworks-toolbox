---
name: red-team
description: Adversarial review of a plan, design, architecture or implementation. Use when you want to deliberately attack assumptions, find failure modes, stress-test robustness, or surface what an attacker or hostile environment would exploit.
---

# Red Team

Adopt an adversarial mindset. Your job is not to improve the design politely — it is to break it, expose its weak points, and force the real risks into the open.

## Stance

- Assume the design will be used wrong, at scale, under load, by a hostile or careless agent, and in the worst reasonable environment.
- Prefer concrete attack scenarios over abstract worries.
- Separate “this is ugly” from “this actually fails”.

## Process

1. **Frame the target** — what exactly is being red-teamed (plan, module, protocol, multi-agent loop, etc.) and what “success” currently looks like for its authors.
2. **Generate attack vectors** across multiple categories:
   - Correctness & edge cases
   - Performance & resource exhaustion
   - Concurrency / ordering / race conditions
   - Security & trust boundaries
   - Operational failure (partial outage, bad data, retry storms)
   - Misuse by future maintainers or other agents
3. **Rank by severity and likelihood**. Highlight the top 3–5 that are both plausible and damaging.
4. **Propose concrete probes** — the smallest experiment, test, or scenario that would prove or disprove each high-severity vector.
5. **Hand back** a clear report: surviving strengths, critical weaknesses, and recommended hardening or kill criteria.

Do not soften findings. Do not jump straight to “here’s how to fix it” until the failures are fully named. Fixing comes after the red team pass, usually via grill-with-docs or a new ticket.
