"""Week 23: a quantized model on the same GPU, and the first comparison table.

Fixed names:
- the route `qwen3-8b-awq`, which vLLM serves as `Qwen/Qwen3-8B-AWQ`
- the result files of week 22 for this route
- the table evals/results/model_comparison.csv that notebooks/model_comparison.ipynb writes
"""

from __future__ import annotations

import pytest

from labkit.gateway import UPSTREAM_KEYS
from phase6_helpers import (
    CLAUDE,
    OPEN,
    QUANTIZED,
    QUANTIZED_UPSTREAM,
    ask,
    dataset_cases,
    events_text,
    load_problems,
    load_result,
    model_rows,
    openai_keys,
    row_problems,
    table_problems,
    tool_then_answers,
)

# ---- steps 2 and 3: the quantized model -----------------------------------------------------------


def test_the_gateway_has_a_route_for_the_quantized_model(gateway):
    status, body = gateway.admin("GET", "/model/info")
    names = {row.get("model_name") for row in body.get("data", [])} if status == 200 else set()
    assert QUANTIZED in names, (
        f"The gateway has no route `{QUANTIZED}`. Add it: the model `hosted_vllm/{QUANTIZED_UPSTREAM}` on the "
        "same pod (step 3)."
    )


def test_the_assistant_answers_with_the_quantized_model_through_the_gateway(client, fake_openai, gateway, monkeypatch):
    monkeypatch.setenv("CLAUDE_MODEL", QUANTIZED)
    cases = dataset_cases(1)
    fake_openai.always(tool_then_answers(cases))
    result = ask(client, cases[0]["question"])
    assert result.answer is not None, f"No answer from `{QUANTIZED}` through the gateway. Events: {events_text(result)}"
    models = {body.get("model") for body in fake_openai.requests}
    assert models == {QUANTIZED_UPSTREAM}, f"vLLM must get the model `{QUANTIZED_UPSTREAM}`, not {models}."
    assert openai_keys(fake_openai) == {UPSTREAM_KEYS["vllm"]}, "The route must send the key of vLLM."


def test_the_test_set_results_of_the_quantized_model():
    problems = row_problems(QUANTIZED, model_rows(QUANTIZED))
    assert not problems, f"The test set results are not complete: {problems[:10]}"


@pytest.mark.parametrize("route", [OPEN, QUANTIZED])
def test_the_load_test_result_and_the_gpu_memory_of_each_open_model(route):
    problems = load_problems(route, load_result(route))
    assert not problems, f"evals/results/load/{route}.json is not right: {problems}"


# ---- step 5: the table ------------------------------------------------------------------------------


def test_the_table_compares_the_hosted_the_open_and_the_quantized_model():
    problems = table_problems([CLAUDE, OPEN, QUANTIZED])
    assert not problems, f"evals/results/model_comparison.csv: {problems}"
