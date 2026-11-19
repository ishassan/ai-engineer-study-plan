# A governed data assistant in English and Arabic, with its test scores

## The problem

Analysts spend time to find the right dataset, read the report that defines a number, and write SQL on tables that they may or may not read. A plain search page does not join these steps. A plain chat model answers without sources and without permissions.

## What I built

An agent that answers questions about 50 public datasets and their reports, in English and Arabic. It searches with hybrid search and a re-ranker, runs read-only SQL through MCP tool servers that apply the permissions of each user, and asks a person to approve each catalogue change. Every request is traced in Langfuse, and a test suite and an attack suite run on each pull request. The full reasons for each choice are in docs/architecture.md.

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

## What did not work

- The first grader passed almost every answer. The traces showed that the rubric did not say what a search before the answer is. Two examples in the rubric fixed it.
- The guardrails did not stop the attacks in poisoned documents. The defence that worked was the permissions of the tool servers and the approval step.

## Run it yourself

The code and the result files are in the repository https://github.com/ishassan/ai-engineer-study-plan. You need Docker, about 20 GB of disk, and a Claude API key for the live runs. Start with `make up`, then `make ask Q="Which datasets are about crude oil?"`.
