# ruff: noqa: N803
# Input names are upstream's camelCase names; they are the public tool schema.
"""Core tools: projects, teams, identities, and the current user."""

from typing import Literal

from fastmcp import Context, FastMCP
from fastmcp.tools import ToolResult

from ..constants import (
    CORE_GET_CURRENT_USER,
    CORE_GET_IDENTITY_IDS,
    CORE_LIST_PROJECT_TEAMS,
    CORE_LIST_PROJECTS,
    READ_ONLY_ANNOTATIONS,
)
from ..elicitation import resolve_project
from ..operations import CONNECTION_DATA, PROJECTS, TEAMS
from ..utils import JsonValue
from ._shared import (
    Skip,
    Top,
    action_label,
    ado_tool,
    get_client,
    get_settings,
    json_result,
    plain_error,
    reply_value,
    search_identities,
)

_LIST_TEAMS_MESSAGE = "Select the Azure DevOps project to list teams for."
_NO_PROJECTS = "No projects found"
_NO_TEAMS = "No teams found"
_NO_IDENTITIES = "No identities found"
_NO_USER = "No authenticated user found"


@ado_tool
async def core_list_projects(
    ctx: Context,
    stateFilter: Literal["all", "wellFormed", "createPending", "deleted"] = "wellFormed",
    top: Top | None = None,
    skip: Skip | None = None,
    continuationToken: int | None = None,
    projectNameFilter: str | None = None,
) -> ToolResult:
    """List the collection's projects, optionally filtered by a name substring."""
    reply = await get_client(ctx).send(
        PROJECTS,
        label=action_label(CORE_LIST_PROJECTS),
        method="GET",
        query={
            "stateFilter": stateFilter,
            "$top": top,
            "$skip": skip,
            "continuationToken": continuationToken,
            "getDefaultTeamImageUrl": False,
        },
    )
    projects = reply_value(reply)
    if not isinstance(projects, list):
        return plain_error(_NO_PROJECTS)
    if projectNameFilter:
        # Case-insensitive substring match on the name, applied locally as upstream does.
        wanted = projectNameFilter.lower()
        projects: list[JsonValue] = [
            project
            for project in projects
            if isinstance(project, dict)
            and isinstance(project.get("name"), str)
            and wanted in str(project["name"]).lower()
        ]
    return json_result(projects)


@ado_tool
async def core_list_project_teams(
    ctx: Context,
    project: str | None = None,
    mine: bool | None = None,
    top: Top | None = None,
    skip: Skip | None = None,
) -> ToolResult:
    """List a project's teams, asking for the project when none is given."""
    client = get_client(ctx)
    resolved = await resolve_project(ctx, client, get_settings(ctx), project, _LIST_TEAMS_MESSAGE)
    reply = await client.send(
        TEAMS,
        label=action_label(CORE_LIST_PROJECT_TEAMS),
        method="GET",
        route_values={"projectId": resolved},
        query={"$mine": mine, "$top": top, "$skip": skip, "$expandIdentity": False},
    )
    teams = reply_value(reply)
    if teams is None:
        return plain_error(_NO_TEAMS)
    return json_result(teams)


@ado_tool
async def core_get_identity_ids(ctx: Context, searchFilter: str) -> ToolResult:
    """Look up identities and return each one's ID, display name, and descriptor."""
    identities = await search_identities(
        get_client(ctx), searchFilter, action_label(CORE_GET_IDENTITY_IDS)
    )
    if not identities:
        return plain_error(_NO_IDENTITIES)
    trimmed: list[JsonValue] = [
        {
            "id": identity.get("id"),
            "displayName": identity.get("providerDisplayName"),
            "descriptor": identity.get("descriptor"),
        }
        for identity in identities
        if isinstance(identity, dict)
    ]
    return json_result(trimmed)


def _property_value(properties: JsonValue, name: str) -> str | None:
    """Read `properties[name]["$value"]` from a connectionData user, if it is a string.

    Example: `({"Account": {"$value": "ana"}}, "Account")` -> `"ana"`.
    """
    entry = properties.get(name) if isinstance(properties, dict) else None
    value = entry.get("$value") if isinstance(entry, dict) else None
    return value if isinstance(value, str) else None


@ado_tool
async def core_get_current_user(ctx: Context) -> ToolResult:
    """Return the authenticated user's ID, display name, and assignable unique name."""
    reply = await get_client(ctx).send(
        CONNECTION_DATA, label=action_label(CORE_GET_CURRENT_USER), method="GET"
    )
    user = reply.get("authenticatedUser") if isinstance(reply, dict) else None
    if not isinstance(user, dict) or not user.get("id"):
        return plain_error(_NO_USER)
    properties = user.get("properties")
    domain = _property_value(properties, "Domain")
    account = _property_value(properties, "Account")
    # System.AssignedTo accepts the domain-qualified account, e.g. "CORP\\ana".
    unique_name = f"{domain}\\{account}" if domain and account else account
    return json_result(
        {
            "id": user.get("id"),
            "displayName": user.get("providerDisplayName") or user.get("customDisplayName"),
            "uniqueName": unique_name,
        }
    )


def register(mcp: FastMCP) -> None:
    """Register the four core tools."""
    annotations = dict(READ_ONLY_ANNOTATIONS)
    mcp.tool(
        core_list_projects,
        name=CORE_LIST_PROJECTS,
        description="Retrieve a list of projects in your Azure DevOps collection.",
        annotations=annotations,
    )
    mcp.tool(
        core_list_project_teams,
        name=CORE_LIST_PROJECT_TEAMS,
        description=(
            "Retrieve a list of teams for an Azure DevOps project. If a project is not "
            "specified, you will be prompted to select one."
        ),
        annotations=annotations,
    )
    mcp.tool(
        core_get_identity_ids,
        name=CORE_GET_IDENTITY_IDS,
        description="Retrieve Azure DevOps identity IDs for a provided search filter.",
        annotations=annotations,
    )
    mcp.tool(
        core_get_current_user,
        name=CORE_GET_CURRENT_USER,
        description=(
            "Retrieve the authenticated user for the configured collection: identity ID, "
            "display name, and the unique name that System.AssignedTo accepts. This tool is "
            "specific to ado-mcp."
        ),
        annotations=annotations,
    )
