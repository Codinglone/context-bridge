.PHONY: install test lint format type-check clean build upload check serve docs

PYTHON := python3
VENV := .venv
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff
MYPY := $(VENV)/bin/mypy
TWINE := $(VENV)/bin/twine

# Development setup
install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -e ".[dev]"

# Testing
test:
	$(PYTEST) tests/ -v

test-fast:
	$(PYTEST) tests/ -q

test-cov:
	$(PYTEST) tests/ --cov=context_bridge --cov-report=html --cov-report=term

# Linting and formatting
lint:
	$(RUFF) check src/ --ignore B008

format:
	$(RUFF) check src/ --ignore B008 --fix
	$(RUFF) format src/

type-check:
	$(MYPY) src/ --ignore-missing-imports

check: lint type-check test
	@echo "All checks passed!"

# Cleaning
clean:
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .mypy_cache/ htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

# Building and distribution
build: clean
	$(PYTHON) -m build

upload-test: build
	$(TWINE) upload --repository testpypi dist/*

upload: build
	$(TWINE) upload dist/*

# Running
serve:
	$(VENV)/bin/context-bridge serve --config ~/.config/context-bridge/config.yaml

serve-http:
	$(VENV)/bin/context-bridge serve --transport http

# Documentation
docs:
	@echo "See README.md and docs/ for documentation"

# Release helpers
version := $(shell $(PYTHON) -c "import context_bridge; print(context_bridge.__version__)")

tag:
	git tag -a v$(version) -m "Release $(version)"
	git push origin v$(version)

# Help
help:
	@echo "Available targets:"
	@echo "  install      - Create venv and install in editable mode"
	@echo "  test         - Run test suite"
	@echo "  lint         - Run ruff linter"
	@echo "  format       - Auto-fix linting and format code"
	@echo "  type-check   - Run mypy type checker"
	@echo "  check        - Run lint + type-check + test"
	@echo "  clean        - Remove build artifacts"
	@echo "  build        - Build wheel and sdist"
	@echo "  upload-test  - Upload to TestPyPI"
	@echo "  upload       - Upload to PyPI"
	@echo "  serve        - Start MCP server (stdio)"
	@echo "  serve-http   - Start MCP server (HTTP)"
	@echo "  tag          - Create git tag for release"
