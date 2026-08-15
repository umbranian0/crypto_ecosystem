#!/bin/sh
# INF-014: create the non-superuser runtime role validation-service/gateway-api
# actually connect as, so Postgres RLS (FORCE ROW LEVEL SECURITY, migrations
# 0002_add_row_level_security.py / 0002_add_identity_rls.py) is enforced --
# Postgres unconditionally exempts superusers/BYPASSRLS roles from RLS, and
# `naive_first` (the migration-owner role) is both. `naive_first` itself is
# untouched here; it stays the migration-time role.
#
# reporting added by INF-018: reporting-service's own DATABASE_URL (Compose
# entry) connects as this same role, per the same RLS-enforcement rationale --
# see reporting-service's migrations/versions/0002_add_row_level_security.py
# (RS-002). RS-002's own test run had already granted naive_first_app USAGE/
# CRUD on `reporting` by hand against the live container (test-fixture-scoped
# at the time, flagged there as a disclosed infra gap for a future ticket);
# this makes that grant reproducible on a fresh volume too, matching
# validation/identity's own since-INF-014 treatment.
#
# Written as a .sh (not a raw .sql) because docker-entrypoint-initdb.d does
# not substitute env vars into .sql files, and the role's password must come
# from POSTGRES_APP_PASSWORD, not be hardcoded.
#
# Only runs automatically against a FRESH data volume (docker-entrypoint-initdb.d
# convention) -- see infra/README.md for how this was additionally applied by
# hand against the already-running Sprint 06 container/volume.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE naive_first_app LOGIN PASSWORD '$POSTGRES_APP_PASSWORD'
        NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;

    GRANT USAGE ON SCHEMA validation, identity, reporting TO naive_first_app;

    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA validation, identity, reporting TO naive_first_app;

    ALTER DEFAULT PRIVILEGES IN SCHEMA validation, identity, reporting
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO naive_first_app;
EOSQL
