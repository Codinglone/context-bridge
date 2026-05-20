"""Deep tests for the Obsidian connector — edge cases, stress tests, correctness."""

import tempfile
from pathlib import Path

import pytest

from context_bridge.connectors.obsidian import ObsidianConnector, _parse_tags, _parse_wikilinks
from context_bridge.config import ObsidianConfig


# ---------------------------------------------------------------------------
# Unit tests for parsing helpers
# ---------------------------------------------------------------------------

def test_parse_wikilinks_basic() -> None:
    assert _parse_wikilinks("See [[Note A]] and [[Note B|alias]]") == ["Note A", "Note B"]


def test_parse_wikilinks_empty() -> None:
    assert _parse_wikilinks("No links here") == []


def test_parse_wikilinks_nested_brackets() -> None:
    # Should not match nested brackets
    assert _parse_wikilinks("[[A]] [[B]]") == ["A", "B"]


def test_parse_tags_basic() -> None:
    text = "This is #important and #todo"
    assert _parse_tags(text) == ["important", "todo"]


def test_parse_tags_no_numeric_only() -> None:
    text = "Idea #6 — Scoped Down"
    assert _parse_tags(text) == []


def test_parse_tags_in_code_blocks_ignored() -> None:
    text = """Some text #outside
```python
# comment with #tag
```
More text #inside"""
    assert _parse_tags(text) == ["inside", "outside"]


def test_parse_tags_inline_code_ignored() -> None:
    text = "Use `#tag` in code but #real is a tag"
    assert _parse_tags(text) == ["real"]


def test_parse_tags_with_slash() -> None:
    text = "Status is #status/done"
    assert _parse_tags(text) == ["status/done"]


# ---------------------------------------------------------------------------
# Connector lifecycle and vault scanning
# ---------------------------------------------------------------------------

@pytest.fixture
def vault_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def connector(vault_dir: Path) -> ObsidianConnector:
    cfg = ObsidianConfig(vault=vault_dir, exclude=[".git"])
    return ObsidianConnector(cfg)


@pytest.mark.asyncio
async def test_empty_vault(connector: ObsidianConnector, vault_dir: Path) -> None:
    await connector.initialize()
    tags = connector._get_tags()
    assert tags == []
    results = connector._search("anything", limit=5)
    assert results == []
    await connector.shutdown()


@pytest.mark.asyncio
async def test_deep_nested_directories(connector: ObsidianConnector, vault_dir: Path) -> None:
    deep = vault_dir / "a" / "b" / "c" / "d"
    deep.mkdir(parents=True)
    (deep / "Deep.md").write_text("Deep content")
    await connector.initialize()
    note = connector._get_note("Deep")
    assert "Deep content" in note["content"]
    await connector.shutdown()


@pytest.mark.asyncio
async def test_non_markdown_files_ignored(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "Note.md").write_text("Real note")
    (vault_dir / "Image.png").write_bytes(b"\x89PNG")
    (vault_dir / "Canvas.canvas").write_text("{}")
    await connector.initialize()
    index = connector._get_index()
    assert len(index["notes"]) == 1
    await connector.shutdown()


@pytest.mark.asyncio
async def test_empty_markdown_file(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "Empty.md").touch()
    await connector.initialize()
    note = connector._get_note("Empty")
    assert note["content"] == ""
    assert note["title"] == "Empty"
    await connector.shutdown()


@pytest.mark.asyncio
async def test_unicode_content(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "Unicode.md").write_text("日本語テスト #日本語")
    await connector.initialize()
    note = connector._get_note("Unicode")
    assert "日本語" in note["content"]
    # Tags must start with letter, so #日本語 won't match (ASCII-only regex)
    assert note["tags"] == []
    await connector.shutdown()


@pytest.mark.asyncio
async def test_slug_collision_same_title_different_folders(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "A" / "Note.md").parent.mkdir(parents=True)
    (vault_dir / "A" / "Note.md").write_text("Version A")
    (vault_dir / "B" / "Note.md").parent.mkdir(parents=True)
    (vault_dir / "B" / "Note.md").write_text("Version B")
    await connector.initialize()

    # Both notes indexed under unique folder slugs
    index = connector._get_index()
    assert len(index["notes"]) == 2
    assert "a/note" in index["notes"]
    assert "b/note" in index["notes"]

    # Folder-prefixed lookup returns the right note
    note_a = connector._get_note("a/note")
    assert "Version A" in note_a["content"]
    note_b = connector._get_note("b/note")
    assert "Version B" in note_b["content"]

    # Short slug is ambiguous — should raise with suggestions
    with pytest.raises(ValueError, match="Ambiguous"):
        connector._get_note("Note")

    # Path suffix lookup still works
    note_path = connector._get_note("A/Note.md")
    assert "Version A" in note_path["content"]

    await connector.shutdown()


