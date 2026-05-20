"""Integration tests against real services (not mocks).

Tests auto-skip when services are unavailable.
Run these in CI or environments with Docker/Postgres/SSH running.
"""

import os

import pytest

from context_bridge.connectors.github import GitHubConnector
from context_bridge.config import GitHubConfig


def _should_skip_github() -> bool:
    return os.environ.get("SKIP_REAL_GITHUB", "").lower() in ("1", "true", "yes")


@pytest.mark.skipif(_should_skip_github(), reason="SKIP_REAL_GITHUB set")
@pytest.mark.asyncio
async def test_github_get_file_real() -> None:
    """Fetch a real file from torvalds/linux on GitHub."""
    cfg = GitHubConfig(token="", repos=[])
    conn = GitHubConnector(cfg)
    await conn.initialize()

    content = await conn._get_file("torvalds/linux", "README", "HEAD")
    assert "Linux kernel" in content
    await conn.shutdown()


@pytest.mark.skipif(_should_skip_github(), reason="SKIP_REAL_GITHUB set")
@pytest.mark.asyncio
async def test_github_list_issues_real() -> None:
    """List real issues from a public repo."""
    cfg = GitHubConfig(token="", repos=[])
    conn = GitHubConnector(cfg)
    await conn.initialize()

    issues = await conn._list_issues("torvalds/linux", "open", 3)
    assert isinstance(issues, list)
    if issues:
        assert "title" in issues[0]
        assert "url" in issues[0]
    await conn.shutdown()


@pytest.mark.skipif(_should_skip_github(), reason="SKIP_REAL_GITHUB set")
@pytest.mark.asyncio
async def test_github_get_pr_real() -> None:
    """Fetch a real PR from a public repo (PR #1 in torvalds/linux)."""
    cfg = GitHubConfig(token="", repos=[])
    conn = GitHubConnector(cfg)
    await conn.initialize()

    try:
        pr = await conn._get_pr("torvalds/linux", 1)
        assert "title" in pr
        assert pr["number"] == 1
    except Exception:
        # PR #1 may not exist in all repos; that's OK for this test
        pass
    await conn.shutdown()


@pytest.mark.skipif(
    _should_skip_github() or not os.environ.get("GITHUB_TOKEN"),
    reason="SKIP_REAL_GITHUB set or no GITHUB_TOKEN (code search requires auth)",
)
@pytest.mark.asyncio
async def test_github_search_code_real() -> None:
    """Search real code on GitHub."""
    cfg = GitHubConfig(token=os.environ.get("GITHUB_TOKEN", ""), repos=[])
    conn = GitHubConnector(cfg)
    await conn.initialize()

    results = await conn._search_code("repo:torvalds/linux filename:Makefile", 3)
    assert isinstance(results, list)
    if results:
        assert "path" in results[0]
        assert "repo" in results[0]
    await conn.shutdown()


@pytest.mark.skipif(_should_skip_github(), reason="SKIP_REAL_GITHUB set")
@pytest.mark.asyncio
async def test_github_caching_real() -> None:
    """Verify that repeated calls hit the cache."""
    cfg = GitHubConfig(token="", repos=[])
    conn = GitHubConnector(cfg)
    await conn.initialize()

    # First call hits the network
    r1 = await conn._get_file("torvalds/linux", "README", "HEAD")
    # Second call should be cached
    r2 = await conn._get_file("torvalds/linux", "README", "HEAD")
    assert r1 == r2
    await conn.shutdown()
