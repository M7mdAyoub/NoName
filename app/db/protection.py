"""Hard-delete protection (plan §5.1, decision D-03, resolves L-02).

Every table belongs to exactly one class:

* soft-delete  - has a `deleted_at` column (and is not exempt): gets a `<table>_no_delete` trigger
* HISTORY      - no `deleted_at`, rows are never removed: gets the same trigger
* EXEMPT       - rows may be hard-deleted (join, derived, token and queue tables)
* SYSTEM       - protected by their own migration SQL (`audit_log`, `schema_migrations`)

A table in none of these classes is reported as "unclassified" and makes the migration fail, so
whoever adds the table must decide.
"""

from __future__ import annotations

import re

from sqlalchemy import Connection

EXEMPT: frozenset[str] = frozenset(
    {
        "membership_component",  # PUT replaces the set
        "indicator_field_link",  # rewritten on approval
        "qual_coding",  # rebuilt on re-analysis
        "indicator_dirty",  # work list of indicators to recalculate
        "refresh_token",
        "password_reset",
        "entity_alias",
        "job",
        # MVP tables (docs/MVP.md cuts soft delete): drafts are edited and replaced in place
        "project",
        "framework_upload",
        "result",
        "indicator",
        "form",
        "indicator_definition",
        "submission",
        "open_question",
    }
)
HISTORY: frozenset[str] = frozenset({"submission_revision", "ai_run", "calc_run"})
SYSTEM: frozenset[str] = frozenset({"schema_migrations", "audit_log"})

_SAFE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


def trigger_name(table: str) -> str:
    return f"{table}_no_delete"


def list_tables(conn: Connection) -> dict[str, set[str]]:
    """All user tables with their column names."""
    names = conn.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    ).scalars()
    tables: dict[str, set[str]] = {}
    for name in list(names):
        cols = conn.exec_driver_sql(f'SELECT name FROM pragma_table_info("{name}")').scalars()
        tables[name] = set(cols)
    return tables


def classify(table: str, columns: set[str]) -> str:
    if table in SYSTEM:
        return "system"
    if table in EXEMPT:
        return "exempt"
    if table in HISTORY:
        return "history"
    if "deleted_at" in columns:
        return "soft_delete"
    return "unclassified"


def unclassified_tables(conn: Connection) -> list[str]:
    return sorted(t for t, c in list_tables(conn).items() if classify(t, c) == "unclassified")


def protected_tables(conn: Connection) -> list[str]:
    return sorted(
        t for t, c in list_tables(conn).items() if classify(t, c) in ("soft_delete", "history")
    )


def ensure_triggers(conn: Connection) -> list[str]:
    """Create any missing `<table>_no_delete` trigger. Idempotent. Returns the tables touched."""
    existing = set(
        conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type = 'trigger'").scalars()
    )
    created: list[str] = []
    for table in protected_tables(conn):
        if not _SAFE_NAME.match(table):
            raise ValueError(f"unsafe table name: {table!r}")
        name = trigger_name(table)
        if name in existing:
            continue
        conn.exec_driver_sql(
            f'CREATE TRIGGER "{name}" BEFORE DELETE ON "{table}" '
            "BEGIN SELECT RAISE(ABORT, 'hard delete forbidden; set deleted_at'); END"
        )
        created.append(table)
    return created


def verify_triggers(conn: Connection) -> list[str]:
    """Problems found (empty list = fine): unclassified tables and missing triggers."""
    problems = [
        f"table {t!r} is not classified in app/db/protection.py" for t in unclassified_tables(conn)
    ]
    existing = set(
        conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type = 'trigger'").scalars()
    )
    for table in protected_tables(conn):
        if trigger_name(table) not in existing:
            problems.append(f"table {table!r} lacks trigger {trigger_name(table)}")
    for table in ("audit_log",):
        for suffix in ("no_update", "no_delete"):
            if f"{table}_{suffix}" not in existing and table in list_tables(conn):
                problems.append(f"trigger {table}_{suffix} is missing")
    return problems
