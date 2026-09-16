---
status: accepted
---

# AI-assist model serving: hosted open-weights API for AI-002 (async narrative) and AI-003 (sync chat)
alike; local Ollama Compose service deferred until pilot-scale volume/cost data justifies it; no
`libs/ai_assist` package yet

`docs/product/backlog-ai-integration-ux.md` (AI-001) asks for a documented comparison of at least two
open-source/open-weights LLM serving options against this platform's real constraints (local-first Docker
Compose, CPU-only pilot hosts, a synchronous-request latency budget for some downstream stories but not
others), because AI-002/AI-003/AI-004 each assume a serving pattern that has not yet been chosen or
measured. This is a decision-work spike only, per `docs/sprints/sprint-48.md`'s scope — no feature code,
no new container, no `infra/docker-compose.yml` change, no `libs/ai_assist` scaffolding ships in this
sprint regardless of what this ADR recommends; that is deliberately deferred to the sprint(s) that
implement AI-002/003/004.

**Disclosure on the numbers below**: this spike has no live internet access or benchmarking harness. Every
latency/footprint figure is a **reasoned approximation from well-known public community benchmarks** for
small quantized open-weights models run on CPU (the kind of figures widely reported for llama.cpp-family
inference on consumer/commodity hardware), not a number measured against this platform's own pilot host.
Every figure below is qualified as approximate; none is claimed as empirically measured. A real pilot
measurement (running the actual candidate model against the actual pilot host, timing 20-50 real
~500-token prompts) is called out as required before this recommendation is treated as validated rather
than provisional.

## Options compared

### (a) Local: small quantized open-weights model served via Ollama/llama.cpp, as a new `infra/docker-compose.yml` service

Candidate model class: a ~7-8B-parameter open-weights instruction-tuned model (e.g. the kind of model
commonly distributed in 4-bit/5-bit GGUF quantization for llama.cpp/Ollama — this ADR does not pin an
exact model name/version, since that is an implementation-time choice, not a serving-pattern choice).

- **Approximate latency, ~500-token summarization prompt, CPU-only (no GPU), commodity pilot-host-class
  CPU (4-8 modern cores, no dedicated inference hardware)**: community-reported CPU throughput for a
  7-8B model at 4-bit quantization on this hardware class is commonly in the **single-digit to
  low-double-digit tokens/second range** (roughly 5-15 tok/s is a frequently-cited community figure for
  this model size/quantization/hardware combination). For a ~500-token *output* (a report narrative
  paragraph or chat answer is usually shorter than the 500-token input prompt, but using 500 tokens as the
  approximation basis per the acceptance criterion): **p50 approximately 35-60 seconds, p95 approximately
  70-120 seconds** (accounting for prompt-processing time on top of generation, and variance from other
  containers competing for CPU on the same Compose host). These are wide bands because CPU-only LLM
  inference throughput is highly hardware-dependent; the real number could sit outside this band on either
  side depending on the actual pilot host's CPU.
- **Approximate memory/CPU footprint if local**: a 7-8B model at 4-bit quantization needs roughly
  **4-6 GB of RAM** resident for the model weights plus KV-cache overhead, and will consume most/all
  available CPU cores during generation (CPU-bound, not idle-friendly — a concurrent request queues behind
  the one in flight unless multiple model instances are run, which multiplies the memory cost). On a
  pilot-scale host shared with `validation-service`, `reporting-service`, `dashboard-web`, `gateway-api`,
  Postgres, and Redis, this is a **material** resource claim, not a negligible add-on.
- **Fit against "local-first, cloud-portable, CPU-only pilot host, no GPU required"**: technically fits
  (no GPU required, runs in a Compose service, portable to a cloud host the same way every other service
  is) but at a **real latency and resource cost** that must be weighed against the request path it serves.
  A 35-120 second wait is incompatible with any request currently expecting sub-second-to-low-second
  response, and the memory footprint is a nontrivial fraction of what a modest pilot host provides
  alongside the existing stack.

