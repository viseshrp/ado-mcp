# ruff: noqa: N803
# Input names are upstream's camelCase names; they are the public tool schema.
"""The `work` tool: iterations, team settings, and capacity."""

from types import MappingProxyType
from typing import Annotated, Literal

from fastmcp import Context, FastMCP
from fastmcp.tools import ToolResult
from pydantic import Field

from ..client import AdoClient
from ..constants import DEFAULT_ITERATION_DEPTH, READ_ONLY_ANNOTATIONS, WORK
from ..elicitation import resolve_project, resolve_team
from ..operations import (
    CLASSIFICATION_NODES,
    ITERATION_CAPACITIES,
    TEAM_CAPACITIES,
    TEAM_FIELD_VALUES,
    TEAM_ITERATIONS,
    TEAM_SETTINGS,
)
from ..utils import JsonValue
from ._shared import (
    ItemId,
    action_label,
    ado_tool,
    get_client,
    get_settings,
    json_result,
    plain_error,
    reply_value,
    require,
)

WorkAction = Literal[
    "list_iterations",
    "list_team_iterations",
    "get_team_settings",
    "get_team_capacity",
    "get_iteration_capacities",
]

# Picker messages per action, as upstream words them.
_PROJECT_MESSAGES = MappingProxyType(
    {
        "list_iterations": "Select the Azure DevOps project to list iterations for.",
        "list_team_iterations": "Select the Azure DevOps project to list team iterations for.",
        "get_team_settings": "Select the Azure DevOps project to get team settings for.",
        "get_team_capacity": "Select the Azure DevOps project to get team capacity for.",
        "get_iteration_capacities": (
            "Select the Azure DevOps project to get iteration capacities for."
        ),
    }
)
_TEAM_MESSAGES = MappingProxyType(
    {
        "list_team_iterations": "Select the Azure DevOps team to list iterations for.",
        "get_team_settings": "Select the Azure DevOps team to get settings for.",
    }
)
_ITERATION_STRUCTURE = "iteration"
# The SDK's numeric TreeNodeStructureType for iterations.
_ITERATION_STRUCTURE_CODE = 1
_TEAM_SETTINGS_FIELDS = (
    "backlogIteration",
    "defaultIteration",
    "defaultIterationMacro",
    "backlogVisibilities",
    "bugsBehavior",
    "workingDays",
)
_TEAM_MEMBER_FIELDS = ("displayName", "id", "uniqueName")
_NO_ITERATIONS = "No iterations were found"
_NO_TEAM_ITERATIONS = "No iterations found"
_NO_TEAM_SETTINGS = "No team settings found"
_NO_TEAM_CAPACITY = "No team capacity assigned to the team"
_NO_ITERATION_CAPACITY = "No iteration capacity assigned to the teams"


def _is_iteration(node: JsonValue) -> bool:
    """Whether a classification node is an iteration (by name or the SDK's number)."""
    if not isinstance(node, dict):
        return False
    structure = node.get("structureType")
    if isinstance(structure, str):
        return structure.lower() == _ITERATION_STRUCTURE
    return structure == _ITERATION_STRUCTURE_CODE and not isinstance(structure, bool)


def _exclude_iterations(nodes: list[JsonValue], excluded: frozenset[int]) -> list[JsonValue]:
    """Drop nodes whose `id` is excluded, with their children; filter children recursively."""
    kept: list[JsonValue] = []
    for node in nodes:
        if not isinstance(node, dict):
            kept.append(node)
            continue
        if node.get("id") in excluded:
            continue
        children = node.get("children")
        if isinstance(children, list) and children:
            node = {**node, "children": _exclude_iterations(children, excluded)}
        kept.append(node)
    return kept


async def _list_iterations(
    client: AdoClient, label: str, project: str, depth: int, excludedIds: list[int] | None
) -> ToolResult:
    reply = await client.send(
        CLASSIFICATION_NODES,
        label=label,
        method="GET",
        route_values={"project": project},
        query={"$depth": depth},
    )
    nodes = reply_value(reply)
    if not isinstance(nodes, list):
        return plain_error(_NO_ITERATIONS)
    iterations = [node for node in nodes if _is_iteration(node)]
    if excludedIds:
        iterations = _exclude_iterations(iterations, frozenset(excludedIds))
    if not iterations:
        return plain_error(_NO_ITERATIONS)
    return json_result(iterations)


