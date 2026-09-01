---
name: mlops-deployment
description: Guides serving a trained model or validation pipeline as a production API -- inference optimization, request batching, prediction caching, serialization, health checks, logging, and fallback behavior. Trigger when wrapping model/pipeline code in a FastAPI service or preparing it for real traffic.
---

# MLOps & Production Deployment

Applies when turning model or pipeline code into something a service serves over HTTP -- not training/research scripts (see `/ml-engineer` for that side). This repo already has four services built this way (`gateway-api`, `validation-service`, `reporting-service`, `ingestion-service`) -- match their established patterns instead of inventing new ones.

## Before writing the endpoint

- **Health checks**: every service exposes `GET /health`, and `gateway-api` additionally aggregates all of them at `GET /system/health` (`GW-022`). A new service or endpoint extends that pattern, it doesn't invent a second health-check shape.
- **Structured logging**: use `naive_first_common.logging`'s `configure_structured_logging()` plus its correlation-id middleware, not a bespoke logger. Every request should be traceable across services by the same `correlation_id` (`OPS-006`).
- **Input schema validation**: validate every request body with Pydantic at the route boundary, reusing a `naive_first_common.contracts` shape where one already exists. Reject malformed input before it reaches model/pipeline code -- never let a `KeyError`/`AttributeError` from bad input surface as a raw `500`.

## Serving considerations

- **Serialization**: if a model needs to persist between training and serving, prefer a format inference code can load without re-executing arbitrary training code (`joblib`/`onnx` over raw `pickle` of a live object graph where avoidable). Record the exact library version that produced the artifact -- these formats silently break across major version bumps.
- **Caching predictions**: only add a cache when the same input genuinely recurs and the model is expensive relative to a lookup -- don't add one speculatively. Cache keys must include every input that affects the output, including model/feature-pipeline version, or a stale cache silently serves wrong results after a retrain.
- **Request batching**: only worth adding once a real latency/throughput number justifies it -- implement the naive per-request path first, prove it's too slow, then batch.
- **Fallback behavior**: match this repo's existing downstream-failure convention (`_call_downstream`/`_raise_for_error`, used in `gateway-api`/`validation-service`/`dashboard-web`'s routers) -- a transport failure or timeout translates to a `502`/`504` with a generic message, never a stack trace, and never a silent fallback to a fabricated prediction.

## Non-negotiable for this codebase

Never wrap a model as a "prediction API" that a client or the dashboard calls to get a forecast to act on. Every model-serving endpoint here exists to be *audited* (fed through `naive_first_engine`'s walk-forward/DM-test protocol), not to serve live predictions for trading or investment decisions -- see CLAUDE.md's positioning section and `docs/adr/0002-declined-automated-trading-product.md` for why this line is drawn deliberately, not casually.
