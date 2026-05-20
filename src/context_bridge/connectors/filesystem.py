"""Filesystem connector — read local files and directories."""

import fnmatch
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from context_bridge.cache import CacheManager
from context_bridge.config import FilesystemSource
from context_bridge.connectors.base import BaseConnector


class _ChangeHandler(FileSystemEventHandler):
    """Watchdog handler that invalidates the cache on file changes."""

    def __init__(self, cache: CacheManager, namespace: str) -> None:
        self.cache = cache
        self.namespace = namespace

    def on_any_event(self, event: Any) -> None:
        # Invalidate the entire filesystem namespace on any change.
        # In production this could be finer-grained (per-path).
        self.cache.invalidate_namespace(self.namespace)


class FilesystemConnector(BaseConnector):
    """Read local files and directories with safety limits."""

    name = "fs"
    description = "Local filesystem access"

    def __init__(self, config: list[FilesystemSource]) -> None:
        super().__init__(config)
        self._sources: list[FilesystemSource] = config
        self._roots: list[Path] = []
        self._observer: Observer | None = None
        self._cache = CacheManager()

    async def initialize(self) -> None:
        """Resolve roots and start file watchers."""
        self._roots = [src.path.expanduser().resolve() for src in self._sources]

        self._observer = Observer()
        handler = _ChangeHandler(self._cache, self.name)
        for root in self._roots:
            if root.exists() and root.is_dir():
                self._observer.schedule(handler, str(root), recursive=True)
        self._observer.start()
        self._initialized = True

    async def shutdown(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        self._initialized = False

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "fs.read_file",
                "description": "Read the contents of a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative or absolute file path"}
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "fs.list_dir",
                "description": "List files in a directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path"}
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "fs.find",
                "description": "Search for files matching a glob pattern",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Glob pattern (e.g. *.py)"}
                    },
                    "required": ["pattern"],
                },
            },
            {
                "name": "fs.get_recent_changes",
                "description": "Return the last N modified files",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "n": {"type": "integer", "default": 10, "description": "Number of files"}
                    },
                },
            },
        ]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if tool_name == "read_file":
            return self._read_file(arguments["path"])
        if tool_name == "list_dir":
            return self._list_dir(arguments["path"])
        if tool_name == "find":
            return self._find(arguments["pattern"])
        if tool_name == "get_recent_changes":
            return self._get_recent_changes(arguments.get("n", 10))
        raise ValueError(f"Unknown tool: {tool_name}")

    # --- internal helpers ---

    def _resolve_path(self, raw: str) -> Path:
        """Resolve a user-supplied path against configured roots.

        Raises ValueError if the resolved path escapes any configured root.
        """
        path = Path(raw).expanduser()
        resolved = path.resolve() if path.is_absolute() else (self._roots[0] / path).resolve()

        for root in self._roots:
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue
        raise ValueError(f"Path '{raw}' is outside all configured roots")

    def _is_excluded(self, path: Path) -> bool:
        """Check if a path matches any exclude pattern from any source."""
        rel = str(path)
        for src in self._sources:
            for pattern in src.exclude:
                if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(path.name, pattern):
                    return True
                # Also match against relative path within root
                try:
                    rel_to_root = path.relative_to(src.path.expanduser().resolve())
                    parts = rel_to_root.parts
                    for part in parts:
                        if fnmatch.fnmatch(part, pattern):
                            return True
                except ValueError:
                    pass
        return False

    def _is_binary(self, path: Path) -> bool:
        """Heuristic: check for null bytes in the first 8KB."""
        try:
            with open(path, "rb") as f:
                chunk = f.read(8192)
            return b"\x00" in chunk
        except OSError:
            return True

    def _max_size_for(self, path: Path) -> int:
        for src in self._sources:
            root = src.path.expanduser().resolve()
            try:
                path.relative_to(root)
                return src.max_file_size
            except ValueError:
                continue
        return 1_048_576  # 1 MB fallback

    def _read_file(self, raw_path: str) -> str:
        path = self._resolve_path(raw_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {raw_path}")
        if not path.is_file():
            raise ValueError(f"Not a file: {raw_path}")
        if self._is_excluded(path):
            raise PermissionError(f"Access denied (excluded): {raw_path}")
        if self._is_binary(path):
            raise ValueError(f"Binary file, cannot read as text: {raw_path}")

        max_size = self._max_size_for(path)
        size = path.stat().st_size
        if size > max_size:
            raise ValueError(
                f"File too large ({size} bytes, max {max_size}): {raw_path}"
            )

        return path.read_text(encoding="utf-8", errors="replace")

    def _list_dir(self, raw_path: str) -> list[dict[str, Any]]:
        path = self._resolve_path(raw_path)
        if not path.exists():
            raise FileNotFoundError(f"Directory not found: {raw_path}")
        if not path.is_dir():
            raise ValueError(f"Not a directory: {raw_path}")

        entries: list[dict[str, Any]] = []
        for child in sorted(path.iterdir(), key=lambda p: p.name.lower()):
            if self._is_excluded(child):
                continue
            st = child.stat()
            entry = {
                "name": child.name,
                "path": str(child),
                "type": "directory" if child.is_dir() else "file",
                "size": st.st_size if child.is_file() else None,
                "modified": st.st_mtime,
            }
            entries.append(entry)
        return entries

    def _find(self, pattern: str) -> list[str]:
        """Glob search across all configured roots."""
        results: list[str] = []
        for root in self._roots:
            if not root.exists():
                continue
            for path in root.rglob(pattern):
                if not self._is_excluded(path):
                    results.append(str(path))
        return sorted(results)

    def _get_recent_changes(self, n: int) -> list[dict[str, Any]]:
        """Return the last N modified files across all roots."""
        files: list[tuple[float, Path]] = []
        for root in self._roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_file() and not self._is_excluded(path):
                    mtime = path.stat().st_mtime
                    files.append((mtime, path))
        files.sort(reverse=True)
        return [
            {"path": str(p), "modified": mtime}
            for mtime, p in files[:n]
        ]
