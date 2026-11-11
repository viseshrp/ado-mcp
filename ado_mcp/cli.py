"The console script for ado-mcp."

import click

from . import __version__ as _version
from .ado_mcp import do_stuff


@click.argument(
    "stuff",
    metavar="<what_you_worked_on>",
    nargs=-1,
    required=False,
    type=click.STRING,
)
@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(_version, "-v", "--version")
def main(stuff: tuple[str, ...]) -> None:
    "Python MCP server for on-premises Azure DevOps Server and TFS.\n\n\b\nExample usages:\n"
    do_stuff(stuff)
