"""Server assembly: the FastMCP server, its lifespan, and the transports."""

from collections.abc import AsyncIterator

from fastmcp import FastMCP
from fastmcp.server.lifespan import Lifespan, lifespan

from ._version import __version__
from .client import AdoClient
from .constants import CLIENT_KEY, HTTP_HOST, HTTP_PATH, SERVER_NAME, SETTINGS_KEY
from .content_safety import ResponseBoundaryMiddleware
from .settings import Settings
from .tools import core


def _lifespan(settings: Settings) -> Lifespan:
    """Return a lifespan that owns one collection client for the server's lifetime."""

    @lifespan
    async def client_lifespan(_server: FastMCP) -> AsyncIterator[dict[str, object]]:
        client = AdoClient(settings)
        try:
            yield {CLIENT_KEY: client, SETTINGS_KEY: settings}
        finally:
            await client.aclose()

    return client_lifespan


def create_server(settings: Settings) -> FastMCP:
    """Build the MCP server with every v1.0 tool registered.

    Arguments are validated strictly (no `"10"` for a number), and an unexpected
    exception reaches the client only as FastMCP's generic text.
    """
    mcp = FastMCP(
        SERVER_NAME,
        version=__version__,
        lifespan=_lifespan(settings),
        middleware=[ResponseBoundaryMiddleware()],
        mask_error_details=True,
        strict_input_validation=True,
    )
    core.register(mcp)
    return mcp


def run_server(settings: Settings, *, http: bool, port: int) -> None:
    """Serve MCP on stdio, or on loopback HTTP at `http://127.0.0.1:{port}/mcp`."""
    mcp = create_server(settings)
    if http:
        # "auto" validates Host and Origin headers on a loopback bind, which
        # blocks web pages that reach the port through DNS rebinding.
        mcp.run(
            transport="http",
            host=HTTP_HOST,
            port=port,
            path=HTTP_PATH,
            host_origin_protection="auto",
            show_banner=False,
        )
    else:
        mcp.run(transport="stdio", show_banner=False)
