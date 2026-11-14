# Phase 1 results

Write the numbers of your own runs here. The plan says to record the numbers of each check, and week 26 builds the architecture document from them.

## Week 1: one request

From `make check-live WEEK=1`.

| Measure | Value |
| --- | --- |
| Input tokens | |
| Output tokens | |
| Cost of the first request (USD) | |
| Latency of the first request (ms) | |
| Latency of the replay from the response cache (ms) | |

## Week 2: the loop on the quick set

From `make check-live WEEK=2`.

| Question | Correct | Requests | Cost (USD) | Tools |
| --- | --- | --- | --- | --- |
| | | | | |
| | | | | |
| | | | | |
| | | | | |
| | | | | |

## Week 3: prompt caching

Three questions, before and after the cache breakpoint.

| Measure | Before | After |
| --- | --- | --- |
| Tokens of the tools and the system prompt (from `count_tokens`) | | |
| Cost of three questions (USD) | | |

## Exit test: 30 questions with the response cache off

From `make check-live WEEK=3`. Date of the run:

| Measure | Value |
| --- | --- |
| Questions passed, of 30 | |
| Requests to Claude | |
| Total cost (USD) | |
| Median latency of one question (s) | |
| Requests with a cache read | |
| Share of input tokens from the cache | |

## Failed questions by cause

| Cause | Count |
| --- | --- |
| The search did not return the dataset | |
| The model chose another dataset | |
| The expected IDs in the question file were wrong | |
| Other | |
