---
name: qa-validation
description: Independent pre-production validation pass for a completed sprint or ticket set on the Naive-First platform — verifies acceptance criteria against actual behavior, runs/extends test suites, and checks positioning-rule compliance before sign-off. Trigger when a sprint/ticket set is reported done and needs QA validation before it's considered production-ready, or when the user asks to "QA this", "validate before production", or "find bugs before we ship".
---

# QA Validation

This skill is the process the `qa` agent (and anyone standing in for it) follows to independently verify work a dev squad has already reported as "done," before it's treated as production-ready. It exists because a subagent's or Tech Lead's completion report describes what they *intended* to do — verification of what actually happened is a separate, deliberate step, not a formality.

## When to use this

- A Tech Lead's dev squad has finished a sprint/ticket set and reported it done.
- The user asks to validate, test, or find bugs in recently completed work before production.
- Before merging/deploying a batch of tickets that touch shared or risky surfaces (lifecycle state machines, anything computing leakage-sensitive statistics, anything rendering a number to an end user).

Not a substitute for `/code-review` (style/spec review of a diff) or `/tdd` (test-first development while building) — this is post-hoc, independent, behavior-focused verification of already-claimed-complete work. Running it doesn't require the `qa` agent specifically; the same discipline applies if you're doing this pass directly.

## Process

1. **Rebuild the checklist from source, not from the summary.** Pull acceptance criteria straight from the ticket files and sprint plan — never from the Tech Lead's or dev agent's prose report of what they did. Treat any claim ("tests pass," "criterion met") as unverified until you've reproduced it yourself.

2. **Verify by running things, not reading about them.** Execute the actual test suites (`pytest`, whatever this repo/module uses) and read the real output. Read the actual diff (`git diff`/`git log`) rather than trusting a stated file list.

3. **Map every acceptance criterion to a concrete check.** For each one: an existing passing test, a new test you write to cover it, or an explicit manual trace with reasoning — never leave a criterion "probably fine."

4. **Close test gaps you find, don't just log them.** If a criterion has no automated coverage, write the test. Only skip this when doing so needs scope beyond what's reasonable for a QA pass (e.g. a new fixture/service stand-up) — then flag it explicitly as an open gap, not a pass.

5. **Actively hunt platform-specific failure modes**, not just the ticket's literal words:
   - **Leakage-shaped bugs**: train-only preprocessing actually enforced per split, purge gap actually respected, nothing fit globally. This is this platform's single most important correctness property (see `CLAUDE.md`) and the easiest thing for a rushed ticket to silently violate.
   - **Positioning-rule breaches**: any surfaced number implying a trading signal or forward prediction without the naive baseline and DM verdict/honesty caveat immediately adjacent; any copy implying certainty a naive-first result doesn't support.
   - **Boundary/edge cases**: empty datasets, minimum/maximum configured values (e.g. horizon bounds), cancelled/failed lifecycle states, concurrent access if the sprint touches anything stateful.
   - **Regressions in adjacent modules**: run tests for consumers of what changed, not only the changed module itself. If a thesis-numbers regression check exists for `naive_first_engine`, run it — a sprint must never silently drift those numbers.

6. **Report evidence, not vibes.** Every pass/fail claim in the final report must cite the actual command run and its actual result. Bugs get filed with: file/line, concrete failing scenario (input/state → wrong output), which acceptance criterion or rule it violates, and severity.

7. **Don't fix production logic yourself.** Trivial fixes to your own new test code are fine; anything touching shipped behavior goes back to the Tech Lead for a dev agent to fix, then gets re-verified by you — QA doesn't quietly patch around what it finds.

8. **End with an explicit go/no-go**, not just a list of findings. If everything genuinely passes, say so plainly rather than manufacturing findings to look thorough — a clean report is a valid, useful outcome.
