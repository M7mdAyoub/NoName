"""Forms already in the uploaded documents become the draft's forms; the AI fills the gaps."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.ai import pipeline, steps
from app.ai.mock import MockLLM, map_layout
from app.ingestion import parse_file
from app.ingestion.ir import cell_text
from app.schemas.form import FormField, validate_form

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
WITH_FORMS = "sample_logframe_with_forms.xlsx"


def _ir(name: str) -> dict[str, Any]:
    return {"files": [parse_file(FIXTURES / name, name)]}


def _fields(form: steps.ProposedForm) -> dict[str, FormField]:
    return {f.id: f for f in form.fields}


def test_form_sheets_become_forms_and_feed_their_indicators() -> None:
    draft = pipeline.extract(MockLLM(), _ir(WITH_FORMS))
    forms = {f.key: f for f in draft.forms}
    documents = {k for k, f in forms.items() if isinstance(f, steps.DocumentForm)}
    assert documents == {"follow_up_survey", "training_attendance_records"}
    assert len(forms) == 7  # the other five data sources still get an AI form
    assert all(not validate_form(f.form_schema()) for f in forms.values())

    survey = forms["follow_up_survey"]
    schema = survey.form_schema()
    assert (schema.origin, schema.source) == ("document", f"{WITH_FORMS} > Follow-up survey")
    assert forms["household_survey"].form_schema().origin == "ai"
    fields = _fields(survey)
    assert list(fields) == ["respondent_id", "sex", "since_the_training_have_you_applied_the",
                            "which_practices_have_you_applied_select",
                            "how_many_people_in_your_household_work_o", "comments"]  # fmt: skip
    applied = fields["since_the_training_have_you_applied_the"]
    assert applied.label == "Since the training, have you applied the new practices?"  # "1." gone
    assert applied.type == "select_one" and applied.section == "SECTION A - PRACTICES"
    assert [(o.value, o.label) for o in applied.options] == [
        ("yes_regularly", "Yes, regularly"), ("yes_sometimes", "Yes, sometimes"), ("no", "No")]  # fmt: skip
    assert fields["which_practices_have_you_applied_select"].type == "select_multiple"
    assert fields["how_many_people_in_your_household_work_o"].type == "integer"
    assert fields["comments"].qualitative and fields["comments"].section == "SECTION B - CLOSING"
    assert fields["respondent_id"].pii and survey.entity_key_field == "respondent_id"
    attendance = _fields(forms["training_attendance_records"])
    assert [o.value for o in attendance["sex"].options] == ["female", "male"]  # "Female / Male"
    assert attendance["session_date"].type == "date"
    assert attendance["participant_name"].pii and attendance["phone_number"].pii

    # indicators are linked to the form their data source names, and rules read its questions
    by_name = {i.name: i for i in draft.indicators}
    ratio = by_name["% of trained women applying new practices"]
    assert ratio.ref in survey.indicators
    assert ratio.definition is not None and not ratio.definition_errors
    numerator = ratio.definition.model_dump(exclude_none=True)["numerator"]["count"]
    assert numerator["form"] == "follow_up_survey"
    assert {"field": "since_the_training_have_you_applied_the", "op": "in",
            "value": ["yes_regularly", "yes_sometimes"]} in numerator["where"]["all"]  # fmt: skip
    women = by_name["Number of women completing agri-food training"]
    assert women.ref in forms["training_attendance_records"].indicators


def test_the_plain_sample_has_no_document_forms() -> None:
    draft = pipeline.extract(MockLLM(), _ir("sample_logframe.xlsx"))
    assert not any(isinstance(f, steps.DocumentForm) for f in draft.forms)
    assert len(draft.forms) == 7  # the assumptions table and the notes are not forms


def _form(key: str, data_source: str, cut: bool = False) -> steps.DocumentForm:
    return steps.DocumentForm(key=key, title=data_source, data_source=data_source, indicators=[],
                              fields=[], source="f.xlsx > x", cut_name=cut)  # fmt: skip


def test_data_sources_are_matched_to_document_forms() -> None:
    forms = [_form("survey", "Follow-up survey"), _form("reg", "Market registration form"),
             _form("market", "Market form"),
             _form("long", "Production-support_Partnership_", cut=True)]  # fmt: skip
    assert pipeline.match_form("Follow-up survey", forms) == "survey"
    assert pipeline.match_form("follow_up_survey_form (Q1)", forms) == "survey"
    assert pipeline.match_form("Market_registration_Form", forms) == "reg"
    assert pipeline.match_form("Market", forms) == "market"  # not the registration form
    assert pipeline.match_form("Production-support_Partnership_tracking_form", forms) == "long"
    assert pipeline.match_form("Household survey", forms) is None
    assert pipeline.match_form(None, forms) is None


@pytest.mark.parametrize(
    ("code", "parent", "under"),
    [("1.1", "1", True), ("10", "1", False), ("A1", "A", True), ("X-SO1-A", "X-SO1-0", True),
     ("X-SO1-A1.2", "X-SO1-A1", True), ("X-SO10-A", "X-SO1-0", False), ("1", "1", False)],
)  # fmt: skip
def test_code_hierarchy(code: str, parent: str, under: bool) -> None:
    assert pipeline._code_under(code, parent) is under


def test_imported_questions_must_come_from_the_document() -> None:
    check = steps.check_imported("Respondent ID | (open text)\nSex | Female\nMale")
    form = steps.ImportedForm.model_validate({"is_form": True, "entity_key": "Name", "questions": [
        {"label": "Respondent ID", "type": "text"},
        {"label": "Age group", "type": "select_one", "options": ["Under 30"]},
        {"label": "Sex", "type": "text", "options": ["Female", "Male"]}]})  # fmt: skip
    assert check(form) == [
        "question 'Age group' is not in the document: keep its wording",
        "question 'Age group': select_one needs at least two options",
        "question 'Sex': options are only for select types",
        "entity_key must be the label of one of the questions",
    ]
    assert check(steps.ImportedForm(is_form=False)) == []


def test_cells_keep_their_line_breaks() -> None:
    assert cell_text("  Yes,  regularly \n\n No ") == "Yes, regularly\nNo"


def test_layout_prefers_the_final_target_and_reads_a_type_column() -> None:
    header = ["No.", "Result", "Indicator", "Type", "Target (to be deleted)", "Q1 Target",
              "Final target", "Baseline"]  # fmt: skip
    layout = steps.TableLayout.model_validate(map_layout({"rows": [header]}))
    assert (layout.column("target"), layout.column("level"), layout.column("baseline")) == (6, 3, 7)
