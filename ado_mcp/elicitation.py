"""Resolve the project and team a tool call works on, asking the user when needed.

Order for a project: the tool argument, then `ADO_PROJECT`, then (2026-07-28
connections only) a project carried from an earlier round, then a picker when
the client supports elicitation, else an explicit error. Teams follow the same
order with `ADO_TEAM`. Handshake-era connections (2024-11-05 to 2025-11-25) ask
with a server-initiated elicitation request; 2026-07-28 connections have no such
back-channel, so the call ends with an `InputRequiredResult` and the client
retries it with the answer.
"""

from collections.abc import Sequence
import json

from fastmcp import Context
from fastmcp.server.elicitation import AcceptedElicitation
from fastmcp.tools import ToolResult
from mcp_types import (
    ElicitRequest,
    ElicitRequestFormParams,
    ElicitResult,
    InputRequiredResult,
    InputResponse,
)
from mcp_types.version import MODERN_PROTOCOL_VERSIONS

from .client import AdoClient
from .constants import (
    CORE_LIST_PROJECT_TEAMS,
    CORE_LIST_PROJECTS,
    ELICITATION_PROJECT_LIMIT,
)
from .exceptions import MissingContextError, ToolInterrupt
from .operations import PROJECTS, TEAMS
from .settings import Settings
from .utils import JsonValue

_PROJECT_FIELD = "project"
_PROJECT_TITLE = "Project"
_PROJECT_DESCRIPTION = "The Azure DevOps project."
_PROJECT_CANCELLED = "Project selection cancelled."
_NO_PROJECTS = "No projects found to select from."
_NO_PROJECT_GIVEN = "No project was given. Pass 'project' or set ADO_PROJECT."
_TEAM_FIELD = "team"
_TEAM_TITLE = "Team"
_TEAM_DESCRIPTION = "The team from a specific Azure DevOps project."
_TEAM_CANCELLED = "Team selection cancelled."
_NO_TEAMS = "No teams found to select from."
_NO_TEAM_GIVEN = "No team was given. Pass 'team' or set ADO_TEAM."
_ACCEPT = "accept"


async def resolve_project(
    ctx: Context, client: AdoClient, settings: Settings, provided: str | None, message: str
) -> str:
    """Return the project for this call, or raise `MissingContextError` or `ToolInterrupt`."""
    if provided and provided.strip():
        return provided
    if settings.project:
        return settings.project
    modern = _is_modern(ctx)
    if modern:
        carried = _carried_project(ctx)
        if carried is not None:
            return carried
    if not _client_can_elicit(ctx):
        raise MissingContextError(_NO_PROJECT_GIVEN)
    if modern:
        answered = _answer(ctx, _PROJECT_FIELD, _PROJECT_CANCELLED)
        if answered is not None:
            return answered
    reply = await client.send(
        PROJECTS,
        label=CORE_LIST_PROJECTS,
        method="GET",
        query={
            "stateFilter": "wellFormed",
            "$top": ELICITATION_PROJECT_LIMIT,
            "$skip": 0,
            "getDefaultTeamImageUrl": False,
        },
    )
    choices = _choices(reply)
    if not choices:
        raise ToolInterrupt(ToolResult(_NO_PROJECTS, is_error=True))
    return await _pick(
        ctx,
        message,
        choices,
        field=_PROJECT_FIELD,
        title=_PROJECT_TITLE,
        description=_PROJECT_DESCRIPTION,
        cancelled=_PROJECT_CANCELLED,
        request_state=None,
    )


async def resolve_team(
    ctx: Context,
    client: AdoClient,
    settings: Settings,
    project: str,
    provided: str | None,
    message: str,
) -> str:
    """Return the team for this call, or raise `MissingContextError` or `ToolInterrupt`."""
    if provided and provided.strip():
        return provided
    if settings.team:
        return settings.team
    if not _client_can_elicit(ctx):
        raise MissingContextError(_NO_TEAM_GIVEN)
    if _is_modern(ctx):
        answered = _answer(ctx, _TEAM_FIELD, _TEAM_CANCELLED)
        if answered is not None:
            return answered
    reply = await client.send(
        TEAMS,
        label=CORE_LIST_PROJECT_TEAMS,
        method="GET",
        route_values={"projectId": project},
        query={"$expandIdentity": False},
    )
    choices = _choices(reply)
    if not choices:
        raise ToolInterrupt(ToolResult(_NO_TEAMS, is_error=True))
    # The retried call brings back only the newest answers, so the project
    # chosen in an earlier round travels in the request state.
    return await _pick(
        ctx,
        message,
        choices,
        field=_TEAM_FIELD,
        title=_TEAM_TITLE,
        description=_TEAM_DESCRIPTION,
        cancelled=_TEAM_CANCELLED,
        request_state=json.dumps({_PROJECT_FIELD: project}),
    )


