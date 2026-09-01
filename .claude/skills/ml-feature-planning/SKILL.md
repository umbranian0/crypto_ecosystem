---
name: ml-feature-planning
description: Sequences design-then-test-then-review for ML/data-pipeline feature work in this repo -- clarify edge cases and leakage risks first, then implement test-first, then review. Trigger when starting a new feature-engineering step, model adapter, or data transformation module.
---

# ML Feature Planning

A thin sequencing skill for ML/data-pipeline feature work specifically -- it doesn't redefine what `/grilling`, `/tdd`, or `/code-review` already do, it orders them for this kind of work and calls out the ML-specific edge cases each stage should surface.

1. **Design first, via `/grilling`.** Before writing any transformation or model-adapter code, work the design tree: what's the input shape, what happens on an empty/degenerate input, does this step need to be fit per-split (see `/ml-engineer` rule 1), and where does the seam for testing it live. Don't skip this because the code "looks small" -- leakage bugs are almost always introduced by a step that looked too small to warrant a real design pass.

2. **Implement test-first, via `/tdd`.** One seam, one test, one minimal implementation per cycle, per that skill's rules. Apply `/ml-engineer`'s testing rule (shape/values test plus degenerate-input test per transformation step) at each seam.

3. **Review, via `/code-review`.** Before merging, confirm: no `.fit()`/`fit_transform()` call reaches data from outside the current split; no bare `dict` crosses an API boundary where a Pydantic model belongs; any new model-serving endpoint follows `/mlops-deployment`'s health-check/logging/fallback conventions; nothing in code, docstrings, or API descriptions implies a live prediction/trading capability (CLAUDE.md's positioning section).
