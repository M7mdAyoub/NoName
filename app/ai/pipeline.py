"""Framework IR -> draft (results, indicators, forms, definitions, open questions).

Steps (plan §11.3, simplest version): map each table's layout (LLM) -> build the results tree and
raw indicator rows in code -> normalise each indicator (LLM) -> propose forms grouped by data
source (LLM) -> propose a definition per indicator (LLM) -> cross-check in code.

Pure: no database access, so no transaction is ever held across an LLM call. The caller stores
the returned `Draft`.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from app.ai import steps
from app.ai.llm import LLM, LLMError
from app.schemas.definition import Definition, validate_definition
from app.schemas.form import FormSchema, validate_form


class ExtractionError(Exception):
    pass


@dataclass
class DraftResult:
    key: str
    level_name: str
    code: str | None
    statement: str
    parent_key: str | None
    sort_order: int


@dataclass
class DraftIndicator:
    ref: str
    result_key: str
    raw: dict[str, str]
    name: str
    unit: str | None = None
    kind: str | None = None
    baseline: float | None = None
    target: float | None = None
    frequency: str | None = None
    data_source: str | None = None
    definition: Definition | None = None
    definition_errors: list[str] = field(default_factory=list)


@dataclass
class Draft:
    results: list[DraftResult]
    indicators: list[DraftIndicator]
    forms: list[steps.ProposedForm]
    questions: list[tuple[str | None, str]]  # (indicator ref or None, question)
    tables: list[dict[str, Any]]
    problems: list[str]

    def form_schemas(self) -> dict[str, FormSchema]:
        return {f.key: f.form_schema() for f in self.forms}


# --- C. layout -----------------------------------------------------------------------------------


def _tables(ir: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [
        (file_ir["source"]["filename"], block)
        for file_ir in ir["files"]
        for block in file_ir["blocks"]
        if block["kind"] == "table" and len(block["rows"]) >= 2
    ]


def map_layout(llm: LLM, filename: str, block: dict[str, Any]) -> steps.TableLayout:
    sample = [[cell[:80] for cell in row] for row in block["rows"][: steps.SAMPLE_ROWS]]
    payload = {"file": filename, "table": block["id"], "rows": sample}
    return llm.run("map_layout", steps.MAP_LAYOUT, payload, steps.TableLayout,
                   steps.check_layout(sample))  # fmt: skip


# --- D. structure, in code -----------------------------------------------------------------------

_SPACES = re.compile(r"\s+")


def _clean(value: str) -> str:
    return _SPACES.sub(" ", value).strip()


def _depth(code: str) -> int:
    return len([p for p in code.strip(".").split(".") if p])


def build_structure(
    rows: list[list[str]], layout: steps.TableLayout
) -> tuple[list[DraftResult], list[DraftIndicator]]:
    """Rows -> results tree + raw indicators. Merged-cell continuations (a row with an indicator
    but no result cells) belong to the previous result."""

    def cell(row: list[str], role: str) -> str:
        index = layout.column(role)
        return _clean(row[index]) if index is not None and index < len(row) else ""

    results: dict[tuple[str, str, str], DraftResult] = {}
    level_rank: dict[str, int] = {}
    indicators: list[DraftIndicator] = []
    order: list[DraftResult] = []
    current: DraftResult | None = None
    for row in rows[layout.header_row + 1 :]:
        level, code, statement = (
            cell(row, r) for r in ("level", "result_code", "result_statement")
        )
        indicator = cell(row, "indicator")
        if level or code or statement:
            if not level:
                level = (
                    f"Level {_depth(code)}"
                    if code
                    else (current.level_name if current else "Result")
                )
            if not statement:
                statement = f"Result {code}" if code else "(no statement)"
            key = (level, code, statement)
            if key not in results:
                level_rank.setdefault(level, len(level_rank))
                result = DraftResult(
                    key=f"r{len(results) + 1}",
                    level_name=level,
                    code=code or None,
                    statement=statement,
                    parent_key=_parent(order, level_rank, level, code),
                    sort_order=len(results),
                )
                results[key] = result
                order.append(result)
            current = results[key]
        if indicator and current is not None:
            raw = {role: cell(row, role) for role in
                   ("unit", "baseline", "target", "means_of_verification", "frequency")}  # fmt: skip
            raw["indicator"] = indicator
            indicators.append(
                DraftIndicator(
                    ref=f"i{len(indicators) + 1}", result_key=current.key, raw=raw, name=indicator
                )  # fmt: skip
            )
    return order, indicators


def _parent(order: list[DraftResult], rank: dict[str, int], level: str, code: str) -> str | None:
    """Parent = the higher-level result whose code prefixes this code (1 -> 1.1), else the most
    recent result one level up, else the most recent higher-level result."""
    mine = rank[level]
    higher = [r for r in order if rank[r.level_name] < mine]
    if not higher:
        return None
    if code:
        prefixed = [r for r in higher if r.code and code.startswith(r.code.rstrip(".") + ".")]
        if prefixed:
            return max(prefixed, key=lambda r: len(r.code or "")).key
    one_up = [r for r in higher if rank[r.level_name] == mine - 1]
    return (one_up or higher)[-1].key


# --- E. normalise --------------------------------------------------------------------------------


def normalize(llm: LLM, ind: DraftIndicator, result: DraftResult) -> list[str]:
    """Fill the indicator from the model's answer; returns the open questions."""
    raw = ind.raw
    row = {
        "name": raw["indicator"],
        "unit": raw["unit"],
        "baseline": raw["baseline"],
        "target": raw["target"],
        "means_of_verification": raw["means_of_verification"],
        "frequency": raw["frequency"],
    }
    payload = {
        "result": {"level": result.level_name, "code": result.code, "statement": result.statement},
        "row": row,
    }
    try:
        out = llm.run("normalize_indicator", steps.NORMALIZE, payload, steps.NormalizedIndicator,
                      steps.check_normalized(row))  # fmt: skip
    except LLMError as exc:
        last = exc.last if isinstance(exc.last, steps.NormalizedIndicator) else None
        questions = [
            f"Check this indicator; the AI could not normalise it: {'; '.join(exc.errors)}"
        ]
        if last is None:
            ind.unit = raw["unit"] or None
            ind.data_source = raw["means_of_verification"] or None
            ind.frequency = raw["frequency"] or None
            return questions
        out = last.model_copy(update={"baseline": None, "target": None})
        questions += out.open_questions
    else:
        questions = out.open_questions
    ind.name, ind.unit, ind.kind = out.name, out.unit, out.kind
    ind.baseline, ind.target = out.baseline, out.target
    ind.frequency, ind.data_source = out.frequency, out.data_source
    return questions


