# Context Bridge

[![PyPI](https://img.shields.io/pypi/v/mcp-context-bridge)](https://pypi.org/project/mcp-context-bridge/)
[![Python](https://img.shields.io/pypi/pyversions/mcp-context-bridge)](https://pypi.org/project/mcp-context-bridge/)
[![License](https://img.shields.io/github/license/Codinglone/mcp-context-bridge)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-104%20passing-success)](https://github.com/Codinglone/mcp-context-bridge/actions)
[![Docs](https://img.shields.io/badge/docs-site-blue)](https://codinglone.github.io/mcp-context-bridge/)

A unified context layer that connects your local data — repositories, documents, remote machines, and notes — to LLM interfaces through the Model Context Protocol (MCP).

**[Installation](#installation)** • **[Configuration](#configuration)** • **[Connectors](#key-features)** • **[Contributing](CONTRIBUTING.md)**

## The Problem

Modern LLMs are powerful but context-starved. They don't know about:
- Your local codebase structure and recent changes
- Your Obsidian notes and personal knowledge base
- Your remote servers and their configurations
- Your project's documentation and dependencies
- Your PostgreSQL database schemas and query history
- Your Docker container logs and running services

You end up copy-pasting snippets or trying to explain complex contexts in a chat window.

## The Solution

Context Bridge runs locally, reads your data sources, and exposes them to any MCP-compatible LLM client (Claude Desktop, Cursor, Continue, Aether, etc.). It handles authentication, caching, chunking, and real-time updates so the LLM always has relevant context.

## Installation

### From PyPI (recommended)

```bash
pip install mcp-context-bridge
```

### From Source

```bash
git clone https://github.com/Codinglone/mcp-context-bridge.git
cd mcp-context-bridge
make install
```

## Quick Start

```bash
# Generate a starter config
context-bridge init ~/.config/context-bridge/config.yaml

# Set your GitHub token (optional, for GitHub connector)
export GITHUB_TOKEN="ghp_..."

# Start the MCP server (stdio mode for Claude Desktop)
context-bridge serve

# Or start in HTTP mode for browser extension support
context-bridge serve --transport http
```

## Why Context Bridge?

### What you do today

| Want LLM to see... | Your workflow right now |
|---|---|
| Local code | Copy-paste files, or hope the editor's index is current |
| GitHub PR + issues | Open browser, copy links, paste context |
| Obsidian notes | Export to text, paste into chat |
| PostgreSQL schema | Run `\d` in psql, copy output |
| Docker logs | `docker logs ...`, copy-paste |
| Remote server files | SSH, `cat`, copy-paste |

Each source is a separate manual step. Ten minutes later the LLM still might miss that the DB migration in PR #42 changed a column name.

### What Context Bridge enables

One MCP server exposes structured tools for every source. The LLM can query across boundaries in a single conversation turn:

```
You: "Why is my deploy failing?"

LLM calls:
  docker.get_logs("api-container")     → sees the error
  github.get_pr("my-app", 42)          → sees the migration
  pg.get_schema("users")               → confirms the column rename
  obsidian.get_note("deploy runbook")  → finds your troubleshooting notes
  fs.read_file("src/db/migrations/042_*.sql")  → reads the actual migration
```

The LLM gets the same situational awareness you have when sitting at your terminal — **without you copy-pasting anything**.

### Key advantages

- **Unified toolset** — One server, all sources. No context switching between browser, terminal, and chat.
- **Real-time sync** — File watchers push updates within seconds. No stale indexes.
- **Structured tools** — `obsidian.get_backlinks("Next Steps")` returns your link graph. `pg.get_schema("users")` returns column types + constraints. Way better than raw text dumps.
- **Privacy-first** — SSH keys, DB passwords, vault contents stay local. Only the data *you choose* goes to the LLM.
- **Pluggable** — Need a new source? Write one connector. The rest of the system doesn't change.

## Key Features

- **Filesystem Connector**: Watch local directories, respect `.gitignore`, provide file contents and tree structure
- **GitHub Connector**: Fetch repository code, issues, PRs, and discussions via API
- **SSH Connector**: Execute commands and read files on remote VMs/servers
- **Obsidian Connector**: Index your vault, follow wiki-links, search by tags and backlinks
- **PostgreSQL Connector**: Introspect schemas, list tables, view recent query history
- **Docker Connector**: Inspect running containers, stream logs, view service status
- **MCP Server**: Standard MCP protocol — works with any compatible client
- **Smart Chunking**: RAG-style retrieval so you don't burn context windows on irrelevant data
- **Real-time Sync**: File watchers push updates to connected clients automatically

## Configuration

Context Bridge reads from `~/.config/context-bridge/config.yaml`. Create it with:

```bash
context-bridge init ~/.config/context-bridge/config.yaml
```

### Minimal Example

```yaml
server:
  transport: stdio  # stdio for Claude Desktop; http for remote
  port: 8080

connectors:
  filesystem:
    - path: ~/projects
      name: projects
      exclude: [node_modules, .git, __pycache__]

  github:
    token: ${GITHUB_TOKEN}
    repos: ["owner/repo"]
    cache_ttl: 300

  obsidian:
    vault: ~/Documents/Obsidian Vault
    exclude: [.git, attachments, .trash]

  docker:
    socket: unix:///var/run/docker.sock
```

### Filesystem Connector

Watch local directories with file change detection:

```yaml
connectors:
  filesystem:
    - path: ~/projects
      name: projects
      exclude: [node_modules, .git, __pycache__, .venv, target, dist, build]
      max_file_size: 1048576  # 1 MB
```

- `path`: Directory to watch
- `name`: Alias used in tool calls
- `exclude`: Patterns to ignore
- `max_file_size`: Reject files larger than this (bytes)

### GitHub Connector

Access public and private repositories via the GitHub API:

```yaml
connectors:
  github:
    token: ${GITHUB_TOKEN}
    repos:
      - owner/repo
      - owner/another-repo
    cache_ttl: 300  # seconds
```

**Token setup:**
1. Go to `https://github.com/settings/tokens`
2. Generate a Classic token with `repo` scope
3. Export it: `export GITHUB_TOKEN="ghp_..."`

### SSH Connector

Execute commands and read files on remote servers:

```yaml
connectors:
  ssh:
    - host: prod-server
      user: deploy
      port: 22
      key: ~/.ssh/id_rsa
```

- `host`: Alias or hostname
- `user`: SSH username
- `port`: SSH port (default 22)
- `key`: Path to private key (uses SSH agent if omitted)

**Tools exposed:**
- `ssh.run_command("prod-server", "df -h")`
- `ssh.read_file("prod-server", "/var/log/syslog")`
- `ssh.list_dir("prod-server", "/etc")`

### PostgreSQL Connector

Introspect schemas and run read-only queries:

```yaml
connectors:
  postgresql:
    - name: local-dev
      connection_string: postgresql://user:pass@localhost:5432/mydb
      schemas: [public]
      query_timeout: 30
      # ssh_tunnel: bastion  # Optional: tunnel through SSH host
```

**Connection string formats:**
- URL: `postgresql://user:pass@host:5432/dbname`
- Key-value: `host=localhost port=5432 dbname=mydb user=postgres password=secret`

**SSH Tunnel for remote databases:**

If your database is behind a bastion host, add the SSH host first, then reference it:

```yaml
connectors:
  ssh:
    - host: bastion
      user: admin
      port: 22
      key: ~/.ssh/id_rsa

  postgresql:
    - name: remote-db
      connection_string: postgresql://dbuser:dbpass@db.internal:5432/app
      schemas: [public]
      query_timeout: 30
      ssh_tunnel: bastion  # References the SSH host above
```

Context Bridge will:
1. Open an SSH connection to the bastion
2. Create a local port forward
3. Rewrite the connection string to use `127.0.0.1:<random_port>`
4. Connect PostgreSQL through the tunnel

**Tools exposed:**
- `pg.list_tables("local-dev", "public")`
- `pg.get_schema("local-dev", "public", "users")`
- `pg.get_indexes("local-dev", "public", "users")`
- `pg.get_foreign_keys("local-dev", "public", "users")`
- `pg.run_query("local-dev", "SELECT * FROM users LIMIT 5")`

### Obsidian Connector

Index and query your Obsidian vault:

```yaml
connectors:
  obsidian:
    vault: ~/Documents/Obsidian Vault
    exclude: [.git, attachments, .trash]
```

**Features:**
- Full-text search across all notes
- Wiki-link graph traversal (`[[Note Title]]`)
- Tag extraction (`#tag`)
- Backlink discovery
- Frontmatter parsing
- Real-time re-indexing on file changes

**Tools exposed:**
- `obsidian.search("deploy")`
- `obsidian.get_note("Next Steps")`
- `obsidian.get_backlinks("Context Bridge")`
- `obsidian.get_tags()`

### Docker Connector

Inspect running containers:

```yaml
connectors:
  docker:
    socket: unix:///var/run/docker.sock
    include_stopped: false
    max_log_lines: 500
```

**Tools exposed:**
- `docker.list_containers()`
- `docker.get_logs("api-container", tail=100)`
- `docker.inspect("api-container")`
- `docker.list_services()`  # Docker Compose projects

## Connecting to Claude Desktop

Add to Claude Desktop's MCP config (`~/.config/claude-desktop/config.json`):

```json
{
  "mcpServers": {
    "context-bridge": {
      "command": "/home/codinglone/Documents/projects/context-bridge/.venv/bin/python",
      "args": ["-m", "context_bridge.cli", "serve"]
    }
  }
}
```

Restart Claude Desktop. The LLM will now see all your configured tools.

## Web-Based Chatbots (ChatGPT, Claude Web, etc.)

Web-based chatbots don't support MCP natively — they run in a browser sandbox with no access to your local filesystem. Context Bridge provides three integration paths:

### Option 1: Browser Extension (Recommended)

A Chrome extension is included in `extensions/chrome/`.

**Installation:**
```bash
# 1. Start Context Bridge in HTTP mode
context-bridge serve --transport http

# 2. Load the extension
# Open Chrome → chrome://extensions/ → Enable Developer Mode → Load Unpacked
# Select: extensions/chrome/
```

**Features:**
- **@context trigger button** appears on ChatGPT, Claude, and Poe pages
- Browse all connectors and tools in a searchable modal
- Execute tools with arguments
- Insert results directly into the chat input or copy to clipboard
- Extension popup for quick tool access from the toolbar

**Architecture:**
```
Browser Extension → localhost:8080 → Context Bridge → Your Data
     ↓
Injects context into ChatGPT/Claude/Poe web UI
```

### Option 2: HTTP Server + Manual Copy-Paste

For quick testing without installing the extension:

```bash
context-bridge serve --transport http
# Open http://localhost:8080 in browser
# Click tools, copy results, paste into chat
```

### Option 3: Aether Native Integration

Since you have an `aether` repo, integrate Context Bridge directly into your own AI interface:

```python
from context_bridge.server import ContextBridgeServer
from context_bridge.config import ContextBridgeConfig

config = ContextBridgeConfig.from_yaml("config.yaml")
server = ContextBridgeServer(config)
await server.router.initialize_all()

# In your chat handler:
result = await server.router.call_tool("github.get_file", {
    "repo": "Codinglone/aether",
    "path": "src/main.py"
})
# Feed result.context into your LLM prompt
```

This gives you full control — no browser sandbox, no copy-paste, no extensions.

### Option 4: Proxy Bridge (Advanced)

Run Context Bridge as a proxy between the web chatbot's API and your data:

```
User → Web Chatbot API (OpenAI/Anthropic)
         ↓
    Context Bridge intercepts the prompt
         ↓
    Injects relevant context from fs/github/obsidian/etc.
         ↓
    Forwards enriched prompt to LLM
         ↓
    Returns response to user
```

This requires building a middleware layer but gives fully automatic context injection.

## Status

All 6 connectors implemented with real-world integration tests. See `docs/DESIGN.md` and `docs/ARCHITECTURE.md` for design docs.

## License

MIT