### (b) Hosted-but-open-weights inference API over HTTPS (OpenAI-compatible endpoint pointed at an open-weights model)

A hosted API serving the same class of open-weights model (or a larger one) on provider-managed GPU
infrastructure, called over HTTPS the same way any other external HTTP dependency this platform already
calls (e.g. exchange/on-chain/sentiment connectors in `ingestion-service`) is called.

- **Approximate latency, ~500-token summarization prompt**: hosted GPU-backed inference for this model
  class is commonly reported in the community at roughly **1-3 seconds p50, 3-6 seconds p95** for a
  several-hundred-token generation (network round-trip plus provider queueing included), an order of
  magnitude faster than local CPU inference because the provider runs on GPU hardware this platform does
  not need to own or operate.
- **Approximate memory/CPU footprint if local**: **effectively none** — no model weights resident on the
  pilot host, no dedicated CPU claim beyond a thin HTTP client, matching the resource profile of every
  other external connector this platform already runs.
- **Fit against "local-first, cloud-portable, CPU-only pilot host, no GPU required"**: fits the "no GPU
  required" and "CPU-only pilot host" constraints trivially, since no inference runs on the pilot host at
  all. It is a partial departure from "local-first" in the narrow sense that the model call itself leaves
  the local deployment boundary — but this platform already accepts exactly this shape of dependency for
  every existing external data connector (`ingestion-service`'s exchange/sentiment/on-chain connectors are
  all outbound HTTPS calls to third-party services, not locally-hosted infrastructure), and "open-weights"
  is preserved (the model itself is not a closed proprietary model, only its *hosting* is external) —
  consistent with this backlog's own framing of "open-source AI integration" as being about the model's
  weights/licensing, not mandating that every component physically runs inside the pilot's own Compose
  network. Tenant-data exposure is the real cost here, not deployment-locality: sending a tenant's
  `split_results` numbers to a third-party API is a data-boundary decision, not a "local-first" purity
  question — flagged explicitly as something AI-002/AI-003's future tickets must address (e.g. only
  aggregate metrics leave the boundary, never raw tenant-uploaded prediction files), not resolved by this
  ADR.

## Comparison table

| | (a) Local Ollama/llama.cpp | (b) Hosted open-weights API |
|---|---|---|
| p50 latency, ~500-token prompt | ~35-60s (approx.) | ~1-3s (approx.) |
| p95 latency, ~500-token prompt | ~70-120s (approx.) | ~3-6s (approx.) |
| Local memory footprint | ~4-6 GB RAM + most CPU cores while generating | negligible (thin HTTP client) |
| No-GPU-required constraint | satisfied | satisfied (GPU cost is the provider's, not ours) |
| Local-first (strict) | satisfied | partial — model call leaves the deployment boundary, same shape as existing external data connectors |
| New operational surface | new Compose service, model artifact, host resource contention | new outbound HTTPS dependency + API key management (mirrors existing connector pattern) |
| Tenant-data exposure | none (fully local) | tenant-derived text leaves the network — must be scoped to aggregate/already-public-within-tenant metrics only |

## Recommendation

**Use the hosted open-weights API for both AI-002 and AI-003; do not stand up the local Ollama/llama.cpp
Compose service this sprint or the next.** Justification against each story's actual latency need:

- **AI-002 (report narrative generation)** is triggered off `reporting-service`'s existing `run.completed`
  Redis Streams subscriber (RS-006, already implemented per `services/reporting-service/README.md`) — an
  async, background-friendly point in the pipeline with no live user waiting on the call. This is the
  story where local CPU inference's 35-120 second latency would be *tolerable* in isolation (nothing is
  blocked on it). But the **memory/CPU contention cost is still paid on every run**, competing with
  `validation-service`'s own CPU-bound walk-forward computation on the same pilot host, and the hosted
  API's sub-6-second p95 costs almost nothing in exchange for removing that contention. Recommendation:
  hosted API even for the async case, because the local option's only advantage (tolerable latency) is not
  actually a scarce resource here — throughput/footprint is the real cost, and the hosted API removes it
  for a small per-call cost instead.
