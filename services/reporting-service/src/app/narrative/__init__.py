"""AI-002: LLM-produced plain-language narrative summary, added to a
`"validation_audit"` report's rendered HTML.

Deliberately not `libs/ai_assist` (ADR-0011) -- all prompt-building/model-
calling logic stays inline here, in this service's own module boundary.
Only ever reachable from RS-006's `app.subscriber` event-driven path, never
from `POST /reports/generate`'s synchronous handler (see
`app.generation.generate_validation_audit_report`'s `narrative_client`
parameter, default `None`).
"""
