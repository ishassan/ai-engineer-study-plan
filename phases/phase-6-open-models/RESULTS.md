# Phase 6 results

Write the numbers of your own runs here. The plan says to record the numbers of each check, and week 26 builds the architecture document from them. Write the machine on which you measured the times on your Mac, for example "MacBook Pro, M3, 16 GB", and the GPU of each pod.

Machine:

## Setup

| Measure | Value |
| --- | --- |
| Time of the first `make up` with Phase 6 (image download) | |
| Time until the gateway was healthy, first start | |
| Time until the gateway was healthy, later start | |
| Memory of the gateway, idle (`docker stats`) | |
| Disk space of the gateway image | |

## Week 21: the model gateway

| Measure | Value |
| --- | --- |
| Routes in `gateway/config.yaml` | |
| Price of the route `claude-haiku-5-5` for one input token and one output token | |
| Price of the route `gpt-6-luna` for one input token and one output token | |
| How the assistant sends the user of each call | |
| Name and amount of the budget of each user, and its duration | |
| Models of the virtual key of the assistant | |

From `make check WEEK=21`.

| Measure | Value |
| --- | --- |
| Checks passed, of 10 | |
| Time of the checks | |
| Time after the expensive call until the gateway refused the user | |

The checks of the earlier phases through the gateway (`--gateway`).

| Phase | Checks passed | Checks in the phase | Time of the run |
| --- | --- | --- | --- |
| 1 | | 37 | |
| 2 | | 50 | |
| 3 | | 41 | |
| 4 | | 86 | |
| 5 | | 61 | |

Optional: your own fallback test with a wrong Claude key.

| Measure | Value |
| --- | --- |
| The question | |
| Did the answer come? | |
| Where you saw that OpenAI answered | |
| Cost (USD) | |

From `make check-live WEEK=21`.

| Measure | Value |
| --- | --- |
| Result | |
| Spend of the user that the gateway counted (USD) | |

## Week 22: the open model on vLLM

The pod.

| Measure | Value |
| --- | --- |
| GPU, and Secure Cloud or Community Cloud | |
| Price of one hour (USD) | |
| Size of the volume disk (GB) | |
| Image | |
| Start command (without the key) | |
| Time from the start of the pod to the first answer, first start | |
| Time from the start of the pod to the first answer, later start | |
| HTTP status of `/v1/models` without the key | |
| GPU memory of the weights, from the vLLM log (GiB) | |
| GPU memory in use, from `nvidia-smi` (GiB) | |

The test set (`make model-testset`). Date of the runs:

| Route | Cases | `code_pass` | Quality | Latency p50 (ms) | Latency p95 (ms) | Model calls | Cost (USD) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `claude-haiku-5-5` | | | | | | | |
| `qwen3-8b` | | | | | | | |

| Measure | Value |
| --- | --- |
| Did the open model call the tools? | |
| A case that failed on the open model and passed on Claude, and why | |

The load test of `qwen3-8b` (`make loadtest ROUTE=qwen3-8b`). Date of the run:

| Concurrency | Requests | OK | Errors | Seconds | Output tokens | Tokens per second | Requests per hour | Latency p50 (ms) | Latency p95 (ms) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | | | | | | | | | |
| 8 | | | | | | | | | |
| 32 | | | | | | | | | |

From `make check WEEK=22`.

| Measure | Value |
| --- | --- |
| Checks passed, of 8 | |
| Time of the checks | |
| Result of `make check-live WEEK=22` | |
| Hours of the pod this week | |
| Cost of the pod this week (USD) | |

## Week 23: the quantized model

| Measure | Value |
| --- | --- |
| Start command (without the key) | |
| Both models at the same time, or one after the other | |
| Time from the start of vLLM to the first answer | |

GPU memory of each model.

| Route | Weights, from the vLLM log (GiB) | In use, from `nvidia-smi` (GiB) | `--gpu-memory-gib` that you gave |
| --- | --- | --- | --- |
| `qwen3-8b` | | | |
| `qwen3-8b-awq` | | | |

The load test of `qwen3-8b-awq`. Date of the run:

| Concurrency | Requests | OK | Errors | Seconds | Output tokens | Tokens per second | Requests per hour | Latency p50 (ms) | Latency p95 (ms) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | | | | | | | | | |
| 8 | | | | | | | | | |
| 32 | | | | | | | | | |

Optional: llama.cpp on your Mac.

| Measure | Value |
| --- | --- |
| Version of llama.cpp | |
| Name of the route | |
| Time of the first start (download of the model) | |
| Quality | |
| Latency p50 (ms) | |
| Latency p95 (ms) | |
| Tokens per second of one request | |
| Did it call the tools? | |

The first table (`evals/results/model_comparison.csv`, copy it here).

