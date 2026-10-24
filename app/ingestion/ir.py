"""Intermediate representation (IR) of one parsed file (simplified plan §10.2).

    {"source": {"filename", "type", "sha256"},
     "blocks": [{"id": "b1", "kind": "heading"|"paragraph"|"list_item"|"table", "text"?, "level"?,
                 "rows"?: [[str, ...], ...], "ref": {"sheet"/"page"/"index", "range"?}}],
     "stats": {"blocks", "tables", "rows", "sheets"|"pages"|..., ...},
     "warnings": [str]}

Every cell value is a string ("" for empty) so the AI step sees exactly what a person sees.
"""

from __future__ import annotations

from typing import Any


class IRBuilder:
    def __init__(self, filename: str, file_type: str, sha256: str) -> None:
        self.source = {"filename": filename, "type": file_type, "sha256": sha256}
        self.blocks: list[dict[str, Any]] = []
        self.stats: dict[str, int] = {}
        self.warnings: list[str] = []

    def _add(self, block: dict[str, Any]) -> None:
        block["id"] = f"b{len(self.blocks) + 1}"
        self.blocks.append(block)

    def text(self, kind: str, text: str, ref: dict[str, Any], level: int | None = None) -> None:
        text = text.strip()
        if not text:
            return
        block: dict[str, Any] = {"kind": kind, "text": text, "ref": ref}
        if level is not None:
            block["level"] = level
        self._add(block)

    def table(self, rows: list[list[str]], ref: dict[str, Any]) -> None:
        rows = trim_table(rows)
        if rows:
            self._add({"kind": "table", "rows": rows, "ref": ref})

    def count(self, key: str, n: int = 1) -> None:
        self.stats[key] = self.stats.get(key, 0) + n

    def build(self) -> dict[str, Any]:
        tables = [b for b in self.blocks if b["kind"] == "table"]
        stats = dict(self.stats)
        stats.update(
            blocks=len(self.blocks),
            tables=len(tables),
            rows=sum(len(t["rows"]) for t in tables),
        )
        return {
            "source": self.source,
            "blocks": self.blocks,
            "stats": stats,
            "warnings": self.warnings,
        }


def cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return " ".join(str(value).split())  # collapse internal newlines/whitespace


def trim_table(rows: list[list[str]]) -> list[list[str]]:
    """Drop fully empty rows and columns, pad rows to the same width."""
    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        return []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    keep = [i for i in range(width) if any(r[i] for r in rows)]
    return [[r[i] for i in keep] for r in rows]
