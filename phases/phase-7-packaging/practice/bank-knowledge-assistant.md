# Practice: a bank knowledge assistant

## The prompt

> "Our bank has thousands of internal policies, product sheets and circulars from the regulator. Staff in the branches and in the call centre ask questions about them all day, in Arabic and in English. Design an assistant that answers their questions."

## Questions to ask first

- Who are the users, how many, and what do they do with an answer (read it to a customer, or decide something)?
- Which documents are in scope, in which languages and formats, and how often do they change? Do old versions still apply to old contracts?
- Is customer data in scope, or only documents? Which staff may read which documents?
- What must never happen: a wrong fee, a leak of customer data, an answer from a policy that is not valid any more?
- How does the bank measure the problem today: the time to find an answer, the calls that go to a supervisor?
- Must the data stay in the country or in the bank's own data centre?
- How fast must an answer be during a call with a customer?

## Time plan

| Minutes | Part |
| --- | --- |
| 0 to 5 | Questions, and agree on the users and the scope |
| 5 to 10 | Success criteria with numbers, and the constraints |
| 10 to 25 | The design: ingestion, retrieval, the answer with citations, permissions |
| 25 to 35 | Evaluation, guardrails and monitoring |
| 35 to 42 | A deep dive that the interviewer chooses, and the trade-offs |
| 42 to 45 | Summary: the risks, and what you build first |

## Points that a strong answer covers

| Point | Evidence in your capstone |
| --- | --- |
| Success criteria that you can measure: the share of correct answers on a test set, the share of correct citations, the time to an answer | Your test set and its scores ([Phase 3, week 9](../../phase-3-evaluation/README.md#week-9-error-analysis)) |
| Parsing and chunking of the documents, with Arabic text in the correct order | [Phase 2, week 4](../../phase-2-retrieval/README.md#week-4-parse-and-chunk-the-documents) |
| Hybrid search and a re-ranker, with recall measured for each language | [Phase 2, week 6](../../phase-2-retrieval/README.md#week-6-hybrid-search-and-re-ranking), `evals/results/recall.json` |
| Each answer cites its passages, and code checks that each citation comes from a search of the same request | [Phase 2, week 7](../../phase-2-retrieval/README.md#week-7-retrieval-as-a-tool-with-citations) |
| No source, no answer: the assistant says that it does not know | Your system prompt and the citation check |
| Staff see only the documents of their role, enforced in the database and not in the prompt | [Phase 5, week 19](../../phase-5-guardrails/README.md#week-19-sign-in-and-per-user-permissions) |
| The version and the date of each policy are metadata of the chunk, so an old policy is not cited as current | Your chunk table (a gap of the capstone: say how you would add it) |
| A grader for the largest failure category, with its agreement with your own labels | [Phase 3, week 10](../../phase-3-evaluation/README.md#week-10-the-grader-model) |
| A CI gate that blocks a change that lowers the scores | [Phase 3, week 11](../../phase-3-evaluation/README.md#week-11-evaluation-in-ci) |
| Attacks in a document and personal data in an answer: the attack suite and the output checks | [Phase 5, week 18](../../phase-5-guardrails/README.md#week-18-the-attack-suite), [week 20](../../phase-5-guardrails/README.md#week-20-a-design-pattern-and-input-and-output-checks) |
| A trace, the cost and the latency of each request, and the feedback of the staff | [Phase 3, week 8](../../phase-3-evaluation/README.md#week-8-tracing), the dashboard of week 26 |
| Data that must stay in the bank: a self-hosted model behind the same gateway, with its quality, latency and cost against a hosted model | [Phase 6, week 21](../../phase-6-open-models/README.md#week-21-the-model-gateway), [week 23](../../phase-6-open-models/README.md#week-23-a-quantized-model-on-the-same-gpu), `evals/results/model_comparison.csv` |
| Where not to use a model: a fee is a lookup in a table, not a generated sentence | Your `docs/architecture.md`, section "Where plain code replaced a model call" |
