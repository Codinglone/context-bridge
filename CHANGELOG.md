# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2026-05-20

### Fixed

- Updated PyPI project URLs to point to renamed GitHub repository (`Codinglone/mcp-context-bridge`)

## [0.1.0] - 2026-05-20

### Added

- **Core scaffold**: MCP server, router, cache layer, config manager, CLI
- **Filesystem connector**: Read files, list directories, glob search, recent changes with path traversal prevention and binary detection
- **GitHub connector**: Fetch files, list issues, get PRs, search code with caching
- **SSH connector**: Run commands, read files, list directories with connection pooling
- **Obsidian connector**: Full-text search, note reading, backlink discovery, tag extraction with folder-prefixed slugs for collision handling
- **PostgreSQL connector**: Schema introspection, indexes, foreign keys, read-only queries with SSH tunnel support
- **Docker connector**: List containers, get logs, inspect, list Compose services
- **HTTP transport**: Starlette-based ASGI server for web-based clients
- **Browser extension**: Chrome extension with @context trigger for ChatGPT, Claude, Poe
- **Configuration**: YAML-based config with env var interpolation
- **Dev tooling**: Makefile, ruff, mypy, pytest, GitHub Actions CI
- **Documentation**: README, architecture docs, connector configuration guide
