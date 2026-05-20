---
layout: default
title: Home
---

# Context Bridge

A unified context layer that connects your local data — repositories, documents, remote machines, and notes — to LLM interfaces through the Model Context Protocol (MCP).

[View on GitHub](https://github.com/Codinglone/mcp-context-bridge){: .btn .btn-purple }
[Install from PyPI](https://pypi.org/project/mcp-context-bridge/){: .btn .btn-blue }

---

## Install

```bash
pip install mcp-context-bridge
```

## What It Does

Modern LLMs are powerful but context-starved. They don't know about your local codebase, recent GitHub issues, Obsidian notes, or database schema. Context Bridge bridges that gap with a single MCP server that exposes everything.

## Key Features

- **Filesystem** — Read files, list directories, glob search, recent changes
- **GitHub** — Fetch files, list issues, get PRs, search code
- **SSH** — Run commands, read files, list directories with connection pooling
- **Obsidian** — Full-text search, note reading, backlink discovery, tag extraction
- **PostgreSQL** — Schema introspection, indexes, foreign keys, read-only queries
- **Docker** — List containers, get logs, inspect, list Compose services

## Architecture

Context Bridge is built as an MCP server with a pluggable connector system. Each connector implements a standard interface and exposes domain-specific tools to the LLM.

- [Architecture Overview](ARCHITECTURE.md)
- [Design Decisions](DESIGN.md)

## License

MIT — see [LICENSE](https://github.com/Codinglone/mcp-context-bridge/blob/master/LICENSE) on GitHub.
