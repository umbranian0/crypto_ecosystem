# ARCH-007 — Protocol-agnostic service-identification convention

**Status: done**

## Analysis
Story: ARCH-007 (Should, `docs/product/backlog-technical-upgrades.md`), no dependency. Deferred
since Sprint 06 (added 2026-08-09), re-confirmed unchanged in Sprints 07/08/09 ("codebase shape
hasn't grown," still true today -- one router, one auth dependency, confirmed by the Tech Lead this
sprint). Constraining evidence (backlog, cited directly): `services/gateway-api/src/app/main.py`'s
`app.include_router(runs.router, tags=["validation-service"])` is currently the only place a
downstream-service identifier is attached to an API surface, and it is REST/OpenAPI-tag-specific --
no written convention exists for the gRPC or GraphQL equivalent. This is a pure documentation ticket
-- **zero code changes**, per the backlog's own acceptance criteria (a "short service identification
convention," documented, not implemented against a protocol that doesn't exist yet).

## Design
No design pattern applies -- this documents an existing pattern's naming convention, it does not
introduce a new one. File(s) touched: `services/gateway-api/README.md` (preferred location, since
the one real instance -- `tags=["validation-service"]` -- lives in this service) and/or
`docs/implementation-plan.md` section 9 (dev agent's call on which, or both, per the backlog's own
"e.g." wording -- if both, keep `implementation-plan.md`'s copy short and point at the README for
detail, not duplicate the full convention in two places, per this repo's own DRY convention for
documentation).

DRY check: grep `services/gateway-api/README.md` for any existing "service identification" or
tagging discussion -- none exists (the README's own routing section documents *what* `runs.router`
does, not the naming convention behind its `tags=` value). No existing convention doc to extend;
this is new content.

**Convention shape (per the backlog's own three-part structure)**: (1) REST: every router is tagged
with the backing downstream service's name via `tags=["<service-name>"]` (confirmed existing
instance: `runs.router` tagged `"validation-service"`); (2) gRPC (future, not yet built): the
downstream service's name should appear in the `.proto` package/service naming (e.g. a
`validation_service.v1` package or a service method namespaced consistently with the REST tag), so
a reader can map a gRPC service name to the same backing service a REST tag would name; (3) GraphQL
(future, not yet built): the downstream service's name should appear as a schema-stitching
namespace/type prefix consistent with the same naming, so multiple downstream services' types don't
collide in one unified schema. The dev agent should write this concretely enough to be followed
later, but must not invent gRPC/GraphQL code that doesn't exist -- this is a naming-convention
statement, not a scaffold.

## Implementation acceptance criteria
- [x] A "service identification" convention section exists (in `services/gateway-api/README.md`
  and/or `docs/implementation-plan.md` section 9), documenting the REST tagging rule
  (`tags=["<service-name>"]`) plus the gRPC and GraphQL equivalents, written down now while cheap
  and REST-only per the backlog's own rationale.
- [x] The existing `runs.router` tag (`"validation-service"`) is explicitly confirmed in the new
  section as the first real instance of this convention, not a one-off exception.
- [x] A note for the Tech Lead (not the dev agent) is included stating that any future router added
  to `gateway-api` follows the same tagging rule as part of its own ticket's acceptance criteria --
  this is process guidance, not code.
- [x] Zero files under `services/gateway-api/src/` are modified by this ticket -- confirmed via
  `git status` scoped to that path after the ticket is done (the existing `tags=["validation-service"]`
  code is cited as evidence, not changed).

## Test acceptance criteria
- [x] None apply -- pure documentation, no code path to test. State this explicitly in the ticket's
  Outcome rather than fabricating a test.

## Review acceptance criteria
- Tech Lead personally confirms: (a) the convention text actually covers all three protocols (REST
  written as fact, gRPC/GraphQL written as forward-looking rules, not left implicit); (b) `git
  status` scoped to `services/gateway-api/src/` shows zero changes; (c) the section doesn't
  contradict `docs/implementation-plan.md` section 4's "not using gRPC/GraphQL yet -- unjustified
  complexity at pilot scale" stance -- this ticket documents a *naming convention for if/when* those
  protocols are added, it does not propose adding them now.