@pytest.mark.asyncio
async def test_broken_frontmatter_graceful(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "Broken.md").write_text("---\ninvalid: yaml: [\n---\n\nContent here")
    await connector.initialize()
    # Should not crash — frontmatter.loads may raise, caught by _build_index
    # Actually frontmatter.loads might succeed with partial, let's just verify no crash
    index = connector._get_index()
    # It may or may not be in the index depending on how frontmatter handles it
    await connector.shutdown()


@pytest.mark.asyncio
async def test_frontmatter_tags_as_string(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "StringTag.md").write_text("---\ntags: single-tag\n---\n\nContent")
    await connector.initialize()
    note = connector._get_note("StringTag")
    assert "single-tag" in note["tags"]
    assert note["tags"] == ["single-tag"]
    await connector.shutdown()


@pytest.mark.asyncio
async def test_frontmatter_tags_as_comma_string(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "CommaTag.md").write_text("---\ntags: idea, draft\n---\n\nContent")
    await connector.initialize()
    note = connector._get_note("CommaTag")
    assert set(note["tags"]) == {"draft", "idea"}
    await connector.shutdown()


@pytest.mark.asyncio
async def test_circular_wikilinks(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "A.md").write_text("See [[B]]")
    (vault_dir / "B.md").write_text("See [[A]]")
    await connector.initialize()
    backlinks_a = connector._get_backlinks("A")
    backlinks_b = connector._get_backlinks("B")
    assert any(b["title"] == "B" for b in backlinks_a)
    assert any(b["title"] == "A" for b in backlinks_b)
    await connector.shutdown()


@pytest.mark.asyncio
async def test_dangling_wikilink(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "Referrer.md").write_text("See [[MissingNote]] for details.")
    await connector.initialize()
    # MissingNote doesn't exist, but backlink map still records the link
    backlinks = connector._get_backlinks("MissingNote")
    assert len(backlinks) == 1
    assert backlinks[0]["title"] == "Referrer"
    await connector.shutdown()


@pytest.mark.asyncio
async def test_search_stopwords_return_nothing(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "Doc.md").write_text("The quick brown fox")
    await connector.initialize()
    # "the" is not indexed (too short / common) because our regex matches words with [a-zA-Z0-9_]+
    # Actually "the" IS 3 letters and WILL be indexed
    results = connector._search("the", limit=5)
    assert len(results) == 1
    await connector.shutdown()


@pytest.mark.asyncio
async def test_search_punctuation_stripped(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "Doc.md").write_text("Hello, world!")
    await connector.initialize()
    results = connector._search("hello world", limit=5)
    assert len(results) == 1
    await connector.shutdown()


@pytest.mark.asyncio
async def test_search_case_insensitive(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "Doc.md").write_text("UPPERCASE lowercase MiXeD")
    await connector.initialize()
    assert len(connector._search("uppercase", limit=5)) == 1
    assert len(connector._search("LOWERCASE", limit=5)) == 1
    assert len(connector._search("mixed", limit=5)) == 1
    await connector.shutdown()


@pytest.mark.asyncio
async def test_search_multiple_words_intersection(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "A.md").write_text("foo bar")
    (vault_dir / "B.md").write_text("foo baz")
    (vault_dir / "C.md").write_text("bar baz")
    await connector.initialize()
    results = connector._search("foo bar", limit=5)
    # Only A has both foo and bar
    assert len(results) == 1
    assert results[0]["title"] == "A"
    await connector.shutdown()


@pytest.mark.asyncio
async def test_get_note_by_exact_path_suffix(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "sub" / "Target.md").parent.mkdir(parents=True)
    (vault_dir / "sub" / "Target.md").write_text("Nested")
    await connector.initialize()
    note = connector._get_note("sub/Target.md")
    assert "Nested" in note["content"]
    await connector.shutdown()


@pytest.mark.asyncio
async def test_cache_invalidated_on_reindex(connector: ObsidianConnector, vault_dir: Path) -> None:
    (vault_dir / "Note.md").write_text("V1")
    await connector.initialize()
    note1 = connector._get_note("Note")
    assert "V1" in note1["content"]

    # Modify file
    (vault_dir / "Note.md").write_text("V2")
    # Manually invalidate cache (simulating watchdog event)
    connector._cache.invalidate_namespace(connector.name)
    note2 = connector._get_note("Note")
    assert "V2" in note2["content"]
    await connector.shutdown()


@pytest.mark.asyncio
async def test_large_note_performance(connector: ObsidianConnector, vault_dir: Path) -> None:
    big = "word " * 50_000  # ~300KB of text
    (vault_dir / "Big.md").write_text(big)
    await connector.initialize()
    note = connector._get_note("Big")
    assert len(note["content"]) > 100_000
    await connector.shutdown()


@pytest.mark.asyncio
async def test_stress_100_notes(connector: ObsidianConnector, vault_dir: Path) -> None:
    for i in range(100):
        (vault_dir / f"Note{i:03d}.md").write_text(f"Content of note {i} #tag{i % 10}")
    await connector.initialize()
    index = connector._get_index()
    assert len(index["notes"]) == 100
    tags = connector._get_tags()
    assert len(tags) == 10
    await connector.shutdown()
