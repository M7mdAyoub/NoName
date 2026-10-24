# Targets are thin wrappers over Python scripts so they behave the same on every OS (decision D-01).
# `RUN` runs a command inside the project environment. With an activated venv: `make RUN= check`.
RUN ?= uv run

.PHONY: dev test lint migrate check

dev:      ## migrate, then run API (reload) on :8000 and the job worker; Ctrl+C stops both
	$(RUN) python scripts/dev.py

test:     ## pytest only
	$(RUN) python scripts/check.py test

lint:     ## ruff (lint + format check) and mypy
	$(RUN) python scripts/check.py lint

migrate:  ## apply pending migrations to DATABASE_PATH
	$(RUN) python scripts/migrate.py

check:    ## lint + types + tests + migration / route / hard-delete checks; must be green before a phase is done
	$(RUN) python scripts/check.py
