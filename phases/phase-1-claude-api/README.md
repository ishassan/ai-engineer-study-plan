# Phase 1 lab: the Claude API and a hand-written agent loop

Weeks 1 to 3 of the [study plan](../../README.md#phase-1-the-claude-api-and-a-hand-written-agent-loop-weeks-1-to-3). At the end, a small API service answers questions about a catalogue of 50 public datasets. The service uses a model loop that you wrote, and you know the cost of each request.

The lab gives you the parts that teach nothing new: Docker Compose, the database schema, the catalogue data and the HTTP layer. You write the parts that the phase teaches:

| Week | You write | File |
| --- | --- | --- |
| 1 | The function that calls Claude: streaming, cost log, response cache | `assistant/llm.py` |
| 1 | One request for one question, as a stream of events | `assistant/agent.py` |
| 1 | 30 test questions | `evals/questions.jsonl` |
| 2 | Three tools and their definitions | `assistant/tools.py` |
| 2 | The model loop | `assistant/agent.py` |
| 3 | The typed answer | `assistant/schemas.py` |
| 3 | Prompt caching | `assistant/agent.py` |
| 3 | The test runner | `evals/run.py` |

**Cost:** the offline checks are free. The three live checks of this phase cost about $0.06 together on Claude Haiku 5.5. This number is an estimate from the size of the requests. The response cache keeps your daily work near zero.

## Setup

You need Docker Desktop, [uv](https://docs.astral.sh/uv/getting-started/installation/) and `make`. Run these commands from the repository root.

```bash
make start PHASE=1
```

This command copies the starter files into `assistant/` and `evals/`. It never changes a file that exists, so it is safe to run again.

```bash
cp .env.example .env
```

```bash
make up
```

`make up` builds the API image, starts Postgres and the API, creates the tables and loads the 50 datasets. Then run the checks of week 1:

```bash
make check WEEK=1
```

One check passes (the catalogue is in Postgres) and 12 fail. Each failing check names a step of week 1.

## How the lab works

- **Steps.** Each week below has the same steps as the plan, in the same order.
- **Offline checks.** `make check WEEK=n` runs in a few seconds and costs nothing. The checks start a stand-in for the Claude API on your machine and point the `anthropic` SDK at it. Your code is the same code that calls the real API. The stand-in follows the documented rules for streaming, tool results and prompt caching, and it answers with what each check scripts. Read a failing check: its message says what is missing.
- **Live checks.** `make check-live WEEK=n` calls the real API with your key. Run it one time, when the offline checks pass. If a live check and an offline check disagree, the real API is correct.
- **Hints.** A hint is closed until you click it. Try the step first.
- **Your design.** The checks look at the service from outside: the event stream of `/ask`, the request log, and the requests that reach the API. Inside the files you can add functions and change the structure. Keep only the names in the table below.

| Name | Where | Used by |
| --- | --- | --- |
| `answer_events(question)` | `assistant/agent.py` | The API and the test runner |
| `cost_usd(model, usage)`, `request_hash(request)` | `assistant/llm.py` | Checks of weeks 1 and 3 |
| `TOOLS`, `run_tool(name, tool_input)` | `assistant/tools.py` | Checks of week 2 |
| `Answer` | `assistant/schemas.py` | Checks of week 3 |
| `python -m evals.run` | `evals/run.py` | Checks of week 3 |

Read the settings with `get_settings()` from `assistant/config.py` each time you need one. The checks change environment variables between tests, so a value that you keep in a module constant goes stale.

### The event stream of `/ask`

`POST /ask` with `{"question": "..."}` returns server-sent events. `assistant/api.py` is complete: it sends each `(event, data)` pair that `answer_events()` yields.

| Event | Data | From |
| --- | --- | --- |
| `text` | `{"text": "..."}` for each piece of text | Weeks 1 and 2 |
| `tool` | `{"name": ..., "input": {...}, "is_error": false}` for each tool call | Week 2 |
| `answer` | `{"answer": ..., "dataset_ids": [...], "tools_called": [...]}` | Week 3 |
| `error` | `{"message": "..."}` | Week 2 |
| `done` | `model`, `input_tokens`, `output_tokens`, `cost_usd`, `latency_ms`, `requests`, `stop` | Week 1 |

`done` is always the last event. Its numbers are the sums of all requests to Claude for this question. `stop` is `"final"` when the model gave a final answer, and `"max_turns"` when the loop gave up.

## Week 1: The first request

### Step 1. Read

Claude [Get started](https://platform.claude.com/docs/en/get-started), [Using the Messages API](https://platform.claude.com/docs/en/build-with-claude/working-with-messages) and [Streaming messages](https://platform.claude.com/docs/en/build-with-claude/streaming).

### Step 2. The repository, the service and the catalogue

`make up` did this step. Look at what it made, because your tools read these tables in week 2.

```bash
docker compose exec db psql -U assistant -c "\d datasets" -c "\d dataset_columns"
```

```bash
docker compose exec db psql -U assistant -c "SELECT id, title, owner, records_count FROM datasets ORDER BY id LIMIT 10"
```

The data is the metadata of 50 public-domain datasets about Saudi Arabia from the [KAPSARC data portal](https://datasource.kapsarc.org/). `data/catalogue.json` holds the copy that the loader reads, and `scripts/fetch_catalogue.py` shows how it was made. Note that many dataset IDs do not match their title. The dataset "Crude Oil Production" has the ID `saudi-crude-oil-production-from-sama-annual-statistics-2015-dec`. A model cannot guess these IDs, which is useful: an answer with a correct ID proves that the model used a tool.

### Step 3. The API key and the model

1. In the [Claude Console](https://platform.claude.com/), buy $5 of credit and keep auto-reload off. With auto-reload off, the API stops when the credit is used, so $5 is the most that this phase can cost.
2. Create an [API key](https://platform.claude.com/settings/keys) and put it in `.env` as `ANTHROPIC_API_KEY`. Git ignores `.env`.
3. Run `make up` again, so that the API container gets the key.

The model is Claude Haiku 5.5 (`claude-haiku-5-5`), set in `assistant/config.py` with its prices. These facts from its docs matter for your code:

- Thinking is on by default, and thinking tokens count toward `max_tokens`. A low `max_tokens` cuts the answer off. Use `get_settings().max_tokens`.
- Each response can start with a `thinking` block. Its text is empty by default, and it has a `signature`. You do not show it, but in week 2 you must send it back.
- The [model page](https://platform.claude.com/docs/en/models/haiku-5-5/overview) says to omit `temperature`, `top_p` and `top_k`. Keep the default effort, as the plan says.

### Step 4. `/ask` streams the answer and logs each request

Write these parts.

1. `cost_usd()` in `assistant/llm.py`. For now it counts input and output tokens.
2. `stream_claude()` in `assistant/llm.py`, without the cache. It calls `client.messages.stream(**request)`, yields `("text", piece)` for each piece of text, appends one JSON line to the request log, and yields `("result", ClaudeResult(...))` at the end.
3. `answer_events()` in `assistant/agent.py`. It builds one request with the system prompt and the question, passes the text on as `text` events, and ends with the `done` event.

<details>
<summary>Hint: the shape of the streaming call</summary>

```python
with client.messages.stream(**request) as stream:
    for text in stream.text_stream:
        ...  # one piece of text
    message = stream.get_final_message()  # the complete Message, with usage
```

Measure the latency with `time.perf_counter()` around this block.
</details>

<details>
<summary>Hint: where the client comes from</summary>

`anthropic.Anthropic()` reads `ANTHROPIC_API_KEY` and `ANTHROPIC_BASE_URL` from the environment. Do not pass a base URL in code: the offline checks use that variable to send the SDK to the stand-in.
</details>

Run `make check WEEK=1`. The four checks of this step and the `cost_usd` check must pass.

### Step 5. The response cache

While you build, you send the same request many times. The response cache saves each response in a file and replays it when the same request comes again. A replay is a real response of Claude, costs nothing and takes a few milliseconds.

1. Write `request_hash()`: a hash of the full request body. Two requests with the same content must give the same hash.
2. Add the cache to `stream_claude()`. The rules are in its docstring. A replay yields the saved text, logs a line with `"replayed": true` and a cost of 0, and makes no API call.

The cost in the log must be the money that you spent. If a replay logged the cost of the first call again, the log would not agree with the bill in the Console.

<details>
<summary>Hint: a stable hash</summary>

`json.dumps(request, sort_keys=True)` gives the same text for the same content. Hash that text with `hashlib.sha256`. From week 2 the messages hold SDK objects, which `json.dumps` cannot write. Its `default=` argument takes a function for such objects, and each SDK object has `model_dump()`.
</details>

<details>
<summary>Hint: save and load a message</summary>

`message.model_dump_json()` gives the JSON text of a response. `Message.model_validate_json(text)` builds the same object again, with its usage.
</details>

A response cache is different from prompt caching, which comes in week 3. Here the model does not run at all. Use the cache while you build. Turn it off (`RESPONSE_CACHE=off`) when you measure quality, because a replay is one old sample of an answer that changes from run to run.

### Step 6. The 30 test questions

Write 30 questions in `evals/questions.jsonl`, one JSON object on each line. The file has three examples. For each question, write the dataset IDs that a correct answer must name, and mark 5 questions with `"quick": true`.

Write questions that a user of a data platform asks. Use these kinds, about ten of each:

- **Find one dataset.** Use the words of a user, and not the words of the title: "how much water does each person use" for the dataset "Per Capita Water Consumption In Saudi Regions".
- **Find several datasets.** The catalogue has groups of similar datasets, for example four about imports. A question that needs two of them tests if the model names each one.
- **Ask about one dataset.** Its columns, its size, its last update or its owner. These questions need the schema tool or the stats tool of week 2.

Look for the IDs with SQL, as in step 2. You can ask Claude Code for a first draft from `data/catalogue.json`, which uses your subscription and no API credit. Then read each line and correct it: a wrong expected ID makes a correct answer fail.

### Step 7. Check

```bash
make check WEEK=1
```

All 13 checks pass. Then try the running service:

```bash
make ask Q="Which datasets are about crude oil?"
```

```bash
curl -N -X POST localhost:8000/ask -H "content-type: application/json" -d '{"question": "Which datasets are about crude oil?"}'
```

The text arrives in pieces and the `done` event shows the tokens, the cost and the latency. Send the same question again: the cost is 0 and the latency is a few milliseconds. The answer itself is a guess, because the model cannot see the catalogue before week 2. Then run the live check, which makes one real request (less than $0.001):

```bash
make check-live WEEK=1
```

Write the numbers that it prints in [RESULTS.md](RESULTS.md).

## Week 2: Tool calling and the model loop

### Step 1. Read

Claude [How tool use works](https://platform.claude.com/docs/en/agents-and-tools/tool-use/how-tool-use-works) and [Tutorial: Build a tool-using agent](https://platform.claude.com/docs/en/agents-and-tools/tool-use/build-a-tool-using-agent).

### Step 2. The three tools

In `assistant/tools.py`, write the three functions with `query()` from `assistant/db.py`, the `TOOLS` list with their definitions, and `run_tool()`.

- **The description is the prompt of the tool.** The model reads only the definition. The docs say to aim for at least 3 to 4 sentences for each description: what the tool does, when to use it, what each parameter means and what it returns.
- **Keep results small.** A tool result goes into the prompt of the next request, and you pay for it again in each later turn. `search_datasets` returns the few best matches, with a short description.
- **Make the search forgiving.** Users do not use the words of the titles. Postgres full-text search matches word forms ("consumption" and "consumed"). Decide what happens when only some of the words match.
- **Raise errors with a useful message.** When the dataset does not exist, raise an exception that says what to do, for example "Use search_datasets to find a correct id". The model reads this message and corrects its next call.

<details>
<summary>Hint: full-text search in one query</summary>

`to_tsvector('english', title || ' ' || description)` makes the searchable form of a row, `plainto_tsquery('english', %s)` makes the query, `@@` matches them, and `ts_rank()` orders the results. `plainto_tsquery` needs every word to match. To accept a match on any word, replace `&` with `|` in the text of the query before you cast it to `tsquery`.
</details>

### Step 3. The loop

Change `answer_events()` into the loop. No framework: the loop is about 40 lines.

1. Send the messages with `tools=TOOLS`.
2. If `message.stop_reason` is `"tool_use"`: add the assistant turn to the messages, run each `tool_use` block of the turn with `run_tool()`, add one user message that holds one `tool_result` block for each call, and send again.
3. If the stop reason is something else, the text of this turn is the final answer.
4. Stop after `get_settings().max_turns` requests (8). Then yield an `error` event and set `stop` to `"max_turns"`.
5. When a tool raises an exception, do not stop. Send the message of the exception as the tool result, with `"is_error": True`.

Yield a `tool` event for each tool call, and add up the tokens, cost and latency of all requests for the `done` event.

These rules of the API decide if the loop works:

- **Send the full assistant turn back.** Add `message.content` to the messages as it is, with its `thinking` and `tool_use` blocks. The docs say that you must pass thinking blocks back unchanged when you return tool results.
- **Each `tool_use` needs its `tool_result`** in the next message, with the same `tool_use_id`. If one is missing, the API answers with a 400 error. The stand-in does the same, with the same kind of message.
- **All results of one turn go in one user message.** The model can ask for two tools in one turn.

<details>
<summary>Hint: the two messages that you add in each turn</summary>

```python
messages.append({"role": "assistant", "content": message.content})
messages.append({"role": "user", "content": results})  # a list of tool_result blocks
```

One tool result: `{"type": "tool_result", "tool_use_id": block.id, "content": output, "is_error": False}`.
</details>

Tell the model in the system prompt that it knows the catalogue only through the tools, and that it must give the ID of each dataset that it names.

### Step 4. Check

```bash
make check WEEK=2
```

All 12 checks pass. Then ask the running service a question from your list with `make ask` and read the `tool` events. Run the live check, which sends your 5 quick questions through the real loop (about $0.01):

```bash
make check-live WEEK=2
```

It prints the tools that each question used and checks that at least 4 of the 5 answers name the expected IDs. When an answer is wrong, find the cause before you change the prompt: did the search return the dataset? Call `run_tool()` in a Python shell with the query from the `tool` event.

## Week 3: Structured output, caching and the test runner

### Step 1. Read

Claude [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) and [Prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices).

### Step 2. The typed answer

1. Define `Answer` in `assistant/schemas.py`, with a description on each field.
2. Send its JSON schema in each request of the loop, in `output_config`. The API then returns a final answer that is valid JSON for the schema.
3. Validate the final text with `Answer.model_validate_json()`. Yield the result as one `answer` event. When validation fails, or the stop reason is not `"end_turn"`, yield an `error` event.

The stream changes in this step. Until now you sent each piece of text when it arrived. Now the text is a JSON document, and half a JSON document is of no use to the client. So collect the text, validate it, and send one `answer` event. The `tool` events still arrive while the model works, so the client sees progress. Phase 2 needs the same order for another reason: it rejects an answer that cites a wrong source, and you cannot take back text that you already sent.

Validation still has work to do. A response that stops with `"max_tokens"` is cut-off JSON, and a refusal does not follow the schema.

<details>
<summary>Hint: the schema in the request</summary>

```python
from anthropic import transform_schema

"output_config": {"format": {"type": "json_schema", "schema": transform_schema(Answer)}}
```

`transform_schema()` changes the schema of a Pydantic model into the form that the API accepts.
</details>

Compare `tools_called` in the answer with the `tool` events of the same stream. The first is what the model says that it did, and the second is what your loop ran. They can differ. In week 17 you score the path that the agent took, and not only its answer.

### Step 3. Prompt caching

In the loop, each request sends the tool definitions and the system prompt again. Prompt caching lets the API read this part from a cache at a tenth of the input price. The model still runs and writes a new answer.

1. Finish `cost_usd()`: add the cache write tokens and the cache read tokens, with their prices in `PRICES_PER_MTOK`.
2. Before the change, ask three questions with `make ask` and note the `cost_usd` of each `done` event.
3. Put a cache breakpoint on the system prompt: send `system` as a list with one text block, and give the block `"cache_control": {"type": "ephemeral"}`.
4. Ask the same three questions again, in less than 5 minutes. The request body changed, so the response cache does not answer them. In `logs/requests.jsonl`, the first request has `cache_creation_input_tokens` above 0, and the later ones have `cache_read_input_tokens` above 0. Write the cost before and after in `RESULTS.md`.

A cache entry lives for 5 minutes after its last use. So the saving is large in a test run and in a busy service, and small for one request each hour.

These rules from the docs explain most caching problems:

- **The order of the cached part is tools, then system, then messages.** A breakpoint on the system prompt covers the tools and the system prompt.
- **The part before the breakpoint must have at least 512 tokens** on Haiku 5.5. Below that, the request works and nothing is cached, with no error. Count your tokens with `client.messages.count_tokens()`, which is free. If you are below 512, the system prompt is too thin. Describe the catalogue and the working rules in more detail, which also gives better answers.
- **A cache entry is written only at a breakpoint, and it is found again only if each byte before it is the same.** A date or the question inside the system prompt gives a new entry on each request, and no read.

<details>
<summary>Hint: a second breakpoint for the loop</summary>

The breakpoint on the system prompt gives a cache read on each request of each question. Inside one question, each turn also sends the earlier turns again. A top-level `"cache_control": {"type": "ephemeral"}` in the request adds a second breakpoint on the last block, so each turn reads the turns before it. Measure if it lowers your cost: a cache write costs 25% more than normal input.
</details>

### Step 4. The test runner

Write `evals/run.py`. Its docstring has the arguments and the fields of the result file. A question passes when the answer names each expected dataset ID.

```bash
make eval SET=quick
```

```bash
make eval SET=all ARGS=--no-cache
```

Use the quick set with the response cache on while you change code. Use all 30 questions with the cache off when you measure.

### Step 5. Check: the exit test

```bash
make check PHASE=1
```

All 37 offline checks of the phase pass. Then run the exit test of the plan against the real API: the 30 questions, from one command, with the response cache off (about 90 requests, about $0.05).

```bash
make check-live WEEK=3
```

The check passes when each question has tokens, cost and latency, and the request log shows cache reads. It prints the pass rate, the total cost, the median latency and the share of input tokens that came from the cache. Write them in [RESULTS.md](RESULTS.md).

The plan sets no pass rate for this phase. Read the failed questions anyway, and sort them by cause: the search did not return the dataset, the model chose another dataset, or the expected IDs in your file are wrong. Phase 3 turns this reading into a method.

## Commands

| Command | What it does |
| --- | --- |
| `make up` | Start Postgres and the API, create the tables, load the catalogue |
| `make down` | Stop the services and keep the data |
| `make reset` | Stop the services and delete the database volume |
| `make logs` | Follow the log of the API, with the traceback of each failed request |
| `make check WEEK=2` | Offline checks of one week |
| `make check PHASE=1` | Offline checks of the phase |
| `make check-live WEEK=2` | Live check of one week |
| `make ask Q="..."` | Send one question to the running API |
| `make eval SET=quick` | Run the test questions |

| Setting in `.env` | Default | Meaning |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | none | Your Claude API key |
| `RESPONSE_CACHE` | `on` | `off` sends each request to the API |
| `POSTGRES_PORT` | `5432` | Change it, and the port in `DATABASE_URL`, if 5432 is in use |
| `CLAUDE_MAX_TOKENS` | `4096` | Upper limit of one response, thinking included |
| `AGENT_MAX_TURNS` | `8` | Most requests to Claude for one question |

Your request log is `logs/requests.jsonl`, and the response cache is the folder `.cache/responses/`. Delete the folder to forget all saved responses.
