# ruff: noqa: N803, A002
# Input names are upstream's camelCase names; they are the public tool schema.
"""Work-item read tools: `wit_work_item`, `wit_query`, and `wit_backlog`."""

from datetime import datetime
from types import MappingProxyType
from typing import Annotated, Literal

from fastmcp import Context, FastMCP
from fastmcp.tools import ToolResult
from pydantic import Field

from ..client import AdoClient
from ..constants import (
    DEFAULT_BATCH_FIELDS,
    DEFAULT_PAGE_SIZE,
    IDENTITY_FIELDS,
    MAX_PAGE_SIZE,
    MAX_WIQL_LENGTH,
    READ_CONSISTENCY_HEADER,
    READ_ONLY_ANNOTATIONS,
    WIT_BACKLOG,
    WIT_QUERY,
    WIT_WORK_ITEM,
)
from ..elicitation import resolve_project, resolve_team
from ..exceptions import InvalidInputError
from ..operations import (
    BACKLOG_WORK_ITEMS,
    BACKLOGS,
    COMMENTS,
    ITERATION_WORK_ITEMS,
    PREDEFINED_QUERY,
    QUERY,
    QUERY_BY_ID,
    QUERY_BY_WIQL,
    REVISIONS,
    WORK_ITEM,
    WORK_ITEM_TYPE,
    WORK_ITEMS_BATCH,
)
from ..utils import JsonValue
from ._shared import (
    ItemId,
    Skip,
    Top,
    action_label,
    ado_tool,
    get_client,
    get_settings,
    json_result,
    reply_value,
    require,
)

WorkItemAction = Literal[
    "get", "get_batch", "list_comments", "my", "list_revisions", "list_for_iteration", "get_type"
]
QueryAction = Literal["get", "get_results", "wiql"]
BacklogAction = Literal["list", "list_work_items"]

# Picker messages, as upstream words them.
_WORK_ITEM_PROJECT_MESSAGES = MappingProxyType(
    {
        "get_batch": "Select the Azure DevOps project to retrieve work items for.",
        "list_comments": "Select the Azure DevOps project to list work item comments for.",
        "my": "Select the Azure DevOps project to retrieve work items for.",
        "list_revisions": "Select the Azure DevOps project to list work item revisions for.",
        "list_for_iteration": (
            "Select the Azure DevOps project to retrieve work items for iteration."
        ),
        "get_type": "Select the Azure DevOps project to retrieve the work item type from.",
    }
)
_BACKLOG_PURPOSES = MappingProxyType(
    {"list": "list backlogs", "list_work_items": "list backlog work items"}
)
_DEFAULT_MY_QUERY = "assignedtome"
# Sent as $expand when `fields` is given, because the server rejects both together.
_NO_EXPAND = "none"
# Lets the server answer query results from a read replica (eventual
# consistency), as upstream's read-replica client does.
_READ_CONSISTENCY = MappingProxyType(dict([READ_CONSISTENCY_HEADER]))
_INVALID_AS_OF = "asOf must be an ISO 8601 date-time"
# Keys removed from identity-shaped field values in revisions.
_REVISION_IDENTITY_MARKERS = ("url", "_links", "uniqueName")
_REVISION_IDENTITY_DROPPED = ("url", "_links", "id", "uniqueName", "imageUrl", "descriptor")


def format_identity(value: dict[str, JsonValue]) -> str:
    """Flatten an identity field value to `"{displayName} <{uniqueName}>"`, trimmed.

    Example: `{"displayName": "Ana", "uniqueName": "CORP\\\\ana"}` -> `"Ana <CORP\\\\ana>"`;
    `{}` -> `"<>"`.
    """
    name = value.get("displayName") or ""
    unique_name = value.get("uniqueName") or ""
    return f"{name} <{unique_name}>".strip()


def _flatten_identity_fields(items: JsonValue) -> JsonValue:
    """Replace each object-valued identity field of a batch reply with `format_identity`."""
    if not isinstance(items, list):
        return items
    for item in items:
        fields = item.get("fields") if isinstance(item, dict) else None
        if not isinstance(fields, dict):
            continue
        for name in IDENTITY_FIELDS:
            value = fields.get(name)
            if isinstance(value, dict):
                fields[name] = format_identity(value)
    return items


def _trim_revision_identities(revisions: JsonValue) -> JsonValue:
    """Strip links and IDs from identity-shaped field values in each revision."""
    if not isinstance(revisions, list):
        return revisions
    for revision in revisions:
        fields = revision.get("fields") if isinstance(revision, dict) else None
        if not isinstance(fields, dict):
            continue
        for value in fields.values():
            if (
                isinstance(value, dict)
                and "displayName" in value
                and any(key in value for key in _REVISION_IDENTITY_MARKERS)
            ):
                for key in _REVISION_IDENTITY_DROPPED:
                    value.pop(key, None)
    return revisions


