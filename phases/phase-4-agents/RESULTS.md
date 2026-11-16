# Phase 4 results

Write the numbers of your own runs here. The plan says to record the numbers of each check, and week 26 builds the architecture document from them. Write the machine on which you measured the times, for example "MacBook Pro, M3, 16 GB".

Machine:

## Setup

| Measure | Value |
| --- | --- |
| Time of the first `make up` with Phase 4 (image build) | |
| Checks of Phase 1 that failed after the copy of the given files, before the signature change, of 37 | |
| Checks of Phase 1 passed after the signature change, of 37 | |

## Week 12: memory by hand

From `make check WEEK=12`.

| Measure | Value |
| --- | --- |
| Checks passed, of 9 | |
| Time of the checks | |

Your own test of compaction with the real model, in one conversation.

| Measure | Value |
| --- | --- |
| `COMPACT_AT_TOKENS` for the test | |
| Questions in the conversation | |
| Question after which the first summary came | |
| Input tokens of the request before the summary | |
| Input tokens of the first request after the summary | |
| Did the answer after the summary use an earlier answer? | |
| Cost of the summary call (USD) | |

Your own test of the long-term memory.

| Measure | Value |
| --- | --- |
| The fact that the agent saved | |
| The question of the next conversation that used it | |
| Did another user get the fact? | |

## Week 13: planning by hand

From `make check WEEK=13`.

| Measure | Value |
| --- | --- |
| Checks passed, of 3 | |

A task with a failing step, with the real model and `AGENT_PLANNER=on`.

| Measure | Value |
| --- | --- |
| Task | |
| First plan | |
| Step that failed, and its error | |
| Changed plan | |
| Requests (`done.requests`) | |
| Cost (USD) | |
| Requests and cost of the same task with the planner off | |

## Week 14: the graph on Claude and OpenAI

From `make compare`. Date of the runs:

| Run | Cases | Score (`code_pass`) | Cost (USD) | Time of the run |
| --- | --- | --- | --- | --- |
| Hand-written loop, Claude | | | | |
| Graph, Claude | | | | |
| Graph, OpenAI | | | | |

From `make lines`.

| Code | Lines of code |
| --- | --- |
| Hand-written loop (`agent.py`, `llm.py`, `planner.py`) | |
| Graph (`graph.py`, `models.py`) | |
| Shared by both | |

From `make check WEEK=14`.

| Measure | Value |
| --- | --- |
| Checks passed, of 18 | |
| Time of the checks | |
| Cost of `make check-live WEEK=14` (USD) | |

The comparison, for interviews. Write a few sentences for each row.

| Question | Your answer |
| --- | --- |
| Cases that pass on one loop and fail on the other, and why | |
| Cases that pass on one provider and fail on the other, and why | |
| What the graph made easier | |
| What the graph made harder | |
| The step that you replaced with plain code, and what it saved | |

## Week 15: persistence, approval and the audit log

From `make check WEEK=15`.

| Measure | Value |
| --- | --- |
| Checks passed, of 6 | |
| Time of the checks | |

Your own test with `AGENT_IMPL=langgraph`.

| Measure | Value |
| --- | --- |
| The question that called `register_dataset` | |
| The arguments of the call | |
| Result after a restart of the API and an approval | |
| Result after a refusal | |
| Rows in `audit_log` for the two conversations | |

## Week 16: MCP tool servers

From `make check WEEK=16`.

| Measure | Value |
| --- | --- |
| Checks passed, of 31 | |
| Time of the checks | |

The safety of the SQL server. Write each limit, and a query of your own that it stopped.

| Limit | Your value | A query that it stopped |
| --- | --- | --- |
| Read-only role (name) | | |
| List of allowed tables | | |
| Row limit | | |
| Query timeout (s) | | |

| Measure | Value |
| --- | --- |
| CI cases of the test set that passed on the servers (check of week 16), of 12 | |
| Tool calls in the log of the catalogue server for those cases | |

## Week 17: agent evaluation

| Measure | Value |
| --- | --- |
| Tasks in `evals/agent_tasks.jsonl` | |
| Tasks with `run_sql` | |
| Tasks that ask to register a dataset | |
| Tasks that you corrected by hand after the draft of Claude Code | |
| How `result_score()` compares texts, and why | |

From `make agent-eval`. Date of the run:

| Measure | Value |
| --- | --- |
| Mean result score | |
| Mean path score | |
| Tasks with a result score of 1.0 | |
| Tasks with a path score of 1.0 | |
| Tasks with a correct result on a wrong path | |
| Register calls refused | |
| Total cost (USD) | |
| Time of the run | |

The tasks with the lowest scores.

| Task ID | Result score | Path score | Cause (task, expectation or agent) |
| --- | --- | --- | --- |
| | | | |
| | | | |
| | | | |

| Measure | Value |
| --- | --- |
| `--min-result` in CI | |
| `--min-path` in CI | |
| Result of the CI job on a pull request | |
| Time of the CI job | |
| Cost of one CI run (USD) | |

## Exit test: multi-step tasks and approval

Date:

| Measure | Value |
| --- | --- |
| Checks of week 17 passed, of 19 | |
| Mean result score over the tasks | |
| Mean path score over the tasks | |
| Checks of week 15 passed, of 6 (no write action without approval) | |
| Cost of `make check-live WEEK=17` (USD) | |
| Checks of Phase 4 passed (`make check PHASE=4`) | |
| Checks of Phases 1, 2 and 3 passed at the end of the phase | |
