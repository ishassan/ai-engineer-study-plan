# Phase 3 results

Write the numbers of your own runs here. The plan says to record the numbers of each check, and week 26 builds the architecture document from them. Write the machine on which you measured the times, for example "MacBook Pro, M3, 16 GB".

Machine:

## Week 8: Langfuse and tracing

| Measure | Value |
| --- | --- |
| Langfuse release (image tag) | |
| Time of the first image download | |
| Time of the first start, to healthy | |
| Memory of the six Langfuse services, idle (`docker stats`) | |
| Memory of the whole stack, idle | |

One request in Langfuse, from the trace of `make ask` or of the week 8 checks.

| Measure | Value |
| --- | --- |
| Question | |
| Observations in the trace | |
| Generations | |
| Tool observations | |
| Retriever observations | |
| Total tokens (input / output) | |
| Cost in Langfuse (USD) | |
| `cost_usd` of the `done` event (USD) | |
| Latency of the trace (s) | |

| Measure | Langfuse on | Langfuse stopped |
| --- | --- | --- |
| Time of `make check PHASE=1` | | |
| Checks of Phase 1 passed, of 37 | | |
| Checks of Phase 2 passed, of 50 | | |

## Week 9: the test set and the error analysis

| Measure | Value |
| --- | --- |
| Cases in `evals/testset.jsonl` | |
| English cases | |
| Arabic cases | |
| Cases about datasets | |
| Cases about the documents | |
| Questions that you corrected by hand after the draft of Claude Code | |

From `make testset ARGS="--no-cache"`. Date of the run:

| Measure | Value |
| --- | --- |
| Cases run | |
| `code_pass` | |
| Requests to Claude | |
| Total cost (USD) | |
| Median latency of one case (s) | |

From the notebook `error_analysis.ipynb`.

| Measure | Value |
| --- | --- |
| Traces read | |
| Failures | |
| Expected IDs that were wrong in the test set | |
| Items in the Langfuse dataset `assistant-failures` | |

Failure categories, from `evals/failure_categories.csv`, largest first.

| Category | Count | Description | Example case IDs |
| --- | --- | --- | --- |
| | | | |
| | | | |
| | | | |
| | | | |
| | | | |

## Week 10: the grader

| Measure | Value |
| --- | --- |
| Failure category of the grader | |
| Outputs labelled | |
| Labelled as pass | |
| Labelled as fail | |
| Cost of one run of the grader on the labels (USD) | |

Each run of parts 2 and 3 of the notebook `grader_agreement.ipynb`.

| Run | Change of the rubric (or of a label) | True positive rate | True negative rate |
| --- | --- | --- | --- |
| 1 | first version | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |

| Measure | Value |
| --- | --- |
| Final true positive rate | |
| Final true negative rate | |
| Disagreements where your label was wrong | |
| Disagreements where the rubric was unclear | |

## Week 11: the suite and CI

| Measure | Value |
| --- | --- |
| Cases in the CI subset | |
| Dataset cases in the subset | |
| Document cases in the subset | |
| Size of `data/snapshot/chunks.sql.gz` | |
| Time of `make snapshot` | |

Thresholds and scores of `make evals ARGS="-rA"` on your machine, with your final code.

| Score | Threshold | Run 1 | Run 2 | Run 3 |
| --- | --- | --- | --- | --- |
| Dataset IDs | | | | |
| Citations | | | | |
| Grader | | | | |

| Measure | Value |
| --- | --- |
| Time of `make evals` on your machine | |
| Cost of one `make evals` (USD, from `logs/requests.jsonl`) | |
| Time of the first CI run on the default branch (model download) | |
| Time of a CI run with the model files from the cache | |
| Cost of one CI run (USD) | |

## Exit test: CI blocks a deliberately bad prompt change

Link to the pull request:

Date:

| Score | Threshold | Before the change | After the change |
| --- | --- | --- | --- |
| Dataset IDs | | | |
| Citations | | | |
| Grader | | | |
| Result of the job `evals` | | | |

| Measure | Value |
| --- | --- |
| The bad change, in one sentence | |
| True positive rate of the grader with your labels | |
| True negative rate of the grader with your labels | |
| Labels that the rates come from | |