- **AI-003 (Q&A chat, synchronous, tighter budget)** has a request path with an actual human waiting on a
  dashboard page. A 35-120 second local CPU response is not a "should we optimize this later" gap — it is
  a **disqualifying** latency for a synchronous chat turn (no realistic UX tolerates a full-minute-plus
  wait per message with the page apparently hung, and dashboard-web's existing routes have no
  streaming/long-poll infrastructure to soften this today). The hosted API's ~1-3s p50 is inside a
  plausible synchronous-request budget the way local inference is not. Recommendation: hosted API is not
  just preferred but **required** for AI-003 given local CPU inference's approximate latency band.

Because both stories land on the same option, there is **no split recommendation** and no need to build
two different serving integrations for AI-002 vs. AI-003 — this simplifies the `libs/ai_assist` question
below rather than complicating it.

**This is a clear recommendation, not a "needs user decision, no default" case.** The local option is not
comparably viable for either story once the CPU-only latency band is accounted for: it costs meaningfully
more (host resource contention) while buying nothing AI-002 needs (async tolerance was never the
bottleneck) and disqualifying itself outright for AI-003. If a future pilot measurement shows this
platform's actual host CPU is materially faster than the community-reported band assumed here, or if
per-call hosted-API cost becomes a real constraint at higher usage volume, that would be grounds to revisit
local serving for AI-002 specifically (its async nature is the only story where local's footprint cost
could ever be worth paying) — flagged as a **revisit trigger**, not a currently-open tie.

## `libs/ai_assist` question — binding answer for AI-002/AI-003/AI-004 ticket scoping

**No new `libs/ai_assist` package is created now. Prompt-building/model-calling logic stays inline in
`reporting-service` when AI-002 is built, per implementation-plan.md section 9's "extract on second
duplication" rule** (`docs/implementation-plan.md` line 159: "if two services seem to need the same logic,
that logic belongs in a lib, not copy-pasted") **and the backlog's own scope decision #1**
(`docs/product/backlog-ai-integration-ux.md` lines 21-29), which already anticipated this exact question
and named the trigger as "a second module ends up needing the same LLM-calling logic."

At the time this ADR is written, only `reporting-service` (AI-002) has an approved, in-scope story that
would call a hosted LLM API. `dashboard-web` (AI-003, AI-004) are both still "Should"/"Could" and not yet
scoped into a sprint. The duplication trigger — a second *module* needing the same prompt-building/
model-calling logic — is **not yet met**, because there is only one module with a real call site so far.

Concretely, this means AI-002's implementation ticket should build its hosted-API client and prompt
template inside `services/reporting-service/src/app/narrative/` (per the backlog's own suggested
location), not in a new shared lib. **When AI-003's ticket is scoped** (next sprint or later, per
sprint-48.md's sequencing), the Tech Lead building that ticket must check whether `reporting-service`'s
AI-002 client code is now needed unchanged by `dashboard-web` — if so, *that* is the second-duplication
trigger, and the extraction into `libs/ai_assist` happens as part of AI-003's ticket (or as a dedicated
refactor ticket immediately before it), not preemptively here. This ADR's answer is binding on that future
ticket: **do not re-litigate whether to build `libs/ai_assist` from scratch; the trigger condition is
already defined, only its truth value changes.**

Design note for that future extraction (non-binding, forward-looking only): if/when `libs/ai_assist` is
created, the model-calling client should be wrapped behind an Adapter (implementation-plan.md section 7)
so `reporting-service` and `dashboard-web` share one call surface (`generate(prompt, context) -> text`)
regardless of which HTTP provider backs it — this keeps the hosted-vs-local decision swappable without
touching call sites, consistent with how this platform already isolates other external dependencies
(`DatasetSource` implementations for ingestion connectors are the existing precedent for this shape). This
is not built in this sprint or the next; it is documented here so the eventual extraction does not have to
re-derive the pattern choice from scratch.

