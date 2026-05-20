"""Tests for the filesystem connector."""

import tempfile
from pathlib import Path

import pytest

from context_bridge.connectors.filesystem import FilesystemConnector
from context_bridge.config import FilesystemSource


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def connector(temp_dir: Path) -> FilesystemConnector:
    src = FilesystemSource(path=temp_dir, exclude=[".git"])
    fs = FilesystemConnector([src])
    return fs


@pytest.mark.asyncio
async def test_read_file(connector: FilesystemConnector, temp_dir: Path) -> None:
    (temp_dir / "hello.txt").write_text("world")
    await connector.initialize()
    result = connector._read_file("hello.txt")
    assert result == "world"
    await connector.shutdown()


@pytest.mark.asyncio
async def test_read_file_absolute(connector: FilesystemConnector, temp_dir: Path) -> None:
    (temp_dir / "a" / "b.txt").parent.mkdir(parents=True)
    (temp_dir / "a" / "b.txt").write_text("nested")
    await connector.initialize()
    result = connector._read_file(str(temp_dir / "a" / "b.txt"))
    assert result == "nested"
    await connector.shutdown()


@pytest.mark.asyncio
async def test_list_dir(connector: FilesystemConnector, temp_dir: Path) -> None:
    (temp_dir / "alpha.txt").write_text("a")
    (temp_dir / "beta").mkdir()
    await connector.initialize()
    entries = connector._list_dir(".")
    names = {e["name"] for e in entries}
    assert "alpha.txt" in names
    assert "beta" in names
    await connector.shutdown()


@pytest.mark.asyncio
async def test_path_traversal_blocked(connector: FilesystemConnector, temp_dir: Path) -> None:
    await connector.initialize()
    with pytest.raises(ValueError, match="outside all configured roots"):
        connector._read_file("/etc/passwd")
    await connector.shutdown()


@pytest.mark.asyncio
async def test_excluded_path(connector: FilesystemConnector, temp_dir: Path) -> None:
    (temp_dir / ".git" / "config").parent.mkdir(parents=True)
    (temp_dir / ".git" / "config").write_text("secret")
    await connector.initialize()
    with pytest.raises(PermissionError, match="excluded"):
        connector._read_file(".git/config")
    await connector.shutdown()


@pytest.mark.asyncio
async def test_binary_file_rejected(connector: FilesystemConnector, temp_dir: Path) -> None:
    (temp_dir / "data.bin").write_bytes(b"\x00\x01\x02")
    await connector.initialize()
    with pytest.raises(ValueError, match="Binary file"):
        connector._read_file("data.bin")
    await connector.shutdown()


@pytest.mark.asyncio
async def test_max_file_size(connector: FilesystemConnector, temp_dir: Path) -> None:
    (temp_dir / "huge.txt").write_text("x" * 2_000_000)
    await connector.initialize()
    with pytest.raises(ValueError, match="too large"):
        connector._read_file("huge.txt")
    await connector.shutdown()


@pytest.mark.asyncio
async def test_find_glob(connector: FilesystemConnector, temp_dir: Path) -> None:
    (temp_dir / "a.py").write_text("1")
    (temp_dir / "b.py").write_text("2")
    (temp_dir / "c.txt").write_text("3")
    await connector.initialize()
    results = connector._find("*.py")
    assert len(results) == 2
    await connector.shutdown()


@pytest.mark.asyncio
async def test_recent_changes(connector: FilesystemConnector, temp_dir: Path) -> None:
    (temp_dir / "old.txt").write_text("old")
    (temp_dir / "new.txt").write_text("new")
    await connector.initialize()
    changes = connector._get_recent_changes(2)
    assert len(changes) == 2
    names = [Path(c["path"]).name for c in changes]
    assert "new.txt" in names
    assert "old.txt" in names
    await connector.shutdown()
