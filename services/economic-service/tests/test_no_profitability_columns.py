"""ECON-002's permanent regression guard, load-bearing for this ticket's whole
design decision: no table/column name in `economic.*` may ever match a
profitability-output naming pattern.

Introspects `app.models.Base.metadata` programmatically -- not a hardcoded
list of today's table/column names -- so a future column added to any
existing or new model in this module fails this test loudly instead of
silently slipping past a one-time review note.

Pattern list (documented explicitly per the ticket's Test acceptance
criteria): `pnl`, `profit`, `net_return`, `return`, `revenue`, `forecast`,
`win`, checked as a substring match against every table name and every
column name, case insensitive. `return`/`revenue` are included as substrings
per the ticket's own instruction ("implementer should also check for
return/revenue as a substring") -- broader than the three headline terms so
a column like `total_return` or `revenue_share` is caught too, not just an
exact `pnl`/`profit`/`net_return` name. `forecast`/`win` were added by
ECON-013 (the backlog's own acceptance criteria list for that ticket names
`expected_return`/`forecast_*` explicitly) -- `expected_return` needs no
separate entry since it already contains `return` as a substring and is
therefore already caught by the existing pattern; `forecast` (matching any
`forecast_*`-shaped name) and `win` are genuinely new patterns this list did
not check before.

**ECON-013 carve-out (the one narrow exception to this guard, documented
here and in `app.models.BacktestResult`'s own docstring)**: `backtest_results`
is now the first, separately-authorized exception to the "no computed-output
column" rule -- it legitimately carries `cost_adjusted_return`/
`slippage_adjusted_return` (both matching the `return` substring) because it
persists only rows that already passed `ECON-005`'s unmodified structural
eligibility gate, never a placeholder/speculative figure (see
`docs/tickets/ECON-013.md`'s Analysis section). `_AUTHORIZED_RETURN_EXCEPTIONS`
below scopes this carve-out to exactly that one table and exactly the
`return` pattern -- `backtest_results` still fails this guard if it ever grows
a `pnl`/`profit`/`net_return`/`revenue`/`forecast`/`win` -shaped column, and
every other table (present or future) is still checked against `return`
unconditionally, same as before this ticket.
"""

from __future__ import annotations

from app.models import Base

_FORBIDDEN_SUBSTRINGS = ("pnl", "profit", "net_return", "return", "revenue", "forecast", "win")

# Table name -> forbidden substrings that table is authorized to violate.
# Deliberately narrow: only `backtest_results`, only `return` (see module
# docstring's "ECON-013 carve-out" note above). Never grows a second entry
# without a new, equally-documented, separately-authorized ticket.
_AUTHORIZED_RETURN_EXCEPTIONS: dict[str, set[str]] = {
    "backtest_results": {"return"},
}


def _offending_names(name: str, exceptions: set[str] = frozenset()) -> list[str]:
    lowered = name.lower()
    return [
        pattern
        for pattern in _FORBIDDEN_SUBSTRINGS
        if pattern in lowered and pattern not in exceptions
    ]


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
        exceptions = _AUTHORIZED_RETURN_EXCEPTIONS.get(table.name, frozenset())
        for column in table.columns:
            matches = _offending_names(column.name, exceptions)
            if matches:
                offenders[f"{table.name}.{column.name}"] = matches

    assert offenders == {}, (
        f"economic.* must never contain a profitability-output-shaped column "
        f"outside the one authorized ECON-013 carve-out "
        f"(ECON-002/ECON-010's Won't); offending columns: {offenders}"
    )


def test_metadata_actually_covers_all_four_expected_tables() -> None:
    """Sanity check ruling out this guard passing merely because
    `Base.metadata` is empty/incomplete -- asserts the four tables ECON-002/
    ECON-013 are meant to define are genuinely present and introspected
    above. Renamed from `..._all_three_expected_tables` (ECON-013): the
    hardcoded set below is the one line in this file that would NOT
    automatically pick up `BacktestResult` -- it is an explicit sanity-check
    set, not an introspection, so it must be updated by hand here.
    """
    table_names = set(Base.metadata.tables.keys())
    assert table_names == {
        "fee_schedules",
        "slippage_models",
        "simulation_configs",
        "backtest_results",
    }
