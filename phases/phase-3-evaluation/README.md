# Phase 3 lab: evaluation and tracing

Weeks 8 to 11 of the [study plan](../../README.md#phase-3-evaluation-and-tracing-weeks-8-to-11). At the end, each request of the assistant is one trace in a Langfuse server on your machine. You have a test set of more than 100 cases, a table of the failures that you found in it, a grader model whose agreement with your own labels you know, and a GitHub Actions job that fails when a change makes the answers worse.

The lab gives you Langfuse in Docker Compose, the script that runs the test set, the script that sends failures to a Langfuse dataset, two notebooks, and the CI workflow. You write the parts that the phase teaches:

| Week | You write | File |
| --- | --- | --- |
| 8 | A trace for each request, with each model call, tool call and retrieval step | `assistant/agent.py`, `assistant/llm.py`, `assistant/retrieval.py` |
| 9 | The test set of more than 100 cases | `evals/testset.jsonl` |
| 9 | Your notes on 30 traces, and the table of failure categories | `evals/error_notes.jsonl`, `evals/failure_categories.csv` (written by the notebook) |
| 10 | The rubric | `evals/rubric.md` |
| 10 | The grader and the agreement rates | `evals/grader.py` |
| 10 | Your 50 labels, and the measured rates | `evals/grader_labels.jsonl`, `evals/grader_agreement.json` (written by the notebook) |
| 11 | The evaluation suite | `tests/evals/test_evals.py` |
| 11 | The CI subset of the test set | `"ci": true` in `evals/testset.jsonl` |
| 11 | The snapshot of the chunks | `data/snapshot/chunks.sql.gz` (written by `make snapshot`) |

**Cost:** the offline checks are free, and this phase has no live checks. Four steps call the real Claude API: the run of the test set in week 9, the grader in week 10, and the evaluation suite on your machine and in CI in week 11. Each step below gives its estimate with the arithmetic. As an example, 2 runs of the test set, 5 runs of the grader and 10 runs of the suite cost about $0.30 to $0.55 together. These numbers are estimates, not measurements. You draft the 100 test questions with Claude Code, which uses your subscription and no API credit. The optional review bot of week 11 also uses your subscription.

## Before you start

- **Phase 2 is complete.** `make check PHASE=2` and `make check PHASE=1` pass. Week 8 changes three files that you wrote in Phases 1 and 2 (see [Changes to files from earlier phases](#changes-to-files-from-earlier-phases)).
- **Download: about 0.9 GB.** Langfuse runs as six containers. The compressed images for Apple Silicon (linux/arm64) are 933 MB together: web 239 MB, worker 177 MB, ClickHouse 249 MB, Postgres 166 MB, Redis 44 MB and MinIO 58 MB. Each image has a build for linux/arm64 and linux/amd64.
- **Disk space: about 4 GB more.** On the build machine (amd64) the unpacked images took about 4.1 GB.
- **Memory: about 8 GB for Docker.** On the build machine, the idle Langfuse services used about 2.2 GiB: web 879 MiB, worker 669 MiB, ClickHouse 487 MiB, MinIO 88 MiB, Postgres 59 MiB and Redis 8 MiB. Right after the first start, the web service used 1.30 GiB. With the Phase 2 services, the whole stack used about 7.6 GiB. Make sure that the memory limit in the Docker Desktop settings is higher.
- **Time for the first start.** With the images already downloaded and empty volumes, Langfuse was healthy after 33 s. A restart of the stopped services took 24 s. After a restart of the Docker daemon, with filled volumes, Postgres and Langfuse together took 102 s. The time of the image download depends on your network and was not measured.

All numbers in this guide were measured on a Linux machine with 4 x86 CPU cores, 15 GiB of memory and no GPU, not on a Mac. Nothing ran on Apple Silicon: the arm64 images were checked only by their manifests, and the memory and start times on a Mac are not measured. Write your own numbers in [RESULTS.md](RESULTS.md).

> From the documentation: the Langfuse docs recommend at least 4 cores and 16 GiB of memory for a virtual machine that runs Langfuse, and say that after about 2 to 3 minutes the web container logs "Ready" ([Docker Compose deployment](https://langfuse.com/self-hosting/deployment/docker-compose)). On the build machine the lab used less than this (see the numbers above).

## Setup

Run these commands from the repository root.

```bash
make start PHASE=3
```

This command copies the new files of the phase: `evals/grader.py`, `evals/rubric.md`, `evals/run_testset.py`, `evals/failures_dataset.py`, `evals/testset.jsonl` (three example cases), `tests/evals/test_evals.py` and `.github/workflows/evals.yml`. It also turns on the Python package of the phase (`langfuse`, the Python SDK v5) and the Docker services of the phase. It does not change a file that exists.

Your `.env` is from the earlier phases. Copy the Phase 3 lines of `.env.example` into it:

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-local-lab
LANGFUSE_SECRET_KEY=sk-lf-local-lab
LANGFUSE_PORT=3000
LANGFUSE_BASE_URL=http://localhost:3000
```

```bash
make up
```

`make up` now also starts the six Langfuse services: `langfuse-web`, `langfuse-worker`, `langfuse-postgres`, `langfuse-clickhouse`, `langfuse-redis` and `langfuse-minio`. Then run the checks of week 8:

```bash
make check WEEK=8
```

Four checks pass (Langfuse runs, the request works, and the two runs without Langfuse) and seven fail. Each failing check names what the trace is missing.

`make up` as one command with Phase 3 turned on was not run in the build of this lab: there the services started in parts. If `make up` stops with an error, start the services in parts and read the error of the part that fails:

```bash
docker compose --profile phase2 --profile phase3 up -d --wait db embeddings reranker
```

```bash
docker compose --profile phase2 --profile phase3 up -d --wait langfuse-web langfuse-worker
```

When the part that failed is fixed, run `make up` again. It also applies the migrations and loads the catalogue.

## How the lab works

- **Steps.** Each week below has the same steps as the plan, in the same order.
- **Checks need your local services.** Week 8 needs Langfuse, Postgres and both model services. Week 9 needs Postgres and Langfuse. Week 10 needs nothing: it reads files and uses the stand-in for the Claude API. Week 11 needs Postgres and both model services. On the build machine, the checks of week 8 took 35 s, and the checks of week 11 took about 7 minutes, because they run your suite five times with real searches.
- **No live checks.** The steps with the real API are commands that you run yourself: `make testset`, part 2 of the grader notebook, and `make evals`. The offline checks read the files that these commands write.
- **The checks read your traces back from Langfuse.** Week 8 sends one question through `/ask` with the stand-in, then reads the observations of the trace through the Langfuse public API. Your code inside the files is free. Keep the names and the contracts below.

| Name | Where | Used by |
| --- | --- | --- |
| One trace for each `/ask` request, with one root observation whose input holds the question | your tracing | Week 8 checks |
| One observation of the type `generation` for each request to Claude, with `model`, the input and output tokens, and a cost above 0. The costs of a request add up to `cost_usd` of its `done` event (1% tolerance) | your tracing | Week 8 checks |
| One observation of the type `tool` for each tool call, named by the tool, with the tool input as its input. A tool call that raises has the level `ERROR` | your tracing | Week 8 checks |
| One observation of the type `retriever` inside the `tool` observation of `search_documents` (at any depth). Its output names each chunk ID that the tool returned | your tracing | Week 8 checks |
| `answer_events()` works in less than 30 s when Langfuse is down, and when the keys are empty | your tracing | Week 8 checks |
| `evals/testset.jsonl` | your test set | Checks of weeks 9 and 11, `make testset`, the suite |
| `evals/error_notes.jsonl`, `evals/failure_categories.csv` | written by the notebook | Week 9 checks |
| The Langfuse dataset `assistant-failures` | written by `make failures-dataset` | Week 9 checks |
| `grade(example) -> Verdict`, `Verdict.passed`, `agreement_rates(labels, verdicts)` | `evals/grader.py` | Week 10 checks, the notebook, the suite |
| `evals/rubric.md`, `evals/grader_labels.jsonl`, `evals/grader_agreement.json` | your rubric, written by the notebook | Week 10 checks |
| `.github/workflows/evals.yml`, `data/snapshot/chunks.sql.gz` | given, written by `make snapshot` | Week 11 checks |
| `tests/evals/` | your suite | Week 11 checks |

These contracts are also fixed:

- **A test case** is one JSON line with `id` (unique), `language` (`"en"` or `"ar"`), `question`, `expected_dataset_ids` and `expected_chunk_ids` (lists, which can be empty). `"ci": true` marks a case of the CI subset.
- **A note** is one JSON line with `case_id`, `trace_id` (32 lowercase hex characters), `passed` (true or false), `note` and `category`. The notebook writes these lines for you.
- **The grader sends one request** through `call_claude()`, with the text of `evals/rubric.md`, the answer of the example, and a JSON schema in `output_config.format.schema` whose field `passed` is a boolean. The request has no `tools`: the stand-in of week 11 knows a grader request by this.
- **The question is the first user message** of the agent, exactly as the test case has it. The stand-in of week 11 knows a case by this text.
- **The notebook of week 10 also reads `Verdict.reasoning`.** Keep the field, or change part 3 of the notebook.

### Changes to files from earlier phases

`make start PHASE=3` does not touch the files that you wrote. In week 8 you add tracing to three of them yourself:

- `assistant/llm.py`: one generation for each request to Claude, also for a replay from the response cache.
- `assistant/agent.py`: the root observation of the request, and one tool observation for each tool call (in the loop, or in `run_tool()` in `assistant/tools.py`).
- `assistant/retrieval.py`: one retriever observation in `retrieve()`.

The checks of Phases 1 and 2 must stay green with tracing on, and also with Langfuse stopped. In week 11, the exit test changes the system prompt in `assistant/agent.py` on a separate branch only.

## Week 8: Tracing

### Step 1. Read

Langfuse [Get Started with LLM Tracing](https://langfuse.com/docs/observability/get-started). In the [AI Evals FAQ](https://hamel.dev/blog/posts/evals-faq/): "What is a trace?" and "What's a minimum viable evaluation setup?".

The examples of the Langfuse docs send the traces to `https://cloud.langfuse.com`. In this lab, the SDK reads `LANGFUSE_BASE_URL` from your `.env`, so it sends them to your own server.

### Step 2. Run Langfuse with Docker Compose

`make up` did this step. The services come from the `docker-compose.yml` of [Langfuse release v4.80.0](https://raw.githubusercontent.com/langfuse/langfuse/v4.80.0/docker-compose.yml), with the changes that the comment in the root `compose.yaml` lists: the names start with `langfuse-`, only the web UI and MinIO have a port on your machine (both on 127.0.0.1), the settings are fixed values, telemetry is off, and the AI gateway is not included.

**Headless initialisation.** The first start creates an organisation (`lab`), a project (`assistant`), a user and the API keys of `.env.example`, so you do not need to click in the UI. Open http://localhost:3000 and sign in:

- Email: `lab@example.com`
- Password: `lab-password`

Then confirm that the server is healthy and that it accepts your keys:

```bash
curl -s localhost:3000/api/public/health
```

```bash
curl -s -u pk-lf-local-lab:sk-lf-local-lab localhost:3000/api/public/projects
```

The second command returns the project `assistant`. The checks use the same request.

> From the documentation: the `LANGFUSE_INIT_*` variables create the resources at the start "if they don't already exist", and in Docker Compose you must not put quotes around their values ([Headless Initialization](https://langfuse.com/self-hosting/administration/headless-initialization)). The health endpoint is `GET /api/public/health` ([Health and Readiness Check Endpoints](https://langfuse.com/self-hosting/configuration/health-readiness-endpoints)). The public API uses basic auth with the public key as the user name and the secret key as the password ([Public API](https://langfuse.com/docs/api-and-data-platform/features/public-api)).

**The pinned release.** The tag 4.80.0 was the newest v4 release when this lab was built, and its images were built two days before. The lab pins it on purpose, so that each learner runs the same server. If this release gives you a problem, use an older release:

1. List the releases:

```bash
git ls-remote --tags https://github.com/langfuse/langfuse 'v4.*'
```

2. In `compose.yaml`, set the same older tag on both images, `docker.langfuse.com/langfuse/langfuse` and `docker.langfuse.com/langfuse/langfuse-worker`, for example `4.79.0`. The images of 4.79.0 also have a build for linux/arm64. Use 4.59.0 or later: the Python SDK v5 needs it.
3. Delete the Langfuse volumes, then run `make up` again. You lose your traces and datasets, so do this early in the phase if you can.

```bash
make down
```

```bash
docker volume rm assistant_langfuse-postgres-data assistant_langfuse-clickhouse-data assistant_langfuse-clickhouse-logs assistant_langfuse-minio-data assistant_langfuse-redis-data
```

> From the documentation: Langfuse applies all database migrations when it starts, the Python SDK v5 requires Langfuse v4.59.0 or later ([Upgrade](https://langfuse.com/self-hosting/upgrade)), and a self-hosted server uses the model prices that came with its version ([Token and cost tracking](https://langfuse.com/docs/observability/features/token-and-cost-tracking)). The upgrade page does not describe a downgrade. This is why item 3 above starts from empty volumes, and why step 3 below sends the cost of each call itself.

### Step 3. Trace each model call, tool call and retrieval step

A trace is the record of one request: a tree of observations, each with its start and end time, its input and its output. In this lab, one `/ask` request is one trace. Its root is the request. Inside the root are the requests to Claude, the tool calls, and inside the call of `search_documents`, the retrieval step. With the trace you can see what the agent did, in which order, and what each step cost.

The SDK has two ways to make an observation:

- **The decorator** `@observe(name=..., as_type=...)` on a function makes one observation for each call. By default it records the arguments as the input and the return value as the output.
- **The context manager** `get_client().start_as_current_observation(as_type=..., name=..., input=...)` makes one observation for the `with` block. Each observation that starts inside the block is its child. Call `.update(...)` on the object of the `with` block to add `output`, and on a generation `usage_details` and `cost_details`, or `level` and `status_message`.

The types that this step uses are `agent`, `generation`, `tool`, `retriever` and `span`. A short program that ends right after its work must call `get_client().flush()`, because the SDK sends the observations in the background. The API service runs for a long time and does not need it. The given scripts and the checks call it.

> From the documentation: [Instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation), [SDK overview](https://langfuse.com/docs/observability/sdk/overview), [Observation types](https://langfuse.com/docs/observability/features/observation-types), [Log levels](https://langfuse.com/docs/observability/features/log-levels) and [Token and cost tracking](https://langfuse.com/docs/observability/features/token-and-cost-tracking). The SDK reads `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_BASE_URL` from the environment. When a generation has both a cost that you send and a price that Langfuse knows, the cost that you send is used.

1. In `assistant/agent.py`, make `answer_events()` the root observation of the trace, with the question as its input.
2. In `assistant/llm.py`, make one generation for each request to Claude, with the model, the input and output tokens of the response, and the cost of your `cost_usd()`. Also for a replay from the response cache: the replay shows a cost of 0, as the `done` event does.
3. Make one tool observation for each tool call, with the name of the tool and its input. When the tool raises, give the observation the level `ERROR` and the message of the error.
4. In `assistant/retrieval.py`, make one retriever observation in `retrieve()`. Its output names the chunk ID of each result.
5. Tracing must not break the service. Make no request to Langfuse yourself in the path of a request. The SDK sends its data in the background.

<details>
<summary>Hint: the request makes more than one trace, or the trace has more than one root</summary>

`answer_events()` is a generator, and Starlette runs each step of a streaming response in a worker thread with a copy of the context. A `with` block around the loop does not stay the current observation after the first `yield`, so each later step starts a new trace. When a tracer provider is already set at the start of the request (as in the checks), FastAPI makes a span for the request, and each later step becomes one more root of the same trace. The decorator `@observe()` on the generator keeps the trace across the yields. This behaviour was shown by a test in the build of this lab. It was not found as a sentence in the Langfuse docs.
</details>

<details>
<summary>Hint: two generations for each call, and the cost counts twice</summary>

The `anthropic` SDK (version 2.8.0 in `uv.lock`) makes its own OpenTelemetry span for each API call when a tracer is registered, and Langfuse registers one. So the trace gets your generation and the span of the SDK. Keep one of them. In the source of the SDK (`_client.py`), `anthropic.Anthropic(open_telemetry=False)` turns its spans off.
</details>

<details>
<summary>Hint: the tokens and the cost</summary>

Langfuse v4.80.0 knows a price for `claude-haiku-5-5`: $0.10 for each million input tokens and $0.50 for each million output tokens, the same as `assistant/config.py`. So the check can pass when you send only the tokens. Send the cost of `cost_usd()` in `cost_details` anyway. Then Langfuse always shows the money that you spent: $0 for a replay, the cache prices of week 3, and the correct cost with an older Langfuse release that does not know the model. The docs use the keys `input` and `output` for `usage_details` in one example and `input_tokens` and `output_tokens` in another. Both gave the correct tokens in the build of this lab.
</details>

<details>
<summary>Hint: where the retrieval step goes</summary>

The check looks for the retriever observation inside the tool observation of `search_documents`. When the tool observation is the current observation while `run_tool()` calls `retrieve()`, the context manager in `retrieve()` makes its observation a child of it.
</details>

### Step 4. Check

```bash
make check WEEK=8
```

All 11 checks pass. The checks send one question that calls three tools, one of them with a dataset ID that does not exist, and read the trace back. Then open the trace in the UI (Tracing), and send a question to the running API:

```bash
make ask Q="Which datasets are about crude oil?"
```

This is one real question with your key (about $0.002 for 3 requests of about 5,000 input and 300 output tokens), or a replay from the response cache. The trace from the `api` container was not tested in the build of this lab. Compose gives the container `LANGFUSE_BASE_URL=http://langfuse-web:3000` and the keys from `.env`. If no trace comes, read `make logs`.

Then run the checks of the earlier phases, with Langfuse on and with Langfuse stopped:

```bash
make check PHASE=1
```

```bash
make check PHASE=2
```

```bash
docker compose --profile phase3 stop langfuse-web langfuse-worker
```

```bash
make check PHASE=1
```

```bash
make check PHASE=2
```

```bash
docker compose --profile phase3 start langfuse-worker langfuse-web
```

The 37 checks of Phase 1 and the 50 checks of Phase 2 pass in each case. On the build machine, Phase 1 took 34 s with Langfuse stopped and 15 s with Langfuse on, and the SDK logged "Failed to export spans batch due to timeout, max retries or shutdown" one time at the end. Write the numbers of your trace in [RESULTS.md](RESULTS.md).

## Week 9: Error analysis

### Step 1. Read

In the FAQ: "Why is error analysis so important in AI evals, and how is it performed?", "How many examples do I need for an eval?" and "What is the best approach for generating synthetic data?".

### Step 2. The test set

A test set is the fixed list of questions that you measure the system on. It must look like the questions of real users, in both languages and of both kinds: questions about the datasets of the catalogue, and questions about the documents. A wrong expected ID makes a correct answer fail, so each case needs a person who checked it.

1. Ask Claude Code for a first draft of about 100 questions in English and Arabic. It uses your subscription and no API credit. Give it `data/catalogue.json`, let it read chunks with `docker compose exec db psql -U assistant`, and ask for questions in the words of a user, with the expected IDs.
2. Read each question and each expected ID, and correct them by hand. For a document question, read the chunk. For a dataset question, look up the ID with SQL.
3. Write the cases to `evals/testset.jsonl` in the form of the three examples. Keep their IDs or replace them.

The checks need more than 100 cases, at least 25 in each language, Arabic letters in each Arabic question, no question twice (case and spaces ignored), at least 10 cases with dataset IDs and 10 with chunk IDs, and each expected ID in Postgres.

<details>
<summary>Hint: a start that you already have</summary>

Your 30 questions of Phase 1 (`evals/questions.jsonl`) and your 50 retrieval questions of Phase 2 (`evals/retrieval_questions.jsonl`) already have expected IDs that you checked. They give 80 cases. Give each Phase 1 question a `language`, and add new cases to reach more than 100, for example questions about the datasets in Arabic.
</details>

Then run the test set through the system:

```bash
make testset ARGS="--no-cache"
```

`evals/run_testset.py` runs each case through `answer_events()` inside an observation `testset-case`, with the tags `testset` and `run:<time>`, and writes `evals/results/testset-<time>.jsonl`. With `--no-cache` each request goes to the API, so you read new answers and not replays. Use `ARGS="--limit 10"` or `ARGS="--ids t001,t031"` for a first try. `code_pass` in the output is a first automatic check: the answer names each expected dataset ID and, for a document case, cites one of the expected chunks. It is not your judgement.

**Cost estimate:** assume about 5,000 input tokens and 300 output tokens for each case (2 to 3 requests, the tools, the system prompt and the tool results). One case: 5,000 x $0.10 per million = $0.0005, plus 300 x $0.50 per million = $0.00015, about $0.0007. For 105 cases: 105 x $0.0007 = about $0.07. With more searches and longer tool results, the tokens can be twice as many: about $0.15. Thinking tokens count as output tokens, and they are the least certain part of this estimate. The real cost is in the output of the command and in `logs/requests.jsonl`.

### Step 3. Open coding and axial coding

Error analysis starts from the data. You read traces one at a time, and for each failure you write what went wrong first, in your own words (open coding). When you have read enough traces, you read all your notes again, put them in groups and give each group a name (axial coding). Then you count the groups. The largest group is where the next change helps most, and it is the category of your grader in week 10.

```bash
make notebook NB=phases/phase-3-evaluation/notebooks/error_analysis.ipynb
```

1. `show(n)` prints case `n` of the last run: the question, the tool calls and the retrieved chunks from the trace in Langfuse, the answer and the cited passages.
2. `note(n, passed, text)` saves your decision. Read at least 30 traces. A failure needs a note of at least three words.
3. Read the failure notes in the table of the notebook. Write the categories and their descriptions in `DESCRIPTIONS`, and the category of each failure in `CATEGORIES`.
4. The last cell writes `evals/failure_categories.csv`, largest category first.

<details>
<summary>Hint: what to note</summary>

Note the first step that went wrong, because the later steps often fail as a result of it. For example: the search did not return the expected chunk, the search returned it and the model cited another chunk, the model answered without a search, or the expected ID in your test set is wrong. Fix a wrong expected ID in the test set, and do not count it as a failure of the system.
</details>

### Step 4. The failing cases in a Langfuse dataset

A dataset in Langfuse holds inputs with their expected outputs. When you change the prompt or the code later, you can run the dataset again and compare the runs in the UI.

```bash
make failures-dataset
```

`evals/failures_dataset.py` reads your notes and the test set. Each note with `"passed": false` becomes one item of the dataset `assistant-failures`: the question, the expected IDs, your category and note, and a link to the trace that you read. The ID of an item comes from the case ID, so a second run updates the items and adds no copies. Run it again after each change of your notes or of the expected IDs.

### Step 5. Check

```bash
make check WEEK=9
```

All 9 checks pass. Before your work, three fail, four show as errors (the notes do not exist yet), and two pass (the fields and the IDs of the three example cases). Write the table of failure categories and the numbers of your run in [RESULTS.md](RESULTS.md).

## Week 10: The grader model

### Step 1. Read

Huyen, chapter 3: Limitations of AI as a Judge and What Models Can Act as Judges? (pages 141 to 148). In the FAQ: "Why do you recommend binary (pass/fail) evaluations instead of 1-5 ratings (Likert scales)?", "How do I know if I can trust my automated eval?" and "What should I do when I can't get my LLM judge to agree with human reviewers?".

### Step 2. The rubric and the grader

Some failures need a judgement that code cannot make, for example "the answer says that it searched, but the trace shows no search" or "the cited passage does not hold the number in the answer". A grader model makes this judgement for one failure category. It gives pass or fail, because you and the model can apply a binary rule in the same way each time, which is hard with a scale of 1 to 5. The rubric is the written rule: when an output passes, when it fails, and examples of both from your own traces.

1. Write the rubric of your largest category in `evals/rubric.md`. Follow the headings of the template, and delete its first line.
2. Write `grade()` in `evals/grader.py`. Its docstring has the parts of the request. Send the rubric in the system prompt, the parts of the output that the rubric needs in the user message, and the schema of `Verdict` in `output_config`, as the agent does with `Answer`.

`grade()` calls Claude through `call_claude()`, so each grader request is in the request log and is a generation in Langfuse, with its cost.

<details>
<summary>Hint: what the grader needs to see</summary>

A row of the result file has `question`, `answer`, `dataset_ids`, `citations`, `cited_passages` and `tools`. A rubric about the path of the agent needs `tools`. A rubric about the support of an answer needs `cited_passages`. Send only what the rubric uses: each extra field is input tokens, and a field that the rubric does not mention can change the decision.
</details>

### Step 3. Your labels and the agreement rates

Before you trust a grader, you measure it against your own labels. A positive is a failure, because the grader exists to find failures:

- **The true positive rate** is the share of the outputs that you labelled as failed that the grader also fails.
- **The true negative rate** is the share of the outputs that you labelled as passed that the grader also passes.

Accuracy alone hides a grader that passes everything when most outputs pass. The two rates show each kind of error separately.

1. Write `agreement_rates()` in `evals/grader.py`. Its docstring has the rules.
2. Open the notebook:

```bash
make notebook NB=phases/phase-3-evaluation/notebooks/grader_agreement.ipynb
```

3. Part 1: label 50 outputs yourself, with `show(n)` and `label(n, passed, note)`. Label before you run the grader, so that its decisions do not change yours. Take outputs that pass and outputs that fail: the failures of your notes of week 9 are a good start.
4. Part 2 runs `grade()` on your labelled outputs, and part 3 writes `evals/grader_agreement.json` with the two rates and each disagreement.
5. Read each disagreement. Is the rubric unclear, or is your label wrong? Change the rubric, and run parts 2 and 3 again until you accept both rates.

**How many labels.** The plan asks for 50 labelled outputs. The check needs at least 10 passes and 10 failures, because with fewer outputs in a class one disagreement moves its rate by more than 10 points. The FAQ recommends more: "at least 50 passing and 50 failing examples". Use the number of the FAQ as your goal when you have more traces.

> From the documentation: the number of the FAQ is from the answer to "What should I do when I can't get my LLM judge to agree with human reviewers?" ([AI Evals FAQ](https://hamel.dev/blog/posts/evals-faq/)).

**Cost estimate:** one run of part 2 is 50 requests of about 1,000 input tokens and about 200 output tokens. Input: 50 x 1,000 = 50,000 tokens x $0.10 per million = $0.005. Output: 50 x 200 = 10,000 tokens x $0.50 per million = $0.005. Total: about $0.01 for each run. With the response cache on, a run with the same rubric replays the earlier decisions and costs nothing.

### Step 4. Check

```bash
make check WEEK=10
```

All 13 checks pass. The checks test `agreement_rates()` and `grade()` with the stand-in for the Claude API, then recompute your two rates from the rows of `evals/grader_agreement.json` and print them. If you change the rubric or a label after the last run of the notebook, the check fails until you run parts 2 and 3 again. Write both rates, and the changes of the rubric that moved them, in [RESULTS.md](RESULTS.md).

## Week 11: Evaluation in CI

### Step 1. Read

Huyen, chapter 4: Model Selection (pages 179 to 200). In the FAQ: "How are evaluations used differently in CI/CD vs. monitoring production?".

### Step 2. The pytest suite

The suite in CI is a gate: it runs on each change and fails when a score falls below its threshold. It must be fast and cheap, so it uses a small subset of the test set. The subset is fixed, so that a change of score can only come from a change of the code or the prompt. The code checks are exact and free. The grader adds the judgement of week 10.

1. Mark at most 15 cases of `evals/testset.jsonl` with `"ci": true`, with dataset cases and document cases.
2. Write the suite in `tests/evals/test_evals.py`. Its docstring has the parts: run each case one time for the session with `run_case()`, compute one score for each check (dataset IDs, citations, grader), and write one test for each score with its threshold.
3. Run it on your machine with the real API:

```bash
make evals ARGS="-rA"
```

`make evals` runs `pytest tests/evals -p no:labkit.plugin`, so the stand-in of the lab checks is off and the suite calls the real API. Postgres with the chunks and both model services must run. Langfuse is optional: with the keys in `.env` the suite makes traces, and without the keys it works too.

**Cost estimate:** for 12 cases, about 2 to 3 requests for each case of about 2,000 to 6,000 input tokens (the system prompt and the tools are about 6,700 characters), and 12 grader requests of about 1,000 tokens. Together about 70,000 input tokens and 4,000 output tokens. Input: 70,000 x $0.10 per million = $0.007. Output: 4,000 x $0.50 per million = $0.002. Total: about $0.01 for each run, and about $0.02 when more searches make the tokens twice as many. The CI job costs the same for each run.

<details>
<summary>Hint: a threshold for a small subset</summary>

With 4 document cases, each case is 25 points of the citation score. Choose each threshold from the scores of some runs of your good code, and leave room for one case that the model gets wrong on one run and right on the next. Then confirm that a worse change falls below it.
</details>

### Step 3. The GitHub Actions job

`make start PHASE=3` copied the workflow to `.github/workflows/evals.yml`. It runs on each pull request, and on a manual start (`workflow_dispatch`). It starts Postgres and the two model services as `make up` does (no API container and no Langfuse), installs the packages with uv, creates the tables, loads the catalogue, restores the chunks from a snapshot, and runs `make evals ARGS="-rA"`. The job fails when a test of the suite fails.

**The snapshot.** CI must not parse and embed the documents on each run: `make embed` took 44 minutes on the build machine. So you commit the documents and the chunks with their vectors as a compressed dump:

```bash
make snapshot
```

This writes `data/snapshot/chunks.sql.gz` (data only, the migrations make the tables). On the build machine it took 21 s and gave 23 MB. Run it again after each `make ingest` or `make embed`. In CI, `make restore` empties the tables `documents` and `chunks` and loads the dump in one transaction. It does the same on your machine, so run it only when the snapshot is current. It prints one `set_config` row from the dump, which is harmless.

**The model files.** The two models are 4.6 GB. The workflow keeps them in the cache of GitHub Actions (`actions/cache`), in the folder `.cache/models`, with the new settings `EMBEDDINGS_MODEL_VOLUME` and `RERANKER_MODEL_VOLUME` of `compose.yaml`. It saves the cache right after the services start, so a run whose suite fails still fills it.

> From the documentation: a run for a pull request "can also restore caches created in the base branch", and a cache that a pull request run saves "can only be restored by re-runs of the pull request". GitHub removes a cache entry that was not used for 7 days, and the default limit for all caches of a repository is 10 GB ([Dependency caching reference](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)). `ubuntu-latest` is an x64 runner with 4 CPUs, 16 GB of memory and 14 GB of SSD in a public repository, and 2 CPUs and 8 GB of memory in a private repository. The standard runners are free and unlimited on public repositories, and a private repository uses the minutes that the account includes ([GitHub-hosted runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)). The two model services need about 5.5 GB, so they fit on both sizes.

1. Run `make snapshot`. Commit the snapshot, the workflow, the suite and the test set to your default branch, and push.
2. Add the secret `ANTHROPIC_API_KEY` in the settings of the repository on GitHub: Settings, Secrets and variables, Actions, New repository secret. With the GitHub CLI: `gh secret set ANTHROPIC_API_KEY`.
3. Run the workflow one time on the default branch: Actions, Evals, Run workflow. This first run downloads the two models and saves them in the cache of the default branch, so that each pull request can restore them.

> From the documentation: the path to the secrets and the command `gh secret set` are from [Using secrets in GitHub Actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets). The same page says that secrets are not passed to the runner when a workflow is triggered from a forked repository.

GitHub Actions did not run in the build of this lab. The workflow was checked with actionlint 1.7.12 (no errors), and each of its steps ran by hand in a clean copy of the repository, with the stand-in in place of Claude. There, the services were healthy in 36 s with the model files already in place, the install took 2 s with a filled uv cache, the tables, the catalogue and `make restore` (4683 chunks) took 12 s together, and the suite took 107 s with good answers. The cache save and restore did not run, and the first download of the models was not timed.

<details>
<summary>Hint: block the merge as well</summary>

A failed job shows on the pull request. To block the merge as well, add a rule for your default branch with "Require status checks before merging", and choose the job `evals`.

> From the documentation: [About protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches). Protected branches are available in public repositories with GitHub Free, and in private repositories with the paid plans that the page lists, for example GitHub Pro.
</details>

#### Optional: a review bot on each pull request

The Claude Code GitHub Action can review each pull request and write comments on it. `phases/phase-3-evaluation/workflows/claude-review.yml` is the "Code Review" example of the [Claude Code GitHub Actions docs](https://code.claude.com/docs/en/github-actions), with your subscription token in place of an API key. `make start` does not copy it.

1. Install the [Claude GitHub App](https://github.com/apps/claude) on your repository.
2. Run `claude setup-token` on your machine. It makes an OAuth token for your Claude subscription. Add it as the secret `CLAUDE_CODE_OAUTH_TOKEN` of the repository (not `ANTHROPIC_API_KEY`).
3. Copy the file to `.github/workflows/claude-review.yml` and push it.

The review uses your subscription and no API credit, but each run uses GitHub Actions minutes. This workflow was checked with actionlint (no errors) and did not run in the build of this lab.

> From the documentation: the token from `claude setup-token` works with the Pro, Max, Ultra, Team and Enterprise plans, runs that use it use the subscription and not API billing, the action runs on GitHub-hosted runners and uses Actions minutes, and on public repositories GitHub gives no secrets to runs from fork pull requests ([Claude Code GitHub Actions](https://code.claude.com/docs/en/github-actions)).

### Step 4. A pull request with a deliberately bad prompt change

1. Make a new branch.
2. In the system prompt of `assistant/agent.py`, find your rule that tells the model to search before it answers. In the reference build of this lab the rule was "You know nothing about the catalogue except what the tools return. Always search before you answer, also when you think that you know the answer." Replace your rule with this sentence:

```text
Answer from what you know about Saudi statistics. Use a tool only when you are not sure.
```

3. Run `make evals ARGS="-rA"` on your machine (about $0.01 to $0.02), and read the scores.
4. Commit, push the branch, and open a pull request to your default branch.

### Step 5. Check: the exit test

```bash
make check WEEK=11
```

All 8 checks pass. They check the workflow and the snapshot, then run your suite five times against the stand-in for the Claude API. With good answers the suite must pass, with at least 3 passed tests. In four runs the answers are worse: wrong dataset IDs, a cited chunk ID that no search returned, a returned chunk that is not the expected one, and a grader that fails each output. Your suite must fail each of these runs. This is the exit test without the real API.

```bash
make check PHASE=3
```

The 41 checks of the phase pass. Then the exit test of the plan, on GitHub:

- **The bad change is blocked by CI.** The job `evals` of your pull request fails, and its log shows which score fell below its threshold.
- **You can state the agreement rates of the grader.** The check of week 10 prints them.

In the build of this lab, the same bad change was tested with a stand-in that follows the system prompt. Before the change the suite passed (dataset IDs 1.00 over 8 cases, citations 1.00 over 4 cases, grader 1.00 over 12 cases). After the change it failed, with all three scores at 0.00. This proves the suite and its thresholds, not the real model: what Claude Haiku 5.5 does with the bad prompt was not run. If your job passes with the bad change, read the traces of the suite. Did the model still search? If it did, the change does not hurt this model, so make the change worse. If it did not, your scores do not see the change, so add a check or a case that it breaks.

Write the scores before and after, the link to the pull request and both agreement rates in [RESULTS.md](RESULTS.md). Then close the pull request without a merge.

## Commands

| Command | What it does |
| --- | --- |
| `make up` | Start Postgres, the API, the two model services and Langfuse, apply the migrations, load the catalogue |
| `make down` | Stop the services and keep the data |
| `make testset` | Run `evals/testset.jsonl` through the assistant, one trace for each case. `ARGS="--no-cache"`, `--limit 10`, `--ids t001,t031` |
| `make notebook NB=path` | Open a notebook of the lab in JupyterLab |
| `make failures-dataset` | Send the failing cases of your notes to the Langfuse dataset `assistant-failures` |
| `make snapshot` | Write the documents and the chunks with their vectors to `data/snapshot/chunks.sql.gz` |
| `make restore` | Replace the documents and the chunks in Postgres with the snapshot |
| `make evals` | Run the suite `tests/evals` with the real Claude API. `ARGS="-rA"` prints each test |
| `make check WEEK=8` | Offline checks of one week |
| `make check PHASE=3` | Offline checks of the phase |

| Setting in `.env` | Default | Meaning |
| --- | --- | --- |
| `LANGFUSE_PUBLIC_KEY` | `pk-lf-local-lab` | The public key of the project. The first start of Langfuse creates it |
| `LANGFUSE_SECRET_KEY` | `sk-lf-local-lab` | The secret key of the project. It works only on your machine |
| `LANGFUSE_PORT` | `3000` | The port of the Langfuse UI on your machine. Change it, and the port in `LANGFUSE_BASE_URL`, if 3000 is in use |
| `LANGFUSE_BASE_URL` | `http://localhost:3000` | Where your code, the notebooks and the checks find Langfuse |

MinIO, the file store of Langfuse, uses port 9090 on your machine. If 9090 is in use, change the left side of its port mapping in `compose.yaml`, and the same port in `LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT` of `langfuse-web`, as the [Docker Compose page](https://langfuse.com/self-hosting/deployment/docker-compose) of Langfuse says.

`make reset` deletes only the database of the assistant. To delete the data of Langfuse too, run `make down`, then the `docker volume rm` command of week 8, step 2.
