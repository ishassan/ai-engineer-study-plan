# Phase 7 results

Write the numbers of your own runs here. The plan says to record the numbers of each check. The numbers of the capstone list go in the tables of `docs/architecture.md` and `docs/writeup.md`, with their result files. This file keeps the numbers of the phase itself.

## Week 26: the feedback

| Measure | Value |
| --- | --- |
| How the client shows the feedback control (`scripts/ask.py`, or your own client) | |
| Ratings that you sent, good and bad | |
| Data type of the score `user-feedback` (BOOLEAN or NUMERIC) | |
| What happens with a second rating of the same answer (a second score, or the first one replaced) | |
| Who can rate a trace (any signed-in user, or only the user of the request) | |

## Week 26: the dashboard

From the notebook (`make dashboard`). Date of the run:

| Measure | Value |
| --- | --- |
| Days shown (`DAYS`) | |
| Requests in the period | |
| Names of the root observations (the notebook prints them) | |
| 95th-percentile latency of a request (s) | |
| Mean cost of a request (USD) | |
| Share of good answers of the feedback | |
| Evaluation scores in the chart (file and score) | |

From the dashboards of Langfuse, for the same period.

| Measure | Value |
| --- | --- |
| "P 95 Latency by Use Case", the line of `/ask` (s) | |
| "P 95 Cost per Trace", the line of `/ask` (USD) | |
| Why the numbers of the notebook and of Langfuse differ, if they do | |

## Week 26: the architecture document

| Measure | Value |
| --- | --- |
| Date of the numbers in `docs/architecture.md` | |
| The run file that `make numbers` used for the run numbers | |
| The attack result that `make numbers` used, and its model | |
| Each value of the table compared with `make numbers` (yes or no) | |

From `make check WEEK=26`.

| Measure | Value |
| --- | --- |
| Checks passed, of 10 | |

## Week 27: the write-up and the CV

| Measure | Value |
| --- | --- |
| Date when the repository became public | |
| Address opened in a signed-out browser, with the result files (yes or no) | |
| Result files added with `git add -f` | |
| Date of the new CV | |
| Each number of the CV compared with `docs/writeup.md` (yes or no) | |

From `make check WEEK=27`.

| Measure | Value |
| --- | --- |
| Checks passed, of 3 | |

## Week 28: system design practice

| Design | Date | Minutes | Points missed | Date of the second try | Points missed in the second try |
| --- | --- | --- | --- | --- | --- |
| Bank knowledge assistant | | | | | |
| ERP process agent | | | | | |
| Analytics agent | | | | | |
| On-call agent | | | | | |

## Exit test: the checklist of the plan

From `make exit-test ARGS=--run`. Date of the run:

| Item of the plan | State | Evidence |
| --- | --- | --- |
| An agent with at least three tools completes multi-step tasks for real users | | |
| Answers drawn from documents cite their sources, and retrieval quality is measured | | |
| A test set of 100 or more cases exists, including cases in Arabic | | |
| A grader model scores outputs against a written rubric, and its agreement with your own labels is measured | | |
| A pipeline blocks any change that lowers the test scores | | |
| Every request is traced, with cost and latency reported per request | | |
| A tool server enforces each user's permissions before any data reaches the model | | |
| Write actions cannot run without human approval, and every action is logged | | |
| A prompt-injection test suite runs on every change, and its pass rate is reported | | |
| The same system runs on a self-hosted open model, compared with the hosted one on quality, latency and cost | | |
| An architecture document explains each choice, including where plain code replaced a model call | | |
| The code and results are public, and your CV quotes the numbers | | |

Your answers to the questions of the exit test.

| Question | Answer |
| --- | --- |
| Who are the real users, and where is the evidence? | |
| Which pull request shows the job failing on a bad change? | |
| Is the repository public? | |
| Does the CV quote the numbers of the write-up, with the same values? | |

From `make check`.

| Measure | Value |
| --- | --- |
| Checks of week 28 passed, of 1 | |
| Checks of Phase 7 passed, of 14 (`make check PHASE=7`) | |
| Checks of Phases 1 to 6 passed at the end of the phase | |
