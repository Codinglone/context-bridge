"""Tests for the GitHub connector."""

import base64

import pytest
import respx
from httpx import Response

from context_bridge.connectors.github import GitHubConnector
from context_bridge.config import GitHubConfig


@pytest.fixture
def connector() -> GitHubConnector:
    cfg = GitHubConfig(token="fake-token", repos=["owner/repo"])
    return GitHubConnector(cfg)


@pytest.mark.asyncio
async def test_get_file(connector: GitHubConnector) -> None:
    with respx.mock:
        content = "Hello, world!"
        encoded = base64.b64encode(content.encode()).decode()
        route = respx.get("https://api.github.com/repos/owner/repo/contents/README.md").mock(
            return_value=Response(200, json={"content": encoded, "encoding": "base64"})
        )
        await connector.initialize()
        result = await connector._get_file("owner/repo", "README.md", "HEAD")
        assert result == content
        assert route.called
        await connector.shutdown()


@pytest.mark.asyncio
async def test_list_issues(connector: GitHubConnector) -> None:
    with respx.mock:
        route = respx.get("https://api.github.com/repos/owner/repo/issues").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "number": 1,
                        "title": "Bug",
                        "state": "open",
                        "html_url": "https://github.com/owner/repo/issues/1",
                    }
                ],
            )
        )
        await connector.initialize()
        result = await connector._list_issues("owner/repo", "open", 5)
        assert len(result) == 1
        assert result[0]["title"] == "Bug"
        assert route.called
        await connector.shutdown()


@pytest.mark.asyncio
async def test_get_pr(connector: GitHubConnector) -> None:
    with respx.mock:
        route = respx.get("https://api.github.com/repos/owner/repo/pulls/42").mock(
            return_value=Response(
                200,
                json={
                    "number": 42,
                    "title": "Feature",
                    "state": "open",
                    "body": "Adds feature",
                    "html_url": "https://github.com/owner/repo/pull/42",
                    "head": {"ref": "feature-branch"},
                    "base": {"ref": "main"},
                    "user": {"login": "alice"},
                },
            )
        )
        await connector.initialize()
        result = await connector._get_pr("owner/repo", 42)
        assert result["title"] == "Feature"
        assert result["head"] == "feature-branch"
        assert result["user"] == "alice"
        assert route.called
        await connector.shutdown()


@pytest.mark.asyncio
async def test_search_code(connector: GitHubConnector) -> None:
    with respx.mock:
        route = respx.get("https://api.github.com/search/code").mock(
            return_value=Response(
                200,
                json={
                    "items": [
                        {
                            "path": "src/main.py",
                            "repository": {"full_name": "owner/repo"},
                            "html_url": "https://github.com/owner/repo/blob/main/src/main.py",
                        }
                    ]
                },
            )
        )
        await connector.initialize()
        result = await connector._search_code("repo:owner/repo main.py", 5)
        assert len(result) == 1
        assert result[0]["path"] == "src/main.py"
        assert route.called
        await connector.shutdown()


@pytest.mark.asyncio
async def test_cache_hit(connector: GitHubConnector) -> None:
    with respx.mock:
        content = "cached"
        encoded = base64.b64encode(content.encode()).decode()
        route = respx.get("https://api.github.com/repos/owner/repo/contents/test.md").mock(
            return_value=Response(200, json={"content": encoded, "encoding": "base64"})
        )
        await connector.initialize()
        r1 = await connector._get_file("owner/repo", "test.md", "HEAD")
        r2 = await connector._get_file("owner/repo", "test.md", "HEAD")
        assert r1 == r2 == content
        assert route.call_count == 1  # cached on second call
        await connector.shutdown()


@pytest.mark.asyncio
async def test_api_error(connector: GitHubConnector) -> None:
    with respx.mock:
        respx.get("https://api.github.com/repos/owner/repo/contents/missing").mock(
            return_value=Response(404, json={"message": "Not Found"})
        )
        await connector.initialize()
        with pytest.raises(Exception):
            await connector._get_file("owner/repo", "missing", "HEAD")
        await connector.shutdown()
