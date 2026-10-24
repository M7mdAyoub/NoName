"""Parsers -> IR, on the synthetic sample framework (tests/fixtures, made by scripts/make_samples.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.ingestion import UnsupportedFile, parse_file

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
HEADER = ["Level", "Code", "Result statement", "Indicator", "Unit", "Baseline", "Target",
          "Means of verification", "Frequency"]  # fmt: skip


def tables(ir: dict) -> list[list[list[str]]]:  # type: ignore[type-arg]
    return [b["rows"] for b in ir["blocks"] if b["kind"] == "table"]


def texts(ir: dict, kind: str) -> list[str]:  # type: ignore[type-arg]
    return [b["text"] for b in ir["blocks"] if b["kind"] == kind]


@pytest.mark.parametrize("suffix", ["xlsx", "csv", "docx", "pdf"])
def test_every_format_gives_tables_and_a_consistent_ir(suffix: str) -> None:
    ir = parse_file(FIXTURES / f"sample_logframe.{suffix}")
    assert ir["source"]["filename"] == f"sample_logframe.{suffix}"
    assert ir["source"]["type"] == suffix and len(ir["source"]["sha256"]) == 64
    assert ir["stats"]["tables"] >= 1
    ids = [b["id"] for b in ir["blocks"]]
    assert ids == [f"b{i}" for i in range(1, len(ids) + 1)]
    assert all("ref" in b for b in ir["blocks"])
    all_cells = " ".join(c for t in tables(ir) for row in t for c in row)
    assert "Number of women completing agri-food training" in all_cells
    assert "400" in all_cells


def test_xlsx_unmerges_cells_splits_tables_and_keeps_hidden_sheets() -> None:
    ir = parse_file(FIXTURES / "sample_logframe.xlsx")
    logframe, assumptions = tables(ir)
    assert logframe[0] == HEADER
    women, practices = logframe[2], logframe[3]  # the two indicators under merged outcome cells
    assert (
        women[:3]
        == practices[:3]
        == [
            "Outcome",
            "1",
            "Women's participation in agri-food production increased",
        ]
    )
    assert logframe[1][5:7] == ["310", "400"]  # numbers as people see them (no "310.0")
    assert assumptions[0] == ["Assumption", "Risk level"]
    assert texts(ir, "heading")[0].startswith("Results Framework")
    assert "Targets are end-of-programme values." in texts(ir, "paragraph")
    assert ir["stats"]["sheets"] == 2
    assert any("hidden" in w for w in ir["warnings"])
    refs = [b["ref"] for b in ir["blocks"] if b["kind"] == "table"]
    assert refs[0] == {"sheet": "Logframe", "range": "A3:I10"}


def test_csv_sniffs_the_delimiter_and_decodes_legacy_encodings(tmp_path: Path) -> None:
    ir = parse_file(FIXTURES / "sample_logframe.csv")
    assert tables(ir)[0][0] == HEADER  # the fixture uses ';'
    legacy = tmp_path / "legacy.csv"
    legacy.write_bytes("Indicator,Target\nCaf\xe9 owners,12\n".encode("cp1252"))
    ir = parse_file(legacy)
    assert tables(ir)[0][1] == ["Café owners", "12"]
    assert ir["warnings"]


def test_docx_keeps_order_headings_lists_and_tables() -> None:
    ir = parse_file(FIXTURES / "sample_logframe.docx")
    kinds = [b["kind"] for b in ir["blocks"]]
    assert kinds[:4] == ["heading", "paragraph", "heading", "table"]
    headings = [b for b in ir["blocks"] if b["kind"] == "heading"]
    assert [(h["text"], h["level"]) for h in headings[1:]] == [
        ("Indicators", 2),
        ("Assumptions", 2),
    ]
    assert texts(ir, "list_item") == [
        "Security situation remains stable",
        "Municipal partners keep co-funding",
    ]
    assert tables(ir)[0][0] == HEADER and len(tables(ir)[0]) == 8


def test_pdf_extracts_ruled_table_and_text_without_duplicating_it() -> None:
    ir = parse_file(FIXTURES / "sample_logframe.pdf")
    table = tables(ir)[0]
    assert table[0] == ["Code", "Indicator", "Baseline", "Target"]
    assert table[1] == ["0", "Average monthly household income", "310", "400"]
    prose = " ".join(texts(ir, "paragraph"))
    assert "Results Framework" in prose and "Indicator targets" in prose
    assert "Average monthly household income" not in prose
    assert ir["stats"]["pages"] == 1 and ir["warnings"] == []


def test_unsupported_type_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "slides.pptx"
    path.write_bytes(b"x")
    with pytest.raises(UnsupportedFile, match="unsupported file type"):
        parse_file(path)