def _check_as_of(asOf: str | None) -> None:
    """Reject an `asOf` value that is not an ISO 8601 date-time."""
    if asOf is None:
        return
    try:
        datetime.fromisoformat(asOf)
    except ValueError:
        raise InvalidInputError(_INVALID_AS_OF) from None


async def _get_work_item(
    client: AdoClient,
    label: str,
    project: str | None,
    id: int,
    fields: list[str] | None,
    asOf: str | None,
    expand: str | None,
) -> ToolResult:
    """GET one work item, collection-scoped when `project` is `None`."""
    _check_as_of(asOf)
    if fields and expand is not None:
        expand = _NO_EXPAND
    reply = await client.send(
        WORK_ITEM,
        label=label,
        method="GET",
        route_values={"project": project, "id": id},
        query={"fields": ",".join(fields) if fields else None, "asOf": asOf, "$expand": expand},
    )
    return json_result(reply)


async def _get_batch(
    client: AdoClient, label: str, project: str, ids: list[int], fields: list[str] | None
) -> ToolResult:
    """POST a batch read of work items; flatten identity fields in the `value` list."""
    body: JsonValue = {"ids": list(ids), "fields": list(fields or DEFAULT_BATCH_FIELDS)}
    reply = await client.send(
        WORK_ITEMS_BATCH,
        label=label,
        method="POST",
        route_values={"project": project},
        json_body=body,
    )
    return json_result(_flatten_identity_fields(reply_value(reply)))


@ado_tool
async def wit_work_item(
    ctx: Context,
    action: WorkItemAction,
    project: str | None = None,
    id: ItemId | None = None,
    ids: Annotated[list[ItemId], Field(max_length=MAX_PAGE_SIZE)] | None = None,
    workItemId: ItemId | None = None,
    fields: list[str] | None = None,
    asOf: str | None = None,
    expand: Literal["None", "Relations", "Fields", "Links", "All"] | None = None,
    top: Top | None = None,
    continuationToken: str | None = None,
    includeCompleted: bool = False,
    type: Literal["assignedtome", "myactivity"] | None = None,
    skip: Skip | None = None,
    team: str | None = None,
    iterationId: str | None = None,
    workItemType: str | None = None,
) -> ToolResult:
    """Read work items, their comments, revisions, and type metadata."""
    client = get_client(ctx)
    label = action_label(WIT_WORK_ITEM, action)
    if action == "get":
        # Upstream never resolves a project here: without one, the read is
        # collection-scoped.
        work_item_id = require(id, "id is required for get")
        return await _get_work_item(client, label, project, work_item_id, fields, asOf, expand)
    settings = get_settings(ctx)
    message = _WORK_ITEM_PROJECT_MESSAGES[action]
    # Required inputs are checked before the project is resolved, as upstream does.
    if action == "get_batch":
        batch_ids = require(ids, "ids is required for get_batch")
        resolved = await resolve_project(ctx, client, settings, project, message, label=label)
        return await _get_batch(client, label, resolved, batch_ids, fields)
    if action in ("list_comments", "list_revisions"):
        require(workItemId, f"workItemId is required for {action}")
    elif action == "list_for_iteration":
        require(iterationId, "iterationId is required for list_for_iteration")
    elif action == "get_type":
        require(workItemType, "workItemType is required for get_type")
    resolved = await resolve_project(ctx, client, settings, project, message, label=label)
    page_size = top or DEFAULT_PAGE_SIZE
    if action == "list_comments":
        reply = await client.send(
            COMMENTS,
            label=label,
            method="GET",
            route_values={"project": resolved, "workItemId": workItemId},
            query={"$top": page_size, "continuationToken": continuationToken},
        )
        return json_result(reply)
    if action == "my":
        reply = await client.send(
            PREDEFINED_QUERY,
            label=label,
            method="GET",
            route_values={"project": resolved, "id": type or _DEFAULT_MY_QUERY},
            query={"$top": page_size, "includeCompleted": includeCompleted},
        )
        return json_result(reply)
    if action == "list_revisions":
        reply = await client.send(
            REVISIONS,
            label=label,
            method="GET",
            route_values={"project": resolved, "id": workItemId},
            query={"$top": page_size, "$skip": skip, "$expand": expand},
        )
        return json_result(_trim_revision_identities(reply_value(reply)))
    if action == "list_for_iteration":
        reply = await client.send(
            ITERATION_WORK_ITEMS,
            label=label,
            method="GET",
            route_values={"project": resolved, "team": team, "iterationId": iterationId},
        )
        return json_result(reply)
    reply = await client.send(
        WORK_ITEM_TYPE,
        label=label,
        method="GET",
        route_values={"project": resolved, "type": workItemType},
    )
    return json_result(reply)