def choice_schema(
    field: str, title: str, description: str, choices: Sequence[str]
) -> dict[str, JsonValue]:
    """Build upstream's single-choice elicitation schema.

    Example: `("project", "Project", "The Azure DevOps project.", ["Alpha"])` ->
    `{"type": "object", "properties": {"project": {"type": "string", "title": "Project",
    "description": "The Azure DevOps project.", "oneOf": [{"const": "Alpha", "title":
    "Alpha"}]}}, "required": ["project"]}`.
    """
    return {
        "type": "object",
        "properties": {
            field: {
                "type": "string",
                "title": title,
                "description": description,
                "oneOf": [{"const": choice, "title": choice} for choice in choices],
            }
        },
        "required": [field],
    }


async def _pick(
    ctx: Context,
    message: str,
    choices: list[str],
    *,
    field: str,
    title: str,
    description: str,
    cancelled: str,
    request_state: str | None,
) -> str:
    """Ask the user to choose: elicit on a handshake-era connection, else end the round."""
    if not _is_modern(ctx):
        result = await ctx.elicit(message, choices, response_title=title)
        if isinstance(result, AcceptedElicitation):
            return result.data
        raise ToolInterrupt(ToolResult(cancelled))
    params = ElicitRequestFormParams(
        message=message, requested_schema=choice_schema(field, title, description, choices)
    )
    raise ToolInterrupt(
        InputRequiredResult(
            input_requests={field: ElicitRequest(params=params)}, request_state=request_state
        )
    )


def _is_modern(ctx: Context) -> bool:
    """Whether the connection uses the 2026-07-28 per-request protocol."""
    request_context = ctx.request_context
    return (
        request_context is not None and request_context.protocol_version in MODERN_PROTOCOL_VERSIONS
    )


def _client_can_elicit(ctx: Context) -> bool:
    """Whether the client declared the elicitation capability."""
    capabilities = ctx.session.client_capabilities
    return capabilities is not None and capabilities.elicitation is not None


def _carried_project(ctx: Context) -> str | None:
    """Return the project carried in the request state from an earlier round, if any."""
    state = ctx.request_state
    if not state:
        return None
    try:
        decoded = json.loads(state)
    except ValueError:
        return None
    project = decoded.get(_PROJECT_FIELD) if isinstance(decoded, dict) else None
    return project if isinstance(project, str) and project.strip() else None


def _answer(ctx: Context, field: str, cancelled: str) -> str | None:
    """Return the user's answer for `field` from a retried call, or `None` if not asked yet.

    An answer that was declined, cancelled, or empty ends the call with `cancelled`.
    """
    responses = ctx.input_responses
    if responses is None or field not in responses:
        return None
    choice = _accepted_choice(responses[field], field)
    if choice is None:
        raise ToolInterrupt(ToolResult(cancelled))
    return choice


def _accepted_choice(response: InputResponse, field: str) -> str | None:
    """Return the accepted, non-blank value of `field` from an elicitation response."""
    if not isinstance(response, ElicitResult) or response.action != _ACCEPT:
        return None
    value = (response.content or {}).get(field)
    return value if isinstance(value, str) and value.strip() else None


def _choices(items: JsonValue) -> list[str]:
    """Return each item's `name` (or `id`) from a list reply, without blanks or duplicates.

    Example: `{"value": [{"name": "A"}, {"id": "b-1"}, {"name": "A"}, {"name": " "}]}` ->
    `["A", "b-1"]`.
    """
    entries = items.get("value") if isinstance(items, dict) else None
    if not isinstance(entries, list):
        return []
    choices = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or entry.get("id")
        if isinstance(name, str) and name.strip():
            choices.setdefault(name)
    return list(choices)
