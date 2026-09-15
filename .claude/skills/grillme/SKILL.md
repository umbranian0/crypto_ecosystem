---
name: grillme
description: Grill the user relentlessly about a plan, decision, or idea for the Naive-First platform. Use when the user wants to stress-test their thinking, says "grill me"/"grill this", or wants a decision pressure-tested before it's treated as settled.
---

This is the project-scoped alias for this session's standing "use grilling proactively" convention on the Naive-First platform (crypto_ecosystem). It follows the same process as the global `grilling` skill — use that skill's full methodology (design-tree rounds, numbered questions with a recommended answer, dispatch sub-agents for facts rather than asking the user, stop only when the frontier is empty) verbatim.

## When this gets invoked on this project

Reach for `/grillme` (or the global `/grilling`) before treating any of the following as settled, not just when explicitly asked:

- An ADR or architecture decision, especially anything touching `libs/naive_first_engine` (this platform's core IP — see `CLAUDE.md`'s leakage-safety rules) or a leakage/positioning-sensitive area.
- A blocking-decision ticket in this repo's established pattern (`FHS-001`, `RAV-001`, `MDF-001`/`MDF-002`, and future ones like them).
- A new sprint's scope call, especially one that could quietly expand past what the user actually asked for (this project's standing "keep it simple, don't over-engineer" instruction).
- Any plan that would touch `naive_first_engine`'s leakage-safety guarantees, the mandatory naive-baseline comparison, or the DM-test/Harvey-correction requirement.

## Relationship to this project's own process

This complements, not replaces, the existing QA gate (`/qa-validation`, mandatory before a sprint's production sign-off) and the Tech Lead's own review step. Grilling is upstream — on the decision or plan itself, before implementation work is dispatched to a `dev`/`tech-lead` agent. See `/grill-with-docs` (this project's sibling skill) for the variant that checks a plan against this repo's own documentation as part of the interview, not just logical consistency.
