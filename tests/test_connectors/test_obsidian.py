"""Tests for the Obsidian connector."""

import tempfile
from pathlib import Path

import pytest

from context_bridge.connectors.obsidian import ObsidianConnector
from context_bridge.config import ObsidianConfig


@pytest.fixture
def vault_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def connector(vault_dir: Path) -> ObsidianConnector:
    cfg = ObsidianConfig(vault=vault_dir, exclude=[".git", "attachments"])
    return ObsidianConnector(cfg)


@pytest.mark.asyncio
async def test_initialize_checks_vault_exists(connector: ObsidianConnector) -> None:
    await connector.initialize()
    assert connector._initialized
    await connector.shutdown()


@pytest.mark.asyncio
async def test_initialize_fails_on_missing_vault() -> None:
    cfg = ObsidianConfig(vault=Path("/nonexistent/vault"))
    conn = ObsidianConnector(cfg)
    with pytest.raises(FileNotFoundError):
        await conn.initialize()


@pytest.mark.asyncio
async def test_get_note_by_title(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "Hello.md").write_text("# Hello\n\nThis is a test note.")
    await connector.initialize()
    note = connector._get_note("Hello")
    assert note["title"] == "Hello"
    assert "test note" in note["content"]
    await connector.shutdown()


@pytest.mark.asyncio
async def test_get_note_by_path(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "sub" / "Deep.md").parent.mkdir(parents=True)
    (vault_dir / "sub" / "Deep.md").write_text("Deep content")
    await connector.initialize()
    note = connector._get_note("sub/Deep.md")
    assert "Deep content" in note["content"]
    await connector.shutdown()


@pytest.mark.asyncio
async def test_note_not_found(connector: ObsidianConnector, vault_dir: Path) -> None:
    await connector.initialize()
    with pytest.raises(FileNotFoundError, match="Note not found"):
        connector._get_note("Missing")
    await connector.shutdown()


@pytest.mark.asyncio
async def test_frontmatter_parsed(connector: ObsidianConnector, vault_dir: Path) -> None:
    content = "---\ntags: [idea, draft]\n---\n\n# Idea\n\nSome idea here."
    (vault_dir / "Idea.md").write_text(content)
    await connector.initialize()
    note = connector._get_note("Idea")
    assert note["frontmatter"]["tags"] == ["idea", "draft"]
    await connector.shutdown()


@pytest.mark.asyncio
async def test_wikilinks_extracted(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "A.md").write_text("Links to [[B]] and [[C|alias]]")
    await connector.initialize()
    note = connector._get_note("A")
    assert note["links"] == ["B", "C"]
    await connector.shutdown()


@pytest.mark.asyncio
async def test_backlinks(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "Target.md").write_text("# Target")
    (vault_dir / "Referrer.md").write_text("See [[Target]] for details.")
    await connector.initialize()
    backlinks = connector._get_backlinks("Target")
    assert len(backlinks) == 1
    assert backlinks[0]["title"] == "Referrer"
    await connector.shutdown()


@pytest.mark.asyncio
async def test_tags_extracted(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "Tagged.md").write_text("# Tag Test\n\nThis is #important and #todo.")
    await connector.initialize()
    tags = connector._get_tags()
    assert "important" in tags
    assert "todo" in tags
    await connector.shutdown()


@pytest.mark.asyncio
async def test_search_full_text(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "Python.md").write_text("Python is great for scripting.")
    (vault_dir / "Rust.md").write_text("Rust is great for systems.")
    await connector.initialize()
    results = connector._search("python", limit=5)
    titles = [r["title"] for r in results]
    assert "Python" in titles
    assert "Rust" not in titles
    await connector.shutdown()


@pytest.mark.asyncio
async def test_excluded_files_ignored(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / ".git" / "config").parent.mkdir(parents=True)
    (vault_dir / ".git" / "config").write_text("secret")
    (vault_dir / "Public.md").write_text("visible")
    await connector.initialize()
    with pytest.raises(FileNotFoundError):
        connector._get_note("config")
    # Public note should still work
    note = connector._get_note("Public")
    assert note["title"] == "Public"
    await connector.shutdown()