# --- G. forms ------------------------------------------------------------------------------------


def propose_forms(
    llm: LLM, indicators: list[DraftIndicator], results: dict[str, DraftResult]
) -> tuple[list[steps.ProposedForm], list[str]]:
    payload = {
        "indicators": [
            {
                "ref": i.ref,
                "name": i.name,
                "kind": i.kind,
                "unit": i.unit,
                "data_source": i.data_source,
                "frequency": i.frequency,
                "result": results[i.result_key].statement,
            }  # fmt: skip
            for i in indicators
        ]
    }
    refs = [i.ref for i in indicators]
    try:
        out = llm.run("propose_forms", steps.PROPOSE_FORMS, payload, steps.FormsProposal,
                      steps.check_forms(refs))  # fmt: skip
    except LLMError as exc:
        if not isinstance(exc.last, steps.FormsProposal):
            raise ExtractionError(f"no usable forms: {exc}") from exc
        return exc.last.forms, [f"forms: {e}" for e in exc.errors]
    return out.forms, []


# --- H. definitions ------------------------------------------------------------------------------


def propose_definition(
    llm: LLM, ind: DraftIndicator, forms: list[steps.ProposedForm], schemas: dict[str, FormSchema]
) -> None:
    linked = [f for f in forms if ind.ref in f.indicators] or forms
    payload = {
        "indicator": {
            "name": ind.name,
            "kind": ind.kind,
            "unit": ind.unit,
            "data_source": ind.data_source,
        },  # fmt: skip
        "forms": [steps.form_for_prompt(f.key, schemas[f.key]) for f in linked],
    }
    try:
        ind.definition = llm.run(
            "propose_definition", steps.PROPOSE_DEFINITION, payload, Definition,
            steps.check_definition(schemas, ind.kind),
        )  # fmt: skip
    except LLMError as exc:
        ind.definition = exc.last if isinstance(exc.last, Definition) else None
        ind.definition_errors = exc.errors
    if ind.kind is None and ind.definition is not None:
        ind.kind = ind.definition.kind


