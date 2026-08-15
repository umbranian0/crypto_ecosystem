"""ECON-002's permanent regression guard, load-bearing for this ticket's whole
design decision: no table/column name in `economic.*` may ever match a
profitability-output naming pattern.

Introspects `app.models.Base.metadata` programmatically -- not a hardcoded
list of today's table/column names -- so a future column added to any
existing or new model in this module fails this test loudly instead of
silently slipping past a one-time review note.

Pattern list (documented explicitly per the ticket's Test acceptance
criteria): `pnl`, `profit`, `net_return`, `return`, `revenue`, checked as a
substring match against every table name and every column name, case
insensitive. `return`/`revenue` are included as substrings per the ticket's
own instruction ("implementer should also check for return/revenue as a
substring") -- broader than the three headline terms so a column like
`total_return` or `revenue_share` is caught too, not just an exact
`pnl`/`profit`/`net_return` name.
"""

from __future__ import annotations

from app.models import Base

_FORBIDDEN_SUBSTRINGS = ("pnl", "profit", "net_return", "return", "revenue")


def _offending_names(name: str) -> list[str]:
    lowered = name.lower()
    return [pattern for pattern in _FORBIDDEN_SUBSTRINGS if pattern in lowered]


def test_no_table_name_matches_a_profitability_pattern() -> None:
    offenders = {
        table.name: _offending_names(table.name)
        for table in Base.metadata.tables.values()
        if _offending_names(table.name)
    }
    assert offenders == {}, (
        f"economic.* must never contain a profitability-output-shaped table "
        f"(ECON-002/ECON-010's Won't); offending tables: {offenders}"
    )


def test_no_column_name_matches_a_profitability_pattern() -> None:
    offenders: dict[str, list[str]] = {}
    for table in Base.metadata.tables.values():
        for column in table.columns:
            matches = _offending_names(column.name)
            if matches:
                offenders[f"{table.name}.{column.name}"] = matches

    assert offenders == {}, (
        f"economic.* must never contain a profitability-output-shaped column "
        f"(ECON-002/ECON-010's Won't); offending columns: {offenders}"
    )


def test_metadata_actually_covers_all_three_expected_tables() -> None:
    """Sanity check ruling out this guard passing merely because
    `Base.metadata` is empty/incomplete -- asserts the three tables ECON-002
    is meant to define are genuinely present and introspected above.
    """
    table_names = set(Base.metadata.tables.keys())
    assert table_names == {"fee_schedules", "slippage_models", "simulation_configs"}
