"""GitHub connector — fetch repos, issues, PRs, code via GitHub API."""

from typing import Any

import httpx

from context_bridge.cache import CacheManager
from context_bridge.config import GitHubConfig
from context_bridge.connectors.base import BaseConnector


class GitHubConnector(BaseConnector):
    """Read GitHub repositories, issues, PRs, and code."""

    name = "github"
    description = "GitHub API access"

    def __init__(self, config: GitHubConfig) -> None:
        super().__init__(config)
        self._token = config.token or ""
        self._repos = config.repos
        self._cache_ttl = config.cache_ttl
        self._cache = CacheManager()
        self._client: httpx.AsyncClient | None = None

    async def initialize(self) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        self._client = httpx.AsyncClient(
            base_url="https://api.github.com",
            headers=headers,
            timeout=30.0,
        )
        self._initialized = True

    async def shutdown(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
        self._initialized = False

    def get_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "github.get_file",
                "description": "Read a file from a GitHub repository",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string", "description": "owner/repo"},
                        "path": {"type": "string", "description": "File path in repo"},
                        "ref": {
                            "type": "string",
                            "default": "HEAD",
                            "description": "Branch, tag, or commit SHA",
                        },
                    },
                    "required": ["repo", "path"],
                },
            },
            {
                "name": "github.list_issues",
                "description": "List issues in a repository",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string", "description": "owner/repo"},
                        "state": {
                            "type": "string",
                            "enum": ["open", "closed", "all"],
                            "default": "open",
                        },
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": ["repo"],
                },
            },
            {
                "name": "github.get_pr",
                "description": "Get a pull request by number",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string", "description": "owner/repo"},
                        "number": {"type": "integer", "description": "PR number"},
                    },
                    "required": ["repo", "number"],
                },
            },
            {
                "name": "github.search_code",
                "description": "Search code across GitHub",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "GitHub code search query"},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": ["query"],
                },
            },
        ]

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        if not self._client:
            raise RuntimeError("GitHub connector not initialized")

        if tool_name == "get_file":
            return await self._get_file(
                arguments["repo"], arguments["path"], arguments.get("ref", "HEAD")
            )
        if tool_name == "list_issues":
            return await self._list_issues(
                arguments["repo"],
                arguments.get("state", "open"),
                arguments.get("limit", 10),
            )
        if tool_name == "get_pr":
            return await self._get_pr(arguments["repo"], arguments["number"])
        if tool_name == "search_code":
            return await self._search_code(
                arguments["query"], arguments.get("limit", 10)
            )
        raise ValueError(f"Unknown tool: {tool_name}")

    async def _get_file(self, repo: str, path: str, ref: str) -> str:
        cache_key = ("file", repo, path, ref)
        try:
            return self._cache.get(self.name, *cache_key)
        except KeyError:
            pass

        url = f"/repos/{repo}/contents/{path}"
        params = {"ref": ref}
        resp = await self._client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

        import base64

        if data.get("encoding") == "base64":
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        else:
            content = data.get("content", "")

        self._cache.set(self.name, *cache_key, value=content, ttl=self._cache_ttl)
        return content

    async def _list_issues(self, repo: str, state: str, limit: int) -> list[dict]:
        cache_key = ("issues", repo, state, limit)
        try:
            return self._cache.get(self.name, *cache_key)
        except KeyError:
            pass

        issues = []
        page = 1
        per_page = min(limit, 100)
        while len(issues) < limit:
            resp = await self._client.get(
                f"/repos/{repo}/issues",
                params={"state": state, "per_page": per_page, "page": page},
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            for item in batch:
                if "pull_request" in item:
                    continue  # skip PRs masquerading as issues
                issues.append(
                    {
                        "number": item["number"],
                        "title": item["title"],
                        "state": item["state"],
                        "url": item["html_url"],
                    }
                )
                if len(issues) >= limit:
                    break
            if len(batch) < per_page:
                break
            page += 1

        self._cache.set(self.name, *cache_key, value=issues, ttl=self._cache_ttl)
        return issues

    async def _get_pr(self, repo: str, number: int) -> dict:
        cache_key = ("pr", repo, number)
        try:
            return self._cache.get(self.name, *cache_key)
        except KeyError:
            pass

        resp = await self._client.get(f"/repos/{repo}/pulls/{number}")
        resp.raise_for_status()
        data = resp.json()
        pr = {
            "number": data["number"],
            "title": data["title"],
            "state": data["state"],
            "body": data.get("body", ""),
            "url": data["html_url"],
            "head": data["head"]["ref"],
            "base": data["base"]["ref"],
            "user": data["user"]["login"],
        }

        self._cache.set(self.name, *cache_key, value=pr, ttl=self._cache_ttl)
        return pr

    async def _search_code(self, query: str, limit: int) -> list[dict]:
        cache_key = ("search", query, limit)
        try:
            return self._cache.get(self.name, *cache_key)
        except KeyError:
            pass

        resp = await self._client.get(
            "/search/code",
            params={"q": query, "per_page": limit},
        )
        resp.raise_for_status()
        data = resp.json()
        results = [
            {
                "path": item["path"],
                "repo": item["repository"]["full_name"],
                "url": item["html_url"],
            }
            for item in data.get("items", [])
        ]

        self._cache.set(self.name, *cache_key, value=results, ttl=self._cache_ttl)
        return results
