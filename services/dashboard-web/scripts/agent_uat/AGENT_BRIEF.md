# Agent tester brief

Hand this file to the agent that reviews an `agent_uat` evidence run. It is the "what to look
for" half of the tool -- `run_scenario.py` only captures evidence; this brief is what turns that
evidence into findings.

## Your job

You are acting as a first-time user of the Naive-First platform, reviewing a captured walkthrough.
You did not drive the browser yourself -- a script did, and it left you an evidence directory.
Read the evidence, then report what a real user would have hit.

You are **not** fixing anything. You file findings; the Tech Lead decides what becomes a ticket.

## Inputs

An evidence directory (`scripts/agent_uat/evidence/<timestamp>-<scenario>/`) containing, per step:

- `<step>.png` -- screenshot. **Read these as images.** This is the main signal for usability.
- `<step>.html` -- the rendered HTML for that step, for checking exact copy/markup.
- `<step>.api.json` -- the raw `gateway-api` response for steps with a `verify_against` (only some).
- `manifest.json` -- every step's URL, artifact paths, and `field_diffs`.

Start with `manifest.json`, then read every screenshot in step order so you experience the flow as
a user would.

## What to look for

**1. Accuracy (highest severity).** `manifest.json`'s `field_diffs` lists any value the API
returned that does **not** appear in the rendered HTML. A non-empty `field_diffs` means the UI may
be showing something different from what the system actually computed -- report every one. Also
check by eye: do the numbers in the screenshot match `<step>.api.json`? The mechanical check only
catches absence, not a value rendered against the wrong label (e.g. the naive baseline's MAE shown
in the model's column).

A `verify_error` in the manifest means the cross-check could not run at all -- report that as a gap
in the evidence, not as a pass.

**2. Positioning violations (highest severity -- non-negotiable per CLAUDE.md).** This product is
validation/audit infrastructure, **not** a prediction or trading-signal product. Flag any rendered
copy that implies the system predicts prices, generates signals, or recommends trades. Watch for
"prediction", "forecast", "signal", "recommendation", "alpha", "profit", "return you can expect".
"Validation results", "benchmark comparison", "per-split metrics" are the correct vocabulary. Note
that `forecast horizon` is legitimate domain terminology for the horizon parameter -- judge by
whether the copy claims predictive *value*, not by keyword alone.

**3. Honesty of negative results.** Most runs will show the naive baseline winning -- that is the
expected, honest outcome, not a failure. Check that a "model did not beat Naive0" result is
presented as a legitimate finding, not styled or worded like an error/problem. Also check that any
run submitted without a client model is clearly disclosed as using a placeholder rather than
presented as a real model result.

**4. Broken or dead-end flows.** A step whose screenshot shows an error page, an empty state where
data was expected, or a form that silently discarded input. Note that `run_scenario.py` does not
fail a step when an element is missing -- it screenshots and moves on -- so a missing button shows
up as "the page looks unchanged between step N and N+1". Compare consecutive screenshots.

**5. Usability and comprehension.** Would a non-quant compliance buyer understand this page? Flag
unexplained jargon, numbers with no unit or context, missing explanation of what a DM p-value
means, controls whose effect is unclear, and anything that needs the docs open to interpret.

**6. Accessibility.** This codebase has standing conventions: every `data-tooltip` element carries a
matching `aria-label` (DASH-127), and `base.html` opens with a skip-to-main-content link (UAT-012).
Check the HTML for tooltips missing their `aria-label` pair, images missing alt text, and form
inputs missing an associated `<label>`.

## What to report

Findings only, most severe first. For each one:

- **Where**: the step name and route (from `manifest.json`), plus the screenshot filename.
- **What**: one sentence stating the defect.
- **Why it matters**: the concrete user consequence, not a restatement.
- **Severity**: accuracy/positioning violations first, then broken flows, then usability, then
  accessibility.

Report an empty list if you genuinely found nothing -- do not pad it. Do not report the absence of
a feature that was never in scope for the scenario you reviewed, and do not speculate about code
you did not read: your evidence is the screenshots, HTML, and JSON, nothing else.

## What is out of scope for you

- Whether the underlying validation math is correct -- that is `naive_first_engine`'s own test
  suite's job. You are checking that the UI honestly renders what the API returned.
- Anything requiring you to run the stack, edit code, or open a browser yourself.
