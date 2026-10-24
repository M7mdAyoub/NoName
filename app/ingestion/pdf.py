"""Digital PDF parser (pdfplumber): tables and text per page. No OCR (MVP)."""

from __future__ import annotations

from pathlib import Path

import pdfplumber

from app.ingestion.ir import IRBuilder, cell_text

MAX_PAGES = 200
MIN_TEXT_CHARS = 20  # below this a page is probably scanned


def parse_pdf(path: Path, ir: IRBuilder) -> None:
    with pdfplumber.open(str(path)) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            if number > MAX_PAGES:
                ir.warnings.append(f"stopped after {MAX_PAGES} pages")
                break
            ir.count("pages")
            ref = {"page": number}
            rest = page
            for table in page.find_tables():
                ir.table([[cell_text(c) for c in row] for row in table.extract()], ref)
                rest = rest.outside_bbox(table.bbox)  # table text is not repeated as prose
            text = rest.extract_text() or ""
            if len((page.extract_text() or "").strip()) < MIN_TEXT_CHARS:
                ir.warnings.append(f"page {number} has almost no text (scanned? OCR not supported)")
            for paragraph in text.split("\n\n"):
                ir.text("paragraph", paragraph, ref)
