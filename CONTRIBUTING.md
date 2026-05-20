# Contributing to Context Bridge

Thank you for your interest in contributing! This document covers how to set up your development environment and submit changes.

## Development Setup

### Prerequisites

- Python 3.11+
- Git
- Make

### Install

```bash
git clone https://github.com/Codinglone/mcp-context-bridge.git
cd mcp-context-bridge
make install
```

This creates a virtual environment (`.venv/`) and installs the package in editable mode with all dev dependencies.

### Run Tests

```bash
make test          # Full test suite with verbose output
make test-fast     # Quick run
make test-cov      # With coverage report
```

### Lint and Format

```bash
make lint          # Check for issues
make format        # Auto-fix and format
make type-check    # Run mypy
make check         # Run lint + type-check + test (do this before committing)
```

## Project Structure

```
src/context_bridge/        # Main package
├── server.py               # MCP server entrypoint
├── router.py               # Tool dispatch
├── config.py               # YAML config loading
├── cache.py                # TTL cache
├── cli.py                  # Typer CLI
├── transport_http.py       # HTTP ASGI app
└── connectors/             # Data source connectors
    ├── base.py             # ABC
    ├── filesystem.py
    ├── github.py
    ├── ssh.py
    ├── obsidian.py
    ├── postgresql.py
    └── docker.py

tests/                      # Test suite
├── test_connectors/        # Connector tests (mocked + integration)
└── test_core/              # Core module tests

extensions/                 # Browser extensions
└── chrome/                 # Chrome extension
```

## Writing a New Connector

1. Create `src/context_bridge/connectors/my_connector.py`
2. Inherit from `BaseConnector`
3. Implement `initialize()`, `shutdown()`, `get_tools()`, `call_tool()`
4. Add config model to `src/context_bridge/config.py`
5. Register in `src/context_bridge/server.py::_register_connectors()`
6. Write tests in `tests/test_connectors/test_my_connector.py`
7. Update `README.md` with config example

See existing connectors for patterns.

## Submitting Changes

1. **Check** before committing: `make check`
2. **Write tests** for new features
3. **Update docs** if behavior changes
4. **Follow existing style** — ruff enforces this automatically

## Code Style

- **Line length**: 100 characters
- **Python version**: 3.11+ (use modern syntax)
- **Types**: Add type hints for public APIs
- **Docstrings**: Google-style or concise one-liners
- **Imports**: ruff sorts these automatically

## Release Process

Maintainers only:

```bash
# 1. Update CHANGELOG.md
# 2. Bump version in pyproject.toml and src/context_bridge/__init__.py
# 3. Tag and push
make tag

# 4. Build and upload
make build
make upload-test   # TestPyPI first
make upload        # PyPI production
```

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
