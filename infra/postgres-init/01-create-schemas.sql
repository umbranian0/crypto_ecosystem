-- INF-001: create the per-service schemas inside the single pilot-phase database.
-- One Postgres instance, schema-per-service (implementation-plan.md section 5).
-- validation/identity created here per INF-001/VS-013/GW-012; reporting added
-- by INF-018 (reporting-service's own migrations, RS-002, already targeted this
-- schema against the live container by hand -- this makes that reproducible on
-- a fresh volume too, not just the long-lived Sprint 06+ container/volume).

CREATE SCHEMA IF NOT EXISTS validation;
CREATE SCHEMA IF NOT EXISTS identity;
CREATE SCHEMA IF NOT EXISTS reporting;
