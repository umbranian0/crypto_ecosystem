---
status: accepted
---

# Modules are being built ahead of their documented triggers, but only via a disclosed-override pattern

`implementation-plan.md` section 6 sequences module build order by concrete triggers, not a calendar — e.g. `gateway-api` waits for "the first pilot client," `dashboard-web` waits for a second pilot client or someone asking "where do I log in." By the time of this decision, five modules (`gateway-api`, `ingestion-service`'s connectors, `dashboard-web`, `reporting-service`, `economic-service`) had been built ahead of their own trigger firing, all at explicit user request, none because a real pilot client actually exists. We formalized this as a repeatable pattern rather than treating each override as a one-off exception: every override must be disclosed consistently in four places — the backlog file's own override note, the sprint file's pre-planning checks, the module's README status line, and the ticket index — stating plainly that the trigger has not fired and why the module was built anyway.

The alternative — silently building ahead of trigger without flagging it, or editing the trigger table after the fact to make it look like the condition was met — was rejected because it would make `implementation-plan.md`'s own trigger table meaningless as a signal to future readers (including future sessions) about what's actually pilot-validated versus what's been built speculatively at the user's own risk tolerance. The build-order discipline itself (don't scaffold a service before something concrete needs it) is still the default; overriding it is the exception, and the exception has to stay visibly an exception.

**Consequence for future readers**: `economic-service`'s override (trigger #11) is explicitly *not* an instance of this same pattern — it's a distinct, stronger category (an ethical/business-honesty boundary, not a scheduling convenience) and its disclosures are worded differently everywhere they appear, on purpose (see ADR-0001). Do not homogenize the two override types' language if extending either pattern further.