## Safe vs. unsafe synchronous extension points

**Unsafe — must never gain an inline synchronous LLM call:**

- `GET /runs/{id}` (`gateway-api` and `validation-service`) — a hot-path read with callers (including
  `dashboard-web`'s run-detail page and any polling client) that expect fast, bounded response time; no
  latency budget exists for a ~1-6 second (hosted) or ~35-120 second (local) model round-trip on every
  read.
- `GET /runs`, `GET /runs/{id}/splits`, `GET /runs/trend` — same reasoning; all are existing list/detail
  reads with no latency budget carved out for a model call, and none of AI-002/003/004's acceptance
  criteria ask for a model call on any of these routes (AI-003 explicitly calls these routes to *retrieve*
  data, then makes exactly one separate model call after retrieval — the retrieval calls themselves stay
  LLM-free).
- Any route inside `validation-service`'s `POST /runs` run-submission path — this is the leakage-sensitive
  protocol execution path (`generate_splits`/DM test); no story in this backlog touches it, and this ADR
  confirms it should stay that way — an LLM call has no legitimate reason to sit inside run computation.

**Safe extension points:**

- `reporting-service`'s existing `run.completed` Redis Streams subscriber (RS-006, Observer pattern,
  already implemented) — AI-002's narrative generation call belongs here, after the report's table/metrics
  are already rendered, fully async/background, no live request waiting on it. This is the extension point
  AI-002's future ticket should target.
- A **new, dedicated** `dashboard-web` route for AI-003's chat turn (e.g.
  `POST /assistant/ask`, per the backlog's own suggested `src/app/routers/assistant.py` module) — a
  purpose-built synchronous endpoint whose entire contract is "make one model call and return," not an
  existing route retrofitted with a call it wasn't budgeted for. This route's own latency budget is set by
  its purpose (a chat UI can show a loading state for a few seconds; a list/detail page cannot).
- AI-004's conversational form-assist helper, if built, likewise needs its own new endpoint (not a change
  to the existing `POST /runs` submission path DASH-006 uses) — the backlog's own AI-004 acceptance
  criteria already require this (reuses DASH-006's single `RunRequest` construction site, never a second
  submission path), and this ADR reinforces it from the serving-latency side: the model call that drives
  the conversational helper must sit on its own request, never fused into the actual run-submission call.

## Consequence for future readers

- AI-002's implementation ticket should scope a hosted-API client living in `services/reporting-service/`,
  called from the existing `run.completed` subscriber, with the versioned prompt template the backlog's
  own acceptance criteria require — not a new Compose service, not `libs/ai_assist`.
- AI-003's implementation ticket should scope a hosted-API client living in `services/dashboard-web/`
  behind a new dedicated route, and must re-evaluate the `libs/ai_assist` extraction trigger against
  AI-002's actual shipped code at that time (this ADR predicts, but does not guarantee, that the trigger
  will be met then).
- AI-004, if scoped, follows the same hosted-API-over-a-dedicated-route pattern.
- If a future sprint's real pilot measurement (see disclosure above) shows this platform's actual host CPU
  materially outperforms the community-reported approximation band used here, or hosted-API per-call cost
  becomes a binding constraint at scale, the local-Ollama option should be re-evaluated for AI-002
  specifically (never for AI-003/AI-004's synchronous paths, per the disqualifying-latency reasoning
  above) — this is the one condition under which this ADR's recommendation should be revisited rather than
  treated as settled.
- No `infra/docker-compose.yml`, `Dockerfile`, or `libs/ai_assist` file is created by this ADR or this
  sprint — this document is the recommendation, not the implementation; per sprint-48.md, acting on it is
  explicitly deferred to the sprint(s) that scope AI-002/003/004.
