# Phase 4 lab: agents with LangChain, LangGraph and MCP

Weeks 12 to 17 of the [study plan](../../README.md#phase-4-agents-with-langchain-langgraph-and-mcp-weeks-12-to-17). At the end, the assistant remembers each conversation and the facts of each user, writes a plan and changes it when a step fails, and runs as a LangGraph graph on Claude and on OpenAI. The graph keeps its state in Postgres, waits for a person to approve the write action `register_dataset`, writes an audit log of each tool call, and gets its tools from two MCP servers. You score the agent on 30 multi-step tasks, on the final result and on the path.

From this phase the lab gives less code. It gives the infrastructure (migrations, the conversation store, the two server shells, the runners of the comparison and of the agent tasks, the Compose services), the stubs of the parts that the plan names, and checks that test your code from outside. You write the parts that the phase teaches:

| Week | You write | File |
| --- | --- | --- |
| 12 | The conversation in the loop, compaction, long-term memory and the tool `save_memory` | `assistant/agent.py`, `assistant/memory.py`, `assistant/tools.py` |
| 13 | The planner, and the change of the plan after a failed step | `assistant/planner.py`, `assistant/agent.py` |
| 14 | The graph, the chat models of both providers, the citations in plain code | `assistant/graph.py`, `assistant/models.py` |
| 14 | The comparison of the two loops and the two providers | `evals/results/compare-*.json` (written by `make compare`) |
| 15 | The Postgres checkpointer and store, the approval of `register_dataset`, the audit log | `assistant/graph.py`, `assistant/memory.py`, `assistant/tools.py` |
| 16 | The two MCP servers, the read-only role, the client in the graph | `assistant/servers/`, a new file in `db/migrations/`, `assistant/graph.py` |
| 17 | 30 tasks, the two scores, the CI step | `evals/agent_tasks.jsonl`, `evals/agent_eval.py`, `.github/workflows/evals.yml` |

**Cost:** the offline checks are free. They use the stand-in for the Claude API of Phase 1 and a new stand-in for the OpenAI API. Four steps call a real API: `make compare` in week 14 (Claude and OpenAI), `make agent-eval` in week 17 (Claude, on your machine and in CI), and the two live checks. Each step below gives its estimate with the arithmetic. As an example, three runs of `make compare` on 105 cases, three runs of `make agent-eval` and both live checks cost about $0.30 to $0.80 together. These numbers are estimates, not measurements. You draft the 30 agent tasks with Claude Code, which uses your subscription and no API credit.

## Before you start

- **Phase 3 is complete.** `make check PHASE=1`, `make check PHASE=2` and `make check PHASE=3` pass. This phase changes files that you wrote in Phases 1 to 3 (see [Changes to files from earlier phases](#changes-to-files-from-earlier-phases)).
- **Services.** The phase uses the services of Phases 2 and 3: Postgres, the embedding service, the re-ranking service and Langfuse. The phase adds two services for week 16, `mcp-sql` and `mcp-catalogue`. `make up` builds them from the `Dockerfile` of the API (base image `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`, as in Phase 1), so no new base image comes from the network. The build time, the size of the image with the Phase 4 packages and the memory of the two services were not measured.
- **Download for week 17.** The workflow check runs actionlint in Docker with the image `rhysd/actionlint:1.7.12`. The image has a linux/arm64 build (checked by its manifest). Its size was not measured.
- **An OpenAI API key for week 14.** The graph runs on OpenAI in `make compare` and in the live check of week 14. Week 17 needs only the Claude key.
- **Data.** The repository holds eight data tables of the catalogue in `data/tables/` (3,217 records, 196 KB, CSV exports of the KAPSARC portal with the license "Public Domain"). `make up` loads them into the schema `data` for the SQL server of week 16.

All times in this guide were measured on a Linux machine with 4 x86 CPU cores, 15 GiB of memory and no GPU, not on a Mac. Nothing in this phase ran on Apple Silicon. Write your own numbers in [RESULTS.md](RESULTS.md).

## Setup

Run these commands from the repository root.

```bash
make start PHASE=4
```

This command copies the new files of the phase: `db/migrations/0005_conversations_and_memory.sql`, `0006_audit_log.sql` and `0007_data_tables.sql`, `assistant/conversations.py` (complete), `assistant/memory.py`, `assistant/planner.py`, `assistant/models.py`, `assistant/graph.py` (stubs), `assistant/servers/` (two server shells with stubs), `evals/compare.py` (complete), `evals/agent_eval.py` (the runner is complete, two score functions are stubs) and `evals/agent_tasks.jsonl` (three example tasks). It also turns on the Python packages of the phase (LangChain, LangGraph, the Postgres checkpointer, the MCP SDK and the MCP adapters) and the Docker services of the phase. It does not change a file that exists.

### The given files of Phase 1

`make start` never overwrites a file, so it cannot update the two given files of Phase 1, `assistant/api.py` and `assistant/config.py`. Copy the Phase 4 copies by hand:

```bash
cp phases/phase-4-agents/given/assistant/api.py phases/phase-4-agents/given/assistant/config.py assistant/
```

You did not write these two files, so you lose no work. The new `api.py` reads `conversation_id` from the body of `/ask`, the user from the header `X-User`, chooses the loop with the setting `AGENT_IMPL`, and has `POST /approve` for week 15. The new `config.py` has the settings of the phase and the prices of the OpenAI model.

**Then change one function signature before anything else.** The new `api.py` calls your loop like this:

```python
answer_events(question, conversation_id=..., user=...)
```

Give `answer_events()` in `assistant/agent.py` this signature:

```python
def answer_events(question, conversation_id=None, user="anonymous"):
```

Until you do this, each `/ask` request gives an `error` event (a `TypeError`), and the checks of Phases 1 to 3 fail: on the build machine, 18 of the 37 Phase 1 checks failed. The defaults are part of the contract: `evals/run_testset.py`, `tests/evals` and the week 8 checks call `answer_events()` with the question only. Then run `make check PHASE=1` again.

### Settings and services

Your `.env` is from the earlier phases. Copy the Phase 4 lines of `.env.example` into it, and put your OpenAI key on the first line:

```bash
OPENAI_API_KEY=
AGENT_IMPL=handwritten
PROVIDER=anthropic
MCP_SQL_URL=http://localhost:8091/mcp
MCP_CATALOGUE_URL=http://localhost:8092/mcp
SQL_ROW_LIMIT=200
SQL_TIMEOUT_SECONDS=5
```

```bash
make up
```

`make up` now also applies the new migrations and loads the data tables (`scripts/load_tables.py`). Migration 0005 needs the extension `vector` of Phase 2. `make up` also builds and starts the two MCP servers (profile `phase4`). Their tools are stubs until week 16, so a call to a tool gives an error until then.

> Not run in the build of this lab: `make up` as one command with the Phase 4 profile, and the `api` container with `PROVIDER=openai`. The two MCP services ran from the repository `compose.yaml` with an image built from the same `Dockerfile`, and answered on 127.0.0.1:8091 and 127.0.0.1:8092 and inside the Docker network.

Then run the checks of week 12:

```bash
make check WEEK=12
```

Before your work, 6 checks fail and 3 pass: the tables exist (given migration), the `done` event has the conversation ID (the given `api.py` adds it), and "another user cannot read a conversation" (nothing reaches the model yet).

## How the lab works

- **Steps.** Each week below has the same steps as the plan, in the same order.
- **Checks need your local services.** Week 12 needs Postgres and the embedding service. Week 13 needs Postgres. Week 14 needs Postgres, both model services, Langfuse, and the three result files of `make compare`. Week 15 needs Postgres and the embedding service. Week 16 needs Postgres, both model services, the schema `data` and Langfuse. Week 17 needs Postgres and Docker. Langfuse is optional for weeks 15 and 17: without the keys, the traces are dropped. On the build machine the checks took: week 12 5 s, week 13 2 s, week 14 84 to 90 s, week 15 11 to 14 s, week 16 130 s, week 17 6 s.
- **Which loop.** The checks of weeks 12 and 13 use your hand-written loop (`AGENT_IMPL=handwritten`). The checks of weeks 14 to 17 use the graph (`AGENT_IMPL=langgraph`). Each check sets the value itself, so your `.env` does not matter for the checks.
- **Live checks.** `make check-live WEEK=14` and `make check-live WEEK=17` call the real APIs with your keys. They did not run in the build of this lab.
- **The checks write to your database.** The checks of weeks 12 to 17 write conversations, messages, facts, checkpoints, store items and audit rows for users named `check-<12 hex characters>`, `history-check`, `anonymous` and `agent-eval`. They do not delete them. A new user name in each check keeps the memory search free of old rows. The datasets that the checks register have IDs that start with `check-`, and the checks delete them at the end.
- **Your design.** The checks look at the event stream of `/ask` and `/approve`, the requests that the stand-ins received, the database, the logs of your MCP servers, the traces in Langfuse and the result files. Inside the files you can add functions and change the structure. Keep the names and the contracts below.

| Name | Where | Used by |
| --- | --- | --- |
| `answer_events(question, conversation_id=None, user="anonymous")` | `assistant/agent.py`, `assistant/graph.py` | The given `api.py`, all checks |
| `save_memory` in `TOOLS`, with `required == ["fact"]` and a description of 150 characters or more | `assistant/tools.py` | Checks of weeks 12 and 14 |
| `save_fact(user, fact)`, `search_facts(user, text, k)`: a list of dicts with `text`, closest first | `assistant/memory.py` | Checks of weeks 12, 14 and 15 |
| `Plan` (given): `{"steps": [str]}` | `assistant/planner.py` | Checks of weeks 13 and 14 |
| `resume_events(conversation_id, approved=..., approver=...)` | `assistant/graph.py` | The given `api.py` (`POST /approve`), `evals/agent_eval.py`, checks of weeks 15 to 17 |
| The tool `register_dataset`: `dataset_id`, `title`, `description`, `owner` (required), `source_url` (optional) | the graph (week 15), then `assistant/servers/catalogue_server.py` | Checks of weeks 15 to 17 |
| The table `audit_log` | `db/migrations/0006_audit_log.sql` (given) | Checks of weeks 15 and 16 |
| The tables of `PostgresSaver.setup()` and `PostgresStore.setup()` | your graph and `assistant/memory.py` | Week 15 checks |
| `run_sql(query)`, FastMCP name `sql` | `assistant/servers/sql_server.py` | Checks of weeks 16 and 17 |
| `search_datasets`, `get_dataset_schema`, `get_dataset_stats`, `register_dataset` | `assistant/servers/catalogue_server.py` | Checks of weeks 16 and 17 |
| The read-only role of `SQL_DATABASE_URL` (default `assistant_reader`) | your migration in `db/migrations/` | Week 16 checks |
| `result_score(expected, answer)`, `path_score(expected, actual)` | `evals/agent_eval.py` | Week 17 checks |
| `evals/agent_tasks.jsonl` | your tasks | Week 17 checks, `make agent-eval` |
| `evals/results/compare-<impl>-<provider>.json` | written by `make compare` | Week 14 checks |
| `evals/results/agent-tasks.json` | written by `make agent-eval` | Week 17 checks |
| A step of `.github/workflows/evals.yml` that runs the agent tasks | your workflow | Week 17 checks |

These contracts are also fixed:

- **The request.** `POST /ask` takes `question` and an optional `conversation_id`. Without it, the service makes a new UUID. The service adds `conversation_id` to the `done` event of each stream. After an exception it sends `error`, then `done` with `stop: "error"`. The user is the header `X-User` (empty or absent: `anonymous`). Only `current_user()` in `api.py` reads it, so Phase 5 changes one function.
- **The events.** Both loops give the same events: `plan`, `tool`, `answer`, `error` and `done`, and the graph also gives `approval` from week 15. The `done` event has the keys of Phase 1. Its `requests` counts each request to the model, the plan requests too. Its `input_tokens` does not hold the cache tokens, as the Claude API gives it.
- **A plan request** is a request whose structured output schema has the field `steps` (in `output_config.format.schema`, or in a forced tool with that schema). **An answer request** has the field `dataset_ids` in its schema. The answer schema keeps the field `citations` with `chunk_id` in each item.
- **An approval.** When the graph pauses, the stream of `/ask` sends one `approval` event for each call that needs an approval, as `{"name": "register_dataset", "input": {...}}` (the same keys as the `tool` event), and ends with `done`. The approver is the header `X-User` of `POST /approve`. A refusal goes back to the model as the tool result of the call, and the result and the audit row hold one of the words "refus", "reject", "denied", "declin" or "not approved" (any case).
- **A task** is one JSON line with `id`, `task`, `expected_result` (`dataset_ids`, `contains`) and `expected_tools` (each `{"name"}` or `{"name", "args"}`).

### Trace checks and other runs

The trace checks of week 8 put a mark on each span that starts in the check process while the request runs. They find the traces of the request by this mark. So traces of earlier checks, of your API or of a notebook do not change the result, also when they start at the same time. The week 14 and week 16 checks run the week 8 checks in a new process, and the mark works the same way there.

### Changes to files from earlier phases

`make start PHASE=4` does not touch the files that you wrote. You change them yourself:

- `assistant/api.py` and `assistant/config.py`: replace them with the Phase 4 copies (see [Setup](#the-given-files-of-phase-1)).
- `assistant/agent.py`: the new signature of `answer_events()` first. Then the history of the conversation, compaction and the saved facts (week 12), and the planner (week 13).
- `assistant/tools.py`: the tool `save_memory` (week 12), and `register_dataset` for the graph (week 15).
- `assistant/memory.py`: from your table `memories` to the LangGraph Postgres store (week 15). `save_fact()` and `search_facts()` keep their signatures.
- `.github/workflows/evals.yml`: a step that runs the agent tasks (week 17).

The checks of Phases 1 to 3 must stay green on the hand-written loop (`AGENT_IMPL=handwritten`, the default) through the whole phase.

## Week 12: Memory by hand

### Step 1. Read

Huyen, chapter 6: Memory (pages 300 to 305). [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) for compaction and note-taking.

The essay describes compaction as "taking a conversation nearing the context window limit, summarizing its contents, and reinitiating a new context window with the summary", and note-taking as an agent that "regularly writes notes persisted to memory outside of the context window". Step 2 builds the first, step 3 the second.

### Step 2. Compaction

A conversation is a list of messages. Each new question sends the whole list again, so each request is longer than the one before it. Compaction keeps the list short: when the context gets near a limit, one model call summarises the old messages, and a new context starts with the summary. The old messages stay in the table for the record, but the model does not read them again.

The lab gives the conversation store, `assistant/conversations.py`: `open_conversation(id, user)` (True for a new conversation, `ConversationNotFound` for the ID of another user), `load_context(id)` (the messages of the last context), `append_messages(id, messages)` and `start_new_context(id, messages)`.

1. In `answer_events()`, open the conversation for the user, load the messages of its last context before the question, and append the new messages after the answer. A conversation of another user must give no history to the model.
2. In `assistant/memory.py`, write `context_tokens()` (the size of the context after a reply, from its usage) and `compact()` (one summary call with `call_claude()`). Their docstrings have the rules.
3. When the context reaches `get_settings().compact_at_tokens`, compact the conversation and start a new context with the summary.

**Why the default is 80,000 tokens.** Claude Haiku 5.5 has a context window of 1M tokens, so the default is far below the context limit. The reason is the price: a request whose prompt is over 100,000 tokens pays $0.50 for each million input tokens and $2.50 for each million output tokens, in place of $0.10 and $0.50. With `COMPACT_AT_TOKENS=80000` each request stays at the lower price.

> From the documentation: the context window is from [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview). The prices and the rule "A request's prompt length counts all of its input tokens, including cache reads and cache writes" are from [Pricing](https://platform.claude.com/docs/en/about-claude/pricing), "Long context pricing". So `context_tokens()` counts the cache reads and the cache writes too. The other way to measure is the [token counting endpoint](https://platform.claude.com/docs/en/build-with-claude/token-counting). It is "free to use but subject to requests per minute rate limits", and its count is an estimate. The stand-in of the lab has this endpoint too.

<details>
<summary>Hint: what the summary must keep</summary>

The essay says: "Start by maximizing recall to ensure your compaction prompt captures every relevant piece of information from the trace, then iterate to improve precision". The tool results are the largest part of the context and the safest part to leave out: the essay calls tool result clearing "one of the safest lightest touch forms of compaction". Keep the questions, the dataset IDs and titles of the answers, the cited chunk IDs and the open questions.
</details>

<details>
<summary>Hint: where the summary goes in the messages</summary>

The new context starts with the summary as a user message, and the next question is also a user message. This is valid: the [Messages API reference](https://platform.claude.com/docs/en/api/messages/create) says "Consecutive `user` or `assistant` turns in your request will be combined into a single turn". The reference build of this lab added a short assistant turn after the summary.
</details>

<details>
<summary>Hint: a Phase 1 check fails after this step</summary>

The Phase 1 check `test_a_broken_tool_does_not_stop_the_loop` runs with the database down. When your loop cannot connect to Postgres, it must still answer: catch `psycopg.OperationalError` around the conversation store and the memory, and go on without history and without facts.
</details>

**How the check tests compaction.** The check measures the token estimate of a first request with the stand-in (1 token for each 4 characters), sets `COMPACT_AT_TOKENS` to that number plus 1,000, and asks five questions with answers of about 1,800 characters. A summary request is a request without `tools`. The check passes when a summary request comes in the first four turns and holds the first question, and the request after it holds the summary, is shorter than the request before it and does not hold the first question.

To see compaction with the real model, set `COMPACT_AT_TOKENS` to a small value in `.env`, for example `8000`, and ask some questions in one conversation. `make ask` sends no `conversation_id`, so send the second question with `curl` and the ID from the `done` event of the first one:

```bash
curl -N -X POST localhost:8000/ask -H 'Content-Type: application/json' -H 'X-User: me' -d '{"question": "...", "conversation_id": "..."}'
```

This `curl` line did not run in the build of this lab. **Cost estimate:** 2 to 3 requests for each question, of about 5,000 to 8,000 input tokens and 300 output tokens. From 2 x 5,000 = 10,000 tokens x $0.10 per million = $0.001 to 3 x 8,000 = 24,000 tokens x $0.10 per million = $0.0024, plus less than $0.0005 of output: about $0.001 to $0.003 for each question. Set `COMPACT_AT_TOKENS` back to `80000` after the test.

### Step 3. Long-term memory

Compaction keeps one conversation going. Long-term memory carries facts from one conversation to the next. The agent saves a fact about the user with a tool, and with each new question the code finds the closest facts of the same user and gives them to the model.

1. Add the tool `save_memory` to `TOOLS` in `assistant/tools.py`, with one required argument `fact`, and a description that tells the model when to save a fact and when not to.
2. Write `save_fact()` and `search_facts()` in `assistant/memory.py`. Embed the fact with the embedding service of Phase 2, store it in the table `memories`, and search with pgvector as in `vector_search()` of week 5. Search only the rows of the user.
3. In `answer_events()`, give the model the facts that `search_facts()` returns for the user and the question.

The facts belong to the user of `X-User`. A fact of one user must never reach a request of another user, also for `anonymous`.

### Step 4. Check

```bash
make check WEEK=12
```

All 9 checks pass. They test the tables, the conversation ID, the history, another user with the same conversation ID, compaction, the tool definition, the search, a fact that reaches the next conversation, and a fact that does not reach another user. Then run `make check PHASE=1`, `make check PHASE=2` and `make check PHASE=3`. Write the numbers of the compaction check and of your own test in [RESULTS.md](RESULTS.md).

## Week 13: Planning by hand

### Step 1. Read

Huyen, chapter 6: Agent Overview, Tools and Planning (pages 275 to 298).

### Step 2. The planner

A plan makes the agent think about the whole task before it calls a tool. The model writes the steps, the loop works on them, and when a step fails the model gets the error and writes a new plan, so it does not repeat the same failing call.

With `AGENT_PLANNER=on`, the loop does this:

1. Ask the model for a plan with `write_plan()`, as structured output with the schema of the given class `Plan`. Give the model the names of the tools, so that each step can name one. Send the plan to the client as the event `plan`, before the first `tool` event.
2. Give the plan to the model in the next request, and work on the steps.
3. When a tool returns an error, ask for a new plan with `change_plan()` before the next model call. Give it the question, the plan, the failed call and its error message. Send the new plan as a second `plan` event, and give it to the model.

With the planner off (the default), there is no plan request and no `plan` event.

<details>
<summary>Hint: the done event and the cost of the plan</summary>

The plan requests are requests to the model, so `done.requests` counts them, and their cost is in `cost_usd`. The stub signatures return a `Plan` only. Change them to return the model result too, as the docstring of `planner.py` says.
</details>

### Step 3. Check

```bash
make check WEEK=13
```

All 3 checks pass. Before your work, 2 fail and 1 passes ("without the planner there is no plan"). The stand-in plays the model: it gives a plan whose first step calls `get_dataset_schema` with a dataset ID that does not exist, waits for your new plan request (it must hold the unknown ID and the error text), and then answers. The events must come in this order: plan, tool (error), plan, tool, answer, done.

To see it with the real model, set `AGENT_PLANNER=on` in `.env` and ask a question that needs two tools. The planner adds 2 requests or more to each question. Write the task, both plans and the cost in [RESULTS.md](RESULTS.md).

## Week 14: Move the loop to LangChain and LangGraph

### Step 1. Read

[Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) for workflow patterns and for when plain code beats a model call. LangChain [Agents](https://docs.langchain.com/oss/python/langchain/agents) and [Models](https://docs.langchain.com/oss/python/langchain/models). [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview) and [Graph API overview](https://docs.langchain.com/oss/python/langgraph/graph-api).

The essay says: "Workflows are systems where LLMs and tools are orchestrated through predefined code paths", and "we recommend finding the simplest solution possible, and only increasing complexity when needed". Its prompt chaining pattern adds "programmatic checks" between the model calls. Step 3 is such a check.

The Agents page builds an agent with `create_agent` of the package `langchain`. The lab does not install that package: you build the graph yourself with LangGraph (`StateGraph`, nodes, edges) and use the chat models of `langchain-anthropic` and `langchain-openai`. The versions in `uv.lock` are langgraph 1.2.22, langchain-core 1.8.1, langchain-anthropic 1.7.10 and langchain-openai 1.8.0.

### Step 2. The graph on Claude and OpenAI

A graph makes the loop explicit: each part of the loop is a node, and the edges say which node comes next. The state of the graph holds the messages and the values of the run. The same graph runs on Claude and on OpenAI, because each node uses the LangChain chat model interface and not the SDK of one provider.

1. In `assistant/models.py`, write `chat_model()`: `ChatAnthropic` for `PROVIDER=anthropic` and `ChatOpenAI` for `PROVIDER=openai`, with the model names and `max_tokens` of the settings. Write `usage_of()`: the usage of one reply in the fields of the `done` event, with its cost from `PRICES_PER_MTOK`.
2. In `assistant/graph.py`, build the graph: a model node (the chat model with the tools and the answer schema), a tool node (`run_tool()` for each call, with a `tool` event for each), the planner and the change of the plan, the memory of week 12 (history, facts, compaction), and the citation node of step 3.
3. Write `answer_events()` of the graph. It must give the same events as your loop. Send the events of a node with `get_stream_writer()` and read them with `stream_mode="custom"`.
4. Pass the Langfuse `CallbackHandler` in the config of the run, so each model call is a generation of the trace. Keep `@observe()` on `answer_events()` and your `tool` observations in the tool node.

> From the documentation: `StateGraph`, `add_node`, `add_edge`, `add_conditional_edges`, `START`, `END`, the state as a `TypedDict` with reducers in `Annotated[...]` and `add_messages` are on the [Graph API overview](https://docs.langchain.com/oss/python/langgraph/graph-api). `get_stream_writer()` (from `langgraph.config`) and `stream_mode="custom"` are on [Streaming](https://docs.langchain.com/oss/python/langgraph/streaming). `ChatAnthropic`, `ChatOpenAI`, `bind_tools`, `with_structured_output` and `usage_metadata` are on [Models](https://docs.langchain.com/oss/python/langchain/models), [ChatAnthropic](https://docs.langchain.com/oss/python/integrations/chat/anthropic) and [ChatOpenAI](https://docs.langchain.com/oss/python/integrations/chat/openai). The Langfuse handler is `from langfuse.langchain import CallbackHandler`, passed as `config={"callbacks": [handler]}`, and "Instrumenting LangGraph follows the same pattern" ([Langfuse LangChain integration](https://langfuse.com/integrations/frameworks/langchain)). The `langfuse` 5.2.0 of Phase 3 has this module without an extra package.

**The OpenAI model.** `OPENAI_MODEL` defaults to `gpt-6-luna`: $0.10 for each million input tokens, $0.50 output, $0.01 cached input (standard processing, [OpenAI pricing](https://developers.openai.com/api/docs/pricing)). These are the same input and output prices as Claude Haiku 5.5, so the comparison of the two providers is fair on cost.

<details>
<summary>Hint: the stream writer gives tuples</summary>

The Streaming page shows `version="v2"`, where each chunk is a dict with `chunk["type"]`. Without it, a list of stream modes gives `(mode, chunk)` tuples. Both forms work with langgraph 1.2.22. Choose one and read it in the same way everywhere.
</details>

<details>
<summary>Hint: the tools and the answer schema in one request</summary>

Your loop of Phase 1 sends the tools and the answer schema in one request. `ChatAnthropic.with_structured_output()` defaults to function calling (a forced tool), and `method="json_schema"` uses the structured output of Claude (ChatAnthropic page, "Structured output"). With the tools in the same request, the build of this lab used `bind_tools(TOOLS, response_format=Answer)`: in the source of langchain-anthropic 1.7.10, ChatAnthropic turns `response_format` into `output_config.format`. This is from the source, not from a page. The checks accept both ways: they find the schema in `output_config.format` or in a forced tool.
</details>

<details>
<summary>Hint: the input tokens of the done event</summary>

In `usage_metadata`, LangChain gives `input_tokens` with the cache reads and cache writes in it, and the details in `input_token_details`. The `done` event of your loop gives the input tokens without the cache tokens, as the Claude API does. The check scripts a reply with 1,000 cache-read tokens, so a cost from the LangChain number fails.
</details>

<details>
<summary>Hint: two generations for each Claude call in the trace</summary>

This is the problem of week 8 again. The `anthropic` SDK makes its own span for each call, and the Langfuse callback makes a generation. ChatAnthropic makes its own client, so you cannot pass `open_telemetry=False`. Set the environment variable `ANTHROPIC_OPEN_TELEMETRY=false` before the client is made, for example with `os.environ.setdefault` in `models.py`. This is from the source of the SDK (`anthropic/_tracing.py`, version 2.8.0), not from a page. Without it, the week 8 trace checks fail on the graph.
</details>

<details>
<summary>Hint: no token usage on OpenAI when the graph streams the model</summary>

This hint is only for a graph that streams the model, for example with `stream_mode="messages"`, on the Chat Completions API. The ChatOpenAI page says that when `OPENAI_BASE_URL` is set, "the default is left off" for `stream_usage`, and the checks set `OPENAI_BASE_URL`. Then a streamed reply has no `usage_metadata`. Pass `stream_usage=True`. A graph that calls `invoke()` does not meet this.

Which OpenAI endpoint ChatOpenAI uses depends on the request. In the source of langchain-openai 1.8.0, a model name that starts with `gpt-6` and a request with tools go to the Responses API (`/v1/responses`). The same model without tools (the planner, the summary) goes to Chat Completions (`/v1/chat/completions`). The stand-in serves both.
</details>

### Step 3. Plain code for the citations

The model knows which passage it used. It does not need to copy the title and the page of each passage, because the results of `search_documents` already have them. So the model gives only the chunk ID of each citation, and a plain-code node adds the title and the page from the search results of the request. The rule of week 7 stays in the same node: a cited chunk ID that no search of this request returned is rejected, and the model is asked again one time.

The check makes the model cite a returned chunk with a wrong title and page 999 (when your answer schema has those fields) and a chunk ID that no search returned. The graph must reject the invented ID, ask again (3 requests, the third names the invented ID), and the `answer` event must have the title and the page of the search result. Your answer schema keeps `citations` with `chunk_id` in each item. The title and the page can stay in the schema, or you can take them out.

### Step 4. Run the test set on both providers

`evals/compare.py` (given) runs the test set through the loop that `IMPL` names, with the model that `PROVIDER` names. Each case is one Langfuse trace with the tags `compare` and `<impl>-<provider>`. The result file is `evals/results/compare-<impl>-<provider>.json`, with `code_pass` of week 9 for each case. The hand-written loop runs on Claude only.

```bash
make compare IMPL=handwritten PROVIDER=anthropic
```

```bash
make compare IMPL=langgraph PROVIDER=anthropic
```

```bash
make compare IMPL=langgraph PROVIDER=openai
```

Use the same cases for all three runs. `ARGS="--limit 30"` runs the first 30 cases, `ARGS="--ids t001,t031"` some cases, and `ARGS="--no-cache"` sends each request to the API. The check needs at least 20 cases, with at least 5 document cases and 5 dataset cases.

Then count the code of each loop:

```bash
make lines
```

`scripts/count_lines.py` counts the lines that are not empty, not a comment and not part of a docstring. The hand-written loop is `agent.py`, `llm.py` and `planner.py`. The graph is `graph.py` and `models.py`. The files that both use (`tools.py`, `retrieval.py`, `memory.py`, `conversations.py`, `schemas.py`) are counted apart. Change the lists in the script when your files differ. In the reference build of this lab the counts were 361 lines for the hand-written loop, 255 for the graph and 414 shared. The graph imported the system prompt from `agent.py` and the planner prompts from `planner.py`, so its count did not hold them.

**Cost estimate:** assume about 5,000 input tokens and 300 output tokens for each case, as in week 9 of Phase 3. One case: 5,000 x $0.10 per million = $0.0005, plus 300 x $0.50 per million = $0.00015, about $0.0007. Both providers have the same prices. For 105 cases: about $0.07 for each run, and about $0.21 for the three runs. With twice the tokens: about $0.45 for the three runs. With 30 cases: about $0.06 for the three runs. Cache reads make the input part smaller. The real cost is in the output of the command.

Keep the comparison for interviews: write the three scores, the costs, the line counts and what you learned about each loop in [RESULTS.md](RESULTS.md).

### Step 5. Check

```bash
make check WEEK=14
```

All 18 checks pass. Before your work, 17 fail and 1 passes ("another user cannot read" on the graph). The checks test that the setting chooses the graph (the request has a User-Agent with `langchain`), the same events on the three combinations of loop and provider (the check ignores the `text` events), the tool result IDs on both providers, the tokens and the cost of `done`, the citation node, the planner and the memory checks of week 12 on the graph, the trace checks of week 8 on the graph (in a new process, about 35 s), and the three result files. The last check prints the three scores and passes when the graph on Claude scores at least as well as the hand-written loop. The two "without Langfuse" checks of week 8 call `assistant.agent` directly, so they still test your hand-written loop.

The live check runs one question on each provider:

```bash
make check-live WEEK=14
```

**Cost estimate:** about 2 requests on each provider of about 2,000 input and 300 output tokens. Input: 4 x 2,000 = 8,000 tokens x $0.10 per million = $0.0008. Output: 4 x 300 = 1,200 tokens x $0.50 per million = $0.0006. Total: under $0.01 for both runs.

> Not run in the build of this lab: the real Claude and OpenAI APIs. The scores of `make compare` came from a stand-in that gave the expected answer, so they prove the command and the check, not the quality of either loop. Also not run: the error texts of the real OpenAI API for a wrong tool call ID, and whether the real Responses API accepts the answer schema together with the tools. The build sent the tools without `strict`.

## Week 15: Persistence, approval and the audit log

### Step 1. Read

LangGraph [Memory](https://docs.langchain.com/oss/python/langgraph/add-memory) (the "Use in production" parts) and [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts).

### Step 2. The Postgres checkpointer and store

A checkpointer saves the state of the graph after each step, under a thread ID. With the conversation ID as the thread ID, a new process can continue a conversation from its last step, also in the middle of a run. A store keeps values across threads, so it is the place for the facts of a user.

1. Compile the graph with `PostgresSaver`, and pass the conversation ID as `thread_id` in `config["configurable"]`. Call `setup()` the first time: it makes the tables `checkpoints`, `checkpoint_blobs` and `checkpoint_writes`.
2. Replace the table `memories` with `PostgresStore`, with a vector index (`{"embed": ..., "dims": ...}`) on the embedding service of Phase 2. `setup()` makes the tables `store` and `store_vectors`. Save a fact as `{"text": ...}` in a namespace that has the user as one label. `save_fact()` and `search_facts()` keep their signatures. The week 12 checks read a fact from the table `memories` or from the store, so they stay green.

> From the documentation: `PostgresSaver`, `PostgresStore`, `from_conn_string`, `setup()` and the store index are in the "Use in production" parts of [Memory](https://docs.langchain.com/oss/python/langgraph/add-memory). The versions in `uv.lock` are langgraph-checkpoint-postgres 3.2.1 and psycopg-pool 3.3.3.

<details>
<summary>Hint: one connection for the life of the service</summary>

`from_conn_string()` is a context manager, and the service runs for a long time. A `psycopg_pool.ConnectionPool` lives as long as the process. Give its connections the three settings that `PostgresSaver.from_conn_string()` uses in its source (version 3.2.1): `autocommit=True`, `prepare_threshold=0` and `row_factory=dict_row`.
</details>

<details>
<summary>Hint: a user name with a period</summary>

In the source of the store (`langgraph/store/base/__init__.py`), a namespace label that "contains a period (`.`)" raises `InvalidNamespaceError`. A user name like `ana.smith` is a valid header. Replace the period in the label, for example with `%2E`. The index key `fields` (for example `["text"]`) chooses the field to embed. Its docstring says that it defaults to `["$"]`.
</details>

### Step 3. Approval for register_dataset

`register_dataset` is the first tool that changes data: it adds one row to the table `datasets` with `id = dataset_id`. So a person must approve each call before it runs. The `interrupt()` function pauses the graph and saves its state. The client gets the call to approve, and a later request continues the graph with `Command(resume=...)`.

1. Add the tool `register_dataset` with the arguments `dataset_id`, `title`, `description`, `owner` (required) and `source_url` (optional). Give it to the graph only. The reference build kept it out of `TOOLS`, so the hand-written loop never gets it.
2. Before the tool runs, pause the graph with `interrupt()`. The stream sends an `approval` event for the call and ends with `done`.
3. Write `resume_events(conversation_id, approved, approver)` in `assistant/graph.py`. The given `POST /approve` calls it. After an approval the tool runs. After a refusal it does not run, and the model gets the refusal as the tool result of the call.

The `curl` line to approve:

```bash
curl -N -X POST localhost:8000/approve -H 'Content-Type: application/json' -H 'X-User: reviewer' -d '{"conversation_id": "...", "approved": true}'
```

This line did not run against the `api` container in the build of this lab. The checks post `/approve` to your API run with uvicorn on the host. Approval works only with `AGENT_IMPL=langgraph`.

> From the documentation: [Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) has `interrupt()`, `Command(resume=...)` and `thread_id`. The page also says: "The node restarts from the beginning of the node where the interrupt was called when resumed, so any code before the interrupt runs again". The plan chose the interrupt function and not static breakpoints, because the same page says "Static interrupts are not recommended for human-in-the-loop workflows".

<details>
<summary>Hint: the tool ran two times, or before the approval</summary>

The node restarts from its beginning when the graph continues. So code before `interrupt()` in the same node runs again on each resume. Put only the interrupt in the approval node, and run the tool in another node.
</details>

<details>
<summary>Hint: after a restart the graph does not continue</summary>

The check stops your service with SIGKILL right after the `approval` event, as a crash does. The checkpoint must be in Postgres at that time. The [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers) page, on the durability modes, says that with `"sync"` "LangGraph persists changes synchronously before the next step starts". Pass `durability="sync"` to the run.
</details>

### Step 4. The audit log

An audit log answers the question "who did what, and who allowed it". The given migration `0006_audit_log.sql` has the table `audit_log`: `user_id`, `conversation_id`, `tool`, `arguments` (jsonb), `result`, `approval` (`not_needed`, `approved` or `refused`) and `approver`. A constraint makes `approver` empty exactly when `approval` is `not_needed`.

Write one row for each tool call, when the call ends or when a person refuses it. `user_id` is the user of `/ask`, `approver` the user of `/approve`, and `result` is the text that went back to the model: the result, the error or the refusal.

### Step 5. Check

```bash
make check WEEK=15
```

All 6 checks pass. Before your work, the 6 fail. The checks test:

- **The checkpointer.** The three tables exist, and `checkpoints` has rows for the conversation of one question.
- **The store.** `save_fact()` writes to the store (with a vector), not to `memories`, and `search_facts()` finds it.
- **The restart.** The check starts your API with uvicorn as a process (free port, `AGENT_IMPL=langgraph`), asks a question whose scripted reply calls `register_dataset`, reads the `approval` event, stops the process with SIGKILL, starts it again and posts `/approve`. It passes when exactly one new model request comes (the graph continues from the tool call), with the question and the result of the call with the ID from before the restart, and the dataset row exists. After a second restart, the next question holds the earlier messages.
- **The refusal.** No row before the approval and after a refusal, and the next request holds the refusal as the tool result.
- **The audit log.** A reply with `search_datasets` and `get_dataset_schema` (with an unknown ID), then `register_dataset`: two rows before the approval and three after, with the user, the arguments, the approval and the approver, and the error text in the failed row. A refusal gives one row `refused` with the approver.

Write what you tested in [RESULTS.md](RESULTS.md).

## Week 16: MCP tool servers

### Step 1. Read

MCP [Architecture overview](https://modelcontextprotocol.io/docs/learn/architecture) and [Build an MCP server](https://modelcontextprotocol.io/docs/develop/build-server). LangChain [Model Context Protocol (MCP)](https://docs.langchain.com/oss/python/langchain/mcp).

**The LangChain MCP page changed after the plan was written.** It now teaches `langchain.mcp.MCPAdapter`. The page says: "The `langchain.mcp` namespace requires `langchain[mcp]>=1.4.0` and is in beta. Importing from it raises a `LangChainBetaWarning` once per process. The API may change." The page [Migrate from langchain-mcp-adapters](https://docs.langchain.com/oss/python/migrate/langchain-mcp-adapters) says that the new namespace "replaces the standalone langchain-mcp-adapters package, whose MultiServerMCPClient is collapsed into a single MCPAdapter class".

This lab teaches the package `langchain-mcp-adapters` (version 0.3.2 in `uv.lock`) and its `MultiServerMCPClient`, because the new class is in beta. Read the MCP concepts on the plan page. For the code, read the README of the package, which comes with the installed package:

```bash
uv run python -c "from importlib.metadata import metadata; print(metadata('langchain-mcp-adapters').get_payload())"
```

The checks test your servers from outside, with the MCP client of the official SDK, and they look at the requests of the graph and the logs of your servers. They do not look at the client class in your graph. So `MCPAdapter` is an option that you can try. It is not in `uv.lock`: on PyPI, langchain 1.5.0 has the extra `mcp` with `fastmcp>=4.0.11`. The build of this lab did not install it or try it.

### Step 2. The SQL server and the catalogue server

MCP separates the tools from the agent. A server lists its tools and runs them. A client (here, the graph) connects to the server, gets the list, and calls a tool by name. Another agent can use the same server, and a tool can change without a change of the agent.

`make start` copied two server shells to `assistant/servers/`. Each one is a `FastMCP` server with the transport "streamable HTTP" on the path `/mcp`. Your work is the tools:

- **The SQL server** (`sql_server.py`, name `sql`): one tool, `run_sql(query)`. Step 3 makes it safe. Its docstring is the description that the model gets: write when to use it, the tables that it can read, and the row limit (150 characters or more).
- **The catalogue server** (`catalogue_server.py`): `search_datasets(query, limit)`, `get_dataset_schema(dataset_id)`, `get_dataset_stats(dataset_id)` and `register_dataset(...)`. Use the functions of `assistant/tools.py`, and give each tool the description of its definition there, so the model sees no change.

The approval and the audit log stay in the graph: the server does not know the user. A tool that fails raises an exception. The SDK sends it to the client as a result with `isError`.

Start a server on your machine:

```bash
uv run python -m assistant.servers.sql_server
```

It reads `MCP_HOST` (default 127.0.0.1) and `MCP_PORT` (8091 for SQL, 8092 for the catalogue). `make up` starts both servers in Docker. The source folder is mounted on `/app`, so after a change of your code restart them:

```bash
docker compose restart mcp-sql mcp-catalogue
```

> From the documentation: `FastMCP(name, instructions, host, port, stateless_http, json_response)`, `@mcp.tool()`, `mcp.run(transport="streamable-http")`, and "Use `stateless_http=True` and `json_response=True` for optimal scalability" are on the [MCP Python SDK server page](https://py.sdk.modelcontextprotocol.io/v1/server/) (the v1.x docs, for mcp 1.30.0 in `uv.lock`). The same page describes the `isError` flag. The client of the checks, `streamable_http_client()` with `ClientSession`, is on the [client page](https://py.sdk.modelcontextprotocol.io/v1/client/). In the source of mcp 1.30.0, FastMCP turns on its DNS rebinding protection only when the host is 127.0.0.1, localhost or ::1. Compose sets `MCP_HOST=0.0.0.0`, so the other containers can connect by service name.

### Step 3. A safe SQL server

The model writes the SQL, so the server must assume that a query can try anything. Each limit stops a different kind of harm:

- **A read-only database role.** Write a new migration in `db/migrations/` that makes the role of `SQL_DATABASE_URL` (default `assistant_reader` with the password `assistant_reader`). The role is not a superuser, cannot create roles or databases, does not bypass row security, owns no table, cannot INSERT, UPDATE, DELETE or TRUNCATE a table of the schemas `public` and `data`, and can SELECT the tables of `data`. Connect `run_sql` with `get_settings().sql_database_url`.
- **A list of allowed tables:** the schema `data`, and `public.datasets` and `public.dataset_columns`. Refuse each other table. This also covers the tables that any role can read, such as `pg_catalog.pg_tables` and `pg_roles`, so the role alone is not enough.
- **A row limit.** Return at most `get_settings().sql_row_limit` rows, and `truncated: true` when you cut rows.
- **A query timeout.** Stop a query after `get_settings().sql_timeout_seconds`.

Refuse each statement that changes data, also a change in a CTE or after a semicolon. The result is a JSON object with `rows` (a list) and `truncated` (a boolean). You can add more keys, for example `columns`.

<details>
<summary>Hint: a table in a subquery or a CTE</summary>

A check of the first word, or of the table names in the text, misses many queries. Postgres can tell you each table that a query reads: the plan of `EXPLAIN (FORMAT JSON)` names the relation of each scan. Read each node of the plan, not only the top node: a table in a subquery or a CTE is in a lower node. A read-only transaction is a second wall against a write.
</details>

<details>
<summary>Hint: the migration ran, and you changed it</summary>

`make up` applies each new migration file one time. A file that ran does not run again when you edit it. Add a new file, or run `make reset` (it deletes the database).
</details>

### Step 4. Connect the agent to the servers

Connect the graph to both servers with `MultiServerMCPClient` of langchain-mcp-adapters, with the transport `streamable_http` and the URLs `get_settings().mcp_sql_url` and `get_settings().mcp_catalogue_url`. `await client.get_tools()` gives LangChain tools. The graph gets `run_sql` and the four catalogue tools from the servers, and keeps `search_documents` and `save_memory` as local tools. The approval of `register_dataset` and the audit log stay in your graph.

<details>
<summary>Hint: the tools are async</summary>

The adapter tools are async only. A graph whose nodes are plain functions can call `asyncio.run(tool.ainvoke(arguments))` for each call.
</details>

<details>
<summary>Hint: the trace has two tool observations for each MCP call</summary>

An adapter tool is a LangChain tool. When you call it inside a node of a run that has the Langfuse `CallbackHandler`, the callback makes its own `tool` observation, next to the one of your tool node. Then the trace has two observations for each MCP call, for example `['search_datasets', 'search_datasets', 'get_dataset_schema', ...]`, and the week 8 check "one tool observation for each tool call" fails. Pass `config={"callbacks": []}` to `ainvoke()`, and keep your own observation in the tool node: it also gives a failed call the level `ERROR`.
</details>

### Step 5. Check

```bash
make check WEEK=16
```

All 31 checks pass. The checks start both of your servers from `assistant/servers/` as processes on free ports for the whole run, with `SQL_ROW_LIMIT=40` and `SQL_TIMEOUT_SECONDS=2`, and point `MCP_SQL_URL` and `MCP_CATALOGUE_URL` at them. So a check always tests your current code, and the Compose services can run at the same time. The checks test:

- **The tools.** The names and required arguments on both servers, the description of `run_sql`, and the catalogue descriptions equal to `assistant/tools.py`. The catalogue tools answer.
- **The role and the queries.** The role of `SQL_DATABASE_URL` (as above), a SELECT that returns the 4 population rows of 2014, and `SELECT current_user`.
- **The refusals.** Nine statements that write (INSERT, UPDATE, DELETE, a DELETE in a CTE, a DELETE and an UPDATE after a semicolon, DROP, TRUNCATE, CREATE TABLE AS) with no change of data, and eight reads of tables outside the list, some in a subquery or a CTE. Each refusal check first needs a good query to work, so a `run_sql` that refuses everything fails.
- **The limits.** 40 of the 1,352 rows of `data.gas_sales` with `truncated: true`, exactly 40 rows not cut, and a slow query (a triple cross join of `data.gas_sales`) that ends with an error in under 17 s.
- **The agent on the servers.** The first request has `run_sql`, the four catalogue tools, `search_documents` and `save_memory`. A `run_sql` of all gas sales gives 40 rows, the limit of the server process. A `search_datasets` call adds a tool call to the log of the catalogue server, and with that server stopped it gives no results.
- **Week 15 again.** The restart, the refusal and the audit log, with the tools on the servers.
- **Week 8 again.** The trace checks in a new process, on the graph with the MCP tools.
- **The test set.** The 12 CI cases of `evals/testset.jsonl` run through the graph with a stand-in that searches and then answers with the expected IDs. Each `code_pass` must be true, and the catalogue server must log a tool call for each of the 8 dataset cases.

Before your work of the week, most checks fail or show as errors: each check that needs a working `run_sql` is an error. Some can pass: the trace check (the graph has no MCP tools yet), and the three week 15 checks that week 16 runs again (they test the graph, not the servers). Write the refusals that you tried, the limits and the test set result in [RESULTS.md](RESULTS.md).

## Week 17: Agent evaluation

### Step 1. Read

Huyen, chapter 6: Agent Failure Modes and Evaluation (pages 298 to 300). In the [AI Evals FAQ](https://hamel.dev/blog/posts/evals-faq/): "How do I evaluate agentic workflows?".

### Step 2. The 30 multi-step tasks

An agent can give the correct answer by a wrong path (a guess, or a tool that it was not meant to use), or a wrong answer by a correct path. So each task has two expectations: the final result, and the tool calls that a good agent makes.

1. Ask Claude Code for a first draft of 30 tasks. It uses your subscription and no API credit. Give it `data/catalogue.json`, the eight tables of the schema `data` (`data/tables/sources.json` lists them), the format of `evals/agent_tasks.jsonl` and its three example tasks.
2. Check each expected value yourself with SQL, for example with `docker compose exec db psql -U assistant`, and correct the tasks by hand.
3. Write the tasks to `evals/agent_tasks.jsonl`. Keep the three examples or replace them.

The checks need 30 tasks or more, each ID and each task text only one time, two or more expected calls in each task, only tools that exist (the local tools and the tools that your two servers list), an expected result in each task, only dataset IDs of the catalogue, at least 5 tasks with `run_sql`, and at least 2 tasks that ask to register a dataset, each with a new dataset ID.

<details>
<summary>Hint: values to avoid</summary>

The values of the tables are as on the portal, with their faults. `data.population` has a year 2023 total of 187,201, which is only part of the groups. `data.generation_capacity.value_gw` holds GW, although the title of the dataset says MW. A task on these values tests the data, not the agent.
</details>

### Step 3. Score the result and the path, and add the tasks to CI

`evals/agent_eval.py` runs each task through the graph as one Langfuse trace (tag `agent-eval`), with the user `agent-eval`. It refuses each approval, so a task never registers a dataset. Write the two score functions. Their docstrings have the rules:

- **`path_score(expected, actual)`**: the length of the longest common subsequence of the expected calls and the actual calls, divided by the number of expected calls. A call matches when the names are equal and each argument that the expected call names has the same value. Extra actual calls do not lower the score. An empty expected list scores 1.0.
- **`result_score(expected, answer)`**: each expected dataset ID must be in `dataset_ids` of the answer, and each `contains` text in the answer text. No answer scores 0.0, and a result that meets each expectation scores 1.0. You choose how strictly to compare the texts (letter case, spaces, the commas in a number). Write your choice and the reason in [RESULTS.md](RESULTS.md).

<details>
<summary>Hint: the longest list, not the first match</summary>

A greedy match takes the first actual call that fits each expected call, and it can miss a longer list. Expected `[a, b, c]` with actual `[b, c, a]`: the greedy match takes `a` at position 3, and then finds no `b` or `c` after it, so it scores 1 of 3. The longest common subsequence is `[b, c]`, 2 of 3. The dynamic programming of a longest common subsequence finds the longest list each time. The checks have ten cases, among them "the longest list and not the first match" and "one actual call for two expected calls".
</details>

Then run the tasks:

```bash
make agent-eval
```

`ARGS="--ids a01,a02"` runs some tasks. The result file is `evals/results/agent-tasks.json`, with the mean `result_score` and `path_score`, the cost, and one row for each task (its calls, the refused calls, the errors and both scores). Read the rows with low scores, and the traces in Langfuse. Is the task wrong, the expectation too strict, or the agent wrong?

**Cost estimate:** about 3 to 5 requests for each task, of about 2,000 to 6,000 input tokens and about 300 output tokens. Input: from 30 x 3 x 2,000 = 180,000 tokens ($0.018) to 30 x 5 x 6,000 = 900,000 tokens ($0.09), at $0.10 per million. Output: from 30 x 3 x 300 = 27,000 tokens ($0.014) to 30 x 5 x 300 = 45,000 tokens ($0.023), at $0.50 per million. Total: about $0.03 to $0.11 for each run.

**The CI step.** Add a step to `.github/workflows/evals.yml` that runs the agent tasks with both minimum scores, so that a worse agent fails the job:

```bash
make agent-eval ARGS="--min-result 0.8 --min-path 0.8"
```

`--min-result` and `--min-path` make the command exit with an error when a mean score is below the value. Choose each value from the scores of some runs of your good code, as in week 11. The job needs more than the Phase 3 job: the packages of phase 4, the data tables (`scripts/load_tables.py`, after the migrations), and the two services `mcp-sql` and `mcp-catalogue`. The check looks for `agent-eval` (or `evals.agent_eval`), `--min-result`, `--min-path`, `mcp-sql`, `mcp-catalogue`, `phase4` and `load_tables` in the file, and runs actionlint on it. The CI step costs the same as one run on your machine, on each pull request.

<details>
<summary>Hint: what the job must turn on</summary>

The Phase 3 job writes `.lab-phases` with the phases 1 to 3 and runs `uv sync` with their groups. Add phase 4 to both. Compose builds the image of the MCP services with the build argument `UV_GROUPS`, which the Makefile makes from `.lab-phases`. Outside of `make`, give it the same value, for example `--group phase1 ... --group phase4`. The services are in the profile `phase4`.
</details>

> Not run in the build of this lab: GitHub Actions. The workflow of the reference build passed actionlint 1.7.12, but its new commands did not run as one job (the image build in CI, and `make agent-eval` with the secret).

### Step 4. Check: the exit test

```bash
make check WEEK=17
```

All 19 checks pass. Before your work, the 19 fail. The checks test both score functions on fixed cases, the runner with the stand-in and your MCP servers (a correct path, a wrong path, a correct result on a wrong path, a register task that is refused with an audit row `refused` by `agent-eval`, and the exit code below `--min-path`), your 30 tasks, the result file (each score of each row equal to your score functions on the row, the means, each register call refused, and no dataset of a register task in the catalogue), and the workflow.

The exit test of the plan has two parts:

- **30 multi-step tasks are scored on the final result and on the path taken.** Run `make agent-eval`, then `make check WEEK=17`. The check prints both mean scores.
- **The write action cannot run without approval.** `make check WEEK=15` passes: `register_dataset` does not run before an approval or after a refusal, also after a restart. The week 17 check also proves that the evaluation never approves the write action.

The live check runs three tasks on the real Claude API, through your MCP servers:

```bash
make check-live WEEK=17
```

**Cost estimate:** about 10 requests of about 3,000 input and 300 output tokens. Input: 10 x 3,000 = 30,000 tokens x $0.10 per million = $0.003. Output: 10 x 300 = 3,000 tokens x $0.50 per million = $0.0015. Total: under $0.01.

> Not run in the build of this lab: the real Claude API. The reference result file came from a stand-in that made the expected calls in order and then gave the expected texts. It proves the runner, the scores and the checks, not the quality of the agent.

```bash
make check PHASE=4
```

Then run the checks of the earlier phases one more time on the hand-written loop: `make check PHASE=1`, `make check PHASE=2` and `make check PHASE=3`. Write both scores, the cost, the CI run and the exit test in [RESULTS.md](RESULTS.md).

## Commands

| Command | What it does |
| --- | --- |
| `make up` | Start the services of the started phases, apply the migrations, load the catalogue and the data tables |
| `make down` | Stop the services and keep the data |
| `make ask Q="..."` | Send one question to the running API, as a new conversation |
| `make compare IMPL=langgraph PROVIDER=openai` | Run the test set on one loop and one provider. `IMPL` is `handwritten` or `langgraph` (default `langgraph`), `PROVIDER` is `anthropic` (default) or `openai`. `ARGS="--limit 30"`, `--ids t001,t031`, `--no-cache` |
| `make lines` | Count the lines of code of the hand-written loop, the graph and the shared files |
| `make agent-eval` | Run `evals/agent_tasks.jsonl` through the graph and score each task. `ARGS="--ids a01,a02"`, `--min-result 0.8 --min-path 0.8` |
| `docker compose restart mcp-sql mcp-catalogue` | Restart the two MCP servers after a change of their code |
| `uv run python scripts/fetch_tables.py` | Optional. Download the eight CSV exports again from KAPSARC and rewrite `data/tables/` |
| `make check WEEK=12` | Offline checks of one week |
| `make check PHASE=4` | Offline checks of the phase |
| `make check-live WEEK=14` | The live check of week 14 (Claude and OpenAI) |
| `make check-live WEEK=17` | The live check of week 17 (Claude) |

| Setting in `.env` | Default | Meaning |
| --- | --- | --- |
| `OPENAI_API_KEY` | none | Your OpenAI API key, for the graph on OpenAI in week 14 |
| `AGENT_IMPL` | `handwritten` | The loop of the API: `handwritten` (`assistant/agent.py`) or `langgraph` (`assistant/graph.py`). Another value raises an error |
| `PROVIDER` | `anthropic` | The provider of the graph: `anthropic` or `openai` |
| `OPENAI_MODEL` | `gpt-6-luna` | The OpenAI model |
| `COMPACT_AT_TOKENS` | `80000` | Compact the conversation when its context reaches this number of tokens |
| `AGENT_PLANNER` | `off` | `on` makes the agent write a plan first |
| `MEMORY_RESULTS` | `5` | The number of saved facts that the agent gives the model with a question |
| `MCP_SQL_URL` | `http://localhost:8091/mcp` | Where the graph finds the SQL server. Compose gives the API container `http://mcp-sql:8091/mcp` |
| `MCP_CATALOGUE_URL` | `http://localhost:8092/mcp` | Where the graph finds the catalogue server. Compose gives the API container `http://mcp-catalogue:8092/mcp` |
| `SQL_DATABASE_URL` | `postgresql://assistant_reader:assistant_reader@localhost:5432/assistant` | The read-only role of the SQL server. Compose gives `mcp-sql` the same URL with the host `db` |
| `SQL_ROW_LIMIT` | `200` | The most rows that `run_sql` returns |
| `SQL_TIMEOUT_SECONDS` | `5` | The time after which `run_sql` stops a query |

The two MCP servers are reachable only from your machine (127.0.0.1:8091 and 127.0.0.1:8092). In the `api` container, the `environment` of `compose.yaml` comes before `.env`, so the container uses the service names even when your `.env` has `localhost`.
