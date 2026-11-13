from collections.abc import AsyncIterator, Generator
from pathlib import Path

from fastmcp import Client
import httpx2
import pytest

from tests.fake_collection import COLLECTION_URL, PAT, FakeCollection, make_client


def do_cleanup() -> None:
    """Perform any necessary cleanup after tests."""
    # Add your cleanup code here
    pass


@pytest.fixture(scope="session", autouse=True)
def cleanup() -> Generator[None, None, None]:
    yield
    do_cleanup()


@pytest.fixture
def collection(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeCollection:
    """Settings for a fake collection, with every HTTP request answered by it.

    The test runs in an empty directory, so no `.env` file leaks in, and no default
    project or team is set.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ADO_PROJECT", raising=False)
    monkeypatch.delenv("ADO_TEAM", raising=False)
    monkeypatch.setenv("ADO_COLLECTION_URL", COLLECTION_URL)
    monkeypatch.setenv("ADO_PAT", PAT)
    fake = FakeCollection()
    real_client = httpx2.AsyncClient

    class MockedAsyncClient(real_client):
        """The real HTTP client with its network replaced by the fake collection."""

        def __init__(self, **kwargs: object) -> None:
            super().__init__(transport=httpx2.MockTransport(fake.handle), **kwargs)

    monkeypatch.setattr(httpx2, "AsyncClient", MockedAsyncClient)
    return fake


@pytest.fixture
async def mcp_client(collection: FakeCollection) -> AsyncIterator[Client]:
    """An MCP client connected to the server, which talks to the fake collection."""
    async with make_client() as client:
        yield client
