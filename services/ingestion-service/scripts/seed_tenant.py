"""INGEST-010: `seed_tenant.py` -- thin CLI wrapper (argument parsing + stdout
only) around `app.seed_platform_history`'s real backfill logic, mirroring
`gateway-api/scripts/provision_tenant.py`'s "CLI wrapper imports the real
function from `src/app`" shape exactly (see that module's own docstring for
why `scripts/` can't hold the real logic: it isn't part of this service's
packaged wheel).

Two mutually exclusive modes:
  seed_tenant.py --tenant-id <id> --source <source> --from <path-or-"platform-csv"> [--dry-run]
  seed_tenant.py --all-existing-tenants [--dry-run]

`--tenant-id` has no hardcoded default anywhere in this script (ticket
Review AC) -- it is only ever read from the required CLI argument.
"""
from __future__ import annotations

import argparse
import os
import sys

from naive_first_common import configure_structured_logging

from app.dependencies.repositories import get_connector_record_repository
from app.seed_platform_history import (
    seed_all_existing_tenants,
    seed_single_source,
)

_GATEWAY_API_URL_ENV_VAR = "GATEWAY_API_URL"
_DEFAULT_GATEWAY_API_URL = "http://localhost:8000"
_OPERATOR_TOKEN_ENV_VAR = "OPERATOR_TOKEN"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill the platform-wide historical CSV archive into one "
            "tenant's rows, or into every existing tenant's rows."
        )
    )
    parser.add_argument("--tenant-id", help="Single-tenant mode: the tenant to seed.")
    parser.add_argument(
        "--source",
        help=(
            "Single-tenant mode: the DB source identifier, e.g. "
            "binance_price_btcusdt_1h, blockchain_info_hash-rate, "
            "blockchain_info_n-unique-addresses, kaggle_bitcoin_sentiments_21_24."
        ),
    )
    parser.add_argument(
        "--from",
        dest="from_path",
        help='Single-tenant mode: "platform-csv" or an arbitrary CSV path.',
    )
    parser.add_argument(
        "--all-existing-tenants",
        action="store_true",
        help="Seed every existing tenant (via gateway-api's GET /tenants) with all four CSV-backed sources.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print row counts that would be written, without writing anything.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_structured_logging()
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.all_existing_tenants:
        if args.tenant_id or args.source or args.from_path:
            parser.error("--all-existing-tenants cannot be combined with --tenant-id/--source/--from")

        gateway_api_url = os.environ.get(_GATEWAY_API_URL_ENV_VAR, _DEFAULT_GATEWAY_API_URL)
        operator_token = os.environ.get(_OPERATOR_TOKEN_ENV_VAR)
        if not operator_token:
            print(f"error: {_OPERATOR_TOKEN_ENV_VAR} is not set", file=sys.stderr)
            return 1

        try:
            results = seed_all_existing_tenants(
                gateway_api_url,
                operator_token,
                get_connector_record_repository(),
                dry_run=args.dry_run,
            )
        except Exception as exc:  # gateway-api unreachable, non-2xx, etc.
            print(f"error: could not enumerate tenants via {gateway_api_url}: {exc}", file=sys.stderr)
            return 1

        verb = "would write" if args.dry_run else "wrote"
        for tenant_id, per_source in results.items():
            print(f"tenant {tenant_id}:")
            for source, row_count in per_source.items():
                print(f"  {source}: {verb} {row_count} rows")
        return 0

    if not args.tenant_id or not args.source or not args.from_path:
        parser.error("--tenant-id, --source, and --from are all required (or use --all-existing-tenants)")

    row_count = seed_single_source(
        args.tenant_id,
        args.source,
        args.from_path,
        get_connector_record_repository(),
        dry_run=args.dry_run,
    )
    verb = "would write" if args.dry_run else "wrote"
    print(f"tenant {args.tenant_id}, source {args.source}: {verb} {row_count} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
