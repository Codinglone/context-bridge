"""Obsidian connector — index vault, search notes, follow wiki-links."""

import json
import re
from pathlib import Path
from typing import Any

import frontmatter
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from context_bridge.cache import CacheManager
from context_bridge.config import ObsidianConfig
from context_bridge.connectors.base import BaseConnector

# Regexes for Obsidian syntax
WIKILINK_RE = re.compile(r"\[\[(.*?)\]\]")
TAG_RE = re.compile(r"(?:^|\s)#([a-zA-Z][a-zA-Z0-9_/-]*)")


def _parse_wikilinks(content: str) -> list[str]:
    """Extract [[Wiki Link]] targets from markdown text."""
    matches = WIKILINK_RE.findall(content)
    # Normalize: remove aliases
    return [m.split("|")[0].strip() for m in matches]


def _parse_tags(content: str) -> list[str]:
    """Extract #tags from markdown text (excluding code blocks)."""
    # Strip code blocks for tag extraction
    text = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
    text = re.sub(r"`[^`]*`", "", text)
    return sorted(set(TAG_RE.findall(text)))


def _slugify(title: str) -> str:
    """Normalize a note title for lookup."""
    return title.lower().strip()


def _normalize_tags(raw: Any) -> list[str]:
    """Coerce frontmatter tags to a list of strings."""
    if raw is None:
        return []
    if isinstance(raw, str):
        # Could be comma-separated or a single tag
        return [t.strip() for t in raw.split(",") if t.strip()]
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    return [str(raw).strip()]


class _VaultChangeHandler(FileSystemEventHandler):
    """Invalidate the Obsidian index on vault changes."""

    def __init__(self, cache: CacheManager, namespace: str) -> None:
        self.cache = cache
        self.namespace = namespace

    def on_any_event(self, event: Any) -> None:
        self.cache.invalidate_namespace(self.namespace)


