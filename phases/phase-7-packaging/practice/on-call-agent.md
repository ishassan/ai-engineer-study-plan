# Practice: an on-call agent

## The prompt

> "Our site reliability team gets paged at night. Design an agent that helps the engineer on call: it reads the alerts, the logs and the runbooks, and suggests actions or takes them."

## Questions to ask first

- How many alerts arrive in a night, and which share needs a person?
- Which data can the agent read (logs, metrics, deployments, tickets), and with which credentials?
- Which actions may it take alone (a restart, a rollback, more instances), and which need the engineer?
- How is the team measured today: the time to acknowledge, the time to resolve?
- Do the runbooks exist, and are they current?
- What happens when the agent itself, or its model provider, is down during an incident?

## Time plan

| Minutes | Part |
| --- | --- |
| 0 to 5 | Questions, and agree on the users and the actions |
| 5 to 10 | Success criteria with numbers, and the limits of the agent |
| 10 to 25 | The design: the tools, the runbook search, the suggestion, the approval of an action |
| 25 to 35 | Evaluation on past incidents, safety and monitoring |
| 35 to 42 | A deep dive that the interviewer chooses, and the trade-offs |
| 42 to 45 | Summary: the risks, and what you build first |

## Points that a strong answer covers

| Point | Evidence in your capstone |
| --- | --- |
| Success criteria that you can measure: the time to resolve, the share of correct first suggestions on past incidents | Your agent tasks and their scores ([Phase 4, week 17](../../phase-4-agents/README.md#week-17-agent-evaluation)) |
| The agent starts read-only. Each action that changes production needs the decision of the engineer, and the audit log keeps it | [Phase 4, week 15](../../phase-4-agents/README.md#week-15-persistence-approval-and-the-audit-log) |
| Tools on a tool server, with credentials limited to what each tool needs | [Phase 4, week 16](../../phase-4-agents/README.md#week-16-mcp-tool-servers), [Phase 5, week 19](../../phase-5-guardrails/README.md#week-19-sign-in-and-per-user-permissions) |
| The runbook search cites the runbook and its section, so the engineer can check the step | [Phase 2, week 7](../../phase-2-retrieval/README.md#week-7-retrieval-as-a-tool-with-citations) |
| Log lines are untrusted text. Private data, untrusted content and a way to send data out together are the lethal trifecta: do not give one agent all three | [Phase 5, week 18](../../phase-5-guardrails/README.md#week-18-the-attack-suite), [week 20](../../phase-5-guardrails/README.md#week-20-a-design-pattern-and-input-and-output-checks) |
| Evaluation by a replay of past incidents, with the result and the path of the agent | [Phase 4, week 17](../../phase-4-agents/README.md#week-17-agent-evaluation) |
| A trace of each step of the agent, for the review after the incident | [Phase 3, week 8](../../phase-3-evaluation/README.md#week-8-tracing) |
| A fallback when the model provider is down, or a self-hosted model | [Phase 6, week 21](../../phase-6-open-models/README.md#week-21-the-model-gateway), [week 22](../../phase-6-open-models/README.md#week-22-an-open-model-on-vllm) |
| Where not to use a model: the grouping of duplicate alerts and the thresholds are rules in code | Your `docs/architecture.md`, section "Where plain code replaced a model call" |
