# Commands of the labs. Run `make help` for the list.

UV := uv run $(if $(wildcard .env),--env-file .env)
SET ?= quick

.PHONY: help start up down reset logs check check-live ask eval

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

start:
	@$(UV) python scripts/lab.py start $(PHASE)

up:
	@test -f assistant/api.py || (echo "Run 'make start PHASE=1' first." && exit 1)
	docker compose up -d --build --wait
	@$(UV) python scripts/migrate.py
	@$(UV) python scripts/load_catalogue.py

down:
	docker compose down

reset:
	docker compose down --volumes

logs:
	docker compose logs -f api

check:
	@$(UV) python scripts/lab.py check $(if $(WEEK),--week $(WEEK)) $(if $(PHASE),--phase $(PHASE))

check-live:
	@$(UV) python scripts/lab.py check --live $(if $(WEEK),--week $(WEEK)) $(if $(PHASE),--phase $(PHASE))

ask:
	@$(UV) python scripts/ask.py "$(Q)"

eval:
	@$(UV) python -m evals.run --set $(SET) $(ARGS)
