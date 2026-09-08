-- INF-001: create the per-service schemas inside the single pilot-phase database.
-- One Postgres instance, schema-per-service (implementation-plan.md section 5).
-- validation/identity created here per INF-001/VS-013/GW-012; reporting added
-- by INF-018 (reporting-service's own migrations, RS-002, already targeted this
-- schema against the live container by hand -- this makes that reproducible on
-- a fresh volume too, not just the long-lived Sprint 06+ container/volume).
--
-- Found live during Sprint 29 (SETUP-004's own fresh-Postgres-volume dry
-- run, not hypothetical): `02-create-app-role.sh` (this directory, runs
-- immediately after this file per docker-entrypoint-initdb.d's alphabetical
-- ordering) grants `naive_first_app` USAGE on `validation, identity,
-- reporting, ingestion` in one combined statement -- on a genuinely fresh
-- volume that statement failed entirely with `schema "ingestion" does not
-- exist` (this file never created it, even though the grant script already
-- named it, per that script's own "ingestion added during Sprint 25 live
-- UAT" comment), which silently left `naive_first_app` with **zero**
-- grants on *any* of the four schemas -- not just `ingestion` -- since a
-- single multi-schema GRANT statement is all-or-nothing. Every app service
-- querying Postgres via `naive_first_app` (gateway-api's own `SETUP-001`
-- being the one that surfaced it first) then failed with a misleading
-- `relation "tenants" does not exist` (Postgres's standard behavior for
-- hiding a real table's existence from a role with no schema USAGE, rather
-- than a clearer "permission denied"). Adding the missing schema here is
-- the same category of fix `INF-001`'s own comment already documents for
-- `reporting` -- the schema must exist before the grant script (which
-- already expects it) runs.
CREATE SCHEMA IF NOT EXISTS validation;
CREATE SCHEMA IF NOT EXISTS identity;
CREATE SCHEMA IF NOT EXISTS reporting;
CREATE SCHEMA IF NOT EXISTS ingestion;
