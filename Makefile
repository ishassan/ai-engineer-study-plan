# Commands of the labs. Run `make help` for the list.

# `make start PHASE=n` writes the number of the phase to .lab-phases. Each started phase adds
# its Python packages (a dependency group in pyproject.toml) and its Docker services (a
# profile in compose.yaml).
PHASES := $(shell cat .lab-phases 2>/dev/null)
export UV_GROUPS := $(foreach p,$(PHASES),--group phase$(p))
UV := uv run $(UV_GROUPS) $(if $(wildcard .env),--env-file .env)
COMPOSE := docker compose $(foreach p,$(PHASES),--profile phase$(p))
SET ?= quick

.PHONY: help start up down reset logs check check-live ask eval documents ingest embed recall notebook \
	testset failures-dataset evals snapshot restore compare lines agent-eval \
	poison unpoison attacks attack-report token model-testset loadtest train-smoke

help:
	@echo "make start PHASE=1      copy the starter files of a phase into the project"
	@echo "make up                 start Postgres and the API, apply migrations, load the catalogue"
	@echo "make down               stop the services and keep the data"
	@echo "make reset              stop the services and delete the database volume"
	@echo "make logs               follow the log of the API service"
	@echo "make check WEEK=1       run the free offline checks of a week (or PHASE=1 for a phase)"
	@echo "make check-live WEEK=1  run the checks that call the real Claude API"
	@echo "make ask Q='...'        send one question to the running API (from week 19 add AS=viewer)"
	@echo "make eval SET=quick     run the test questions (SET=all ARGS=--no-cache for the full run)"
	@echo "make documents          Phase 2: download the documents of data/documents.csv"
	@echo "make ingest             Phase 2: parse, chunk and store the documents"
	@echo "make embed              Phase 2: embed the chunks that have no vector"
	@echo "make recall             Phase 2: measure the recall (ARGS='--modes vector' for one mode)"
	@echo "make notebook NB=path   open a notebook of a lab in JupyterLab"
	@echo "make testset            Phase 3: run evals/testset.jsonl, one Langfuse trace for each case"
	@echo "make failures-dataset   Phase 3: send the failing cases of your notes to a Langfuse dataset"
	@echo "make evals              Phase 3: run the evaluation suite tests/evals (real Claude API)"
	@echo "make snapshot           Phase 3: write the documents and chunks to data/snapshot/chunks.sql.gz"
	@echo "make restore            Phase 3: replace the documents and chunks with the snapshot"
	@echo "make compare IMPL=langgraph PROVIDER=openai   Phase 4: run the test set on one loop and provider"
	@echo "make lines              Phase 4: count the lines of code of the hand-written loop and the graph"
	@echo "make agent-eval         Phase 4: score the agent on evals/agent_tasks.jsonl (result and path)"
	@echo "make poison             Phase 5: load data/poisoned/ into the documents and the catalogue"
	@echo "make unpoison           Phase 5: remove the poisoned documents and datasets again"
	@echo "make attacks LABEL=week18   Phase 5: run the attack suite (MODEL=obedient for the offline model)"
	@echo "make attack-report      Phase 5: print the two result files and compare each kind of attack"
	@echo "make token AS=viewer    Phase 5: print an access token of a test user (viewer, analyst, auditor)"
	@echo "make model-testset ROUTE=qwen3-8b   Phase 6: run the test set on one model of the gateway"
	@echo "make loadtest ROUTE=qwen3-8b        Phase 6: send 1, 8 and 32 requests at the same time to one model"
	@echo "make train-smoke        Phase 6: train the LoRA script for a few steps on a tiny model, on your CPU"

start:
	@uv run python scripts/lab.py start $(PHASE)

up:
	@test -f assistant/api.py || (echo "Run 'make start PHASE=1' first." && exit 1)
	$(COMPOSE) up -d --build --wait
	@$(UV) python scripts/migrate.py
	@$(UV) python scripts/load_catalogue.py
	@$(UV) python scripts/load_tables.py

down:
	$(COMPOSE) down

reset:
	$(COMPOSE) down
	docker volume rm --force assistant_db-data

logs:
	$(COMPOSE) logs -f api

check:
	@$(UV) python scripts/lab.py check $(if $(WEEK),--week $(WEEK)) $(if $(PHASE),--phase $(PHASE))

check-live:
	@$(UV) python scripts/lab.py check --live $(if $(WEEK),--week $(WEEK)) $(if $(PHASE),--phase $(PHASE))

ask:
	@$(UV) python scripts/ask.py "$(Q)" "$(if $(filter command line environment,$(origin AS)),$(AS))"

