"""Framework IR -> draft (results, indicators, forms, definitions, open questions).

Steps (plan §11.3, simplest version): map each table's layout (LLM) -> build the results tree and
raw indicator rows in code -> normalise each indicator (LLM) -> turn the forms found in the
documents into form schemas (LLM, one call per sheet/table) and link indicators to them by data
source (code) -> propose forms for the indicators left over, grouped by data source (LLM) ->
propose a definition per indicator (LLM) -> cross-check in code.

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
from app.schemas.form import FormField, FormSchema, Option, unique_slug, validate_form


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
    code: str | None = None
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
            named = next((n for n in level_rank if statement.lower().startswith(n.lower() + " ")),
                         None)  # fmt: skip
            if not level and named:
                level = named  # an empty level cell, but "Activity D | ..." names a known level
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
                    ref=f"i{len(indicators) + 1}",
                    result_key=current.key,
                    raw=raw,
                    name=indicator,
                    code=code or None,
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
        prefixed = [r for r in higher if r.code and _code_under(code, r.code)]
        if prefixed:
            return max(prefixed, key=lambda r: len(r.code or "")).key
    one_up = [r for r in higher if rank[r.level_name] == mine - 1]
    return (one_up or higher)[-1].key


_TRAILING_ZERO = re.compile(r"[.\-_ ]0$")


def _code_under(code: str, parent: str) -> bool:
    """Does `code` sit under `parent`? 1 -> 1.1, A -> A1, X-SO1-0 -> X-SO1-A (a trailing 0
    segment marks the head of its group), but not 1 -> 10."""
    base = _TRAILING_ZERO.sub("", parent.rstrip(".-_ "))
    if not base or code == parent or len(code) <= len(base) or not code.startswith(base):
        return False
    after = code[len(base)]
    return after in ".-_ " or (base[-1].isalpha() and after.isdigit())


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


# --- F. forms found in the documents ---------------------------------------------------------


@dataclass
class FormCandidate:
    title: str  # sheet name, or the heading above the table
    source: str  # "file.xlsx > Sheet", for people
    rows: list[list[str]]
    cut_name: bool = False  # a sheet name at Excel's 31-character limit may have been cut


EXCEL_SHEET_NAME_LIMIT = 31


def form_candidates(ir: dict[str, Any], skip: set[tuple[str, str]]) -> list[FormCandidate]:
    """Tables that may be forms: each sheet (all its tables together) and each document table
    that is not a framework table. The model decides which really are forms."""
    out: list[FormCandidate] = []
    for file_ir in ir["files"]:
        filename = file_ir["source"]["filename"]
        sheets: dict[str, list[list[str]]] = {}
        heading: str | None = None
        for block in file_ir["blocks"]:
            if block["kind"] == "heading":
                heading = block["text"]
            if block["kind"] != "table" or (filename, block["id"]) in skip:
                continue
            sheet = block["ref"].get("sheet")
            if sheet is not None:
                sheets.setdefault(sheet, []).extend(block["rows"])
            else:
                title = heading or filename.rsplit(".", 1)[0]
                out.append(FormCandidate(title, f"{filename} > {title}", block["rows"]))
        for sheet, rows in sheets.items():
            out.append(FormCandidate(sheet, f"{filename} > {sheet}", rows,
                                     cut_name=len(sheet) == EXCEL_SHEET_NAME_LIMIT))  # fmt: skip
    return out


def import_form(llm: LLM, cand: FormCandidate) -> tuple[steps.ImportedForm | None, list[str]]:
    """Ask the model to read one candidate as a form; None if it is not one."""
    rows = [[cell[:400] for cell in row] for row in cand.rows[: steps.FORM_SAMPLE_ROWS]]
    payload = {"title": cand.title, "rows": rows}
    text = "\n".join(" | ".join(row) for row in rows)
    try:
        out = llm.run("convert_form", steps.CONVERT_FORM, payload, steps.ImportedForm,
                      steps.check_imported(text))  # fmt: skip
    except LLMError as exc:
        return None, [f"{cand.source}: could not be read as a form: {exc}"]
    return (out if out.is_form and out.questions else None), []


_NUMBERING = re.compile(r"^\s*(?:[A-Z]?\d+(?:\.\d+)*[.)]|[a-z][.)])\s+")


def to_document_form(
    out: steps.ImportedForm, cand: FormCandidate, keys: set[str]
) -> steps.DocumentForm:
    """Model answer -> form: field ids and option values are made in code from the labels."""
    ids: set[str] = set()
    fields: list[FormField] = []
    entity: str | None = None
    for q in out.questions:
        label = _NUMBERING.sub("", q.label).strip() or q.label.strip()
        values: set[str] = set()
        labels = dict.fromkeys(o.strip() for o in q.options if o.strip())
        field_ = FormField(id=unique_slug(label, ids), type=q.type, label=label,
                           required=q.required, pii=q.pii,
                           options=[Option(value=unique_slug(o, values), label=o) for o in labels],
                           qualitative=q.qualitative and q.type == "text",
                           section=q.section)  # fmt: skip
        if entity is None and q.label == out.entity_key and q.type in ("text", "integer"):
            entity, field_.required = field_.id, True
        fields.append(field_)
    title = out.title.strip() or cand.title.replace("_", " ").strip()
    return steps.DocumentForm(key=unique_slug(cand.title, keys, 30), title=title,
                              data_source=cand.title, indicators=[], entity_key_field=entity,
                              fields=fields, source=cand.source,
                              cut_name=cand.cut_name)  # fmt: skip


_FORM_WORDS = frozenset({"form", "forms", "sheet", "questionnaire", "template", "the", "tool"})


def _name_tokens(text: str) -> list[str]:
    text = re.sub(r"\(.*?\)", " ", text.lower())
    return [t for t in re.findall(r"[a-z0-9]+", text) if t not in _FORM_WORDS]


def match_form(data_source: str | None, forms: list[steps.DocumentForm]) -> str | None:
    """The document form an indicator's data source names, if exactly one fits: the same words
    once "form", "sheet" ... and anything in brackets are dropped, or, for a sheet name Excel may
    have cut at 31 characters, the start of the data source."""
    wanted = _name_tokens(data_source or "")
    if not wanted:
        return None
    exact = [f for f in forms
             if wanted in (_name_tokens(f.data_source or ""), _name_tokens(f.title))]  # fmt: skip
    if len(exact) == 1:
        return exact[0].key
    joined = " ".join(wanted)
    cut = [f for f in forms
           if f.cut_name and joined.startswith(" ".join(_name_tokens(f.data_source or "")))]  # fmt: skip
    return cut[0].key if len(cut) == 1 else None


# --- G. forms ------------------------------------------------------------------------------------


def propose_forms(
    llm: LLM,
    indicators: list[DraftIndicator],
    results: dict[str, DraftResult],
    keys_in_use: frozenset[str] = frozenset(),
) -> tuple[list[steps.ProposedForm], list[str]]:
    payload: dict[str, Any] = {
        "keys_in_use": sorted(keys_in_use),
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
        ],
    }
    refs = [i.ref for i in indicators]
    try:
        out = llm.run("propose_forms", steps.PROPOSE_FORMS, payload, steps.FormsProposal,
                      steps.check_forms(refs, keys_in_use))  # fmt: skip
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
    framework_blocks: set[tuple[str, str]] = set()
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
        framework_blocks.add((filename, block["id"]))
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

    # Forms the documents already contain come first; the AI only designs the missing ones.
    found = form_candidates(ir, framework_blocks)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        imported = list(pool.map(lambda c: import_form(llm, c), found))
    keys: set[str] = set()
    document_forms: list[steps.DocumentForm] = []
    for cand, (out, import_problems) in zip(found, imported, strict=True):
        problems += import_problems
        if out is not None:
            document_forms.append(to_document_form(out, cand, keys))
    left: list[DraftIndicator] = []
    for ind in indicators:
        key = match_form(ind.data_source or ind.raw["means_of_verification"], document_forms)
        if key is None:
            left.append(ind)
        else:
            next(f for f in document_forms if f.key == key).indicators.append(ind.ref)
    forms: list[steps.ProposedForm] = list(document_forms)
    if left:
        ai_forms, form_problems = propose_forms(llm, left, by_key, frozenset(keys))
        forms += ai_forms
        problems += form_problems
    schemas = {f.key: f.form_schema() for f in forms}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(pool.map(lambda i: propose_definition(llm, i, forms, schemas), indicators))

    draft = Draft(results, indicators, forms, questions, tables, problems)
    cross_check(draft)
    return draft
