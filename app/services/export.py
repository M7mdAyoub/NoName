"""`GET /export.csv`: the dashboard as a flat table, one row per indicator and per breakdown value.

Built from `dashboard.get`, so it holds only computed aggregates: no submission data and so no
`pii` answers. Breakdown rows repeat the indicator columns and fill `dimension`/`dimension_value`.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from app.db.connection import Database
from app.services import dashboard

COLUMNS = ["result_level", "result_code", "result_statement", "indicator_code", "indicator",
           "kind", "unit", "baseline", "target", "actual", "progress_pct", "status", "reason",
           "records", "dimension", "dimension_value"]  # fmt: skip


def _cell(value: Any) -> Any:
    return "" if value is None else value


def to_csv(db: Database) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, COLUMNS, lineterminator="\n")
    writer.writeheader()
    for ind in dashboard.get(db)["indicators"]:
        result = ind["result"] or {}
        base = {"result_level": result.get("level_name"), "result_code": result.get("code"),
                "result_statement": result.get("statement"), "indicator_code": ind["code"],
                "indicator": ind["name"], "kind": ind["kind"], "unit": ind["unit"],
                "baseline": ind["baseline"], "target": ind["target"]}  # fmt: skip
        writer.writerow({k: _cell(v) for k, v in {
            **base, "actual": ind["actual"], "progress_pct": ind["progress_pct"],
            "status": ind["status"], "reason": ind["reason"], "records": ind["records"],
        }.items()})  # fmt: skip
        for breakdown in ind["breakdowns"]:
            for v in breakdown["values"]:
                writer.writerow({k: _cell(x) for k, x in {
                    **base, "actual": v["actual"], "status": v["status"], "reason": v["reason"],
                    "records": v["records"], "dimension": breakdown["label"],
                    "dimension_value": v["label"],
                }.items()})  # fmt: skip
    return buffer.getvalue()
