.DEFAULT_GOAL := help
PYTHON ?= python3
VENV ?= .venv
BIND ?= 127.0.0.1
PORT ?= 8000
.PHONY: help setup run test demo archive-init archive-run archive-worker
help:
	@printf '%s\n' 'Setup: docs/development.md | Docs: docs/README.md' 'make setup | run | test | demo' 'make archive-init | archive-run | archive-worker'
setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install -e './apps/ranger-duck/backend[test]' -e './services/archive[models,test]'
run:
	$(VENV)/bin/python scripts/serve.py --bind $(BIND) --port $(PORT)
test:
	node --test tests/*.test.mjs
	$(VENV)/bin/python -m pytest tests apps/ranger-duck/backend/tests services/archive/tests -q
archive-init:
	$(VENV)/bin/video-archive init
archive-run:
	$(VENV)/bin/video-archive serve
archive-worker:
	$(VENV)/bin/video-archive worker
demo:
	$(PYTHON) tests/fixture_server.py