def _ids_only(reply: JsonValue) -> JsonValue:
    """Reduce a query result to `{"ids": [...], "count": n}` from `workItems[].id`."""
    items = reply.get("workItems") if isinstance(reply, dict) else None
    ids = [
        item["id"]
        for item in (items if isinstance(items, list) else [])
        if isinstance(item, dict) and item.get("id") is not None
    ]
    return {"ids": ids, "count": len(ids)}


@ado_tool
async def wit_query(
    ctx: Context,
    action: QueryAction,
    project: str | None = None,
    query: str | None = None,
    expand: Literal["None", "Wiql", "Clauses", "All", "Minimal"] | None = None,
    depth: Annotated[int, Field(ge=0)] = 0,
    includeDeleted: bool = False,
    useIsoDateFormat: bool = False,
    id: str | None = None,
    team: str | None = None,
    timePrecision: bool | None = None,
    top: Top = DEFAULT_PAGE_SIZE,
    responseType: Literal["full", "ids"] = "full",
    wiql: Annotated[str, Field(max_length=MAX_WIQL_LENGTH)] | None = None,
) -> ToolResult:
    """Read a saved query, run it, or run an ad-hoc WIQL query."""
    client = get_client(ctx)
    label = action_label(WIT_QUERY, action)
    resolved = await resolve_project(
        ctx,
        client,
        get_settings(ctx),
        project,
        f"Select the Azure DevOps project for {action}.",
        label=label,
    )
    if action == "get":
        query_path = require(query, "query is required for get")
        reply = await client.send(
            QUERY,
            label=label,
            method="GET",
            route_values={"project": resolved, "query": query_path},
            query={
                "$expand": expand,
                "$depth": depth,
                "$includeDeleted": includeDeleted,
                "$useIsoDateFormat": useIsoDateFormat,
            },
        )
        return json_result(reply)
    if action == "get_results":
        query_id = require(id, "id is required for get_results")
        reply = await client.send(
            QUERY_BY_ID,
            label=label,
            method="GET",
            route_values={"project": resolved, "team": team, "id": query_id},
            query={"timePrecision": timePrecision, "$top": top},
            headers=_READ_CONSISTENCY,
        )
        return json_result(_ids_only(reply) if responseType == "ids" else reply)
    query_text = require(wiql, "wiql is required for wiql")
    reply = await client.send(
        QUERY_BY_WIQL,
        label=label,
        method="POST",
        route_values={"project": resolved, "team": team},
        query={"timePrecision": timePrecision, "$top": top},
        json_body={"query": query_text},
        headers=_READ_CONSISTENCY,
    )
    return json_result(reply)


@ado_tool
async def wit_backlog(
    ctx: Context,
    action: BacklogAction,
    project: str | None = None,
    team: str | None = None,
    backlogId: str | None = None,
) -> ToolResult:
    """List a team's backlog levels, or the work items in one backlog level."""
    client = get_client(ctx)
    settings = get_settings(ctx)
    label = action_label(WIT_BACKLOG, action)
    purpose = _BACKLOG_PURPOSES[action]
    resolved = await resolve_project(
        ctx,
        client,
        settings,
        project,
        f"Select the Azure DevOps project to {purpose} for.",
        label=label,
    )
    resolved_team = await resolve_team(
        ctx,
        client,
        settings,
        resolved,
        team,
        f"Select the Azure DevOps team to {purpose} for.",
        label=label,
    )
    route_values = {"project": resolved, "team": resolved_team}
    if action == "list":
        reply = await client.send(BACKLOGS, label=label, method="GET", route_values=route_values)
        return json_result(reply_value(reply))
    backlog = require(backlogId, "backlogId is required for list_work_items")
    reply = await client.send(
        BACKLOG_WORK_ITEMS,
        label=label,
        method="GET",
        route_values={**route_values, "backlogId": backlog},
    )
    return json_result(reply)


def register(mcp: FastMCP) -> None:
    """Register the three work-item read tools."""
    annotations = dict(READ_ONLY_ANNOTATIONS)
    mcp.tool(
        wit_work_item,
        name=WIT_WORK_ITEM,
        description=("Retrieve work item data. Use the action parameter to specify the operation."),
        annotations=annotations,
    )
    mcp.tool(
        wit_query,
        name=WIT_QUERY,
        description=(
            "Retrieve work item query data for a project. Use the action parameter to "
            "specify the operation."
        ),
        annotations=annotations,
    )
    mcp.tool(
        wit_backlog,
        name=WIT_BACKLOG,
        description=(
            "Retrieve backlog data for a project and team. Use the action parameter to "
            "specify the operation."
        ),
        annotations=annotations,
    )
