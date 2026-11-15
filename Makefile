# Commands of the labs. Run `make help` for the list.

# `make start PHASE=n` writes the number of the phase to .lab-phases. Each started phase adds
# its Python packages (a dependency group in pyproject.toml) and its Docker services (a
# profile in compose.yaml).
PHASES := $(shell cat .lab-phases 2>/dev/null)
export UV_GROUPS := $(foreach p,$(PHASES),--group phase$(p))
UV := uv run $(UV_GROUPS) $(if $(wildcard .env),--env-file .env)
COMPOSE := docker compose $(foreach p,$(PHASES),--profile phase$(p))
SET ?= quick

.PHONY: help start up down reset logs check check-live ask eval documents ingest embed recall notebook

help:
	@echo "make start PHASE=1      copy the starter files of a phase into the project"
	@echo "make up                 start Postgres and the API, apply migrations, load the catalogue"
	@echo "make down               stop the services and keep the data"
	@echo "make reset              stop the services and delete the database volume"
	@echo "make logs               follow the log of the API service"
	@echo "make check WEEK=1       run the free offline checks of a week (or PHASE=1 for a phase)"
	@echo "make check-live WEEK=1  run the checks that call the real Claude API"
	@echo "make ask Q='...'        send one question to the running API"
	@echo "make eval SET=quick     run the test questions (SET=all ARGS=--no-cache for the full run)"
	@echo "make documents          Phase 2: download the documents of data/documents.csv"
	@echo "make ingest             Phase 2: parse, chunk and store the documents"
	@echo "make embed              Phase 2: embed the chunks that have no vector"
	@echo "make recall             Phase 2: measure the recall (ARGS='--modes vector' for one mode)"
	@echo "make notebook NB=path   open a notebook of a lab in JupyterLab"

start:
	@uv run python scripts/lab.py start $(PHASE)

up:
	@test -f assistant/api.py || (echo "Run 'make start PHASE=1' first." && exit 1)
	$(COMPOSE) up -d --build --wait
	@$(UV) python scripts/migrate.py
	@$(UV) python scripts/load_catalogue.py

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
	@$(UV) python scripts/ask.py "$(Q)"

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
