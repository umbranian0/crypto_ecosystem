---
name: grill-with-docs
description: Grill a plan or decision for the Naive-First platform against this repo's own documentation, not just logical consistency. Use when the user says "grill with docs", asks to stress-test a plan against the docs, or when a decision's soundness genuinely depends on what CLAUDE.md/implementation-plan.md/an ADR/a backlog file actually says.
---

The documentation-grounded variant of this project's grilling convention (see the sibling `/grillme` skill and the global `/grilling` skill for the base process — design-tree rounds, numbered questions with a recommended answer, dispatch sub-agents for facts, stop only when the frontier is empty). Use this variant whenever the thing being grilled is a plan, ADR, or ticket whose correctness depends on what this repo's own documents actually say — not general reasoning alone.

## What's different from plain `/grillme`

Before (or as part of) building the design tree, read the documents actually relevant to the plan under review. For the Naive-First platform (crypto_ecosystem) that typically means:

- `CLAUDE.md` (repo root) — the non-negotiable positioning and leakage rules. Any plan that could brush against "no prediction/trading-signal framing" or "preprocessing fit train-fold-only" gets checked against this file's exact wording, not a paraphrase.
- `docs/implementation-plan.md` — module boundaries (section 2), inter-service communication (section 4), the trigger-based build order (section 6), design patterns (section 7), and the DRY/engineering conventions (section 9). A plan that would pull a module forward against an un-fired trigger, or blur a module's "owns/does not own" boundary, needs this cross-check before it's treated as settled.
- The relevant ADR(s) already on record (`docs/adr/`) — check whether the plan under review contradicts, duplicates, or should supersede an existing accepted decision, rather than silently drifting from it.
- The relevant backlog file(s) (`docs/product/backlog-*.md`) and any blocking-decision ticket they reference (e.g. `FHS-001`, `RAV-001`, `MDF-001`/`MDF-002`) — a plan that reopens a question a backlog already answered should say so explicitly, not quietly re-decide it.
- Each touched module's own README "owns / does not own / contract" section, when the plan crosses a service boundary.

## How this changes the interview

Findings from these documents become facts you bring into the design tree the same way a sub-agent's filesystem lookup would — cite the specific file/section, not a vague "per the docs." When a frontier question can be answered by something already written down (not by the user's judgment), answer it yourself from the document and only put the *residual* judgment call to the user — don't make the user re-derive something this repo has already decided and recorded. When the documents are silent or ambiguous on a point the plan depends on, say so explicitly — that's itself a real finding worth a question, not something to paper over with an assumption.

Reserve this variant for when the docs genuinely bear on the decision; for a plan whose soundness is really just internal logical consistency, plain `/grillme` is enough and doesn't need the extra reading pass.
