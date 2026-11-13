"The console script for ado-mcp."

import click

from . import __version__ as _version
from .ado_mcp import run_server
from .constants import DEFAULT_HTTP_PORT
from .exceptions import ConfigurationError
from .settings import load_settings

_MAX_PORT = 65535
_PORT_WITHOUT_HTTP = "--port requires --http"


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--http",
    "http",
    is_flag=True,
    help="Serve MCP over HTTP at http://127.0.0.1:PORT/mcp instead of stdio. "
    "The server listens on the loopback address only.",
)
@click.option(
    "--port",
    type=click.IntRange(1, _MAX_PORT),
    default=None,
    help=f"Port for --http. Defaults to {DEFAULT_HTTP_PORT}.",
)
@click.version_option(_version, "-v", "--version")
def main(http: bool, port: int | None) -> None:
    """Python MCP server for on-premises Azure DevOps Server and TFS.

    Reads ADO_COLLECTION_URL, ADO_PAT, and the optional ADO_PROJECT and ADO_TEAM
    from the environment or a .env file in the current directory, then serves MCP
    on stdio. With --http it serves at http://127.0.0.1:8000/mcp instead.
    """
    if port is not None and not http:
        raise click.UsageError(_PORT_WITHOUT_HTTP)
    try:
        settings = load_settings()
    except ConfigurationError as error:
        raise click.ClickException(str(error)) from None
    run_server(settings, http=http, port=port or DEFAULT_HTTP_PORT)
