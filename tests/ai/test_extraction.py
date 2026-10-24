"""M2: IR -> draft with the mock LLM, the retry-with-feedback loop and the HTTP client."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx
import make_samples
import pytest

from app.ai import pipeline
from app.ai.llm import LLM, LLMError, OpenAICompatibleLLM
from app.ai.mock import MockLLM
from app.ai.steps import TableLayout, check_layout
from app.config import Settings
from app.ingestion import parse_file

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _ir(*names: str) -> dict[str, Any]:
    return {"files": [parse_file(FIXTURES / n, n) for n in names]}


def test_xlsx_framework_becomes_a_complete_valid_draft() -> None:
    draft = pipeline.extract(MockLLM(), _ir("sample_logframe.xlsx"))

    # Results: the distinct (level, code, statement) rows of the sample, as a tree
    expected = list(dict.fromkeys((r[0], r[1], r[2]) for r in make_samples.ROWS))
    assert [(r.level_name, r.code, r.statement) for r in draft.results] == expected
    code_of = {r.key: r.code for r in draft.results}
    parents = {r.code: code_of.get(r.parent_key or "") for r in draft.results}
    assert parents == {"0": None, "1": "0", "1.1": "1", "1.2": "1", "2": "0", "2.1": "2"}

    # Indicators: every row, under the right result, with numbers parsed and kinds set
    assert [i.name for i in draft.indicators] == [r[3] for r in make_samples.ROWS]
    assert [code_of[i.result_key] for i in draft.indicators] == [r[1] for r in make_samples.ROWS]
    assert [i.kind for i in draft.indicators] == [
        "average", "count", "ratio", "count", "count", "sum", "milestone"]  # fmt: skip
    assert [(i.baseline, i.target) for i in draft.indicators] == [
        (310, 400), (0, 400), (0, 60), (0, 80), (0, 250), (12000, 50000), (0, 1)]  # fmt: skip
    assert [i.data_source for i in draft.indicators] == [r[7] for r in make_samples.ROWS]

    # Forms: one per data source, each feeding its indicators; every definition is valid
    assert len(draft.forms) == len({r[7] for r in make_samples.ROWS})
    assert sorted(ref for f in draft.forms for ref in f.indicators) == sorted(
        i.ref for i in draft.indicators
    )
    assert all(i.definition is not None and i.definition_errors == [] for i in draft.indicators)
    women = draft.indicators[1].definition
    assert women is not None and women.count is not None and women.count.unit == "entity"
    assert draft.questions  # at least the ratio's denominator
    assert draft.problems == []
    assert [t["framework"] for t in draft.tables] == [True, False]  # assumptions table ignored


@pytest.mark.parametrize("name", ["sample_logframe.csv", "sample_logframe.docx",
                                  "sample_logframe.pdf"])  # fmt: skip
def test_other_formats_give_the_same_indicators(name: str) -> None:
    draft = pipeline.extract(MockLLM(), _ir(name))
    assert [i.name[:48] for i in draft.indicators] == [r[3][:48] for r in make_samples.ROWS]
    assert len(draft.results) == 6
    assert all(i.definition is not None and not i.definition_errors for i in draft.indicators)


def test_several_files_use_the_richest_framework_table() -> None:
    draft = pipeline.extract(MockLLM(), _ir("sample_logframe.pdf", "sample_logframe.xlsx"))
    used = [t for t in draft.tables if t.get("used")]
    assert [t["file"] for t in used] == ["sample_logframe.xlsx"]
    assert len(draft.indicators) == 7 and "ignored" in draft.problems[0]


def test_no_framework_table_is_an_error() -> None:
    ir = {"files": [{"source": {"filename": "x.csv"}, "blocks": [
        {"id": "b1", "kind": "table", "rows": [["Assumption", "Risk"], ["Stable", "Low"]]}]}]}  # fmt: skip
    with pytest.raises(pipeline.ExtractionError, match="no results framework"):
        pipeline.extract(MockLLM(), ir)


class ScriptedLLM(LLM):
    """Returns the given answers in order and records what it was sent."""

    mode = "scripted"

    def __init__(self, answers: list[str]) -> None:
        super().__init__()
        self.answers = answers
        self.sent: list[list[dict[str, str]]] = []

    def _complete(self, step: str, messages: list[dict[str, str]], schema: dict[str, Any],
                  payload: Any) -> str:  # fmt: skip
        self.sent.append(list(messages))
        return self.answers.pop(0)


ROWS = [["Code", "Indicator"], ["1", "Number of x"]]


def test_invalid_output_is_sent_back_and_retried() -> None:
    good = {"is_framework": True, "columns": [{"index": 0, "role": "result_code"},
                                              {"index": 1, "role": "indicator"}]}  # fmt: skip
    llm = ScriptedLLM([
        "not json",
        json.dumps({"is_framework": True, "columns": [{"index": 5, "role": "indicator"}]}),
        "```json\n" + json.dumps(good) + "\n```",
    ])  # fmt: skip
    out = llm.run("map_layout", "instr", {"rows": ROWS}, TableLayout, check_layout(ROWS))
    assert out.column("indicator") == 1
    assert llm.calls == {"map_layout": 3}
    feedback = llm.sent[2][-1]["content"]
    assert "column indices must be below 2" in feedback
    assert "INPUT>>>" in llm.sent[0][1]["content"]  # the document is wrapped as data


def test_after_three_failures_the_last_parsed_output_is_kept() -> None:
    bad = json.dumps({"is_framework": True, "columns": [{"index": 0, "role": "unit"}]})
    llm = ScriptedLLM([bad, bad, bad])
    with pytest.raises(LLMError) as info:
        llm.run("map_layout", "instr", {"rows": ROWS}, TableLayout, check_layout(ROWS))
    assert isinstance(info.value.last, TableLayout)
    assert any("'indicator' column" in e for e in info.value.errors)
    assert llm.failures == {"map_layout": 1}


def test_an_invalid_definition_becomes_an_open_question() -> None:
    class BrokenDefinitions(MockLLM):
        def _complete(self, step: str, messages: list[dict[str, str]], schema: dict[str, Any],
                      payload: Any) -> str:  # fmt: skip
            if step == "propose_definition":
                return json.dumps({"kind": payload["indicator"]["kind"] or "count",
                                   "count": {"form": "missing_form"}})  # fmt: skip
            return super()._complete(step, messages, schema, payload)

    draft = pipeline.extract(BrokenDefinitions(), _ir("sample_logframe.csv"))
    count = draft.indicators[1]  # "Number of women ..." keeps its (invalid) count definition
    assert count.definition is not None
    assert any("does not exist" in e for e in count.definition_errors)
    asked = [q for ref, q in draft.questions if ref == count.ref]
    assert any("invalid" in q for q in asked)
    average = draft.indicators[0]  # a count block for an average indicator does not even parse
    assert average.definition is None
    assert any(ref == average.ref and "No calculation rule" in q for ref, q in draft.questions)


def test_openai_compatible_client_sends_a_json_schema_request() -> None:
    seen: list[dict[str, Any]] = []
    answer = {"is_framework": False, "columns": []}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"url": str(request.url), "auth": request.headers["authorization"],
                     "body": json.loads(request.content)})  # fmt: skip
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})

    settings = Settings(app_env="test", llm_base_url="http://llm.local/v1/",
                        llm_model_extract="qwen", llm_api_key="k")  # fmt: skip
    llm = OpenAICompatibleLLM(settings, transport=httpx.MockTransport(handler))
    out = llm.run("map_layout", "instr", {"rows": ROWS}, TableLayout, check_layout(ROWS))
    llm.close()
    assert out.is_framework is False
    body = seen[0]["body"]
    assert seen[0]["url"] == "http://llm.local/v1/chat/completions"
    assert seen[0]["auth"] == "Bearer k"
    assert body["model"] == "qwen" and body["temperature"] == 0
    assert body["response_format"]["json_schema"]["schema"]["title"] == "TableLayout"


@pytest.mark.skipif(not os.environ.get("LLM_BASE_URL"), reason="set LLM_BASE_URL to test a model")
def test_real_endpoint_extracts_the_sample() -> None:  # pragma: no cover - needs a model
    settings = Settings(app_env="test", llm_mode="real")
    llm = OpenAICompatibleLLM(settings)
    try:
        draft = pipeline.extract(llm, _ir("sample_logframe.xlsx"), settings.llm_max_concurrency)
    finally:
        llm.close()
    assert len(draft.results) == 6 and len(draft.indicators) == 7
    assert sum(i.definition is not None and not i.definition_errors for i in draft.indicators) >= 5
