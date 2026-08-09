-- INF-001: create the per-service schemas inside the single pilot-phase database.
-- One Postgres instance, schema-per-service (implementation-plan.md section 5).
-- Only validation and identity are created here (VS-013/GW-012 own pointing their
-- own Alembic env.py at these schemas -- that's tracked on those tickets, not here).

CREATE SCHEMA IF NOT EXISTS validation;
CREATE SCHEMA IF NOT EXISTS identity;
