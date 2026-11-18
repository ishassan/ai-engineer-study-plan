# Practice: an analytics agent

## The prompt

> "Business users want to ask questions about the sales data in our warehouse in plain language, and get numbers and charts without writing SQL. Design it."

## Questions to ask first

- Who asks, how many people, and what do they do with the number (a report to the board, a quick check)?
- How many tables, and is there a catalogue or a semantic layer with the definitions of the measures?
- Which users may see which rows (regions, customers, salaries)?
- What does a wrong number cost? Must each number show the query that made it?
- Which languages do the users ask in?
- How large is the warehouse, and what does a slow or a large query cost?

## Time plan

| Minutes | Part |
| --- | --- |
| 0 to 5 | Questions, and agree on the users and the data |
| 5 to 10 | Success criteria with numbers, and the constraints |
| 10 to 25 | The design: the catalogue, the choice of a table, the SQL, the answer |
| 25 to 35 | Evaluation, permissions, attacks and monitoring |
| 35 to 42 | A deep dive that the interviewer chooses, and the trade-offs |
| 42 to 45 | Summary: the risks, and what you build first |

## Points that a strong answer covers

| Point | Evidence in your capstone |
| --- | --- |
| Success criteria that you can measure: the share of questions with the correct table and the correct number, on a test set with expected results | [Phase 3, week 9](../../phase-3-evaluation/README.md#week-9-error-analysis), `evals/testset.jsonl` |
| The agent finds the table with a search of the catalogue and reads its schema before it writes SQL | [Phase 1, week 2](../../phase-1-claude-api/README.md#week-2-tool-calling-and-the-model-loop) (tools), [Phase 4, week 16](../../phase-4-agents/README.md#week-16-mcp-tool-servers) (SQL server) |
| The database computes the numbers. The model writes the query and explains the result, and does not do arithmetic | Your `docs/architecture.md`, section "Where plain code replaced a model call" |
| Read-only SQL with limits and a timeout, and row security for each user in the database | [Phase 4, week 16](../../phase-4-agents/README.md#week-16-mcp-tool-servers) (read-only role, timeout), [Phase 5, week 19](../../phase-5-guardrails/README.md#week-19-sign-in-and-per-user-permissions) |
| The answer names the dataset and shows the query, so a user can check the number | Your answer schema with `dataset_ids` ([Phase 1, week 3](../../phase-1-claude-api/README.md#week-3-structured-output-caching-and-the-test-runner)) |
| A question with two meanings gets a question back, not a guess | A case for your test set (a gap of the capstone: say how you would test it) |
| Questions in Arabic and in English give the same table | The Arabic cases of your test set, `evals/results/recall.json` |
| Values in the data are untrusted text: an attack in a tool result is in the attack suite | [Phase 5, week 18](../../phase-5-guardrails/README.md#week-18-the-attack-suite) |
| Cost and latency of each request, the cache of the prompt, and the feedback of the users | [Phase 1, week 3](../../phase-1-claude-api/README.md#week-3-structured-output-caching-and-the-test-runner), [Phase 3, week 8](../../phase-3-evaluation/README.md#week-8-tracing), the dashboard of week 26 |
| A model choice from measurements: a smaller or a self-hosted model where the scores allow it | [Phase 6, week 22](../../phase-6-open-models/README.md#week-22-an-open-model-on-vllm), `evals/results/model_comparison.csv` |
