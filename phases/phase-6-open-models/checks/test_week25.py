"""Week 25: the adapter beside the base model, and the exit test.

Fixed names:
- the route `qwen3-8b-arabic` (vLLM serves the adapter under the name of its --lora-modules flag)
- evals/model_costs.py with hosted_cost_per_1000(), best_requests_per_hour() and gpu_cost_per_1000()
- the result files of weeks 22 and 23 for the four routes
- the table evals/results/model_comparison.csv

The training script (train/train_lora.py) needs PyTorch, so no offline check runs it. Its smoke
mode (`make train-smoke`) is your check before you rent the GPU.
"""

from __future__ import annotations

import pytest

from labkit.gateway import UPSTREAM_KEYS
from phase6_helpers import (
    CLAUDE,
    FINE_TUNED,
    OPEN,
    OPEN_UPSTREAM,
    QUANTIZED,
    QUANTIZED_UPSTREAM,
    ask,
    comparison_table,
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

ROUTES = [CLAUDE, OPEN, QUANTIZED, FINE_TUNED]


# ---- step 3: the adapter in the gateway -----------------------------------------------------------


def test_the_gateway_has_a_route_for_the_adapter(gateway):
    status, body = gateway.admin("GET", "/model/info")
    names = {row.get("model_name") for row in body.get("data", [])} if status == 200 else set()
    assert FINE_TUNED in names, (
        f"The gateway has no route `{FINE_TUNED}`. Add it: the model `hosted_vllm/<name of the adapter in "
        "--lora-modules>`, on the same pod as the base model (step 3)."
    )


def test_the_assistant_answers_with_the_adapter_through_the_gateway(client, fake_openai, gateway, monkeypatch):
    monkeypatch.setenv("CLAUDE_MODEL", FINE_TUNED)
    cases = dataset_cases(1)
    fake_openai.always(tool_then_answers(cases))
    result = ask(client, cases[0]["question"])
    assert result.answer is not None, f"No answer from `{FINE_TUNED}` through the gateway. Events: {events_text(result)}"
    models = {body.get("model") for body in fake_openai.requests}
    assert len(models) == 1 and not models & {OPEN_UPSTREAM, QUANTIZED_UPSTREAM}, (
        f"vLLM must get the name of the adapter, not the base model: {models}. A request for the base model "
        "does not use the adapter."
    )
    assert openai_keys(fake_openai) == {UPSTREAM_KEYS["vllm"]}, "The route must send the key of vLLM."


def test_the_results_of_the_adapter():
    problems = row_problems(FINE_TUNED, model_rows(FINE_TUNED)) + load_problems(FINE_TUNED, load_result(FINE_TUNED))
    assert not problems, f"The results of the adapter are not complete: {problems[:10]}"


# ---- step 4: the cost functions ---------------------------------------------------------------------


def costs():
    from evals import model_costs

    return model_costs


def test_the_cost_of_a_hosted_model_comes_from_its_calls():
    rows = [{"cost_usd": 0.004, "requests": 2}, {"cost_usd": 0.002, "requests": 1}, {"cost_usd": 0.0, "requests": 1}]
    assert costs().hosted_cost_per_1000(rows) == pytest.approx(1.5), (
        "hosted_cost_per_1000: 1,000 times the cost of all rows divided by all their calls (0.006 / 4 calls: $1.50)."
    )
    with pytest.raises(ValueError):
        costs().hosted_cost_per_1000([{"cost_usd": 0.0, "requests": 0}])


def test_the_best_load_is_the_fastest_load_without_errors():
    result = {"loads": [
        {"concurrency": 1, "errors": 0, "requests_per_hour": 900.0},
        {"concurrency": 8, "errors": 0, "requests_per_hour": 5000.0},
        {"concurrency": 32, "errors": 3, "requests_per_hour": 9000.0},
    ]}
    assert costs().best_requests_per_hour(result) == pytest.approx(5000.0), (
        "best_requests_per_hour: the highest requests_per_hour of the loads without errors."
    )
    with pytest.raises(ValueError):
        costs().best_requests_per_hour({"loads": [{"concurrency": 1, "errors": 1, "requests_per_hour": 10.0}]})


def test_the_cost_of_an_open_model_comes_from_the_gpu_hour():
    assert costs().gpu_cost_per_1000(0.59, 6000.0) == pytest.approx(0.59 / 6), (
        "gpu_cost_per_1000: a GPU of $0.59 an hour that serves 6,000 requests an hour costs $0.0983 for 1,000."
    )
    assert costs().gpu_cost_per_1000(0.69, 1000.0) == pytest.approx(0.69)
    with pytest.raises(ValueError):
        costs().gpu_cost_per_1000(0.59, 0.0)


# ---- step 4: the exit test --------------------------------------------------------------------------


def test_the_exit_table_compares_the_four_models_for_quality_and_latency():
    problems = table_problems(ROUTES)
    assert not problems, f"evals/results/model_comparison.csv: {problems}"


@pytest.mark.parametrize("route", ROUTES)
def test_the_exit_table_has_the_cost_of_1000_requests(route):
    row = comparison_table().get(route)
    assert row is not None, f"The table has no row for {route}. Run the notebook again."
    try:
        found = float(row.get("cost_per_1000_requests") or "nan")
    except ValueError:
        found = float("nan")
    if route == CLAUDE:
        expected = costs().hosted_cost_per_1000(model_rows(route))
    else:
        result = load_result(route)
        expected = costs().gpu_cost_per_1000(result["gpu_price_per_hour"], costs().best_requests_per_hour(result))
    assert found == pytest.approx(round(expected, 4), abs=1e-4), (
        f"{route}: the cost for 1,000 requests is {row.get('cost_per_1000_requests')!r} in the table, but "
        f"{expected:.4f} from the result files. Write evals/model_costs.py and run the notebook again."
    )
