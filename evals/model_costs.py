"""Reference solution.

The cost of 1,000 requests of a model, for the comparison table of the exit test. Week 25.

notebooks/model_comparison.ipynb (in phases/phase-6-open-models/) calls these functions. In the
table, one request is one model call through the gateway:

- A hosted model costs its token prices. The result file of the test set (make model-testset)
  has, for each case, the cost of its calls (`cost_usd`, from the token prices in llm.py) and the
  number of its calls (`requests`). Run the test set with --no-cache: a replayed answer costs 0.
- An open model costs the hourly price of its GPU, whatever the number of tokens. The result file
  of the load test (make loadtest) has the requests per hour that the GPU served at each load.
"""

from __future__ import annotations

from typing import Any


def hosted_cost_per_1000(rows: list[dict[str, Any]]) -> float:
    """US dollars for 1,000 model calls: 1,000 times the cost of all rows divided by their calls.

    `rows` are the rows of a result file of the test set. Raise ValueError when the rows hold no
    model call.
    """
    calls = sum(row["requests"] for row in rows)
    if calls <= 0:
        raise ValueError("The rows hold no model call.")
    return 1000 * sum(row["cost_usd"] for row in rows) / calls


def best_requests_per_hour(load_result: dict[str, Any]) -> float:
    """The highest `requests_per_hour` of the loads of a load test result without errors.

    A load with errors does not count: a GPU that fails requests does not serve them. Raise
    ValueError when no load is without errors.
    """
    clean = [load["requests_per_hour"] for load in load_result["loads"] if load["errors"] == 0]
    if not clean:
        raise ValueError("No load of the load test is without errors.")
    return max(clean)


def gpu_cost_per_1000(price_per_hour: float, requests_per_hour: float) -> float:
    """US dollars for 1,000 model calls on a GPU that costs `price_per_hour` and serves `requests_per_hour`.

    Raise ValueError when requests_per_hour is not more than 0.
    """
    if requests_per_hour <= 0:
        raise ValueError("requests_per_hour must be more than 0.")
    return 1000 * price_per_hour / requests_per_hour
