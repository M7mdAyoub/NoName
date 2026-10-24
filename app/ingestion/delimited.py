"""CSV parser: one table block (§10.3). Delimiter sniffed; UTF-8 (with BOM) or cp1252."""

from __future__ import annotations

import csv
from pathlib import Path

from app.ingestion.ir import IRBuilder, cell_text


def parse_csv(path: Path, ir: IRBuilder) -> None:
    raw = path.read_bytes()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("cp1252", errors="replace")
        ir.warnings.append("file is not UTF-8; read as Windows-1252")
    try:
        dialect: type[csv.Dialect] | csv.Dialect = csv.Sniffer().sniff(
            content[:4096], delimiters=",;\t|"
        )
    except csv.Error:
        dialect = csv.excel
    rows = [[cell_text(v) for v in row] for row in csv.reader(content.splitlines(), dialect)]
    ir.table(rows, {"index": 0})
