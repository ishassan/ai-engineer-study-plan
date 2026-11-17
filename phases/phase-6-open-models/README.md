# Phase 6 lab: the model gateway and self-hosted models

Weeks 21 to 25 of the [study plan](../../README.md#phase-6-the-model-gateway-and-self-hosted-models-weeks-21-to-25). At the end, each model call of the assistant goes through a LiteLLM gateway on your Mac. The gateway falls back from Claude to OpenAI when Claude refuses, and it stops a user who spent the budget. An open model (Qwen3-8B), its 4-bit AWQ version and a LoRA adapter that you trained run on a rented GPU with vLLM, behind the same gateway. One table compares the hosted, the open, the quantized and the fine-tuned model on the same test set, for quality, latency and the cost of 1,000 requests.

The lab gives the infrastructure: the gateway service in Compose with its own database, a gateway configuration with the structure and no routes, a check gateway that runs your configuration with the fake APIs as its providers, the load test script with two stubs, the training script with two stubs and a smoke mode, the cost module with three stubs, and the comparison notebook. You write the parts that the phase teaches:

| Week | You write | File |
| --- | --- | --- |
| 21 | The routes of Claude and OpenAI with their prices, the fallback, the budget of each user | `gateway/config.yaml` |
| 21 | Each model call of the assistant through the gateway, with the user of the call | `assistant/llm.py`, `assistant/agent.py`, `assistant/models.py`, `assistant/graph.py` |
| 22 | The route of the open model, a cost of 0 for a model with no price | `gateway/config.yaml`, `assistant/llm.py` |
| 22 | The load test | `scripts/loadtest.py` |
| 22, 23, 25 | The test set and load test results of each model | `evals/results/models/<route>.jsonl`, `evals/results/load/<route>.json` (written by `make model-testset` and `make loadtest`) |
| 23 | The route of the quantized model, and the first table | `gateway/config.yaml`, `evals/results/model_comparison.csv` (written by the notebook) |
| 24 | The training set | `data/train.jsonl` |
| 25 | The LoRA settings and the trainer call | `train/train_lora.py` |
| 25 | The route of the adapter, the cost functions, the exit table | `gateway/config.yaml`, `evals/model_costs.py`, `evals/results/model_comparison.csv` |

**Cost:** the offline checks are free. They use the fake Claude API and the fake OpenAI API of the earlier phases, and the fake OpenAI API also stands in for vLLM, so they need no GPU and no key. The paid parts are the GPU time on RunPod, the disk of the pod, one run of the test set on Claude, and two live checks. [Costs of the phase](#costs-of-the-phase) gives each estimate with its arithmetic. These numbers are estimates, not measurements. You draft the training examples with Claude Code, which uses your subscription and no API credit.

## Before you start

- **Phase 5 is complete.** `make check PHASE=1` to `make check PHASE=5` pass. This phase changes files that you wrote in Phases 1 to 5 (see [Changes to files from earlier phases](#changes-to-files-from-earlier-phases)).
- **One new service.** `gateway` uses the image `ghcr.io/berriai/litellm:v1.109.1` (LiteLLM 1.109.1, the newest release on PyPI on 2026-11-17). The image has a linux/arm64 build (checked by its manifest). The arm64 download is about 431 MB compressed. On the build machine the amd64 image took 1.84 GB on disk. A one-shot service `gateway-db` uses the image of `db`, so it downloads nothing. It creates the database `litellm` in the Postgres service, because LiteLLM does not create its own database.
- **First start.** With an empty database, the gateway was ready after about 25 seconds on the build machine (LiteLLM applies its database migrations at the first start).
- **A RunPod account with credit, from week 22.** The GPU, the image of vLLM and the model weights are on the pod, not on your Mac. The image `vllm/vllm-openai:v0.33.0` is about 9.7 GB compressed (amd64, from Docker Hub). The weights of `Qwen/Qwen3-8B` are 16.38 GB and those of `Qwen/Qwen3-8B-AWQ` are 6.1 GB (safetensors files, from the Hugging Face API). Neither repository is gated, so the pod needs no Hugging Face token to download them.
- **Disk on your Mac.** The gateway image (above). `make train-smoke` in week 25 installs PyTorch, TRL, PEFT and Transformers in the cache of uv and downloads a tiny model of about 21 MB. The size of that cache was not measured. The optional llama.cpp step of week 23 downloads the 4-bit file `Qwen3-8B-Q4_K_M.gguf`, 5.03 GB.
- **Port.** The gateway listens on 127.0.0.1:4000. Change `GATEWAY_PORT` and `GATEWAY_URL` in `.env` if the port is in use.

All numbers in this guide were measured on a Linux machine with 4 x86 CPU cores, 15 GiB of memory and no GPU, not on a Mac. Nothing in this phase ran on Apple Silicon or on a GPU. The steps on RunPod, vLLM on a GPU, the training on the GPU and llama.cpp come from the documentation, and each step says so. Write your own numbers in [RESULTS.md](RESULTS.md).

## Setup

Run these commands from the repository root.

```bash
make start PHASE=6
```

This command copies the new files of the phase: `gateway/config.yaml` (the structure, no routes), `scripts/loadtest.py` (two stubs), `evals/model_costs.py` (three stubs), `train/requirements.txt` (complete) and `train/train_lora.py` (two stubs). It also turns on the Python package of the phase (PyYAML, for the checks) and the Docker services of the phase. It does not change a file that exists.

### The given file of Phase 1

`make start` never overwrites a file, so copy the Phase 6 copy of `assistant/config.py` by hand:

```bash
cp phases/phase-6-open-models/given/assistant/config.py assistant/
```

You did not write this file, so you lose no work. It has the settings of Phase 5 and two more: `GATEWAY_URL` and `GATEWAY_KEY` (see [Commands](#commands)). With an empty `GATEWAY_URL`, the assistant calls the providers directly, as in Phases 1 to 5.

### Settings and services

Copy the Phase 6 lines of `.env.example` into your `.env`:

```bash
GATEWAY_PORT=4000
LITELLM_MASTER_KEY=sk-lab-gateway-master
GATEWAY_URL=http://localhost:4000
GATEWAY_KEY=
VLLM_API_BASE=
VLLM_API_KEY=
```

`GATEWAY_KEY` stays empty until step 2 of week 21, and the two vLLM settings until week 22. The master key opens the admin API and the admin UI at http://localhost:4000/ui (user `admin`, password = the master key, from the [Docker quick start](https://docs.litellm.ai/docs/proxy/docker_quick_start) of LiteLLM). Compose binds the port to 127.0.0.1, so only your machine can use it.

```bash
make up
```

With the Phase 6 profile, `make up` also runs `gateway-db` and starts `gateway`. The gateway reads `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` from `.env`. Compose gives the API container `GATEWAY_URL=http://gateway:4000`.

Then run the checks of week 21:

```bash
make check WEEK=21
```

Before your work, 9 checks fail and 1 passes: the gateway starts with the given configuration.

## How the lab works

- **Steps.** Each week below has the same steps as the plan, in the same order.
- **The check gateway.** Most checks start one more container of the service `gateway` (`labkit/gateway.py`): the same image and your `gateway/config.yaml`, with the fake Claude API and the fake OpenAI API as its providers. The fake OpenAI API also stands in for vLLM on your pod: vLLM speaks the same protocol, the OpenAI Chat Completions API. Each provider gets a key that only the check gateway has, so a check sees whether a request came through the gateway or directly from your code. The check gateway keeps its spend and budgets in a database of its own, `litellm_checks_<process id>`, so the checks never change the spend and the budgets of your own gateway. When your configuration names a default budget for each user (`max_end_user_budget_id`), the check gateway creates that budget with $1,000, so a check can spend it on purpose.
- **The checks need Docker and Postgres.** Run `make up` first. On the build machine the checks took about 1 minute for week 21, about 35 seconds for week 22, about 30 seconds each for weeks 23 and 25, and a few seconds for week 24.
- **Some checks read the files of your real runs.** In weeks 22, 23 and 25 the checks also read your test set results, your load test results and the table. These files come from the runs on the pod. A check cannot make a GPU number for you, so these checks pass only after the runs.
- **All earlier checks through the gateway.** The plugin of the lab has a new option, `--gateway`: each model call of each offline check goes through a check gateway with your configuration. So you can see that the checks of Phases 1 to 5 still pass when each call goes through your gateway (week 21, step 4).
- **Without `--gateway`, the checks call the fake APIs directly.** The plugin clears `GATEWAY_URL` and `GATEWAY_KEY` for each check, and the fixture `gateway` sets them for the checks that need the gateway. So the `.env` of your own gateway does not change the checks.
- **macOS can ask once.** While the checks run, the relays of the fake APIs listen on all network interfaces, because the container of the check gateway must reach them. macOS can ask whether Python may accept incoming connections. This was not tested on a Mac.
- **Live checks.** `make check-live WEEK=21` calls Claude through your gateway, and `make check-live WEEK=22` calls the open model on your pod through your gateway. They did not run in the build of this lab.

| Name | Where | Used by |
| --- | --- | --- |
| `gateway/config.yaml`, mounted on `/app/config.yaml` of the service `gateway`. `general_settings` (given): `master_key: os.environ/LITELLM_MASTER_KEY`, `database_url: os.environ/DATABASE_URL` | your configuration | All Phase 6 checks, `--gateway` |
| The route `claude-haiku-5-5` (the default `CLAUDE_MODEL`) and the route `gpt-6-luna` (the default `OPENAI_MODEL`). The key of each comes from `os.environ/ANTHROPIC_API_KEY` and `os.environ/OPENAI_API_KEY`. No `api_base`: the checks point each provider at its fake with an environment variable of the gateway | your configuration | Week 21 checks |
| The price of each of these two routes: `input_cost_per_token` and `output_cost_per_token` (in `litellm_params` or `model_info`), equal to `PRICES_PER_MTOK` of `assistant/config.py` divided by 1,000,000 | your configuration | Week 21 checks |
| A fallback from `claude-haiku-5-5` to `gpt-6-luna` in `router_settings` | your configuration | Week 21 checks (the behaviour, not the text) |
| `litellm_settings.max_end_user_budget_id`: the budget of each user | your configuration | Week 21 checks, live check |
| The route `qwen3-8b`: vLLM gets the model name `Qwen/Qwen3-8B` and the key `os.environ/VLLM_API_KEY`, at `os.environ/VLLM_API_BASE` | your configuration | Week 22 checks |
| The route `qwen3-8b-awq`: vLLM gets the model name `Qwen/Qwen3-8B-AWQ`, same base and key | your configuration | Week 23 checks |
| The route `qwen3-8b-arabic`: vLLM gets the name of the adapter in `--lora-modules` (any name other than the two base names) | your configuration | Week 25 checks |
| `GATEWAY_URL`, `GATEWAY_KEY` | given `config.py` | Your code. Empty URL: direct calls |
| The gateway knows the user of each model call | your code | Week 21 checks test the behaviour, not how you send it |
| `scripts/loadtest.py`: the flags `--model --loads --requests-per-slot --max-tokens --gpu --gpu-price --gpu-memory-gib --out`, and the result file of its docstring | starter, `one_request()` and `run_load()` are yours | Week 22 checks |
| `evals/results/models/<route>.jsonl`: the rows of `evals/run_testset.py` (`id`, `question`, `answer`, `dataset_ids`, `code_pass`, `requests`, `cost_usd`, `latency_ms`), one row for each case of `evals/testset.jsonl` | written by `make model-testset ROUTE=<route>` | Weeks 22, 23 and 25 checks, the notebook |
| `evals/results/load/<route>.json`: the loads 1, 8 and 32, with `gpu`, `gpu_price_per_hour` and `gpu_memory_gib` above 0 | written by `make loadtest ROUTE=<route>` | Weeks 22, 23 and 25 checks, the notebook |
| `evals/results/model_comparison.csv`: `model, cases, quality, latency_ms_p50, latency_ms_p95, gpu_memory_gib, cost_per_1000_requests, cost_basis` | written by the notebook | Weeks 23 and 25 checks |
| `data/train.jsonl`: one object `{"messages": [...]}` on each line | your training set | Week 24 checks, the training script |
| `hosted_cost_per_1000(rows)`, `best_requests_per_hour(load_result)`, `gpu_cost_per_1000(price_per_hour, requests_per_hour)` | `evals/model_costs.py` | Week 25 checks, the notebook |
| `lora_config()` and `train(model, dataset, output, smoke)` | `train/train_lora.py` | `make train-smoke`, the run on the pod. No offline check (it needs PyTorch) |

The Make targets of this phase take `ROUTE=`, not `MODEL=`, because `MODEL` is the model of the attack suite of Phase 5.

### Checks that can fail on correct code

Two checks of earlier phases can fail one time on correct code: the trace check of Phase 3 week 8 and a trace check of Phase 4 week 16. In the build of this lab each failed once in some full runs and passed when it ran again. When one of them fails, run it again one time before you debug.

### Changes to files from earlier phases

`make start PHASE=6` does not touch the files that you wrote. You change them yourself:

- `assistant/config.py`: replace it with the Phase 6 copy (see [Setup](#the-given-file-of-phase-1)).
- `assistant/llm.py`: the client of the anthropic SDK goes to the gateway when `GATEWAY_URL` is set (week 21). The cost of a call to a model with no price is 0 (week 22).
- `assistant/agent.py`: each request of the hand-written loop names its user (week 21).
- `assistant/models.py`: both chat models of the graph go to the gateway, and name the user (week 21).
- `assistant/graph.py`: the graph gives the user of the request to its chat models (week 21).

The checks of Phases 1 to 5 must stay green through the whole phase, also with `--gateway`.

## Costs of the phase

| Item | Estimate | Arithmetic and source |
| --- | --- | --- |
| Offline checks | $0 | The fake APIs |
| `make check-live WEEK=21` | less than $0.01 | One short question to Claude: about 50 input and 100 output tokens (an estimate). 50 x $0.10 per million + 100 x $0.50 per million = about $0.00006. The prices are `PRICES_PER_MTOK` of `assistant/config.py` |
| Your own fallback test in week 21 (optional) | about $0.001 | One question through OpenAI: about 5,000 input and 300 output tokens at $0.10 and $0.50 per million = $0.0005 + $0.00015 |
| `make model-testset ROUTE=claude-haiku-5-5` (week 22) | about $0.07, up to about $0.15 | The estimate of the Phase 3 guide: 105 cases of about 5,000 input and 300 output tokens. 105 x ($0.0005 + $0.00015) = about $0.07. Twice the tokens: about $0.15 |
| The test set and the load tests on the open models | $0 in tokens | The routes of the open models have the price 0. You pay the pod by the hour |
| `make check-live WEEK=22` | $0 in tokens | One question to the pod |
| GPU time | the hours x the price of the hour | [RunPod pricing](https://www.runpod.io/pricing) (updated November 12, 2026): A40 (48 GB) $0.59 an hour on Secure Cloud and $0.35 on Community Cloud. RTX A6000 (48 GB) $0.69 on Secure Cloud and $0.33 on Community Cloud. The plan gives the Secure Cloud prices. For example, a session of 3 hours on an A40 of Secure Cloud: 3 x $0.59 = $1.77. The hours that each week needs are not known, because nothing ran on a GPU in the build of this lab |
| Volume disk of the pod | about $2.30 a month while the pod runs, about $4.60 a month while it is stopped | [Pods pricing](https://docs.runpod.io/pods/pricing): volume disk $0.10 per GB a month on a running pod, $0.20 on a stopped pod, billed by the second. The two models are about 23 GB: 23 x $0.10 = $2.30 and 23 x $0.20 = $4.60. A larger volume costs more in proportion. Delete the pod to stop this cost |
| A network volume (optional, week 25) | $0.07 per GB a month | The same pricing page. It stays when you delete the pod |
| Training on the pod (week 25) | the hours x the price of the hour | Not run, so the time is not known |

The prices on these pages change. Read them again before you rent, and give the price that you pay to the load test (`--gpu-price`).

## Week 21: The model gateway

### Step 1. Read

Huyen, chapter 10: Step 3. Add Model Router and Gateway, and Step 4. Reduce Latency with Caches (pages 456 to 463). LiteLLM [AI Gateway](https://docs.litellm.ai/docs/simple_proxy) and [Fallbacks](https://docs.litellm.ai/docs/proxy/reliability).

The AI Gateway page says: "Your applications send requests to the gateway. The gateway sends each request to the provider of the model." It lists what the gateway does: access control with virtual keys, spend tracking, reliability ("Load balancing, fallbacks, and retries"), guardrails, logging and the admin UI. The LiteLLM pages are not written for one version, and some parts name versions newer than 1.109.1, which the lab pins. Where a page and the pinned version differ, the steps below say so.

### Step 2. Run the gateway and send every model call through it

A gateway is one place between your code and the model providers. Your code sends each call to the gateway with one key. The gateway has the provider keys, chooses the provider for the model name, counts the spend of each caller, and can send the call to another model when one fails. So a change of provider, a fallback or a budget is a change of the gateway configuration, not of your code.

**The service (given).** `make up` starts the gateway with `gateway/config.yaml`. A route in `model_list` maps a model name that your code sends (`model_name`) to a provider model (`litellm_params.model`). A value `os.environ/NAME` reads the environment variable `NAME` of the gateway container ([Config.yaml overview](https://docs.litellm.ai/docs/proxy/configs)). After each change of the file, restart the gateway:

```bash
docker compose restart gateway
```

**The request format.** The assistant keeps the Anthropic Messages format, and sends it to the endpoint `/v1/messages` of the gateway. The page [/v1/messages](https://docs.litellm.ai/docs/anthropic_unified/) says: "Use LiteLLM to call all your LLM APIs in the Anthropic v1/messages format". Its table lists cost tracking, end-user tracking, streaming and fallbacks ("Works between supported models"), and its example makes `anthropic.Anthropic(base_url="http://0.0.0.0:4000", api_key="sk-<your-litellm-api-key>")`. So the code of Phases 1 to 5 keeps its cache breakpoints (`cache_control`), its typed output, its tool calls and the cache fields of the usage. The graph on OpenAI keeps the OpenAI format and sends it to `/v1` of the gateway.

> From the build of this lab, not from a page: with LiteLLM 1.109.1 and the fake APIs, a request to a Claude route reached the provider with `cache_control`, `tools`, `output_config` and `metadata` unchanged, and the cache fields came back in the usage. On the fallback to `gpt-6-luna`, LiteLLM called the OpenAI Responses API (`/v1/responses`), with the tools as function tools and the schema as `text.format`, and gave the answer back in the Anthropic format. For a vLLM route it called `/v1/chat/completions` with `response_format` and `tools`. The page [Structured Output /v1/messages](https://docs.litellm.ai/docs/anthropic_unified/structured_output) lists only Anthropic, Azure AI and Bedrock (Claude models) for typed output, so the translation for the other providers is observed, not documented.

1. **Two routes.** Add the routes `claude-haiku-5-5` and `gpt-6-luna` (see [Fixed names](#how-the-lab-works)). Give each route its prices for one token, so that the gateway counts the spend in the prices that your assistant writes in its results.
2. **The anthropic SDK through the gateway.** In `assistant/llm.py`, when `GATEWAY_URL` is set, make the client with `base_url=GATEWAY_URL` and `api_key=GATEWAY_KEY`. When it is empty, keep the direct client of Phase 1.
3. **The graph through the gateway.** In `assistant/models.py`, give `ChatAnthropic` the address of the gateway, and `ChatOpenAI` the address of the gateway with `/v1`, both with the gateway key. In langchain-anthropic 1.7.10 and langchain-openai 1.8.0 (the versions of `uv.lock`) both classes take `base_url`, `api_key` and `default_headers`.
4. **A virtual key for the assistant.** The master key opens the admin API. The assistant gets its own key, limited to the routes of the lab. The form is from [Virtual Keys](https://docs.litellm.ai/docs/proxy/virtual_keys) ("Generate a Key"):

```bash
curl http://localhost:4000/key/generate -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
    -H 'Content-Type: application/json' \
    -d '{"models": ["claude-haiku-5-5", "gpt-6-luna", "qwen3-8b", "qwen3-8b-awq", "qwen3-8b-arabic"]}'
```

Put the key of the answer in `GATEWAY_KEY` in `.env`, and run `make up` again, so that the API container gets it. In the build of this lab, a key made this way got 403 for a model outside its list. This exact command did not run against a learner gateway: the checks call the same endpoint with other values. The quick start page says: "Virtual keys also require a database." The lab gives the gateway its database.

<details>
<summary>Hint: one client for each address</summary>

`assistant/llm.py` keeps one client. When the settings can change between calls (the checks change `GATEWAY_URL` for each test), a client that you made once still points at the old address. Make the client from the address and the key, and keep one client for each pair.
</details>

<details>
<summary>Hint: the check sees a direct call</summary>

Each check of this step gives the fake API a key that only the check gateway has. A failure that says the request did not come through the gateway means that your code called the fake API directly: a client that reads `ANTHROPIC_BASE_URL`, or a chat model of the graph that has no `base_url`. Look at each place that makes a client: `assistant/llm.py` and `assistant/models.py`.
</details>

### Step 3. A fallback from Claude to OpenAI, and a budget for each user

**The fallback.** The Fallbacks page says: "If a call fails after num_retries, LiteLLM falls back to another model group". It names three types: `content_policy_fallbacks`, `context_window_fallbacks`, and `fallbacks` "For all remaining errors". A refused key (HTTP 401) is one of the remaining errors. Add a fallback from `claude-haiku-5-5` to `gpt-6-luna` in `router_settings`, in the form of the page.

**Cooldown.** After failures, LiteLLM keeps a deployment out of use for `cooldown_time` seconds. The page shows `allowed_fails: 3` and `cooldown_time: 30` as an example. In LiteLLM 1.109.1 the default is 5 seconds (`DEFAULT_COOLDOWN_TIME_SECONDS` in `litellm/constants.py` of the image). So after Claude fails, the next calls go straight to OpenAI for a short time. The fallback checks of week 21 run last and wait 6 seconds after each. A long `cooldown_time` can send later checks of the same run to OpenAI.

**The budget of each user.** Read [Budgets, Rate Limits](https://docs.litellm.ai/docs/proxy/users), the part "Customers". A customer (an end user) is the user of a call, not the owner of a key. The page has two steps: create a budget with `POST /budget/new`, then name it in the configuration: `max_end_user_budget_id` is "applied to any 'user' without their own budget", also to customers that are not in the database yet. Create the budget in your gateway, with a duration so that it starts again each month ("Reset Budgets" on the same page):

```bash
curl http://localhost:4000/budget/new -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
    -H 'Content-Type: application/json' \
    -d '{"budget_id": "per-user", "max_budget": 1.0, "budget_duration": "30d"}'
```

Choose your own name and amount. This command did not run against a learner gateway: the checks create the budget of your configuration with the same endpoint. Then set `max_end_user_budget_id` to the name, and make the assistant send the user of each request (the user of `/ask`) with each model call: in the hand-written loop and in both chat models of the graph.

The page also says:

- "LiteLLM caches the budget object for 60 seconds, so edits to it take up to a minute to apply."
- Budget reservation is on by default: "LiteLLM estimates the request's maximum cost from the request body and the model's pricing", and "If the reservation would exceed the budget, LiteLLM rejects the request before sending it to the provider." So a budget smaller than one call at `max_tokens` refuses the first call. The assistant sends `max_tokens` 4096 (`CLAUDE_MAX_TOKENS`): 4,096 x $0.50 per million = about $0.002.
- Fallback to 'free' models: "Budget checks are skipped entirely for zero-cost models." The routes of the open models have the price 0, so a user over the budget can still call them.

The gateway writes the spend to its database in batches: `proxy_batch_write_at`, default 10 seconds ([config settings](https://docs.litellm.ai/docs/proxy/config_settings)). So the refusal comes some seconds after the expensive call. In the build of this lab the refusal was HTTP 422 with the type `budget_exceeded` and the text `ExceededBudget: End User=... over budget. Spend=..., Budget=...` on `/v1/messages`. The Users page shows 401 for `/chat/completions`. The anthropic SDK raises an exception for the 422, and your API already turns an exception into an `error` event.

<details>
<summary>Hint: how the gateway knows the user</summary>

The page [Customers](https://docs.litellm.ai/docs/proxy/customers) names the header `x-litellm-end-user-id` (and `x-litellm-customer-id`) and the field `user`, as the legacy end-user tracking that "remain supported". In the source of LiteLLM 1.109.1 (`litellm/proxy/auth/auth_utils.py`), the gateway also reads `metadata.user_id`, the field of the Messages API. A header works the same for the anthropic SDK (`extra_headers` of each request) and for both chat models (`default_headers`). The page also says that "Customer Management is the recommended setup from v1.111". That is a newer version than the one of the lab. The lab uses the end-user budgets of the Users page.
</details>

<details>
<summary>Hint: the budget check sees no spend</summary>

The gateway counts spend only for a route with a price. The prices are for one token: `0.0000001`, not `0.10`. A route with a price for one million tokens makes each call cost a million times more. The price list that comes with LiteLLM 1.109.1 also has `claude-haiku-5-5` and `gpt-6-luna`, but the week 21 checks require the prices on each route: the list changes with each release, and the spend of a user must use the prices that the assistant writes.
</details>

Any caller with a gateway key can set the header of the user. Here only the assistant, a backend with its own virtual key, calls the gateway, so this is acceptable for the lab.

### Step 4. Check

```bash
make check WEEK=21
```

All 10 checks pass. They test that the gateway starts with your configuration, a route with the right prices for each of the two models, the hand-written loop and the graph on Claude and on OpenAI through the gateway, the budget of a user that stops only that user (with the hand-written loop and with the graph), the fallback when the fake Claude API refuses the key with 401, and five cases of the test set that pass through the gateway without the Claude key.

This is the check of the plan: when you remove the Claude key, requests fall back to OpenAI, and the test suite passes. The second part is the suites of all phases through your gateway configuration. Run each phase with `--gateway`:

```bash
uv run --group phase1 --group phase2 --group phase3 --group phase4 --group phase5 --group phase6 \
    --env-file .env python -m pytest phases/phase-1-claude-api/checks --gateway
```

Run the same command for `phases/phase-2-retrieval/checks`, `phases/phase-3-evaluation/checks`, `phases/phase-4-agents/checks` and `phases/phase-5-guardrails/checks`. In the build of this lab, with the reference configuration, all passed: 37, 50, 41, 86 and 61 checks. The runs took about 30 seconds for Phase 1, 4 minutes for Phase 2, 9 minutes for Phase 3, 5 minutes for Phase 4 and 7 minutes for Phase 5. The start of the check gateway adds about 30 seconds to each run.

**With your own keys (optional).** To see the fallback with the real providers, put a wrong value in `ANTHROPIC_API_KEY` in `.env`, for example `sk-ant-wrong`, and run `make up`. The Fallbacks page says to "trigger an actual provider error" to test a fallback on the proxy, because the mock flags are stripped from proxy requests since v1.85.0. `docker compose restart` does not read a changed `.env` again: the Compose page of [restart](https://docs.docker.com/reference/cli/docker/compose/restart/) says that "changes to environment variables ... are not updated after restarting", and [up](https://docs.docker.com/reference/cli/docker/compose/up/) "picks up the changes by stopping and recreating the containers". Ask one question with `make ask AS=analyst Q="Which datasets cover water?"`. OpenAI must give the answer. The admin UI has a page of logs. Whether it shows the model of the fallback was not tested. Then put the right key back and run `make up` again. Cost: about $0.001.

The live check calls Claude through your gateway with the virtual key, and checks that the gateway counted the spend of the user and has your budget. It needs `GATEWAY_URL`, `GATEWAY_KEY` and `LITELLM_MASTER_KEY` in `.env`:

```bash
make check-live WEEK=21
```

Cost: less than $0.01 (see [Costs of the phase](#costs-of-the-phase)).

## Week 22: An open model on vLLM

### Step 1. Read

Huyen, chapter 9, the first half (pages 405 to 426). vLLM [Using Docker](https://docs.vllm.ai/en/latest/deployment/docker/). RunPod [Pods overview](https://docs.runpod.io/pods/overview) and [Expose ports](https://docs.runpod.io/pods/configuration/expose-ports).

The Docker page of vLLM says that the image "can be used to run OpenAI compatible server and is available on Docker Hub as vllm/vllm-openai", and that "You can add any other engine-args you need after the image tag". It shows the tags `v<version>`, `v<version>-x86_64` and `v<version>-aarch64`. The lab uses `vllm/vllm-openai:v0.33.0`, which has amd64 and arm64 builds on Docker Hub. The latest page can describe a newer version. The flags of v0.33.0 are on the page [vllm serve, v0.33.0](https://docs.vllm.ai/en/v0.33.0/cli/serve/).

### Step 2. Rent a pod and serve the open model

> From the documentation, not run in the build of this lab: each RunPod and vLLM command of this step. No pod ran and no GPU was used.

A pod is a container on a rented GPU. RunPod pulls the image that you name and runs it, so vLLM runs in the same image as on any machine with a GPU. The gateway and the rest of the system stay on your Mac. The pod's port is open to the internet, so vLLM needs a key.

1. **The pod.** Deploy a pod with one 48 GB GPU (A40 or RTX A6000). In its template, the page [Manage templates](https://docs.runpod.io/pods/templates/manage-templates) names the fields: "Container image", "Container start command" ("This overrides the default CMD instruction in your Docker container") and "HTTP ports" ("accessible via Runpod's HTTP proxy"). Set the image `vllm/vllm-openai:v0.33.0` and the HTTP port 8000. The entrypoint of the image is `vllm serve` (from the image configuration on Docker Hub), so the start command holds only the arguments of vLLM.
2. **The volume disk.** The page [Storage types](https://docs.runpod.io/pods/storage/types) says that the volume disk at `/workspace` "survives Pod stops and restarts, but is deleted when the Pod is terminated". The container disk is "erased when Pod stops" ([Pods pricing](https://docs.runpod.io/pods/pricing)). Keep the weights on the volume disk, so a restart does not download them again. Give it room for both models (about 23 GB).
3. **A key for vLLM.** Make a long random key, for example with `openssl rand -hex 32`, and keep it in `VLLM_API_KEY` of `.env`.
4. **The start command:**

```text
--model Qwen/Qwen3-8B --api-key <your key> --port 8000 --download-dir /workspace/models --enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3
```

Each flag is on the serve page of v0.33.0. `--api-key`: "If provided, the server will require one of these keys to be presented in the header." `--port`: "Default: 8000". `--download-dir`: "Directory to download and load the weights". Without `--served-model-name`, "the model name will be the same as the --model argument", so requests name the model `Qwen/Qwen3-8B`. The tool flags and the reasoning parser are from the [Qwen vLLM page](https://qwen.readthedocs.io/en/latest/deployment/vllm.html): "vllm serve Qwen/Qwen3-8B --enable-auto-tool-choice --tool-call-parser hermes" and "Since vLLM 0.9.0, one can also use vllm serve Qwen/Qwen3-8B --reasoning-parser qwen3". The [model card of Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B) shows `--enable-reasoning --reasoning-parser deepseek_r1`, the form for older versions of vLLM.

5. **The address.** The Expose ports page gives the address `https://[POD_ID]-[INTERNAL_PORT].proxy.runpod.net`. Put `https://<pod id>-8000.proxy.runpod.net/v1` in `VLLM_API_BASE` of `.env`, and run `make up`, so that the gateway gets both settings. The check gateway of the lab uses a base address that ends with `/v1`, as here.
6. **Test the key.** The first start downloads the image and the weights, so it takes some time. Then ask for the list of models without and with the key:

```bash
curl -i https://<pod id>-8000.proxy.runpod.net/v1/models
curl https://<pod id>-8000.proxy.runpod.net/v1/models -H "Authorization: Bearer $VLLM_API_KEY"
```

The first must be refused and the second must list `Qwen/Qwen3-8B`. The security page of vLLM 0.33.0 ([source](https://raw.githubusercontent.com/vllm-project/vllm/v0.33.0/docs/usage/security.md)) says that with `--api-key` the endpoints under `/v1` "require Bearer token authentication".

**What the key does not protect.** The serve page says that `--api-key` "only authenticates endpoints under the /v1, /v2, and /inference path prefixes", that other endpoints "remain unauthenticated", and "Do not rely on --api-key alone to secure vLLM". The Expose ports page says: "Your service becomes publicly accessible." So stop the pod when you do not use it, and do not keep data on it that others must not see.

**Stop the pod at the end of each session.** The page [Manage Pods](https://docs.runpod.io/pods/manage-pods) gives `runpodctl pod stop POD_ID` and `runpodctl pod delete POD_ID`, or the same buttons in the console. A stopped pod keeps `/workspace`, and its volume disk is still billed (see [Costs of the phase](#costs-of-the-phase)). The same page says that a start can fail when "the GPUs on the Pod's host machine are no longer free".

<details>
<summary>Hint: requests that end with an error 524</summary>

The Expose ports page says: "Cloudflare enforces a maximum connection time of 100 seconds". A request through the proxy address that takes longer ends with the error 524. With 32 requests at the same time and long answers, a request can wait longer than that. The load test writes such a request as an error.
</details>

### Step 3. Add the model to the gateway, run the test set, and send loads

**The route.** Add the route `qwen3-8b` to `gateway/config.yaml`. The page [vLLM](https://docs.litellm.ai/docs/providers/vllm) of LiteLLM gives the prefix `hosted_vllm/` ("add hosted_vllm/ prefix to route as OpenAI provider") and an `api_base`. Read the address and the key from the environment of the gateway. Give the route the price 0 for input and output: the prices of the open models are not in the price list of LiteLLM 1.109.1 under these names, and the GPU hour is the cost of an open model (week 25). Restart the gateway.

**The cost of a call.** `cost_usd()` in `assistant/llm.py` reads `PRICES_PER_MTOK` with the model name. The open models are not in that table. Make the cost of a model with no price 0, so that the loop does not stop with a `KeyError`.

**The test set.** `make model-testset` runs the test set of Phase 3 through the gateway on one route, with the hand-written loop. It sets `CLAUDE_MODEL` to the name of the route, turns the response cache off, and writes `evals/results/models/<route>.jsonl`. Run it on Claude and on the open model:

```bash
make model-testset ROUTE=claude-haiku-5-5
make model-testset ROUTE=qwen3-8b
```

The run on Claude costs about $0.07, up to about $0.15. The run on the open model costs no tokens. Write the quality (`code_pass`), the latency and the failures of each model in [RESULTS.md](RESULTS.md).

> Open questions with a real vLLM, not testable in the build of this lab. LiteLLM sends both `response_format` (a JSON schema) and `tools` to vLLM. Whether Qwen3 on vLLM 0.33.0 still calls a tool when a schema is set is not known. If the open model never calls a tool, look at this first. The model card says that thinking is on by default ("Default is True"), and with `--reasoning-parser qwen3` vLLM returns the thinking in `reasoning_content`. How LiteLLM maps it to the Anthropic format is not known. The Qwen vLLM page shows how to turn thinking off for one request (`"chat_template_kwargs": {"enable_thinking": false}`) and says that this "is not OpenAI API compatible".

**The load test.** One request at a time tells you the latency of one user. A server with many users answers many requests at the same time, and vLLM puts them in one batch on the GPU. So the tokens per second of the whole server go up with the load, and the latency of each request also goes up. The load test measures both at 1, 8 and 32 requests at the same time.

Write `one_request()` and `run_load()` in `scripts/loadtest.py`. Their docstrings and the docstring of the module have the rules: the questions of the test set in turn, at most the load at the same time, `requests-per-slot` times the load requests (4 by default: 4, 32 and 128 requests), the latency from the start of a request to the end of its answer, and the output tokens from the usage of each answer. A failed request goes into the result, and the function does not raise. `percentile()` is given.

```bash
make loadtest ROUTE=qwen3-8b ARGS="--gpu A40 --gpu-price 0.59 --gpu-memory-gib <GiB>"
```

Give the GPU of your pod, the price that you pay for one hour, and the GPU memory that the model uses (see the next hint). The script writes `evals/results/load/qwen3-8b.json`. Use `ARGS="--loads 1,8"` for a short first try.

<details>
<summary>Hint: the requests of a load at the same time</summary>

`asyncio.gather()` starts all requests of a load. An `asyncio.Semaphore` of the size of the load lets only that many run at the same time. Measure `seconds` once for the whole load, not as the sum of the requests. The check counts the requests that its fake vLLM had at the same time.
</details>

<details>
<summary>Hint: which GPU memory to write</summary>

The serve page says that `--gpu-memory-utilization` takes "the default value of 0.92" of the GPU. So vLLM takes about the same share of the GPU for each model, and `nvidia-smi` on the pod can show about the same total for both models. This follows from the flag, it was not measured. The part that depends on the model is the memory of its weights, which vLLM writes in its log at the start. Write that number in `--gpu-memory-gib`, and write both numbers in [RESULTS.md](RESULTS.md). The wording of the log line was not seen in the build of this lab.
</details>

### Step 4. Check

```bash
make check WEEK=22
```

All 8 checks pass. Before your work, all 8 fail. The checks test the route `qwen3-8b` in the gateway, an answer of the assistant and three cases of the test set on the open model through the gateway (vLLM gets the name `Qwen/Qwen3-8B` and the key of vLLM), the load test against a slow fake vLLM (all requests of a load at the same time, the tokens per second and the latency), and your result files: the test set on `claude-haiku-5-5` and on `qwen3-8b`, and the load test of `qwen3-8b` with the loads 1, 8 and 32 and the GPU fields.

This is the check of the plan: the test set runs on the open model through the gateway. While the pod runs, the live check sends one question to `qwen3-8b` through your gateway. It costs no tokens, only the time of the pod:

```bash
make check-live WEEK=22
```

Write the table of the load test in [RESULTS.md](RESULTS.md), then stop the pod.

## Week 23: A quantized model on the same GPU

### Step 1. Read

Huyen, chapter 9, the second half (pages 426 to 447), and chapter 7: Quantization (pages 328 to 332).

### Step 2. Serve the AWQ model on the same GPU

> From the documentation, not run in the build of this lab.

A 4-bit model keeps each weight in 4 bits in place of 16, so its weights take less GPU memory: the AWQ files of [Qwen3-8B-AWQ](https://huggingface.co/Qwen/Qwen3-8B-AWQ) are 6.1 GB, the files of Qwen3-8B are 16.38 GB (Hugging Face API). The question of this week is what that costs in quality and what it gives in speed.

The Qwen vLLM page says of the pre-quantized models: "The command serving those models are the same as the original models except for the name change". So the start command of week 22 with `--model Qwen/Qwen3-8B-AWQ` serves it. To change the command of your pod, the Manage Pods page gives "Edit Pod", and says: "Editing a running Pod resets it completely, erasing all data not stored in /workspace or a network volume." The weights in `/workspace/models` stay.

<details>
<summary>Hint: both models at the same time</summary>

You can also run the two models one after the other, which is simpler and gives each model the whole GPU. To serve both at the same time on one GPU, each vLLM process needs a smaller `--gpu-memory-utilization`, and maybe a smaller `--max-model-len`. Both flags are on the serve page. This was not tested.
</details>

### Step 3. Add the quantized model to the gateway, and measure it again

Add the route `qwen3-8b-awq`, restart the gateway, and run the same measurements as in week 22:

```bash
make model-testset ROUTE=qwen3-8b-awq
make loadtest ROUTE=qwen3-8b-awq ARGS="--gpu A40 --gpu-price 0.59 --gpu-memory-gib <GiB>"
```

Use the same loads and the same GPU type as in week 22, so the two results compare. Write how much GPU memory each model uses in [RESULTS.md](RESULTS.md).

### Step 4. Optional: the same model on your Mac with llama.cpp

> From the documentation, not run in the build of this lab.

On macOS, llama.cpp uses the Apple GPU through Metal, and Docker on a Mac cannot use the GPU, so run it directly on macOS. The [Install](https://github.com/ggml-org/llama.cpp/blob/master/docs/install.md) page has "Homebrew (Mac and Linux)":

```bash
brew install llama.cpp
llama serve -hf Qwen/Qwen3-8B-GGUF:Q4_K_M
```

The [GGUF repository](https://huggingface.co/Qwen/Qwen3-8B-GGUF) has the file `Qwen3-8B-Q4_K_M.gguf` (5.03 GB). The README of llama.cpp shows `llama serve -hf <repository>` as the command that launches the "OpenAI-compatible API server". The [README of the server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) documents its options for `llama-server`: `-hf` takes a repository with an optional quant ("default to Q4_K_M"), `--port` has the default 9931, `--host` the default 127.0.0.1, `--api-key` sets a key, and `--jinja` is on by default. The same README says of its `/v1/messages` endpoint: "Tool use requires `--jinja` flag." Run `llama serve --help` to see the options of your version.

The gateway runs in Docker and reaches your Mac at `host.docker.internal` (Compose gives the gateway this name). Whether Docker Desktop reaches a server on 127.0.0.1 of the Mac this way was not tested. `--host 0.0.0.0` with `--api-key` avoids the question. Add a route of your own name with the prefix `hosted_vllm/` and `api_base: http://host.docker.internal:9931/v1`, and run `make model-testset ROUTE=<your route>`. The notebook counts a route without a load test file as a hosted model, so its cost comes from its token prices: 0. Write its quality and latency in [RESULTS.md](RESULTS.md), and the speed that you see on your Mac.

### Step 5. Check: the first table

Build the table with the notebook. It reads each file in `evals/results/models/` and `evals/results/load/`, and writes `evals/results/model_comparison.csv`. Until you write `evals/model_costs.py` in week 25, the cost column stays empty.

```bash
make notebook NB=phases/phase-6-open-models/notebooks/model_comparison.ipynb
```

Run all cells. Then:

```bash
make check WEEK=23
```

All 6 checks pass. Before your work, 5 fail, and the check of the load test of `qwen3-8b` passes (a file of week 22). The checks test the route `qwen3-8b-awq` and an answer through it (vLLM gets `Qwen/Qwen3-8B-AWQ`), your test set results of the quantized model, the load test files of both open models with their GPU memory, and the table: a row for the hosted, the open and the quantized model, with the quality and the latency of your newest result files. This is the check of the plan: a table that compares the hosted, the open and the quantized models on the same test set. Copy the table to [RESULTS.md](RESULTS.md), then stop the pod.

## Week 24: Training data for a LoRA fine-tune

### Step 1. Read

Huyen, chapter 7: When to Finetune and Parameter-Efficient Finetuning (pages 311 to 319 and 333 to 347).

### Step 2. Choose one Arabic task where the open model fails

A fine-tune changes how the model behaves on one task. It does not add facts that the agent can look up with its tools. So choose a task where the open model fails in your test set and the hosted model does not, and where the fix is a behaviour: for example, answers in Arabic about the catalogue that name the right dataset ID.

1. Compare `evals/results/models/qwen3-8b.jsonl` with `claude-haiku-5-5.jsonl`: the cases that fail on the open model, by language and by kind.
2. Read some of the failed answers, as in the error analysis of Phase 3. Name the failure in one sentence.
3. Write the task and the count of failed cases in [RESULTS.md](RESULTS.md).

### Step 3. Make the training set

`data/train.jsonl` holds one example on each line, in the conversational format of the TRL SFT trainer. The [SFT Trainer](https://huggingface.co/docs/trl/sft_trainer) page shows the form "Conversational language modeling": `{"messages": [{"role": "user", "content": ...}, {"role": "assistant", "content": ...}]}`, and says: "When provided with a conversational dataset, the trainer will automatically apply the chat template to the dataset." The page also shows prompt-completion forms. The checks require the `messages` form.

1. **Sources.** Make the examples from your traces and labels: the questions and answers in Langfuse and in `logs/requests.jsonl`, your labels of Phase 3 (`evals/grader_labels.jsonl`, `evals/error_notes.jsonl`), and the answers of the hosted model that passed. An answer that you train on must be right: read it, or take it from a case that passed and that you checked.
2. **More questions.** A few hundred examples is more than your traces have. Ask Claude Code to draft new Arabic questions about the catalogue and their answers from `data/catalogue.json`, in the form of your examples. It uses your subscription and no API credit. Check a sample of the drafts by hand.
3. **Duplicates.** Remove each example whose question is the same as another. "The same" is after `normalise_arabic()` of your Phase 2 `assistant/ingest.py` (no diacritics, no tatweel), with the spaces collapsed, the end punctuation removed and the case ignored. Two questions that differ only in a diacritic are the same question for the model.
4. **The test cases.** Remove each example whose question holds the question of a case of `evals/testset.jsonl`, in the same form. A model that trained on a test case gets a score that you cannot trust.

Write the counts in [RESULTS.md](RESULTS.md): the examples before and after each removal.

<details>
<summary>Hint: a system prompt in the examples</summary>

A system message is allowed, as the first message only. When the assistant calls the model, it sends its own system prompt. Training with a short system prompt in Arabic, or with none, is a choice of yours. Write the choice in [RESULTS.md](RESULTS.md).
</details>

<details>
<summary>Hint: a test question inside a longer prompt</summary>

The check of the test cases looks for the normalised test question inside the normalised user text, not only for an equal text. A test question with "please" in front of it is still the test question. Do the same comparison in your script, or the check finds the cases that your script kept.
</details>

### Step 4. Check

```bash
make check WEEK=24
```

All 5 checks pass. Before your work, all 5 fail (there is no file). The checks test the format of the SFT trainer (roles `system` first only, `user` and `assistant`, the last message from the assistant, a text in each message), at least 200 examples, answers in Arabic in at least 80 % of the examples, no duplicate question, and no question of the test set in a user text, in the normalised form above. This is the check of the plan: no case in the training set is also in the test set.

## Week 25: Train and serve the adapter

### Step 1. Read

TRL [SFT Trainer](https://huggingface.co/docs/trl/sft_trainer), the part "Train adapters with PEFT". vLLM [LoRA Adapters](https://docs.vllm.ai/en/latest/features/lora/), the part "Serving LoRA Adapters".

The TRL part gives the trainer the name of a model as its first argument, `train_dataset=dataset` and `peft_config=LoraConfig()`. The vLLM part shows `--enable-lora` and `--lora-modules {name}={path}`, and says: "Requests can specify the LoRA adapter as if it were any other model via the model request parameter." The TRL page is the newest version of the docs. The lab pins TRL 1.18.0.

### Step 2. Run one LoRA fine-tune on the rented GPU

LoRA keeps the weights of the base model fixed and trains two small matrices for some layers. The rank `r` sets the size of these matrices. The adapter is a small folder that vLLM can load beside the base model.

**Your part of `train/train_lora.py`.** `lora_config()` returns a `peft.LoraConfig`, and `train()` runs the SFT trainer with the model name, the dataset, your LoRA settings and the given `training_config()`, then saves the adapter. The [LoraConfig reference](https://huggingface.co/docs/peft/package_reference/lora) of PEFT describes each setting: `r` ("Lora attention dimension (the 'rank')", default 8), `lora_alpha` ("The alpha parameter for Lora scaling", default 8), `lora_dropout` (default 0.0), `target_modules` ("The names of the modules to apply the adapter to", or `all-linear`), and `task_type` (`CAUSAL_LM` for this model). The flag `--max-lora-rank` of vLLM 0.33.0 has the default 16 (serve page), so an adapter with a larger rank needs that flag too.

**The smoke run on your Mac first.** A run on the pod costs money for each minute, also when it fails on a typo. The smoke mode trains a tiny model with the same architecture (a test model of the TRL team at a fixed revision, about 21 MB, named in `SMOKE_MODEL`) for 3 steps on the CPU, on the first 16 examples of `data/train.jsonl`:

```bash
make train-smoke
```

The command installs the packages of `train/requirements.txt` (TRL 1.18.0, PEFT 0.21.3, Transformers 5.23.0, Datasets 5.2.0, Accelerate 1.16.0) and PyTorch 2.9.1 in the cache of uv, not in the project. On the build machine (Linux), the reference smoke run took about 30 seconds with the download of the tiny model, and wrote `adapter_config.json` and `adapter_model.safetensors` (220 kB) to `train/smoke-adapter/`. The loss of a random tiny model stays near 11.9, which is normal. PyTorch 2.9.1 has a wheel for macOS on arm64 on PyPI. `make train-smoke` did not run on a Mac in the build of this lab.

<details>
<summary>Hint: the names of the target modules</summary>

The smoke model has the same module names as Qwen3-8B. Print them on your Mac: load the tiny model with `transformers.AutoModelForCausalLM.from_pretrained()` and look at `model.named_modules()`. The attention and the MLP layers of each block are the usual targets.
</details>

**The run on the pod.**

> From the documentation, not run in the build of this lab: the pod, the training on the GPU, and the transfer of files. The time and the cost of the training are not known.

1. Deploy a pod with one 48 GB GPU from the official PyTorch template of RunPod. The Pods overview page says that with this template you do not install PyTorch yourself. Which version of PyTorch the template has was not checked. TRL 1.18.0 requires PyTorch 2.6.0 or later (from its package metadata), so check it on the pod: `python -c "import torch; print(torch.__version__)"`.
2. Copy the training files to the pod. The page [Transfer files](https://docs.runpod.io/pods/storage/transfer-files) lists `runpodctl` ("Preinstalled on Pods"), SCP, rsync and cloud sync. For example, on your Mac `tar czf train.tgz train/requirements.txt train/train_lora.py data/train.jsonl` and `runpodctl send train.tgz`, then `runpodctl receive <code>` on the pod.
3. Install and train:

```bash
pip install -r train/requirements.txt
python train/train_lora.py --output /workspace/adapter
```

`training_config()` gives the settings of the run on the GPU: 2 epochs, a batch of 4, gradient accumulation 4, learning rate 2e-4, bf16 and a maximum length of 1024 tokens. Write the settings, the time and the last loss in [RESULTS.md](RESULTS.md).

<details>
<summary>Hint: the base model downloads again</summary>

The trainer downloads `Qwen/Qwen3-8B` (16.38 GB) to the cache of Hugging Face. Where that cache is on the pod was not checked. When it is not under `/workspace`, it is on the container disk, which is erased when the pod stops, so a stop between the download and the training means a second download. Keep the pod running until the adapter is saved.
</details>

### Step 3. Serve the adapter beside the base model, score it, and delete the pod

> From the documentation, not run in the build of this lab.

1. **The adapter on the vLLM pod.** The vLLM pod needs the adapter folder. Two ways from the RunPod pages: copy it with the ways of the Transfer files page, or train on a pod with a network volume and attach the same volume to the vLLM pod. The Storage types page says that you can "attach a network volume to multiple Pods" and that it is retained "even after deleting a Pod". A network volume "must be attached during Pod creation", and "replaces the volume disk at /workspace".
2. **The start command.** The command of week 22 with `--enable-lora --lora-modules arabic-catalogue=/workspace/adapter`. The name before `=` is the model name of the adapter: choose your own. Add `--max-lora-rank` when your rank is above 16. `/v1/models` then lists the adapter beside the base model.
3. **The route.** Add the route `qwen3-8b-arabic` with the prefix `hosted_vllm/` and the name of the adapter, restart the gateway, and measure it:

```bash
make model-testset ROUTE=qwen3-8b-arabic
make loadtest ROUTE=qwen3-8b-arabic ARGS="--gpu A40 --gpu-price 0.59 --gpu-memory-gib <GiB>"
```

4. **Copy the adapter to your Mac**, to `train/adapter/` (in `.gitignore`), with the ways of the Transfer files page. Then delete each pod with `runpodctl pod delete POD_ID`. The Manage Pods page says: "Terminating permanently deletes all data not stored in a network volume." Delete a network volume too when you do not need it, because it is billed until you delete it.

### Step 4. Check: the exit test

**The cost of 1,000 requests.** Write the three functions of `evals/model_costs.py`. Their docstrings have the rules:

- A hosted model costs its token prices: 1,000 times the cost of all rows divided by their model calls. A row of the test set holds several calls (`requests`), so divide by the calls, not by the rows.
- An open model costs the hourly price of its GPU, whatever the number of tokens: 1,000 times the price of one hour divided by the requests per hour.
- The requests per hour of an open model are the highest `requests_per_hour` of its loads without errors. A load with errors does not count: a GPU that fails requests does not serve them.

In the table, one request is one model call through the gateway. The load test sends short calls without tools (`max_tokens` 256), and the test set sends agent calls with tools and a long system prompt. So a hosted call and an open call in the table are not calls of the same size. Write this next to the table in [RESULTS.md](RESULTS.md). The cost of an open model also assumes a GPU that is busy for the whole hour. An idle GPU still costs its hourly price.

Run all cells of the notebook again, then:

```bash
make notebook NB=phases/phase-6-open-models/notebooks/model_comparison.ipynb
make check WEEK=25
```

All 11 checks pass. Before your work, all 11 fail. The checks test the route `qwen3-8b-arabic` and an answer through it (vLLM gets the name of the adapter, not a base name), the results of the adapter (test set and load test), the three cost functions with numbers of their own (also the `ValueError` cases), the quality and the latency of the four models in the table, and the cost of 1,000 requests of each model, computed again from your result files.

The exit test of the plan: one table compares the hosted, open, quantized and fine-tuned models on the same test set, for quality, latency and cost per 1,000 requests, and the cost of the open models comes from the GPU's hourly price and the requests per hour that you measured. Copy the table to [RESULTS.md](RESULTS.md).

Then run the checks of all phases one more time: `make check PHASE=1` to `make check PHASE=6`, and the earlier phases with `--gateway` (week 21, step 4).

## Commands

| Command | What it does |
| --- | --- |
| `make up` | Start the services of the started phases (with Phase 6 also `gateway-db` and `gateway`). Run it again after a change of `.env` |
| `docker compose restart gateway` | Read `gateway/config.yaml` again after a change |
| `make model-testset ROUTE=qwen3-8b` | Run the test set on one route of the gateway with the hand-written loop, with no response cache, and write `evals/results/models/<ROUTE>.jsonl` |
| `make loadtest ROUTE=qwen3-8b ARGS="--gpu A40 --gpu-price 0.59 --gpu-memory-gib <GiB>"` | Send 1, 8 and 32 requests at the same time to one route, and write `evals/results/load/<ROUTE>.json`. `ARGS="--loads 1,8"` for fewer loads |
| `make notebook NB=phases/phase-6-open-models/notebooks/model_comparison.ipynb` | Open the comparison notebook. Run all cells to write `evals/results/model_comparison.csv` |
| `make train-smoke` | Train the LoRA script for 3 steps on a tiny model on your CPU, and write `train/smoke-adapter/` |
| `make check WEEK=21` | Offline checks of one week |
| `make check PHASE=6` | Offline checks of the phase |
| `uv run --group phase1 ... --group phase6 --env-file .env python -m pytest phases/phase-1-claude-api/checks --gateway` | The checks of an earlier phase, with each model call through a check gateway with your configuration |
| `make check-live WEEK=21` | The live check of week 21: Claude through your gateway |
| `make check-live WEEK=22` | The live check of week 22: the open model on your pod through your gateway |

| Setting in `.env` | Default | Meaning |
| --- | --- | --- |
| `GATEWAY_PORT` | `4000` | The port of the gateway on your machine. Change `GATEWAY_URL` with it |
| `LITELLM_MASTER_KEY` | `sk-lab-gateway-master` | The key of the admin API and the password of the admin UI |
| `GATEWAY_URL` | empty in `config.py`, `http://localhost:4000` in `.env.example` | The gateway. Empty: direct calls to the providers. Compose gives the API container `http://gateway:4000` |
| `GATEWAY_KEY` | empty | The virtual key of the assistant (week 21, step 2) |
| `VLLM_API_BASE` | empty | The address of vLLM on your pod: `https://<pod id>-8000.proxy.runpod.net/v1` |
| `VLLM_API_KEY` | empty | The key of the `--api-key` flag of vLLM |
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | from earlier phases | The gateway reads them. Your code calls the gateway with `GATEWAY_KEY` |

The gateway is reachable only from your machine (127.0.0.1:4000). vLLM on the pod is reachable from the internet, with its key.