# --- J. cross-check ------------------------------------------------------------------------------


def cross_check(draft: Draft) -> None:
    """Deterministic checks; every failure becomes a problem and, where a person must decide,
    an open question."""
    schemas = draft.form_schemas()
    for form in draft.forms:
        for error in validate_form(schemas[form.key]):
            draft.problems.append(f"form '{form.key}': {error}")
    result_keys = {r.key for r in draft.results}
    seen: set[tuple[str, str]] = set()
    for ind in draft.indicators:
        if ind.result_key not in result_keys:
            draft.problems.append(f"indicator '{ind.name}' has no result")
        dup = (ind.result_key, ind.name.lower())
        if dup in seen:
            draft.questions.append((ind.ref, f"'{ind.name}' appears twice under the same result. "
                                              "Is it a duplicate?"))  # fmt: skip
        seen.add(dup)
        if ind.definition is None:
            draft.questions.append(
                (
                    ind.ref,
                    f"No calculation rule could be proposed for '{ind.name}'. "
                    "How should it be calculated?",
                )  # fmt: skip
            )
            continue
        ind.definition_errors = validate_definition(ind.definition, schemas)
        if ind.definition_errors:
            draft.questions.append(
                (
                    ind.ref,
                    f"The proposed calculation for '{ind.name}' is invalid: "
                    + "; ".join(ind.definition_errors),
                )  # fmt: skip
            )


# --- the whole pipeline --------------------------------------------------------------------------


def extract(llm: LLM, ir: dict[str, Any], max_workers: int = 4) -> Draft:
    problems: list[str] = []
    tables: list[dict[str, Any]] = []
    candidates: list[tuple[dict[str, Any], list[DraftResult], list[DraftIndicator]]] = []
    for filename, block in _tables(ir):
        info: dict[str, Any] = {"file": filename, "block": block["id"], "framework": False}
        tables.append(info)
        try:
            layout = map_layout(llm, filename, block)
        except LLMError as exc:
            problems.append(f"{filename} {block['id']}: layout not understood: {exc}")
            continue
        if not layout.is_framework:
            continue
        results, indicators = build_structure(block["rows"], layout)
        roles = sum(c.role != "ignore" for c in layout.columns)
        info.update(framework=True, columns=roles, results=len(results), indicators=len(indicators))
        if indicators:
            candidates.append((info, results, indicators))
    if not candidates:
        raise ExtractionError("no results framework table with indicators was found")
    # One framework per upload: the table with the most indicators wins, then the one with the
    # most mapped columns (levels, statements, units ...), then the first one.
    chosen, results, indicators = max(candidates, key=lambda c: (len(c[2]), c[0]["columns"]))
    for t in tables:
        t["used"] = t is chosen
    if len(candidates) > 1:
        problems.append(f"{len(candidates) - 1} other framework table(s) ignored; "
                        f"used {chosen['file']} {chosen['block']}")  # fmt: skip

    by_key = {r.key: r for r in results}
    questions: list[tuple[str | None, str]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        asked = list(pool.map(lambda i: normalize(llm, i, by_key[i.result_key]), indicators))
    for ind, qs in zip(indicators, asked, strict=True):
        questions += [(ind.ref, q) for q in qs]

    forms, form_problems = propose_forms(llm, indicators, by_key)
    problems += form_problems
    schemas = {f.key: f.form_schema() for f in forms}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(pool.map(lambda i: propose_definition(llm, i, forms, schemas), indicators))

    draft = Draft(results, indicators, forms, questions, tables, problems)
    cross_check(draft)
    return draft
