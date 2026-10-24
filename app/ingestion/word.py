"""Word parser (python-docx): headings, paragraphs, list items and tables in document order."""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.ingestion.ir import IRBuilder, cell_text

_HEADING = re.compile(r"^(Heading|Title)\s*(\d*)", re.IGNORECASE)


def parse_docx(path: Path, ir: IRBuilder) -> None:
    document = Document(str(path))
    for index, item in enumerate(document.iter_inner_content()):
        ref = {"index": index}
        if isinstance(item, Paragraph):
            style = item.style.name if item.style is not None else ""
            heading = _HEADING.match(style)
            if heading:
                ir.text("heading", item.text, ref, level=int(heading.group(2) or 1))
            elif "list" in style.lower():
                ir.text("list_item", item.text, ref)
            else:
                ir.text("paragraph", item.text, ref)
        elif isinstance(item, Table):
            ir.count("word_tables")
            # row.cells repeats a merged cell for every grid column it spans, i.e. "unmerged"
            rows = [[cell_text(cell.text) for cell in row.cells] for row in item.rows]
            ir.table(rows, ref)