class ObsidianConnector(BaseConnector):
    """Index and query an Obsidian vault."""

    name = "obsidian"
    description = "Obsidian vault access"

    def __init__(self, config: ObsidianConfig) -> None:
        super().__init__(config)
        self._vault = config.vault.expanduser().resolve()
        self._exclude = set(config.exclude)
        self._observer: Observer | None = None
        self._cache = CacheManager()
        self._index_ttl = 60  # seconds

    # --- lifecycle ---

    async def initialize(self) -> None:
        if not self._vault.exists():
            raise FileNotFoundError(f"Vault not found: {self._vault}")
        self._observer = Observer()
        handler = _VaultChangeHandler(self._cache, self.name)
        self._observer.schedule(handler, str(self._vault), recursive=True)
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
                "name": "obsidian.search",
                "description": "Full-text search notes in the vault",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search text"},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "obsidian.get_note",
                "description": "Read a note by title or path",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Note title or path"}
                    },
                    "required": ["title"],
                },
            },
            {
                "name": "obsidian.get_backlinks",
                "description": "Find notes that link to a given note",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Target note title"}
                    },
                    "required": ["title"],
                },
            },
            {
                "name": "obsidian.get_tags",
                "description": "List all tags in the vault",
                "parameters": {"type": "object", "properties": {}},
            },
        ]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if tool_name == "search":
            return self._search(arguments["query"], arguments.get("limit", 10))
        if tool_name == "get_note":
            return self._get_note(arguments["title"])
        if tool_name == "get_backlinks":
            return self._get_backlinks(arguments["title"])
        if tool_name == "get_tags":
            return self._get_tags()
        raise ValueError(f"Unknown tool: {tool_name}")

    # --- indexing ---

    def _get_index(self) -> dict[str, Any]:
        """Build (or return cached) vault index."""
        try:
            return self._cache.get(self.name, "index")
        except KeyError:
            index = self._build_index()
            self._cache.set(self.name, "index", value=index, ttl=self._index_ttl)
            return index

    def _build_index(self) -> dict[str, Any]:
        """Scan vault and build in-memory index structures."""
        notes: dict[str, dict] = {}          # folder_slug -> note metadata
        short_slugs: dict[str, list[str]] = {}  # short slug -> list of folder_slugs
        tag_map: dict[str, set[str]] = {}    # tag -> set of folder_slugs
        backlink_map: dict[str, set[str]] = {}  # slug -> set of folder_slugs that link TO it
        inverted: dict[str, set[str]] = {}   # word -> set of folder_slugs

        for md_path in self._vault.rglob("*.md"):
            if self._is_excluded(md_path):
                continue
            try:
                note = self._parse_note(md_path)
            except Exception:
                continue
            folder_slug = note["folder_slug"]
            short = note["slug"]

            notes[folder_slug] = note
            short_slugs.setdefault(short, []).append(folder_slug)

            for tag in note["tags"]:
                tag_map.setdefault(tag, set()).add(folder_slug)

            for word in note["words"]:
                inverted.setdefault(word, set()).add(folder_slug)

        # Second pass: build backlink map (target slug -> list of folder_slugs)
        for folder_slug, note in notes.items():
            for target in note["links"]:
                target_slug = _slugify(target)
                backlink_map.setdefault(target_slug, set()).add(folder_slug)

        return {
            "notes": notes,
            "short_slugs": short_slugs,
            "tags": {k: sorted(v) for k, v in tag_map.items()},
            "backlinks": {k: sorted(v) for k, v in backlink_map.items()},
            "inverted": {k: sorted(v) for k, v in inverted.items()},
        }

    def _is_excluded(self, path: Path) -> bool:
        """Check if a path matches any exclusion rule."""
        rel = str(path.relative_to(self._vault))
        for pattern in self._exclude:
            if path.name == pattern or rel.startswith(pattern):
                return True
        # Respect .obsidian/app.json exclusions if present
        app_json = self._vault / ".obsidian" / "app.json"
        if app_json.exists():
            try:
                app_cfg = json.loads(app_json.read_text())
                for pattern in app_cfg.get("userIgnoreFilters", []):
                    # Simple prefix match for Obsidian ignore filters
                    if rel.startswith(pattern.rstrip("/")):
                        return True
            except Exception:
                pass
        return False

    def _parse_note(self, path: Path) -> dict[str, Any]:
        """Parse a single markdown note into structured metadata."""
        raw = path.read_text(encoding="utf-8", errors="replace")
        post = frontmatter.loads(raw)
        content = post.content
        title = post.get("title") or path.stem
        links = _parse_wikilinks(content)
        tags = _normalize_tags(post.get("tags")) + _parse_tags(content)
        words = set(re.findall(r"[a-zA-Z0-9_]+", content.lower()))

        # Folder slug: relative vault path with .md stripped, lowercased, forward slashes
        rel = path.relative_to(self._vault)
        folder_slug = "/".join(rel.with_suffix("").parts).lower()

        return {
            "slug": _slugify(title),
            "folder_slug": folder_slug,
            "title": title,
            "path": str(path),
            "content": content,
            "frontmatter": dict(post.metadata),
            "links": links,
            "tags": sorted(set(tags)),
            "words": words,
        }

    # --- tools ---

    def _search(self, query: str, limit: int) -> list[dict[str, Any]]:
        """Full-text search across note contents."""
        index = self._get_index()
        inverted = index["inverted"]
        words = re.findall(r"[a-zA-Z0-9_]+", query.lower())
        if not words:
            return []

        # Intersection of word postings
        candidates: set[str] | None = None
        for word in words:
            posting = set(inverted.get(word, []))
            if candidates is None:
                candidates = posting
            else:
                candidates &= posting

        if not candidates:
            return []

        notes = index["notes"]
        results = []
        for slug in sorted(candidates):
            note = notes[slug]
            results.append({
                "title": note["title"],
                "path": note["path"],
                "tags": note["tags"],
            })
            if len(results) >= limit:
                break
        return results

    def _get_note(self, title: str) -> dict[str, Any]:
        """Read a note by title, slug, or path.

        Lookup order:
          1. folder_slug exact match (e.g. "a/note")
          2. short slug — if unique, return it; if ambiguous, raise with options
          3. path suffix match
          4. exact title match
        """
        index = self._get_index()
        notes = index["notes"]
        short_slugs = index["short_slugs"]
        query = title.lower().strip()

        # 1. Folder-slug exact match
        if query in notes:
            note = notes[query]
            return self._format_note(note)

        # 2. Short slug lookup
        candidates = short_slugs.get(query, [])
        if len(candidates) == 1:
            return self._format_note(notes[candidates[0]])
        if len(candidates) > 1:
            options = ", ".join(sorted(candidates))
            raise ValueError(
                f"Ambiguous note title '{title}' — found in: {options}. "
                f"Use a folder-prefixed path like 'a/{title}' to disambiguate."
            )

        # 3. Path suffix match
        for note in notes.values():
            if note["path"].endswith(title) or note["title"] == title:
                return self._format_note(note)

        raise FileNotFoundError(f"Note not found: {title}")

    def _format_note(self, note: dict[str, Any]) -> dict[str, Any]:
        """Return a sanitized note dict for tool output."""
        return {
            "title": note["title"],
            "path": note["path"],
            "content": note["content"],
            "frontmatter": note["frontmatter"],
            "tags": note["tags"],
            "links": note["links"],
        }

    def _get_backlinks(self, title: str) -> list[dict[str, Any]]:
        """Find notes that link to the given title."""
        index = self._get_index()
        slug = _slugify(title)
        backlink_slugs = index["backlinks"].get(slug, [])
        notes = index["notes"]
        return [
            {
                "title": notes[s]["title"],
                "path": notes[s]["path"],
            }
            for s in backlink_slugs
            if s in notes
        ]

    def _get_tags(self) -> list[str]:
        """Return all unique tags in the vault."""
        index = self._get_index()
        return sorted(index["tags"].keys())