| Model | Cases | Quality | Latency p50 (ms) | Latency p95 (ms) | GPU memory (GiB) |
| --- | --- | --- | --- | --- | --- |
| `claude-haiku-5-5` | | | | | |
| `qwen3-8b` | | | | | |
| `qwen3-8b-awq` | | | | | |

From `make check WEEK=23`.

| Measure | Value |
| --- | --- |
| Checks passed, of 6 | |
| Time of the checks | |
| Hours of the pod this week | |
| Cost of the pod this week (USD) | |

## Week 24: the training data

| Measure | Value |
| --- | --- |
| The task (one sentence) | |
| Cases of the task in the test set | |
| Cases of the task that failed on `qwen3-8b` | |
| Cases of the task that failed on `claude-haiku-5-5` | |
| The failure of the open model (one sentence) | |
| System prompt in the examples, and why | |

The training set.

| Measure | Value |
| --- | --- |
| Examples from traces and labels | |
| Examples drafted with Claude Code | |
| Examples that you corrected by hand | |
| Examples before the removal of duplicates | |
| Duplicates removed | |
| Examples removed because they held a test question | |
| Examples in `data/train.jsonl` | |
| Share of answers in Arabic | |

From `make check WEEK=24`.

| Measure | Value |
| --- | --- |
| Checks passed, of 5 | |

## Week 25: the adapter

The smoke run on your Mac (`make train-smoke`).

| Measure | Value |
| --- | --- |
| Time of the first run (with the installation of the packages) | |
| Time of a later run | |
| Loss of the last step | |
| Files in `train/smoke-adapter/` | |
| Errors that the smoke run found before the pod | |

The training run on the pod.

| Setting or result | Value |
| --- | --- |
| Base model | |
| Template of the pod, and version of PyTorch | |
| GPU, and price of one hour (USD) | |
| `r` | |
| `lora_alpha` | |
| `lora_dropout` | |
| `target_modules` | |
| Examples | |
| Epochs | |
| Batch size, and gradient accumulation | |
| Learning rate | |
| Maximum length (tokens) | |
| Steps | |
| Loss of the first logged step | |
| Loss of the last logged step | |
| Time of the training | |
| Size of the adapter folder | |
| Cost of the training run (USD) | |

Serving the adapter.

| Measure | Value |
| --- | --- |
| How the adapter came to the vLLM pod | |
| Start command (without the key) | |
| Name of the adapter in `--lora-modules` | |
| Models in `/v1/models` | |
| GPU memory of the base model and the adapter, from the vLLM log (GiB) | |

The load test of `qwen3-8b-arabic`. Date of the run:

| Concurrency | Requests | OK | Errors | Seconds | Output tokens | Tokens per second | Requests per hour | Latency p50 (ms) | Latency p95 (ms) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | | | | | | | | | |
| 8 | | | | | | | | | |
| 32 | | | | | | | | | |

The task of week 24 on each model.

| Route | Cases of the task | Passed |
| --- | --- | --- |
| `claude-haiku-5-5` | | |
| `qwen3-8b` | | |
| `qwen3-8b-arabic` | | |

| Measure | Value |
| --- | --- |
| Adapter copied to `train/adapter/` (date) | |
| Pods deleted (date) | |
| Network volume deleted, if you used one (date) | |

## Exit test: the hosted, open, quantized and fine-tuned models

From `evals/results/model_comparison.csv`. Date:

| Model | Cases | Quality | Latency p50 (ms) | Latency p95 (ms) | GPU memory (GiB) | Cost of 1,000 requests (USD) | Basis of the cost |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `claude-haiku-5-5` | | | | | | | |
| `qwen3-8b` | | | | | | | |
| `qwen3-8b-awq` | | | | | | | |
| `qwen3-8b-arabic` | | | | | | | |

The numbers behind the cost of each open model.

| Model | Price of one hour (USD) | Best requests per hour (loads without errors) | At the load | Cost of 1,000 requests (USD) |
| --- | --- | --- | --- | --- |
| `qwen3-8b` | | | | |
| `qwen3-8b-awq` | | | | |
| `qwen3-8b-arabic` | | | | |

| Measure | Value |
| --- | --- |
| Why a hosted request and an open request in the table are not calls of the same size | |
| Which model you would use for the assistant, and why | |

From `make check WEEK=25`.

| Measure | Value |
| --- | --- |
| Checks passed, of 11 | |
| Checks of Phase 6 passed (`make check PHASE=6`) | |
| Checks of Phases 1 to 5 passed at the end of the phase | |
| Checks of Phases 1 to 5 passed with `--gateway` at the end of the phase | |

The cost of the phase.

| Item | Cost (USD) |
| --- | --- |
| Claude and OpenAI calls (live checks, test set, your own tests) | |
| GPU hours (hours x price) | |
| Volume disk and network volume | |
| All | |