eval:
	@$(UV) python -m evals.run --set $(SET) $(ARGS)

documents:
	@$(UV) python scripts/fetch_documents.py

ingest:
	@$(UV) python -m assistant.ingest

embed:
	@$(UV) python -m assistant.ingest --embed

recall:
	@$(UV) python -m evals.recall $(ARGS)

# JupyterLab and pandas are not packages of the project. uv installs them in a cache for this command.
NB ?= phases/phase-2-retrieval/notebooks/recall.ipynb
notebook:
	@$(UV) --with jupyterlab --with pandas jupyter lab $(NB)

# Phase 3
testset:
	@$(UV) python -m evals.run_testset $(ARGS)

failures-dataset:
	@$(UV) python -m evals.failures_dataset

# The suite calls the real Claude API, so the fake API of the lab checks is turned off.
evals:
	@$(UV) python -m pytest tests/evals -p no:labkit.plugin $(ARGS)

# The documents and the chunks with their vectors, without the schema: the migrations make it.
SNAPSHOT := data/snapshot/chunks.sql.gz
snapshot:
	@mkdir -p $(dir $(SNAPSHOT))
	$(COMPOSE) exec -T db pg_dump -U assistant --data-only --table=documents --table=chunks | gzip -9 > $(SNAPSHOT)
	@ls -lh $(SNAPSHOT)

restore:
	@test -f $(SNAPSHOT) || (echo "$(SNAPSHOT) does not exist. Run 'make snapshot' first." && exit 1)
	(echo "TRUNCATE documents, chunks;" && gunzip -c $(SNAPSHOT)) | \
		$(COMPOSE) exec -T db psql -U assistant -d assistant -q -v ON_ERROR_STOP=1 --single-transaction
	@$(COMPOSE) exec -T db psql -U assistant -d assistant -t -c "SELECT count(*) || ' chunks' FROM chunks"

# Phase 4
IMPL ?= langgraph
PROVIDER ?= anthropic
compare:
	@$(UV) python -m evals.compare --impl $(IMPL) --provider $(PROVIDER) $(ARGS)

lines:
	@$(UV) python scripts/count_lines.py

agent-eval:
	@$(UV) python -m evals.agent_eval $(ARGS)

# Phase 5
poison:
	@$(UV) python scripts/poisoned.py load

unpoison:
	@$(UV) python scripts/poisoned.py remove

# MODEL=claude (the default) calls the real Claude API, so the fake API of the lab checks is
# turned off. MODEL=obedient uses the obedient model of labkit on the fake API: free and offline.
MODEL ?= claude
LABEL ?= run
attacks:
	@$(UV) python -m pytest tests/attacks $(if $(filter claude,$(MODEL)),-p no:labkit.plugin) \
		--attack-model $(MODEL) --attack-label $(LABEL) --attack-results evals/results/attacks-$(LABEL).json $(ARGS)

attack-report:
	@$(UV) python -m evals.attacks $(ARGS)

# make has a built-in AS (the assembler), so ?= does not set it. Use viewer when AS is not given.
ifeq ($(origin AS),default)
AS := viewer
endif
token:
	@$(UV) python scripts/get_token.py $(AS) $(ARGS)

# Phase 6
# The hand-written loop sends CLAUDE_MODEL as its model name. Through the gateway, it can be the
# name of any route, also an open model on vLLM. Each run sends each request again (--no-cache).
# ROUTE, not MODEL: MODEL is the model of the attack suite (Phase 5).
model-testset:
	@test -n "$(ROUTE)" || (echo "Give the name of a route of the gateway: make model-testset ROUTE=qwen3-8b" && exit 1)
	@CLAUDE_MODEL=$(ROUTE) $(UV) python -m evals.run_testset --no-cache --out evals/results/models/$(ROUTE).jsonl $(ARGS)

loadtest:
	@test -n "$(ROUTE)" || (echo "Give the name of a route of the gateway: make loadtest ROUTE=qwen3-8b" && exit 1)
	@$(UV) python scripts/loadtest.py --model $(ROUTE) $(ARGS)

# The training script needs PyTorch, TRL and PEFT. They are not packages of the project: uv installs
# the versions of train/requirements.txt (and PyTorch for your CPU) in a cache for this command.
TORCH_VERSION ?= 2.9.1
train-smoke:
	@uv run --no-project --python 3.12 --with-requirements train/requirements.txt --with "torch==$(TORCH_VERSION)" \
		python train/train_lora.py --smoke $(ARGS)
