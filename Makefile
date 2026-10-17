.DEFAULT_GOAL := help
SHELL := /bin/sh

PYTHON ?= python3
VENV ?= .venv
BIND ?= 127.0.0.1
PORT ?= 8000

# Read configuration from the environment; never embed or print its value.
export INGRESS_URL USERNAME PASSWORD

.PHONY: help setup run test demo check-setup

help:
	@printf '%s\n' \
	  'Video search — quick start' \
	  '' \
	  '  1. Load the trusted workshop config in Bash (see below).' \
	  '  2. make setup                      Install Python dependencies in .venv' \
	  '  3. make run                        Open http://127.0.0.1:8000' \
	  '' \
	  'In Bash, replace YOUR_TEAM.config with your existing assigned team file:' \
	  '  set +x' \
	  '  set -a' \
	  '  source /config/YOUR_TEAM.config' \
	  '  set +a' \
	  'Keep INGRESS_URL, USERNAME and PASSWORD in that same shell; do not print them.' \
	  'Search immediately. VSS authentication stays on the server. Ctrl+C stops it.' \
	  '' \
	  'Targets:' \
	  '  make help                          Show these instructions (also: make)' \
	  '  make setup PYTHON=python3.12        Choose Python when creating the venv' \
	  '  make run PORT=8080                 Use another port' \
	  '  make test                          Run Python and JavaScript tests' \
	  '  make demo                          Synthetic data at 127.0.0.1:8001' \
	  '' \
	  'Requirements: Python 3.10+ for the service; Python 3.11+ and Node 20+ for tests.' \
	  'Optional: VENV=.venv, BIND=127.0.0.1 and PORT=8000 (BIND/PORT affect run only).' \
	  'The demo needs no sign-in and never connects to VSS.' \
	  'Full setup and VM instructions: docs/spec.md'

$(VENV)/bin/python:
	@"$(PYTHON)" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else "Python 3.10+ is required. Try: make setup PYTHON=python3.12")'
	@"$(PYTHON)" -m venv "$(VENV)"

setup: $(VENV)/bin/python
	@"$(VENV)/bin/python" -m pip install -r requirements.txt

check-setup:
	@test -x "$(VENV)/bin/python" || { printf '%s\n' 'Run make setup first.'; exit 1; }
	@"$(VENV)/bin/python" -c 'import fastapi, httpx, uvicorn' >/dev/null 2>&1 || { printf '%s\n' 'Dependencies are missing. Run make setup.'; exit 1; }

run: check-setup
	@test -n "$$INGRESS_URL" || { printf '%s\n' 'INGRESS_URL is missing. Load the trusted workshop config in Bash. See make help.'; exit 1; }
	@test -n "$$USERNAME" || { printf '%s\n' 'USERNAME is missing. Load the trusted workshop config in Bash. See make help.'; exit 1; }
	@test -n "$$PASSWORD" || { printf '%s\n' 'PASSWORD is missing. Load the trusted workshop config in Bash. See make help.'; exit 1; }
	@"$(VENV)/bin/python" scripts/serve.py --bind "$(BIND)" --port "$(PORT)"

test: check-setup
	@"$(VENV)/bin/python" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "The Python tests require Python 3.11+.")'
	@node --test tests/*.test.mjs
	@"$(VENV)/bin/python" -m unittest discover -s tests -p 'test_*.py'

demo:
	@"$(PYTHON)" tests/fixture_server.py
