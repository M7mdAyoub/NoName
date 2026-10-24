"""Mock LLM: deterministic, keyword-based answers for every extraction step.

It answers from the step's input payload (not the prompt text) and goes through the same
validation and checks as a real model. Heuristics are generic (column titles, units, the wording
"number of", "% of", "average", "total"), nothing project-specific. Good enough to demo and test
the whole flow without a model; a real model does better on unusual documents.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from app.ai.llm import LLM
from app.schemas.form import slugify

# --- map_layout ----------------------------------------------------------------------------------

_ROLE_WORDS: list[tuple[str, tuple[str, ...]]] = [
    ("indicator", ("indicator",)),
    ("means_of_verification", ("verification", "data source", "source", "mov")),
    ("baseline", ("baseline",)),
    ("target", ("target",)),
    ("frequency", ("frequency", "periodicity")),
    ("unit", ("unit",)),
    ("level", ("level",)),
    ("result_code", ("code", "ref", "no.", "#")),
    ("result_statement", ("result", "statement", "objective", "narrative", "outcome", "output")),
]


_LEVEL_TITLES = {"type", "result type", "type of result", "results level", "hierarchy"}
_PREFERRED = ("final", "overall", "total", "end", "life of", "lop", "cumulative")
_OBSOLETE = ("deleted", "obsolete", "old", "previous", "draft")


def _role(title: str) -> str | None:
    text = title.lower().strip()
    if not text:
        return None
    if text in _LEVEL_TITLES:
        return "level"
    for role, words in _ROLE_WORDS:
        if any(w in text for w in words):
            return role
    return None


def _preference(title: str) -> int:
    """Among columns with the same role: final/overall ones first, obsolete ones last."""
    text = title.lower()
    if any(w in text for w in _OBSOLETE):
        return -1
    return 1 if any(w in text for w in _PREFERRED) else 0


def map_layout(payload: dict[str, Any]) -> dict[str, Any]:
    rows: list[list[str]] = payload["rows"]
    for header_row, row in enumerate(rows[:5]):
        best: dict[str, tuple[int, int]] = {}  # role -> (preference, -index)
        for index, title in enumerate(row):
            role = _role(title)
            if role and (role not in best or (_preference(title), -index) > best[role]):
                best[role] = (_preference(title), -index)
        used = set(best)
        columns: list[dict[str, Any]] = [
            {"index": -neg_index, "role": role}
            for role, (_, neg_index) in sorted(best.items(), key=lambda kv: -kv[1][1])
        ]
        if len(columns) >= 2:
            framework = "indicator" in used and bool({"result_statement", "result_code"} & used)
            return {"is_framework": framework, "header_row": header_row, "columns": columns}
    return {"is_framework": False, "header_row": 0, "columns": []}


# --- normalize_indicator -------------------------------------------------------------------------

_YES = {"yes", "done", "achieved", "true", "y"}
_NO = {"no", "not done", "not achieved", "false", "n", "none"}
_NUMBER = re.compile(r"^-?\d+(?:[.,]\d+)?$")


def _number(value: str) -> float | None:
    text = value.strip().replace(" ", "").rstrip("%")
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", text):
        text = text.replace(",", "")
    return float(text.replace(",", ".")) if _NUMBER.match(text) else None


def _kind(name: str, unit: str, baseline: str, target: str) -> str | None:
    lower, unit_l = name.lower(), unit.lower()
    yes_no = {baseline.lower(), target.lower()} <= _YES | _NO | {""}
    if (unit_l == "milestone" or yes_no) and (baseline or target):
        return "milestone"
    if unit_l in ("%", "percent", "percentage") or lower.startswith(
        ("%", "percentage", "share", "proportion", "rate")
    ):
        return "ratio"
    if lower.startswith(("average", "mean", "median")):
        return "average"
    if lower.startswith(("total", "amount", "value", "volume", "sum")):
        return "sum"
    if lower.startswith(("number", "no.", "#", "count")):
        return "count"
    return None


def normalize_indicator(payload: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, str] = payload["row"]
    name, unit = row["name"].strip(), row["unit"].strip()
    kind = _kind(name, unit, row["baseline"].strip(), row["target"].strip())
    if "milestone" in (payload["result"]["level"] or "").lower():
        kind = "milestone"  # the framework says so in its level/type column
    questions: list[str] = []
    values: dict[str, float | None] = {}
    for part in ("baseline", "target"):
        cell = row[part].strip()
        if kind == "milestone" and cell.lower() in _YES | _NO:
            values[part] = 1.0 if cell.lower() in _YES else 0.0
            continue
        values[part] = _number(cell)
        if values[part] is None:
            questions.append(f"What is the {part} of '{name}'? The document gives "
                             + (f"'{cell}'." if cell else "none."))  # fmt: skip
    if kind is None:
        questions.append(f"How is '{name}' measured: a count, a total, an average, a percentage "
                         "or a milestone?")  # fmt: skip
    if kind == "ratio":
        questions.append(f"What is the denominator of '{name}'?")
    return {
        "name": name,
        "unit": None if unit.lower() == "milestone" else unit or None,
        "kind": kind,
        "baseline": values["baseline"],
        "target": values["target"],
        "frequency": row["frequency"].strip() or None,
        "data_source": row["means_of_verification"].strip() or None,
        "open_questions": questions,
    }


# --- propose_forms -------------------------------------------------------------------------------

PEOPLE = ("people", "person", "persons", "participant", "beneficiar", "women", "men", "youth",
          "farmer", "student", "household", "trainee", "member")  # fmt: skip
_LEAD = re.compile(
    r"^(%|percentage|proportion|share|rate|number|no\.|#|count|total|amount|value|volume|sum|"
    r"average|mean|median)(\s+of)?\s+",
    re.IGNORECASE,
)
_YES_NO = [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]
_SEX = [{"value": "female", "label": "Female"}, {"value": "male", "label": "Male"}]


slug = slugify


def measure_field(name: str) -> str:
    """The field id the mock gives the question behind an indicator (shared with definitions)."""
    return slug(_LEAD.sub("", name.strip()))


def _about_people(ind: dict[str, Any]) -> bool:
    text = f"{ind['name']} {ind.get('unit') or ''}".lower()
    return ind["kind"] in ("count", "ratio") and any(w in text for w in PEOPLE)


def _sex_filter(name: str) -> str | None:
    words = set(re.findall(r"[a-z]+", name.lower()))
    if words & {"women", "woman", "female", "girls"}:
        return "female"
    if words & {"men", "man", "male", "boys"}:
        return "male"
    return None


def propose_forms(payload: dict[str, Any]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for ind in payload["indicators"]:
        groups.setdefault(ind["data_source"] or "Project records", []).append(ind)
    forms = []
    used_keys: set[str] = set(payload.get("keys_in_use", []))
    for source, inds in groups.items():
        key = base = slug(source, 30)
        n = 2
        while key in used_keys:
            key, n = f"{base}_{n}", n + 1
        used_keys.add(key)
        fields: list[dict[str, Any]] = []
        people = any(_about_people(i) for i in inds)
        if people:
            fields.append({"id": "respondent_id", "type": "text", "label": "Respondent ID",
                           "required": True, "pii": True})  # fmt: skip
            fields.append({"id": "sex", "type": "select_one", "label": "Sex", "required": True,
                           "options": _SEX})  # fmt: skip
        for ind in inds:
            fid, label = measure_field(ind["name"]), _LEAD.sub("", ind["name"]).strip()
            if ind["kind"] in ("sum", "average"):
                field = {"id": fid, "type": "decimal", "label": label[:1].upper() + label[1:],
                         "required": True, "unit": ind["unit"], "constraints": {"min": 0}}  # fmt: skip
            elif ind["kind"] in ("ratio", "milestone"):
                field = {"id": fid, "type": "select_one", "label": label[:1].upper() + label[1:] + "?",
                         "required": True, "options": _YES_NO}  # fmt: skip
            else:
                continue  # counts need no extra question: every record (or person) counts
            if all(f["id"] != fid for f in fields):
                fields.append(field)
        if not fields:
            fields.append({"id": "notes", "type": "text", "label": "Notes", "qualitative": True})
        forms.append({
            "key": key,
            "title": source,
            "data_source": source,
            "indicators": [i["ref"] for i in inds],
            "entity_key_field": "respondent_id" if people else None,
            "fields": fields,
        })  # fmt: skip
    return {"forms": forms}


# --- propose_definition --------------------------------------------------------------------------


def propose_definition(payload: dict[str, Any]) -> dict[str, Any]:
    ind = payload["indicator"]
    form = payload["forms"][0]
    ids = {f["id"] for f in form["fields"]}
    fid = measure_field(ind["name"])
    entity = "entity" if form["entity_key_field"] else "record"
    sex = _sex_filter(ind["name"]) if "sex" in ids else None
    sex_where = {"field": "sex", "op": "eq", "value": sex} if sex else None
    breakdown = ["sex"] if "sex" in ids and not sex else []
    kind = ind["kind"] or "count"
    yes: dict[str, Any] = {"field": fid, "op": "eq", "value": "yes"}
    if fid not in ids:  # a form from the documents: use its question closest to the indicator
        if kind in ("sum", "average") and (num := _closest(ind["name"], form, NUMERIC)):
            fid = num["id"]
        elif kind in ("ratio", "milestone") and (q := _closest(ind["name"], form, YES_NO)):
            values = [v for v in q["options"] if _is_yes(v)]
            yes = {"field": q["id"], "op": "in", "value": values}
    defn: dict[str, Any] = {"schema_version": 1, "kind": kind}
    if kind == "count":
        defn["count"] = {"form": form["key"], "unit": entity, "where": sex_where}
    elif kind in ("sum", "average"):
        defn["value"] = {"form": form["key"], "field": fid}
    elif kind == "ratio":
        defn["numerator"] = {"count": {"form": form["key"], "unit": entity,
                                       "where": {"all": [sex_where, yes]} if sex_where else yes}}  # fmt: skip
        defn["denominator"] = {"count": {"form": form["key"], "unit": entity, "where": sex_where}}
        defn["scale"] = 100
    else:
        defn["milestone"] = {"form": form["key"], "achieved_when": yes}
    if kind in ("count", "ratio") and breakdown:
        defn["disaggregate_by"] = breakdown
    return defn


NUMERIC = ("integer", "decimal")
YES_NO = ("select_one",)


def _is_yes(value: str) -> bool:
    return value == "yes" or value.startswith("yes_")


def _words(text: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z]{3,}", text.lower())} - _STOP


def _closest(name: str, form: dict[str, Any], types: tuple[str, ...]) -> dict[str, Any] | None:
    """The form question sharing most words with the indicator name (selects need a yes)."""
    want = _words(name)
    scored = [
        (len(want & _words(f["label"])), -i, f)
        for i, f in enumerate(form["fields"])
        if f["type"] in types and (types != YES_NO or any(_is_yes(v) for v in f["options"]))
    ]
    best = max(scored, key=lambda s: s[:2], default=None)
    return best[2] if best and best[0] > 0 else None


# --- convert_form ----------------------------------------------------------------------------------

_FORM_TITLE_WORDS = ("form", "questionnaire", "survey", "registration", "register", "profile",
                     "checklist", "check list", "log", "intake", "follow up")  # fmt: skip
_TAG = re.compile(r"^[A-Za-z]{0,8}\d{0,3}$")  # short row tags like "All", "SO1", "Impact"
_SECTION = re.compile(r"^(section\b|part\b|[A-Z]\d*\.\s)", re.IGNORECASE)
_PII_WORDS = ("phone", "mobile", "email", "e-mail", "national id", "national_id", "id number",
              "passport", "address", "contact person")  # fmt: skip
_PERSON_NAME = re.compile(r"^(participant|respondent|farmer|beneficiary|person|full)?\s*name\b",
                          re.IGNORECASE)  # fmt: skip
_OPEN_TEXT = ("open text", "____", "<", "same list", "same option")
_INTEGER_WORDS = ("number of", "how many", "age", "capacity", "duration", "count", "number:")
_QUALITATIVE_WORDS = ("note", "comment", "describe", "explain", "why", "reason", "suggest")


def _split_options(spec: str) -> list[str]:
    lines = [line.strip(" /") for line in spec.split("\n")]
    parts = [p for p in lines if p and not p.lower().startswith("response options")]
    if len(parts) < 2 and parts:
        parts = [p.strip() for p in parts[0].split(" / ") if p.strip()]
    return parts if len(parts) >= 2 and all(len(p) <= 120 for p in parts) else []


def _question(cells: list[str]) -> tuple[str, str]:
    """(question, answer spec) of a row: skip a short leading tag, take the next cell after."""
    filled = [c for c in cells if c.strip()]
    if len(filled) >= 3 and _TAG.match(filled[0].strip()) and len(filled[1]) > len(filled[0]):
        filled = filled[1:]
    return filled[0].strip(), (filled[1].strip() if len(filled) > 1 else "")


def convert_form(payload: dict[str, Any]) -> dict[str, Any]:
    rows: list[list[str]] = payload["rows"]
    title = payload["title"]
    words = " " + " ".join(re.findall(r"[a-z]+", title.lower())) + " "
    looks_like_form = any(f" {w} " in words for w in _FORM_TITLE_WORDS)
    questions: list[dict[str, Any]] = []
    section: str | None = None
    entity: str | None = None
    for row in rows:
        filled = [c.strip() for c in row if c.strip()]
        if not filled:
            continue
        if len(set(filled)) == 1 and (filled[0].isupper() or _SECTION.match(filled[0])):
            # a merged section row arrives with its text copied into every cell
            section = filled[0]
            continue
        label, spec = _question(row)
        if label.lower() in ("question", "questions", "field", "item"):
            continue  # a header row
        lower, spec_l = label.lower(), spec.lower()
        options = [] if any(w in spec_l for w in _OPEN_TEXT) else _split_options(spec)
        multiple = "all that apply" in f"{lower} {spec_l}" or "select multiple" in spec_l
        pii = (
            any(w in lower for w in _PII_WORDS)
            or bool(_PERSON_NAME.match(label))
            or bool(re.search(r"\bid\b", lower))
        )
        if options and not pii:
            kind = "select_multiple" if multiple else "select_one"
            looks_like_form = True
        elif "date" in re.findall(r"[a-z]+", lower) and not pii:
            kind, options = "date", []
        elif not pii and any(w in f"{lower} {spec_l}" for w in _INTEGER_WORDS):
            kind, options = "integer", []
        else:
            kind, options = "text", []
        if label.endswith("?") or "open text" in spec_l:
            looks_like_form = True
        if entity is None and pii and re.search(r"\bid\b|_id\b", lower) and "valid" not in lower:
            entity = label
        questions.append({"label": label, "type": kind, "options": options, "pii": pii,
                          "required": label == entity, "section": section,
                          "qualitative": kind == "text" and not pii
                          and any(w in lower for w in _QUALITATIVE_WORDS)})  # fmt: skip
    if not looks_like_form or not questions:
        return {"is_form": False}
    return {"is_form": True, "title": title.replace("_", " ").strip(), "entity_key": entity,
            "questions": questions}  # fmt: skip


# --- propose_themes (qualitative) ----------------------------------------------------------------

_STOP = frozenset({"about", "after", "again", "also", "because", "been", "before", "being",
                   "both", "could", "from", "have", "into", "just", "many", "more", "most",
                   "much", "only", "other", "over", "said", "same", "should", "some", "such",
                   "than", "that", "their", "them", "then", "there", "these", "they", "this",
                   "those", "very", "want", "were", "what", "when", "where", "which", "while",
                   "with", "would", "your", "went", "asked"})  # fmt: skip
MOCK_THEMES = 5


def _stem(word: str) -> str:
    return word[:-1] if len(word) > 4 and word.endswith("s") and not word.endswith("ss") else word


def propose_themes(payload: dict[str, Any]) -> dict[str, Any]:
    """Greedy keyword themes: the word most answers share, then the next among the rest, ..."""
    words = {
        a["id"]: {_stem(w) for w in re.findall(r"[a-z]{4,}", a["text"].lower())} - _STOP
        for a in payload["answers"]
    }
    left = set(words)
    themes: list[dict[str, Any]] = []
    while left and len(themes) < MOCK_THEMES:
        freq: dict[str, int] = {}
        for i in left:
            for w in words[i]:
                freq[w] = freq.get(w, 0) + 1
        best = min(freq.items(), key=lambda kv: (-kv[1], kv[0]), default=None)
        if best is None or best[1] < 2:
            break
        ids = sorted(i for i in left if best[0] in words[i])
        themes.append({"name": best[0].capitalize(),
                       "description": f"Answers that mention '{best[0]}'.", "answers": ids})  # fmt: skip
        left -= set(ids)
    return {"themes": themes}


HANDLERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "map_layout": map_layout,
    "normalize_indicator": normalize_indicator,
    "propose_forms": propose_forms,
    "propose_definition": propose_definition,
    "convert_form": convert_form,
    "propose_themes": propose_themes,
}


class MockLLM(LLM):
    mode = "mock"
    model = "mock"

    def _complete(
        self, step: str, messages: list[dict[str, str]], schema: dict[str, Any], payload: Any
    ) -> str:
        return json.dumps(HANDLERS[step](payload))
