# Applied Research (Phase 3)

Regime-sensitive models (HMM, hybrids), broader model comparison (boosting, GRU, Transformer), and per-split explainability (SHAP/feature importance) — all tested under the same purged walk-forward protocol against the naive benchmark, never as a standalone claim of predictive edge.

See [../docs/da-tese-ao-produto.md](../docs/da-tese-ao-produto.md) section 1.6.

Status: greenlit (Sprint 33, `docs/sprints/sprint-33.md`) — the user has approved starting this phase,
but no model-class research work has begun. Sprint 33 itself only shipped MR-001 (`docs/tickets/MR-001.md`),
a `services/validation-service` input-validation guardrail, not any code in this directory. MR-002
(engineered feature set) through MR-006 (per-split explainability) remain not started, each pending its
own future sprint; MR-004/MR-005 are additionally blocked on MR-001 already being live, which it now
is. No feature-engineering code, candidate `Baseline` model, or model training exists under `research/`
yet.
