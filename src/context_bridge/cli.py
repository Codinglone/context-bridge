"""Typer-based CLI for Context Bridge."""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from context_bridge.config import DEFAULT_CONFIG_PATH, ContextBridgeConfig
from context_bridge.server import ContextBridgeServer

app = typer.Typer(help="Context Bridge — Unified context layer for LLMs via MCP")
console = Console()


@app.command()
def serve(
    config: Path = typer.Option(
        DEFAULT_CONFIG_PATH,
        "--config",
        "-c",
        help="Path to configuration YAML file",
    ),
    transport: str = typer.Option("stdio", "--transport", "-t", help="Transport: stdio or http"),
) -> None:
    """Start the MCP server."""
    import asyncio

    cfg = _load_config(config, transport)
    server = ContextBridgeServer(cfg)

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Shutting down...[/bold yellow]")
        asyncio.run(server.stop())


@app.command()
def health(
    config: Path = typer.Option(
        DEFAULT_CONFIG_PATH,
        "--config",
        "-c",
        help="Path to configuration YAML file",
    ),
) -> None:
    """Check connector health."""
    cfg = _load_config(config)
    server = ContextBridgeServer(cfg)

    table = Table(title="Connector Health")
    table.add_column("Connector", style="cyan")
    table.add_column("Status", style="green")

    # We don't actually initialize connectors here, so health is minimal.
    # In a future enhancement we could initialize and check real health.
    for name, status in server.router.health().items():
        table.add_row(name, str(status))

    if not server.router._connectors:
        console.print("[yellow]No connectors registered.[/yellow]")
    else:
        console.print(table)


@app.command()
def init(
    path: Path = typer.Argument(
        DEFAULT_CONFIG_PATH,
        help="Where to write the initial config file",
    ),
) -> None:
    """Generate a starter configuration file."""
    if path.exists():
        overwrite = typer.confirm(f"{path} already exists. Overwrite?")
        if not overwrite:
            raise typer.Exit(0)

    starter = """server:
  transport: stdio
  port: 8080
  host: 127.0.0.1

connectors:
  filesystem:
    - path: ~/projects
      name: projects
      exclude: [node_modules, .git, __pycache__]
      max_file_size: 1048576

  github:
    token: ${GITHUB_TOKEN}
    repos: []
    cache_ttl: 300

  ssh: []

  obsidian:
    vault: ~/Documents/Obsidian Vault
    exclude: [.git, attachments, .trash]

  postgresql: []

  docker:
    socket: unix:///var/run/docker.sock
    include_stopped: false
    max_log_lines: 500
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(starter, encoding="utf-8")
    console.print(f"[green]Created starter config at {path}[/green]")


def _load_config(path: Path, transport_override: str | None = None) -> ContextBridgeConfig:
    """Load config from file or return defaults."""
    if path.exists():
        cfg = ContextBridgeConfig.from_yaml(path)
    else:
        console.print(f"[yellow]Config not found at {path}, using defaults.[/yellow]")
        cfg = ContextBridgeConfig()

    if transport_override:
        cfg.server.transport = transport_override

    return cfg


def main() -> None:
    app()
