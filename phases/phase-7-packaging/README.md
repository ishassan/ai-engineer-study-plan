# Phase 7 lab: packaging

Weeks 26 to 28 of the [study plan](../../README.md#phase-7-packaging-weeks-26-to-28). At the end, each answer of the assistant has a feedback control, and the rating goes to Langfuse with the trace of the answer. A dashboard shows the 95th-percentile latency, the cost of a request and the evaluation scores over time. Two documents explain the system with numbers from your own runs: the architecture document and the public write-up. Your CV quotes the same numbers, and you have practised four agent designs aloud. The exit test goes through the checklist of the plan, which is also the list of the [capstone project](../../README.md#capstone-project).

The lab gives the tools. `scripts/ask.py` has the feedback prompt, and a notebook is the dashboard. `make numbers` prints each number of the capstone list with its result file, and `make exit-test` goes through the checklist. The lab also gives the templates of the two documents, a one-page guide for the CV and a practice sheet for each design. You write the parts that the phase teaches:

| Week | You write | File |
| --- | --- | --- |
| 26 | The trace ID in the `done` event of both loops | `assistant/agent.py`, `assistant/graph.py` |
| 26 | `POST /feedback`, which stores the rating as a Langfuse score on the trace | `assistant/api.py` |
| 26 | The architecture document | `docs/architecture.md` (from the template) |
| 27 | The public write-up | `docs/writeup.md` (from the template) |
| 27 | The new CV | Not in the repository |
| 28 | Four designs, aloud | Nothing to commit |

**Cost:** Phase 7 has no live checks, and no check calls a paid API. The feedback, the dashboard, the numbers and the exit test use your local services and your result files. You can draft the documents with Claude Code, which uses your subscription and no API credit. [Costs of the phase](#costs-of-the-phase) gives the estimate of the few real questions that you send yourself.

## Before you start

- **Phase 6 is complete.** `make check PHASE=1` to `make check PHASE=6` pass. This phase changes three files that you wrote in earlier phases (see [Changes to files from earlier phases](#changes-to-files-from-earlier-phases)).
- **The result files of Phases 1 to 6 exist.** The numbers, the documents and the exit test read them. When a file does not exist, `make numbers` prints "missing" and the exit test marks the item as missing.

| File | Written by | Phase and week |
| --- | --- | --- |
| `evals/testset.jsonl` | you | Phase 3, week 9 |
| `evals/results/testset-<time>.jsonl` | `make testset` | Phase 3, week 9 |
| `evals/results/recall.json` | `make recall` | Phase 2, weeks 5 and 6 |
| `evals/rubric.md`, `evals/grader_agreement.json` | you, and the notebook of week 10 | Phase 3, week 10 |
| `.github/workflows/evals.yml` | you | Phase 3, week 11, and Phase 5, week 18 |
| `evals/results/agent-tasks.json` | `make agent-eval` | Phase 4, week 17 |
| `evals/results/attacks-<label>.json` | `make attacks` | Phase 5, weeks 18 and 20 |
| `evals/results/model_comparison.csv` | the notebook of Phase 6 | Phase 6, weeks 23 and 25 |

- **No new service and no new image.** The checks of week 26 need Postgres and the Langfuse of Phase 3 (`make up`). The graph checks start your two MCP servers themselves. The checks of weeks 27 and 28 read files and need no service.
- **No new Python package.** The dependency group `phase7` in `pyproject.toml` is empty. `make dashboard` adds JupyterLab, pandas and matplotlib to the cache of uv the first time you run it. The size of this download was not measured.
- **A public repository, from week 27,** on GitHub, GitLab, Codeberg or Bitbucket.

All times in this guide were measured on a Linux machine (x86_64), not on a Mac. Write your own numbers in [RESULTS.md](RESULTS.md).

## Setup

Run these commands from the repository root.

```bash
make start PHASE=7
```

This command copies the two templates, `docs/architecture.md` and `docs/writeup.md`. It does not change a file that exists. Phase 7 has no Python packages and no Docker services of its own.

```bash
make up
make check WEEK=26
```

Before your work, all 10 checks of week 26 fail.

## How the lab works

- **Steps.** Each week below has the same steps as the plan, in the same order.
- **The checks of week 26 read Langfuse.** They send questions through `/ask` and one approval through `/approve` with the fake Claude API of the lab, post feedback to `/feedback`, and read the traces and the scores back through the public API of Langfuse. They use `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` of your `.env` (Phase 3). Langfuse stores a score some seconds after it gets it, so a check waits up to 45 seconds before it fails. On the build machine the 10 checks took about 14 to 22 seconds when they passed.
- **The checks of weeks 27 and 28 read files.** Your documents under `docs/`, the result files under `evals/`, and git. Each run takes about 1 to 2 seconds.
- **No live checks.** No step of this phase needs a paid API, so there is no `make check-live` for weeks 26 to 28.
- **A check reads the form of a document, not its quality.** It finds a section that holds only the template, a number without its result file, or a write-up without the address of the repository. It cannot judge whether a reason is good. That part is for you and for the people who read the documents.

### Fixed names

| Name | Where | Used by |
| --- | --- | --- |
| `trace_id` in the `done` event of `/ask` (both loops) and of `/approve` (the graph): the ID of the Langfuse trace of the request, 32 lowercase hexadecimal characters | `assistant/agent.py`, `assistant/graph.py` | Week 26 checks, `scripts/ask.py` |
| `POST /feedback` with the JSON body `{"trace_id": "...", "rating": "good" or "bad", "comment": "..."}`. The comment is optional. A 2xx status on success. 422 for another rating, for a trace ID that is not 32 hexadecimal characters, and for a body without a trace ID. 401 without a token | `assistant/api.py` | Week 26 checks, `scripts/ask.py` |
| The Langfuse score of the feedback: the name `user-feedback`, the value 1 for good and 0 for bad, the data type BOOLEAN or NUMERIC, the comment of the request, on the trace of `trace_id` | `assistant/api.py` | Week 26 checks, the dashboard notebook |
| `docs/architecture.md`: the sections and the table of numbers of its template | from the template | Week 26 check, item 11 of the exit test |
| `docs/writeup.md`: the sections and the table of numbers of its template, your own title, and the address of the repository | from the template | Week 27 checks, item 12 of the exit test |

The rules of the two documents are in `labkit/capstone.py`:

- **Sections.** Each `## ` section of the template is in the document, with text outside the HTML comments that differs from the template. The guidance of each template is in HTML comments, and the checks do not count it.
- **The table of numbers.** The first table whose header has a column `Source`. It has one row for each number of the template, with the same name in the column `Number`. Each value has at least one digit. Each source names one or more files under `evals/` that exist, in backticks (or as a word with a `/`).
- **The title of the write-up** differs from the title of the template.
- **The repository.** The write-up holds the address `https://<host>/<account>/<repository>` outside the comments. The host is `github.com`, `gitlab.com`, `codeberg.org` or `bitbucket.org`. When `git remote get-url origin` gives an address, the write-up must name that repository. An ssh address counts in its https form, and `.git` and the letter case do not count. When the project is a git repository, git must track each source file of the table.

### The numbers of the capstone list

`make numbers` prints each number of the plan's list with the file that it comes from. `make numbers ARGS=--markdown` prints the rows of the table of the two documents. The rules are in `labkit/capstone.py`:

| Number | How `make numbers` gets it | File |
| --- | --- | --- |
| Test set size | The cases of the test set, with the count of each language (the field `language`) | `evals/testset.jsonl` |
| Task success rate on the test set | The share of rows with `code_pass` | the run file (below) |
| Retrieval recall, English and Arabic | Each search mode for each language, with k and the number of questions | `evals/results/recall.json` |
| Groundedness score | The share of the document answers that cite correctly (below) | the run file |
| Grader agreement with your labels | The true positive rate and the true negative rate, with the number of labels | `evals/grader_agreement.json` |
| Attack-suite pass rate | The newest result of the attack suite (by its `created` time), with its model | `evals/results/attacks-<label>.json` |
| 95th-percentile latency | Nearest rank over `latency_ms` of the rows, in seconds | the run file |
| Cost per request | The mean of `cost_usd` of the rows | the run file |
| Hosted against self-hosted model: quality, latency and cost | The columns `quality`, `latency_ms_p95` and `cost_per_1000_requests`, one value for each model | `evals/results/model_comparison.csv` |

**The run file.** Four numbers come from one run of the test set on the hosted model. `make numbers` takes the newest `evals/results/testset-<time>.jsonl` that has a row for each case of `evals/testset.jsonl`. If there is none, it takes a Phase 6 file `evals/results/models/<route>.jsonl` that covers the test set. Only a route without a load test counts, because that is a hosted model. If there is none, it takes the newest `testset-<time>.jsonl`, also when it covers only some cases. Phase 7 needs no new run. If you want new numbers, `make testset ARGS=--no-cache` is the run of Phase 3, with its cost (see [Costs of the phase](#costs-of-the-phase)).

**The groundedness score.** No phase of the plan measures a score with this name. The lab uses the citation rule of the Phase 3 suite. A document case is a row with `expected_chunk_ids`. Its answer is grounded when it cites at least one chunk, each cited chunk is a passage that the search returned in the same request (`cited_passages`), and one cited chunk is an expected chunk of the case. The suite of Phase 3 also compares the page and the title of each citation, which needs the database, so this number does not. So the number tells you how often a document answer points at the right passage and invents no source. It does not tell you whether each sentence of the answer agrees with the passage. A grader of week 10 with a rubric about the support of the answer can measure that. Write this meaning next to the number in your documents.

**A request in the two tables.** In the run file, one row is one request to `/ask`, with all its model calls. So the 95th-percentile latency and the cost per request are for one question. In `model_comparison.csv` of Phase 6, one request is one model call through the gateway. Say which one you quote.

### Changes to files from earlier phases

`make start PHASE=7` does not touch the files that you wrote. You change them yourself in week 26:

- `assistant/agent.py`: the `done` event of the hand-written loop has `trace_id`.
- `assistant/graph.py`: the `done` event of the graph (for `/ask` and `/approve`) has `trace_id`.
- `assistant/api.py`: the new endpoint `POST /feedback`.

`scripts/ask.py` is given, and the repository already has its new version. The checks of Phases 1 to 6 must stay green. In the build of this lab, with the reference solution of week 28, all checks of Phases 1 to 6 passed (37, 50, 41, 86, 61 and 40 checks). The checks of Phases 1 to 5 also passed with `--gateway`.

## Costs of the phase

| Item | Estimate | Arithmetic and source |
| --- | --- | --- |
| Offline checks of weeks 26 to 28 | $0 | The fake Claude API, Langfuse on your machine, and files |
| `make numbers`, `make dashboard`, `make exit-test` | $0 | They read files and your local Langfuse. `make exit-test ARGS=--run` runs offline checks only |
| Your own questions to try the feedback (week 26, step 2) | about $0.007 for 10 questions | The estimate of the Phase 3 guide: about 5,000 input and 300 output tokens for one question. 5,000 x $0.10 per million + 300 x $0.50 per million = about $0.0007. The prices are `PRICES_PER_MTOK` of `assistant/config.py`. A question that the response cache replays costs 0 |
| A new run of the test set (optional) | about $0.07, up to about $0.15 | The estimate of the Phase 3 guide: 105 cases x $0.0007 = about $0.07, and twice the tokens gives about $0.15 |
| Drafts of the documents with Claude Code | $0 in API credit | Claude Code uses your subscription |

## Week 26: Feedback, monitoring and the architecture document

### Step 1. Read

Huyen, chapter 10: Step 5. Add Agent Patterns, Monitoring and Observability, AI Pipeline Orchestration, and User Feedback (pages 463 to 492).

### Step 2. Add a feedback control to each answer, and store the feedback in Langfuse with the trace

Your test set tells you how the assistant does on the questions that you wrote. Feedback tells you how it does on the questions of real users. A rating alone tells you little. A rating on the trace of its request lets you open the question, the tool calls, the passages and the answer behind it, and find the cause. So the client needs the ID of the trace, and the rating goes to Langfuse with that ID.

> From the documentation: the Langfuse page [User Feedback](https://langfuse.com/docs/observability/features/user-feedback) says: "In Langfuse, feedback is captured as scores and linked to traces." Its first step is "Return trace ID to frontend: Your backend sends the trace ID so frontend can link feedback to the trace." Its example score has the name `user-feedback`, the value "1 for positive, 0 for negative" and `dataType: "BOOLEAN"`. The lab uses the same name and values. The page also says: "You can filter by `user-feedback < 1` to find low-rated responses."

1. **The trace ID in the `done` event.** In `assistant/agent.py`, add `trace_id` to the `done` event of the hand-written loop. It is the ID of the trace that your tracing of Phase 3 makes for the request, not a new ID. In `assistant/graph.py`, do the same where the graph makes its `done` event. The graph answers both `/ask` and `/approve`.
2. **`POST /feedback`.** In `assistant/api.py`, add the endpoint of the [fixed names](#fixed-names). It needs a sign-in, as `/ask` does. It refuses a body with another rating or a malformed trace ID with 422. It stores one Langfuse score on the trace: the name `user-feedback`, the value 1 for good and 0 for bad, and the comment.
3. **Try it.** Ask a question with a test user of Phase 5:

```bash
make ask AS=viewer Q="Which datasets are about crude oil?"
```

When the `done` event has a `trace_id` and the script runs in a terminal, `scripts/ask.py` asks "Was the answer good? [g]ood, [b]ad, Enter to skip", then "Comment (Enter for none)", and posts both to `/feedback`. Then open the trace in Langfuse (http://localhost:3000) and find the score on it.

> Not run in the build of this lab: the prompt of `scripts/ask.py` in a real terminal. It was tested with mocked input, and the checks tested `/feedback` through the test client.

The endpoint checks only the form of the trace ID. A user who knows the ID of another user's trace can rate it. Write this in the section "Limits and next steps" of your architecture document, or close it in your code.

<details>
<summary>Hint: where the trace ID comes from</summary>

In Phase 3, `@observe()` on `answer_events()` keeps the trace of the request across the yields, so inside the generator the current trace is the trace of the request. `get_client().get_current_trace_id()` of the Langfuse client gives its ID. It gives `None` when tracing is off, so add the field only when it has a value. The week 26 checks pass with this call in both loops.
</details>

<details>
<summary>Hint: the 422 answers</summary>

FastAPI answers 422 by itself when the body does not match its Pydantic model. A field of the type `Literal["good", "bad"]` refuses another rating, and `Field(pattern=...)` refuses a malformed ID. A field without a default makes the trace ID required.
</details>

<details>
<summary>Hint: the score</summary>

From the documentation: the page [Scores via SDK](https://langfuse.com/docs/evaluation/evaluation-methods/scores-via-sdk) shows `create_score()` of the Python client, with `name`, `value`, `trace_id`, `data_type` and `comment`. It says: "Boolean scores must be provided as a float, where 1 is true and 0 is false. When read via the v3 scores API, the value is returned as a boolean." The page also says that a numeric value without `data_type` "would be inferred as NUMERIC". In the build of this lab, with langfuse 5.2.0 (the version of `uv.lock`) and Langfuse 4.80.0, a BOOLEAN score came back from the v3 scores API with the value `true`.

The client sends the score in the background. The API service runs for a long time, so it needs no `flush()`. The checks flush before they read.
</details>

<details>
<summary>Hint: a second rating of the same answer</summary>

Each call of `create_score()` makes a new score, so two ratings of one answer give two scores. The example of the User Feedback page gives the score an ID made from the trace ID (`user-feedback-<trace id>`), so a second rating replaces the first. In langfuse 5.2.0, `create_score()` takes `score_id=`. This was seen in the signature and not tested in the build of this lab. The check of a bad rating counts exactly one score on a new trace, so both ways pass.
</details>

### Step 3. Add a dashboard of 95th-percentile latency, cost per request and the evaluation scores over time

The 95th-percentile latency is the time within which 19 of 20 requests answer, so it shows the slow requests that a mean hides. The cost of a request is the sum of the costs of its model calls, and the mean of a day times the requests of the day is what the requests of that day cost. The evaluation scores over time show whether a change lowered the quality, and when.

**What Langfuse shows by itself.** In the build of this lab, the self-hosted Langfuse 4.80.0 of Phase 3 was checked in its UI and through its public API, with the traces of the check runs in it. Under Dashboards it has dashboards marked "Langfuse Maintained":

- The "Langfuse Latency Dashboard" has the widget "P 95 Latency by Use Case": the 95th-percentile latency of the traces, one line for each trace name. The line `ask` is the `/ask` requests. This covers the first number.
- The "Langfuse Cost Dashboard" has "Total costs", "Cost by Model Name", "Top 20 Use Cases (Trace) by Cost" and "P 95 Cost per Trace". The last one is the 95th percentile of the cost of a trace, not the mean.
- The project Home page has traces, model costs, scores and latencies.

What it does not show: the mean cost of a request, and the evaluation scores. A new widget cannot give the mean cost. In 4.80.0 the widget editor offers only the views Observations, Scores Numeric, Scores Categorical and Scores Boolean, with no view of traces. The root observation of a request has a cost of 0, and its generations hold the cost, so no widget adds them up for one request. The evaluation scores of Phases 2 to 6 are in your result files, not in Langfuse, because no phase sends them as scores. Only the feedback of step 2 is a score in Langfuse.

> From the documentation: the page [Custom Dashboards](https://langfuse.com/docs/metrics/features/custom-dashboards) names "Langfuse Curated Dashboards: A set of pre-built dashboards focused on Latency, Cost, and Langfuse usage", says "Your project Home page is a dashboard", and opens the widget editor with Dashboards, the Widgets tab, then New widget.

**The given notebook.** So the lab gives a notebook that reads all three numbers, and you write no code for it:

```bash
make dashboard
```

This opens `phases/phase-7-packaging/notebooks/dashboard.ipynb` in JupyterLab. Run all cells. The notebook reads the requests and the feedback from the public API of Langfuse, and the evaluation scores from the files under `evals/results/`. It writes nothing. It shows:

- For each day of the last 14 days: the requests, the 95th-percentile latency and the mean cost of a request.
- The share of good answers of each day, from the score `user-feedback`.
- One point for each run that a result file holds: `code_pass` of each `testset-<time>.jsonl`, `score` of each `compare-<loop>-<provider>.json`, `result_score` and `path_score` of `agent-tasks.json`, and `pass_rate` of each `attacks-<label>.json`.

Most commands write over their result file, so these files keep only the last run. `make testset` writes a new file for each run, so keep these files to see a trend. A run of the test set also sends requests, so its traces count in the latency and the cost.

> Not run in the build of this lab: `make dashboard` in JupyterLab. The notebook ran from start to end with nbclient (pandas 3.1.1, matplotlib 3.11.2, httpx 0.28.1) against the Langfuse of the build machine.

<details>
<summary>Hint: the notebook finds no requests</summary>

The notebook does not use the names of your observations. It counts each trace one time, by its root observation: Langfuse marks the root of each trace (`isRootObservation`). The notebook leaves out a root of the type of one step (`STEPS` in its first code cell: a model call, a tool call, a retrieval or an embedding), because a check or an evaluation ran that step by itself. So if the notebook finds no requests, open one trace of `/ask` in Langfuse and look at its root. It must be one observation around the whole request (Phase 3, week 8), not a generation. `DAYS` in the same cell sets the number of days.
</details>

Then open the Latency dashboard and the Cost dashboard of Langfuse as a second view of the same traces. Write the numbers of the notebook and of the Latency dashboard in [RESULTS.md](RESULTS.md).

### Step 4. Write an architecture document that explains each choice, including where plain code replaced a model call

A design document gives a reader who does not know the project the reasons behind it. For each choice it says what you chose, the other options, why, what it costs, and the evidence. The plan asks for one more part: where plain code does a job that a model call could do. Phase 4 read Anthropic's [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents), which recommends "finding the simplest solution possible, and only increasing complexity when needed". Your code has such places, for example the cost calculation, the citation check and the routing of the gateway.

1. Open `docs/architecture.md`. Each section has its guidance in an HTML comment. Write each section in your own words, and delete each comment when the section is complete.
2. Print the numbers and the rows of the table:

```bash
make numbers
make numbers ARGS=--markdown
```

3. Put the rows in the table of the section "Numbers". Next to the groundedness score, say what it measures (see [The numbers of the capstone list](#the-numbers-of-the-capstone-list)). If the newest attack result is the run with the obedient model (offline), say so, or quote the run on Claude.
4. For each claim of a section, point to its evidence: a result file, a check, a trace or a row of the table.

You can ask Claude Code for a first draft of a section from your code and your result files, which uses your subscription. Then read each claim against the code and rewrite it in your own words. A reader of the document will ask you about each line in an interview.

<details>
<summary>Hint: a choice without a cost</summary>

If a choice has no cost in your text, you have not written the trade-off yet. Ask what each part adds. For example, how much latency does the re-ranker add? What does the GPU of the self-hosted model cost in an hour when it is idle?
</details>

<details>
<summary>Hint: the diagram</summary>

The comment of the section "How a request goes through the system" says that each arrow of a diagram is a claim. Say each arrow as a sentence, for example "each model call goes through the gateway", and test it with one request of each kind: a question about a dataset, a question about a document, and a write action with approval. Draw only the paths that your code has.
</details>

### Step 5. Check

```bash
make check WEEK=26
```

All 10 checks pass. Two checks test the trace ID of `/ask`, with the hand-written loop and with the graph: the trace of the ID must hold the question of the request. One check stops the graph for an approval of `register_dataset`, approves it, and tests the trace ID of `/approve`: the trace of the ID must hold the answer after the approval. This check adds a dataset with an ID that starts with `check-` and deletes it at the end. Two checks read the score of a good rating with its comment, and of a bad rating. Four checks test the 422 answers for three bad bodies and the 401 answer without a token. The last check reads the architecture document.

This is the check of the plan: every number in the document comes from your own runs. The check confirms that each row of the table has a value and names a result file that exists under `evals/`. It does not compare the value with the file. Compare each value with the output of `make numbers` yourself.

## Week 27: The public write-up and the CV

### Step 1. Write a public write-up with the repository and the numbers from the capstone list

The architecture document is for a reviewer who reads all of it. The write-up is for an engineer or a hiring manager who has five minutes. It says what the system does and what you measured, and it links to the repository, where each number has its result file.

1. Open `docs/writeup.md`. Give it your own title, and write each section. The guidance is in the HTML comments.
2. Put the same table of numbers in the section "Numbers" (`make numbers ARGS=--markdown`).
3. Write the full address of your public repository outside the comments, for example in the section "Run it yourself".
4. **Point `origin` at your public repository.** When `git remote get-url origin` gives an address, the check wants that address in the write-up. If `origin` is still the repository that you cloned the plan from, change it with `git remote set-url origin <the address of your repository>`.
5. **Add the result files.** `evals/results/` is in `.gitignore`, so git does not track the files of your table. Add each source of the table:

```bash
git add -f evals/results/<file>
```

6. Read each file that you add, and the documents, for keys, employer data and personal data. Then commit and push.

<details>
<summary>Hint: the check says that the write-up does not name the repository of this project</summary>

The check compares the address in the write-up with `git remote get-url origin`. An ssh address (`git@github.com:<account>/<repository>.git`) counts as `https://github.com/<account>/<repository>`, and the letter case does not count. If the two still differ, `origin` points at another repository.
</details>

### Step 2. Write a new CV that starts with the target title and the numbers of the project

Read [cv-guide.md](cv-guide.md). It says what goes first (the target title, a summary of two lines, the AI work at the top) and which numbers of the write-up to quote, with the context that each one needs. It has no example CV, because the CV holds your own history. Keep the CV out of the repository.

### Step 3. Check

```bash
make check WEEK=27
```

All 3 checks pass. Before your work, all 3 fail. They test the sections and the title of the write-up, the table of numbers with its result files, and the address of the repository with the files that git tracks.

The plan's check is: the repository is public, and the CV quotes its numbers. A script cannot see either one. Open the address of the repository in a browser window where you are signed out: it must open, with the result files of the table. Then compare each number of the CV with `docs/writeup.md`.

## Week 28: System design practice

### Step 1. Work through four agent designs aloud, about 45 minutes each

In a system design interview you scope a vague problem, agree on success criteria and design under time pressure, and you say when not to use a model. Your capstone is evidence for most of the points, but only when you can connect a point to the part that you built while you speak.

Read [practice/README.md](practice/README.md) for the method, then do one sheet at a time:

| Sheet | The design |
| --- | --- |
| [bank-knowledge-assistant.md](practice/bank-knowledge-assistant.md) | A bank knowledge assistant |
| [erp-process-agent.md](practice/erp-process-agent.md) | An ERP process agent |
| [analytics-agent.md](practice/analytics-agent.md) | An analytics agent |
| [on-call-agent.md](practice/on-call-agent.md) | An on-call agent |

Each sheet has the prompt as an interviewer gives it, the questions to ask first, a time plan for 45 minutes, and the points that a strong answer covers, each with a link to its evidence in your capstone. The sheets have no model answer. Set a timer, read only the prompt, and speak. Then compare what you said with the points. Claude Code can play the interviewer and ask follow-up questions, on your subscription. Do the design first, before you read any answer from it.

Write the date and the points that you missed in [RESULTS.md](RESULTS.md).

### Step 2. Check: the exit test

```bash
make exit-test
```

The script goes through the 12 items of the plan's exit test. For each item it reads the files that prove it, and prints the item, its evidence, the checks that built it, and a state:

- `ok`: the files exist and meet the rule of the item.
- `missing`: a file that proves the item does not exist.
- `fail`: the files exist, but a rule of the item is not met.

| Item of the plan | What the script reads | Weeks that `--run` checks | Question for you |
| --- | --- | --- | --- |
| An agent with at least three tools completes multi-step tasks for real users | `agent-tasks.json`: 3 or more different tools over the tasks, and a task with 2 or more different tools | 16 | Who are the real users, and where is the evidence? |
| Answers drawn from documents cite their sources, and retrieval quality is measured | Both recall numbers, the groundedness score, and an answer of the run file that cites a source | 6, 7 | |
| A test set of 100 or more cases exists, including cases in Arabic | `evals/testset.jsonl`: 100 or more cases, one in Arabic (`language` is `ar`, or Arabic letters) | 9 | |
| A grader model scores outputs against a written rubric, and its agreement with your own labels is measured | `evals/rubric.md` and `evals/grader_agreement.json` | 10 | |
| A pipeline blocks any change that lowers the test scores | `.github/workflows/evals.yml` runs on `pull_request` and runs `make evals` or `tests/evals` | 11 | Which pull request shows the job failing on a bad change? |
| Every request is traced, with cost and latency reported per request | Each row of the run file has a `trace_id` of 32 hexadecimal characters and a `latency_ms` above 0 | 8, 26 | |
| A tool server enforces each user's permissions before any data reaches the model | A migration with `ENABLE ROW LEVEL SECURITY`, and `assistant/auth.py` | 19 | |
| Write actions cannot run without human approval, and every action is logged | `interrupt(` in `assistant/graph.py`, and a migration with an audit table | 15, 19 | |
| A prompt-injection test suite runs on every change, and its pass rate is reported | An `attacks-<label>.json`, and the attack suite in the workflow | 18, 20 | |
| The same system runs on a self-hosted open model, compared with the hosted one on quality, latency and cost | `model_comparison.csv` with a row of the cost basis `tokens`, a row of `GPU hour`, and quality, p95 latency and cost in each row | 25 | |
| An architecture document explains each choice, including where plain code replaced a model call | The rules of `docs/architecture.md` | 26 | |
| The code and results are public, and your CV quotes the numbers | The rules of `docs/writeup.md` and of the repository | 27 | Is the repository public? Does the CV quote the numbers of the write-up, with the same values? |

The questions come after the table. The script prints them and never answers them, because only you can confirm them. The exit code is 1 when an item is not `ok`.

```bash
make exit-test ARGS=--run
```

With `--run`, the script also runs the offline checks of the weeks of each item that is `ok`, and marks the item `fail` when they fail. It needs `make up`, and it takes as long as those checks. `ARGS=--json` prints the same result as JSON.

```bash
make check WEEK=28
make check PHASE=7
```

The check of week 28 passes when each item of the exit test is `ok`. `make check PHASE=7` runs the checks of weeks 26 to 28 (14 checks). Then run the checks of all phases one more time, `make check PHASE=1` to `make check PHASE=7`, and write the state of each item and your answers to the questions in [RESULTS.md](RESULTS.md).

## Commands

| Command | What it does |
| --- | --- |
| `make start PHASE=7` | Copy the templates `docs/architecture.md` and `docs/writeup.md`, and keep each file that exists |
| `make ask AS=viewer Q="..."` | Ask one question as a test user. After the answer, the script asks for a rating and a comment and posts them to `/feedback` |
| `make dashboard` | Open the dashboard notebook in JupyterLab. Run all cells for new data |
| `make numbers` | Print each number of the capstone list with its result file |
| `make numbers ARGS=--markdown` | Print the rows of the table of numbers for the two documents |
| `git add -f evals/results/<file>` | Add a result file of the table of the write-up, which `.gitignore` excludes |
| `make exit-test` | Go through the exit test of the plan, and print the questions that only you can answer |
| `make exit-test ARGS=--run` | The same, and also run the offline checks of the weeks of each item |
| `make exit-test ARGS=--json` | The result of the exit test as JSON |
| `make check WEEK=26` | Offline checks of one week |
| `make check PHASE=7` | Offline checks of weeks 26 to 28 |

Langfuse runs at http://localhost:3000 (user `lab@example.com`, password `lab-password`, from Phase 3). Its Dashboards page has the Latency and Cost dashboards of step 3.
