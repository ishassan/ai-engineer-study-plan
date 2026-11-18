# Architecture of the data platform assistant

<!--
Template of week 26. Write each section in your own words. The text in these comments is guidance,
and the checks do not count it: a section that holds only comments is not written yet. Delete each
comment when the section is complete.

Each number in this document comes from your own runs. Put it in the table of the section
"Numbers", with the result file that it comes from. `make numbers` prints each number of the
capstone list with its file, and `make numbers ARGS=--markdown` prints the rows of that table.
-->

## What the system does

<!--
Two or three short paragraphs for an engineer who does not know the project. Who asks the
questions, about which data, and what the assistant can do for them: answer from the catalogue
and the documents, run governed SQL, and propose catalogue changes that a person approves.
Name the data that the public version uses, in English and in Arabic.
-->

## How a request goes through the system

<!--
Follow one question from the client to the answer: sign-in and the input checks of the API, the
agent loop, the tools (search, SQL, catalogue), the model calls through the gateway, the output
checks, and the trace in Langfuse. A diagram helps (the plan's capstone diagram is a start). Each
arrow of a diagram is a claim: draw only the paths that your code has.
-->

## Choices

<!--
One short subsection (### heading) for each choice. For each one write what you chose, the other
options that you looked at, why you chose it, and what it costs. Point to the evidence: a result
file, a check, a trace, or a number of the table below. Cover at least these:

- The model and the gateway (hosted Claude, OpenAI as the fallback, the budget of each user).
- Retrieval (pgvector, hybrid search, the re-ranker, the chunk size, Arabic).
- The agent loop (the hand-written loop of Phase 1 or the LangGraph graph of Phase 4, and why).
- Tools and permissions (MCP servers, row security, the token of each user).
- Approval of write actions and the audit log.
- Guardrails (the input and output checks, and what they do not stop).
- Evaluation and tracing (the test set, the grader, the CI gate, Langfuse).
- The self-hosted model (quality, latency and cost against the hosted model, and when you would
  use each).
-->

## Where plain code replaced a model call

<!--
List each place where code does a job that a model call could do, and why code is better there:
for example the cost calculation, the check of the citations, the code checks of the test set,
the routing of the gateway, or a rule of the guardrails. Also list the places where you kept a
model call, and why code was not enough.
-->

## Numbers

<!--
One row for each number. Value: the number as you measured it. Source: the path of the result
file in this repository that holds it, in backticks, for example `evals/results/recall.json`.
The week 26 check reads this table: each row must have a value and a source file that exists.
-->

| Number | Value | Source |
| --- | --- | --- |
| Test set size | | |
| Task success rate on the test set | | |
| Retrieval recall, English | | |
| Retrieval recall, Arabic | | |
| Groundedness score | | |
| Grader agreement with your labels | | |
| Attack-suite pass rate | | |
| 95th-percentile latency | | |
| Cost per request | | |
| Hosted against self-hosted model: quality | | |
| Hosted against self-hosted model: latency | | |
| Hosted against self-hosted model: cost | | |

## Limits and next steps

<!--
What the system does not do yet, what you measured on a small sample only, and what you would
change first with more time. Be specific: a reader trusts a document that states its limits.
-->
