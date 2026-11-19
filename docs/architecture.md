# Architecture of the data platform assistant

## What the system does

The assistant answers questions about the datasets and the documents of a statistics organisation. A user asks in English or in Arabic. The assistant searches the catalogue of 50 public datasets and about 4,700 passages of public reports, runs read-only SQL on the tables that the user may read, and gives an answer with the dataset IDs and the cited passages.

A user with the right role can also ask for a change of the catalogue, for example a new dataset. The assistant prepares the change, but a person must approve it before it runs.

## How a request goes through the system

1. The client sends the question to `POST /ask` with an access token from Keycloak.
2. The API checks the token, then sends the question to the input rails of NeMo Guardrails. A blocked question gets a refusal, and no model call happens.
3. The LangGraph graph calls the model through the LiteLLM gateway. The model chooses tools. The tools run on two MCP servers with the token of the user, so row security in Postgres limits each query to the rows of that user.
4. A write tool stops the graph with an interrupt. The stream ends with an `approval` event, and `POST /approve` continues the run. The audit log keeps each tool call and each decision.
5. The output rails mask personal data in the answer. The stream ends with a `done` event that has the cost, the latency and the trace ID.
6. Langfuse keeps one trace for each request, with each model call, tool call and retrieval step inside it. The feedback of the user is a score on the same trace.

## Choices

### The model and the gateway

Claude Haiku 5.5 is the default model, because it is the cheapest hosted model that passed the test set with tools. All calls go through LiteLLM. The gateway falls back to OpenAI when Claude fails, and it stops a user at a monthly budget. The cost of this choice is one more service and one more place to configure.

### Retrieval

The passages are in Postgres with pgvector, so the catalogue, the passages and the permissions are in one database. Hybrid search (vectors and Postgres text search) with the BGE re-ranker gave the best recall in both languages (see the table below). Arabic text is normalised before the search.

### The agent loop

The LangGraph graph replaced the hand-written loop of Phase 1, because it gives checkpoints, interrupts for approval and memory with less of my own code. The hand-written loop stays as a reference and for the test set runs.

### Tools and permissions

The tools run on MCP servers, not in the API process. Each server checks the token of the user, and Postgres row security filters the rows. So a prompt injection cannot read rows that the user cannot read.

### Approval and the audit log

A write tool cannot run without a decision of a person. The audit log has the user, the tool, the arguments, the decision and the approver.

### Guardrails

NeMo Guardrails checks the input and the output. It stops simple direct attacks and masks personal data. It does not stop an attack in a poisoned document, so the permissions and the approval step are the real defence.

### Evaluation and tracing

The test set has 105 cases in English and Arabic. Code checks score the dataset IDs and the citations. A grader model scores the largest failure category. CI runs a fixed subset and the attack suite on each pull request.

### The self-hosted model

Qwen3-8B on vLLM, its AWQ version and a LoRA adapter for Arabic ran on a rented GPU behind the same gateway. The table below compares them with Claude on the same test set. The open models cost less for each request at full load, but the GPU costs money also when nobody asks.

## Where plain code replaced a model call

- The cost of each call comes from the token counts and a price table, not from a model.
- The citations are checked by code: each cited chunk must exist and must come from a search of the same request.
- The code checks of the test set compare the dataset IDs and the chunk IDs with the expected IDs.
- The gateway chooses the model and the fallback by configuration.
- The approval of a write action is a rule in the graph, not a decision of the model.

The grader stays a model call, because "the answer says that it searched, but the trace shows no search" needs a judgement that code cannot make.

## Numbers

| Number | Value | Source |
| --- | --- | --- |
| Test set size | 105 cases (55 English, 50 Arabic) | `evals/testset.jsonl` |
| Task success rate on the test set | 72.4% (76 of 105 cases, code_pass) | `evals/results/testset-20261118-090000.jsonl` |
| Retrieval recall, English | vector 0.84, hybrid 0.84, rerank 0.96 (recall@5, 25 questions) | `evals/results/recall.json` |
| Retrieval recall, Arabic | vector 0.88, hybrid 0.76, rerank 0.96 (recall@5, 25 questions) | `evals/results/recall.json` |
| Groundedness score | 68.0% (34 of 50 document answers) | `evals/results/testset-20261118-090000.jsonl` |
| Grader agreement with your labels | true positive rate 0.94, true negative rate 1.00 (50 labels) | `evals/grader_agreement.json` |
| Attack-suite pass rate | 93.3% (28 of 30 attacks, model obedient) | `evals/results/attacks-week20.json` |
| 95th-percentile latency | 2.06 s (over 105 requests) | `evals/results/testset-20261118-090000.jsonl` |
| Cost per request | $0.00044 (mean of 105 requests) | `evals/results/testset-20261118-090000.jsonl` |
| Hosted against self-hosted model: quality | claude-haiku-5-5 0.371, qwen3-8b-arabic 0.457, qwen3-8b-awq 0.4, qwen3-8b 0.381 | `evals/results/model_comparison.csv` |
| Hosted against self-hosted model: latency | claude-haiku-5-5 54.9 ms p95, qwen3-8b-arabic 119.5 ms p95, qwen3-8b-awq 119.5 ms p95, qwen3-8b 125.0 ms p95 | `evals/results/model_comparison.csv` |
| Hosted against self-hosted model: cost | claude-haiku-5-5 $0.0494 per 1,000 requests, qwen3-8b-arabic $0.0038 per 1,000 requests, qwen3-8b-awq $0.0029 per 1,000 requests, qwen3-8b $0.0034 per 1,000 requests | `evals/results/model_comparison.csv` |

## Limits and next steps

- The test set runs here used a fake model, so the scores show the pipeline, not the quality of Claude.
- The latency numbers come from one machine with no GPU.
- Real users have not used the system yet. The next step is a pilot with one team.
