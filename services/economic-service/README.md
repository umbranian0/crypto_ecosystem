# economic-service

**Status: deferred (trigger #11 — only create once a specific client model has already demonstrated stable outperformance in `validation-service`. Never build or wire this up before that, per the ethical boundary in [../../docs/da-tese-ao-produto.md](../../docs/da-tese-ao-produto.md) section 2.7.)**

Formerly `economic-module/`. See [../../docs/solution-design.md](../../docs/solution-design.md) and [../../docs/da-tese-ao-produto.md](../../docs/da-tese-ao-produto.md) sections 2.3.5, 2.6 (phase 4).

**Will own** (once built): the `economic` Postgres schema, transaction-cost/slippage/turnover modeling, realistic portfolio simulation — applied only to models that already passed `validation-service`.

**Will not own**: any statistical validation logic — this is strictly a post-validation add-on, and its absence must be visible in every `reporting-service` report until it exists (see the mandatory disclaimer in the `naive-first-audit` skill).
