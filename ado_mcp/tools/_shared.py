"""Code shared by the tool modules: context access, results, the tool decorator."""

from collections.abc import Awaitable, Callable
import functools
import logging
from typing import Annotated, ParamSpec

from fastmcp import Context
from fastmcp.tools import ToolResult
from mcp_types import InputRequiredResult, TextContent
from pydantic import Field

from ..client import AdoClient
from ..constants import CLIENT_KEY, MAX_PAGE_SIZE, SETTINGS_KEY
from ..exceptions import AdoMcpError, InvalidInputError, ToolInterrupt
from ..operations import IDENTITIES
from ..settings import Settings
from ..utils import JsonValue, to_json_text

logger = logging.getLogger(__name__)

P = ParamSpec("P")

# Input types shared by several tools.
ItemId = Annotated[int, Field(ge=1)]
Top = Annotated[int, Field(ge=1, le=MAX_PAGE_SIZE)]
Skip = Annotated[int, Field(ge=0)]

_IDENTITY_SEARCH_FILTER = "General"


def get_client(ctx: Context) -> AdoClient:
    """Return the collection client created by the server's lifespan."""
    return ctx.lifespan_context[CLIENT_KEY]


def get_settings(ctx: Context) -> Settings:
    """Return the settings the server started with."""
    return ctx.lifespan_context[SETTINGS_KEY]


def action_label(tool: str, action: str | None = None) -> str:
    """Name a tool action for errors and logs.

    Examples: `("wit_work_item", "get")` -> `"wit_work_item.get"`;
    `("core_list_projects", None)` -> `"core_list_projects"`.
    """
    return f"{tool}.{action}" if action else tool


def json_result(value: JsonValue, *prefix: str) -> ToolResult:
    """Return one text block per `prefix` item, then the value as indented JSON."""
    blocks = [TextContent(text=text) for text in (*prefix, to_json_text(value))]
    return ToolResult(blocks)


def text_result(text: str) -> ToolResult:
    """Return a single plain text block."""
    return ToolResult(text)


def plain_error(text: str) -> ToolResult:
    """Return upstream's plain error text, such as `No teams found`, as an error result."""
    return ToolResult(text, is_error=True)


def error_result(error: AdoMcpError) -> ToolResult:
    """Return an error as the JSON error payload in an error result."""
    return ToolResult(error.to_payload().to_text(), is_error=True)


def reply_value(reply: JsonValue) -> JsonValue:
    """Return the `value` field of an object reply, or `None` when there is none.

    Example: `{"count": 1, "value": [{"id": 1}]}` -> `[{"id": 1}]`; `[1, 2]` -> `None`.
    """
    return reply.get("value") if isinstance(reply, dict) else None


def require(value: object, message: str) -> None:
    """Raise `InvalidInputError(message)` when a required input is `None`, `0`, `""`, or `[]`."""
    if not value:
        raise InvalidInputError(message)


def ado_tool(
    function: Callable[P, Awaitable[ToolResult]],
) -> Callable[P, Awaitable[ToolResult | InputRequiredResult]]:
    """Turn this project's errors and interrupts into tool results.

    `functools.wraps` keeps the wrapped signature, which FastMCP reads to build
    the input schema. A `ToolInterrupt` returns its ready result; an
    `AdoMcpError` becomes an error result naming the tool action. The action is
    filled in from the function name and its `action` argument when the error
    has none. Any other exception propagates to FastMCP, which masks it.
    """

    @functools.wraps(function)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> ToolResult | InputRequiredResult:
        try:
            return await function(*args, **kwargs)
        except ToolInterrupt as interrupt:
            return interrupt.result
        except AdoMcpError as error:
            if error.label is None:
                action = kwargs.get("action")
                error.label = action_label(
                    wrapper.__name__, action if isinstance(action, str) else None
                )
            logger.warning("%s returned an error: %s", error.label, error.code)
            return error_result(error)

    return wrapper


async def search_identities(client: AdoClient, filter_value: str, label: str) -> list[JsonValue]:
    """Search collection identities by name, account, or email; return the raw `value` list."""
    reply = await client.send(
        IDENTITIES,
        label=label,
        method="GET",
        query={"searchFilter": _IDENTITY_SEARCH_FILTER, "filterValue": filter_value},
    )
    identities = reply_value(reply)
    return identities if isinstance(identities, list) else []
