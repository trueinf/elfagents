"""Warehouse access for the launch-readiness use case.

The connection is opened READ-ONLY, deliberately and not as a nicety. BUILD_SPEC
§1.4 and §10 require that the system cannot act: no tool anywhere writes a
launch decision. Enforcing that at the connection means it is not a property of
how carefully the tools were written — DuckDB refuses the write regardless.

DuckDB stands in for Snowflake (e.l.f.'s actual warehouse). The dbt code above
it is warehouse-portable. Say "stand-in" if asked; do not call the file
Snowflake.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB = REPO_ROOT / "data" / "elfagent.duckdb"


class WarehouseMissing(RuntimeError):
    pass


def connect(path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    db = Path(path) if path else DEFAULT_DB
    if not db.exists():
        raise WarehouseMissing(
            f"no warehouse at {db}. Build it first:\n"
            f"    cd dbt && ../.venv/Scripts/dbt.exe build --profiles-dir ."
        )
    return duckdb.connect(str(db), read_only=True)


@contextmanager
def warehouse(path: str | Path | None = None):
    con = connect(path)
    try:
        yield con
    finally:
        con.close()


def rows(con: duckdb.DuckDBPyConnection, sql: str, params: tuple = ()) -> list[dict]:
    """Query returning a list of dicts. Nothing clever; tools stay boring."""
    cur = con.execute(sql, params)
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, record)) for record in cur.fetchall()]


def one(con: duckdb.DuckDBPyConnection, sql: str, params: tuple = ()) -> dict | None:
    found = rows(con, sql, params)
    return found[0] if found else None
