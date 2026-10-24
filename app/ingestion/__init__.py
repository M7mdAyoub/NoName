"""File -> IR. Supported: xlsx/xlsm, csv, docx, digital pdf (docs/MVP.md)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.ingestion.delimited import parse_csv
from app.ingestion.ir import IRBuilder
from app.ingestion.pdf import parse_pdf
from app.ingestion.word import parse_docx
from app.ingestion.xlsx import parse_xlsx

PARSERS: dict[str, Callable[[Path, IRBuilder], None]] = {
    "xlsx": parse_xlsx,
    "xlsm": parse_xlsx,
    "csv": parse_csv,
    "docx": parse_docx,
    "pdf": parse_pdf,
}


class UnsupportedFile(ValueError):  # noqa: N818
    pass


def file_type(filename: str) -> str:
    kind = Path(filename).suffix.lower().lstrip(".")
    if kind not in PARSERS:
        raise UnsupportedFile(
            f"{filename}: unsupported file type; use one of {', '.join(sorted(PARSERS))}"
        )
    return kind


def parse_file(path: Path, filename: str | None = None) -> dict[str, Any]:
    """Parse one file into its IR. Raises UnsupportedFile, or the parser's error."""
    name = filename or path.name
    kind = file_type(name)
    ir = IRBuilder(name, kind, hashlib.sha256(path.read_bytes()).hexdigest())
    PARSERS[kind](path, ir)
    return ir.build()
