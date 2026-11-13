# ruff: noqa: N803
# Input names are upstream's camelCase names; they are the public tool schema.
"""The `search_workitem` tool: full-text work-item search on the collection."""

from fastmcp import Context, FastMCP
from fastmcp.tools import ToolResult

from ..constants import DEFAULT_SEARCH_PAGE_SIZE, READ_ONLY_ANNOTATIONS, SEARCH_WORKITEM
from ..operations import WORK_ITEM_SEARCH
from ..utils import JsonValue
from ._shared import Skip, Top, action_label, ado_tool, get_client, json_result


@ado_tool
async def search_workitem(
    ctx: Context,
    searchText: str,
    project: list[str] | None = None,
    areaPath: list[str] | None = None,
    workItemType: list[str] | None = None,
    state: list[str] | None = None,
    assignedTo: list[str] | None = None,
    includeFacets: bool = False,
    skip: Skip = 0,
    top: Top = DEFAULT_SEARCH_PAGE_SIZE,
) -> ToolResult:
    """Search work items by text, optionally filtered by project, area, type, state, assignee."""
    body: dict[str, JsonValue] = {
        "searchText": searchText,
        "includeFacets": includeFacets,
        "$skip": skip,
        "$top": top,
    }
    # `project` is a filter only: there is no default project and no picker.
    candidates = {
        "System.TeamProject": project,
        "System.AreaPath": areaPath,
        "System.WorkItemType": workItemType,
        "System.State": state,
        "System.AssignedTo": assignedTo,
    }
    filters: dict[str, JsonValue] = {
        name: list(values) for name, values in candidates.items() if values
    }
    if filters:
        body["filters"] = filters
    reply = await get_client(ctx).send(
        WORK_ITEM_SEARCH,
        label=action_label(SEARCH_WORKITEM),
        method="POST",
        json_body=body,
    )
    return json_result(reply)


def register(mcp: FastMCP) -> None:
    """Register the `search_workitem` tool."""
    mcp.tool(
        search_workitem,
        name=SEARCH_WORKITEM,
        description="Get Azure DevOps Work Item search results for a given search text.",
        annotations=dict(READ_ONLY_ANNOTATIONS),
    )