async def _list_team_iterations(
    client: AdoClient, label: str, project: str, team: str, timeframe: str | None
) -> ToolResult:
    reply = await client.send(
        TEAM_ITERATIONS,
        label=label,
        method="GET",
        route_values={"project": project, "team": team},
        query={"$timeframe": timeframe},
    )
    iterations = reply_value(reply)
    if iterations is None:
        return plain_error(_NO_TEAM_ITERATIONS)
    return json_result(iterations, f"Project: {project}, Team: {team}")


async def _get_team_settings(client: AdoClient, label: str, project: str, team: str) -> ToolResult:
    route_values = {"project": project, "team": team}
    settings = await client.send(
        TEAM_SETTINGS, label=label, method="GET", route_values=route_values
    )
    if not isinstance(settings, dict):
        return plain_error(_NO_TEAM_SETTINGS)
    field_values = await client.send(
        TEAM_FIELD_VALUES, label=label, method="GET", route_values=route_values
    )
    values = field_values if isinstance(field_values, dict) else {}
    merged: dict[str, JsonValue] = {name: settings.get(name) for name in _TEAM_SETTINGS_FIELDS}
    merged["defaultAreaPath"] = values.get("defaultValue")
    merged["areaPathField"] = values.get("field")
    merged["areaPaths"] = values.get("values")
    return json_result(merged, f"Project: {project}, Team: {team}")


def _trim_team_member(member: JsonValue) -> JsonValue:
    """Drop a capacity entry's `url` and reduce `teamMember` to display name, ID, unique name."""
    if not isinstance(member, dict):
        return member
    trimmed = {key: value for key, value in member.items() if key != "url"}
    identity = member.get("teamMember")
    trimmed["teamMember"] = (
        {name: identity.get(name) for name in _TEAM_MEMBER_FIELDS}
        if isinstance(identity, dict)
        else None
    )
    return trimmed


async def _get_team_capacity(
    client: AdoClient, label: str, project: str, team: str, iterationId: str
) -> ToolResult:
    reply = await client.send(
        TEAM_CAPACITIES,
        label=label,
        method="GET",
        route_values={"project": project, "team": team, "iterationId": iterationId},
    )
    members = reply.get("teamMembers") if isinstance(reply, dict) else None
    if not isinstance(reply, dict) or members == []:
        return plain_error(_NO_TEAM_CAPACITY)
    members = members if isinstance(members, list) else []
    return json_result({**reply, "teamMembers": [_trim_team_member(m) for m in members]})


async def _get_iteration_capacities(
    client: AdoClient, label: str, project: str, iterationId: str
) -> ToolResult:
    reply = await client.send(
        ITERATION_CAPACITIES,
        label=label,
        method="GET",
        route_values={"project": project, "iterationId": iterationId},
    )
    teams = reply.get("teams") if isinstance(reply, dict) else None
    if not teams:
        return plain_error(_NO_ITERATION_CAPACITY)
    return json_result(reply)


@ado_tool
async def work(
    ctx: Context,
    action: WorkAction,
    project: str | None = None,
    team: str | None = None,
    iterationId: str | None = None,
    timeframe: Literal["current"] | None = None,
    depth: Annotated[int, Field(ge=0)] = DEFAULT_ITERATION_DEPTH,
    excludedIds: list[ItemId] | None = None,
) -> ToolResult:
    """Read iterations, team settings, and capacity for a project or team."""
    client = get_client(ctx)
    settings = get_settings(ctx)
    label = action_label(WORK, action)
    resolved = await resolve_project(ctx, client, settings, project, _PROJECT_MESSAGES[action])
    if action == "list_iterations":
        return await _list_iterations(client, label, resolved, depth, excludedIds)
    if action == "get_iteration_capacities":
        iteration = require(iterationId, "iterationId is required for get_iteration_capacities")
        return await _get_iteration_capacities(client, label, resolved, iteration)
    if action == "get_team_capacity":
        # Upstream requires the team here instead of asking for one.
        required_team = require(team, "Team is required for get_team_capacity")
        iteration = require(iterationId, "iterationId is required for get_team_capacity")
        return await _get_team_capacity(client, label, resolved, required_team, iteration)
    resolved_team = await resolve_team(
        ctx, client, settings, resolved, team, _TEAM_MESSAGES[action]
    )
    if action == "list_team_iterations":
        return await _list_team_iterations(client, label, resolved, resolved_team, timeframe)
    return await _get_team_settings(client, label, resolved, resolved_team)


def register(mcp: FastMCP) -> None:
    """Register the `work` tool."""
    mcp.tool(
        work,
        name=WORK,
        description=(
            "Retrieve work-related data for a project or team. Use the action parameter to "
            "specify the operation."
        ),
        annotations=dict(READ_ONLY_ANNOTATIONS),
    )