## Documentation acceptance criteria
- [x] `services/gateway-api/README.md` (and/or `docs/implementation-plan.md` section 9, per the
  dev agent's placement choice, documented with rationale) carries the new convention section.
- [x] `docs/tickets/README.md`'s `services/gateway-api (GW-*)` section (or a shared ARCH-* note
  alongside the existing Sprint 06 ARCH-* subsection under `libs/common (LC-*)`) gains an
  `ARCH-007` row under a new "Sprint 10" entry, status `done` once verified.

## Outcome (dev agent, pending Tech Lead verification)

Pure documentation ticket, zero code changes. `services/gateway-api/README.md` gained a new
"Service identification convention (ARCH-007)" section (placed after the "Data model" section,
before "CI") covering all three protocols: REST as fact (citing the real `runs.router`
`tags=["validation-service"]` instance as the first real instance, not a one-off), gRPC as a
forward-looking `.proto` package/service naming rule, and GraphQL as a forward-looking
schema-stitching type-prefix rule -- neither gRPC nor GraphQL is implied to exist or to be getting
built now, consistent with `docs/implementation-plan.md` section 4's "explicitly not using
Kafka/RabbitMQ/gRPC yet" stance. A short, non-duplicative pointer was also added to
`docs/implementation-plan.md` section 9 (one bullet, linking back to the README for the full
convention text) so the engineering-conventions section doesn't go silent on this topic -- kept
short per this repo's own DRY-for-documentation rule, full detail lives in exactly one place (the
README, since that's where the one real REST instance lives).

A Tech-Lead-facing process note is included in the new README section: any future router added to
`gateway-api` must carry `tags=["<service-name>"]` per this convention as part of that router's own
ticket's acceptance criteria.

`git status` scoped to `services/gateway-api/src/` shows zero changes from this ticket -- confirmed
by the dev agent before finishing (see below).

**Test acceptance criteria**: none apply. This is pure documentation with no code path to test, per
the ticket's own Design section -- no test was fabricated to satisfy this section.

**Deliberately left undone by this ticket, per explicit instruction**: `docs/tickets/README.md`'s
ticket-index tables are NOT updated by this ticket (no new "Sprint 10" row for ARCH-007 added yet).
ARCH-008 is being delegated immediately after this ticket and also touches
`docs/tickets/README.md`/`services/gateway-api/README.md` -- the two ticket-index rows (ARCH-007 and
ARCH-008) should be added together in one pass after both tickets finish, to avoid two agents racing
edits to the same index file. Status is set to `in-review`, not `done` -- the Tech Lead marks `done`
after independently verifying the three review criteria (protocol coverage completeness, `git
status` scope, no contradiction with implementation-plan.md section 4).

## Tech Lead review (verified independently, not trusted from the dev agent's report)

(a) Protocol coverage confirmed complete: services/gateway-api/README.md's new "Service
identification convention (ARCH-007)" section (read directly) documents REST as fact (citing the
real tags=["validation-service"] instance), gRPC as a forward-looking .proto
package/service-naming rule, and GraphQL as a forward-looking schema-stitching type-prefix rule --
none is left implicit. docs/implementation-plan.md section 9 gained a short, non-duplicative
pointer bullet linking back to the README for the full text, consistent with this repo's
DRY-for-documentation convention.

(b) git status --porcelain -- services/gateway-api/src/ re-run directly by the Tech Lead: shows
auth.py, dependencies/repositories.py, main.py, postgres_repository.py as modified -- but
these are the exact same pre-existing, unrelated-session modifications present in git status
before this sprint began (confirmed against the session's starting git status snapshot), not
changes introduced by ARCH-007. No new modification to any src/ file was introduced by this
ticket.

(c) No contradiction with docs/implementation-plan.md section 4's "explicitly not using
Kafka/RabbitMQ/gRPC yet -- unjustified complexity at pilot scale" stance confirmed by direct
re-read: the new section explicitly frames gRPC/GraphQL as "future, not built" naming rules for
if/when either is introduced, not a proposal to add them now.

Ticket-index row deliberately not yet added here, per this ticket's own note -- added together
with ARCH-008's row in one pass once both are done (see docs/tickets/README.md).