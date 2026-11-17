# Phase 5 results

Write the numbers of your own runs here. The plan says to record the numbers of each check, and week 26 builds the architecture document from them. Write the machine on which you measured the times, for example "MacBook Pro, M3, 16 GB".

Machine:

## Setup

| Measure | Value |
| --- | --- |
| Time of the first `make up` with Phase 5 (guardrails image build and model download) | |
| Time until Keycloak was healthy | |
| Time until the guardrails server was healthy, first start | |
| Time until the guardrails server was healthy, later start | |
| Memory of Keycloak, idle (`docker stats`) | |
| Memory of the guardrails server, after some checks | |
| Disk space of the Keycloak image, the guardrails image and the model | |

## Week 18: the attack suite

| Measure | Value |
| --- | --- |
| Poisoned documents in English | |
| Poisoned documents in Arabic | |
| Poisoned catalogue entries | |
| Chunks of the poisoned documents (`make poison`) | |
| Cases in `evals/attacks.jsonl` | |
| Cases that you corrected by hand after the draft of Claude Code | |

From `make attacks LABEL=week18 MODEL=obedient`. Date of the run:

| Kind | Cases | Passed | Pass rate |
| --- | --- | --- | --- |
| `direct` | | | |
| `poisoned_document` | | | |
| `tool_result` | | | |
| `exfiltration` | | | |
| All | | | |

| Measure | Value |
| --- | --- |
| Time of the run | |
| A case that failed, and its reasons (from the result file) | |

Optional: the same cases on the real model (`make attacks LABEL=week18-claude`). Date of the run:

| Kind | Cases | Passed | Pass rate |
| --- | --- | --- | --- |
| `direct` | | | |
| `poisoned_document` | | | |
| `tool_result` | | | |
| `exfiltration` | | | |
| All | | | |

| Measure | Value |
| --- | --- |
| Cost of the run (USD) | |
| A case that the real model resisted and the obedient model did not | |

From `make check WEEK=18`.

| Measure | Value |
| --- | --- |
| Checks passed, of 9 | |
| Time of the checks | |
| Cost of `make check-live WEEK=18` (USD) | |
| Result of the CI job on a pull request | |
| Pass rate of each kind in the CI run | |
| Time of the CI job | |

## Week 19: sign-in and per-user permissions

The claims of the tokens, from `make token AS=<user> ARGS=--claims`.

| User | `aud` | `scope` | `groups` |
| --- | --- | --- | --- |
| `viewer` | | | |
| `analyst` | | | |
| `auditor` | | | |

What each user got. Write the rows of `data.population` through `run_sql`, and whether `search_documents` returned passages of the Business Confidence documents.

| User | Rows of `data.population` | Business Confidence passages |
| --- | --- | --- |
| `viewer` | | |
| `analyst` | | |
| `auditor` | | |

| Measure | Value |
| --- | --- |
| HTTP status of `/ask` without a token | |
| HTTP status of `/ask` with an expired token | |
| HTTP status of an MCP server without a token | |
| The roles that run the queries of users (SQL server, document search) | |
| How the database session carries the user | |
| How you stopped a query of the model from changing the user of the session | |

From `make check WEEK=19`.

| Measure | Value |
| --- | --- |
| Checks passed, of 36 | |
| Time of the checks | |
| Checks of Phases 1 to 4 passed with sign-in on | |

## Week 20: the design pattern and the input and output checks

| Measure | Value |
| --- | --- |
| The pattern that you applied, and why | |
| The tool results that count as untrusted | |
| The tools that wait for an approval after untrusted content | |
| The reason that an approval event shows (an example) | |

The guardrails server, from your own calls of `/v1/checks`.

| Measure | Value |
| --- | --- |
| Time of the first input check after a start (s) | |
| Time of a later input check (s) | |
| Time of an output check (s) | |

Your test on Arabic text (`evals/guardrails_arabic.jsonl`).

| Measure | Value |
| --- | --- |
| Test strings | |
| Strings in Arabic | |
| Misses (`should` and `result` differ) | |

The misses.

| ID | Rail | What the check should do | What the server did | Why it misses |
| --- | --- | --- | --- | --- |
| | | | | |
| | | | | |
| | | | | |

From `make attacks LABEL=week20 MODEL=obedient`. Date of the run:

| Kind | Cases | Passed in week 18 | Pass rate in week 18 | Passed in week 20 | Pass rate in week 20 |
| --- | --- | --- | --- | --- | --- |
| `direct` | | | | | |
| `poisoned_document` | | | | | |
| `tool_result` | | | | | |
| `exfiltration` | | | | | |
| All | | | | | |

The cases that still fail (`evals/attack_notes.jsonl`).

| Case ID | Kind | Why it gets past the defences | What would stop it |
| --- | --- | --- | --- |
| | | | |
| | | | |

Optional: the real model again (`make attacks LABEL=week20-claude`).

| Kind | Pass rate, week 18 | Pass rate, week 20 |
| --- | --- | --- |
| `direct` | | |
| `poisoned_document` | | |
| `tool_result` | | |
| `exfiltration` | | |

| Measure | Value |
| --- | --- |
| Cost of the run (USD) | |

From `make check WEEK=20`.

| Measure | Value |
| --- | --- |
| Checks passed, of 16 | |
| Time of the checks | |

## Exit test: the attack pass rate in CI

Date:

| Measure | Value |
| --- | --- |
| `make attack-report`: passed or failed | |
| Kinds with a higher pass rate than in week 18, of 4 | |
| Result of the CI job with `make attack-report ARGS="--before week18 --after ci"` | |
| Pass rate of each kind in that CI run | |
| Time of the CI job | |
| Checks of Phase 5 passed (`make check PHASE=5`) | |
| Checks of Phases 1, 2, 3 and 4 passed at the end of the phase | |
