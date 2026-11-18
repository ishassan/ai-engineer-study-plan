# Practice: an ERP process agent

## The prompt

> "Our finance team processes supplier invoices in the ERP system. Many invoices need a person: to match them with a purchase order, to fix an account code, or to ask a manager for approval. Design an agent that does this work."

## Questions to ask first

- How many invoices arrive each day, in which formats, and which share needs a person today?
- Which steps follow fixed rules (the match of an invoice with its order and the goods receipt), and which need a judgement?
- Which actions may the agent take alone, and which need a person: a change of a code, a payment, a message to a supplier?
- Which API of the ERP system can the agent call, with which rights? Is there a test system?
- What does an error cost: a late payment, a double payment, a fraud?
- What must the auditors see afterwards?

## Time plan

| Minutes | Part |
| --- | --- |
| 0 to 5 | Questions, and agree on the process and the scope |
| 5 to 10 | Success criteria with numbers, and the actions that need a person |
| 10 to 25 | The design: the workflow, the tools, the state of a long process, the approval |
| 25 to 35 | Evaluation, safety against attacks, and monitoring |
| 35 to 42 | A deep dive that the interviewer chooses, and the trade-offs |
| 42 to 45 | Summary: the risks, and what you build first |

## Points that a strong answer covers

| Point | Evidence in your capstone |
| --- | --- |
| A workflow in code for the fixed rules, and a model only for the steps that need a judgement | Your `docs/architecture.md`, section "Where plain code replaced a model call". "Building effective agents", the reading of [Phase 4, week 14](../../phase-4-agents/README.md#week-14-move-the-loop-to-langchain-and-langgraph) |
| Success criteria that you can measure: the share of invoices with no person, the error rate, the time that the team saves | Your agent tasks and their scores ([Phase 4, week 17](../../phase-4-agents/README.md#week-17-agent-evaluation)) |
| Narrow tools on a tool server, each with the rights of the user or of a service account, never the rights of an administrator | [Phase 4, week 16](../../phase-4-agents/README.md#week-16-mcp-tool-servers), [Phase 5, week 19](../../phase-5-guardrails/README.md#week-19-sign-in-and-per-user-permissions) |
| No write action without the decision of a person, and an audit log of each action and decision | [Phase 4, week 15](../../phase-4-agents/README.md#week-15-persistence-approval-and-the-audit-log) |
| The state of a long process survives a restart: checkpoints, and an action that runs two times does no harm | [Phase 4, week 15](../../phase-4-agents/README.md#week-15-persistence-approval-and-the-audit-log) (checkpointer) |
| After the agent reads untrusted text (an invoice), the text cannot start an action: a design pattern, for example an approval after untrusted content, or a plan made before the agent reads it | [Phase 5, week 20](../../phase-5-guardrails/README.md#week-20-a-design-pattern-and-input-and-output-checks) (design pattern), [Phase 4, week 13](../../phase-4-agents/README.md#week-13-planning-by-hand) (planner) |
| The text of an invoice is untrusted: attacks in documents and in tool results are in the test suite | [Phase 5, week 18](../../phase-5-guardrails/README.md#week-18-the-attack-suite) |
| Evaluation of the result and of the path (the right tools in the right order) | [Phase 4, week 17](../../phase-4-agents/README.md#week-17-agent-evaluation), `evals/results/agent-tasks.json` |
| A fallback when the model provider fails, and a budget | [Phase 6, week 21](../../phase-6-open-models/README.md#week-21-the-model-gateway) |
| A trace for each process, with its cost and latency, for the auditors and for debugging | [Phase 3, week 8](../../phase-3-evaluation/README.md#week-8-tracing) |
