from typing import NamedTuple

from fastmcp import Client
import pytest

from ado_mcp.utils import JsonValue
from tests.fake_collection import FakeCollection, call_tool

pytestmark = pytest.mark.anyio

WORK_ITEMS_VERSION = "7.1-preview.3"
WORK_VERSION = "7.2-preview.1"


class Request(NamedTuple):
    """A tool call, the reply the collection gives, and the request it must produce."""

    tool: str
    arguments: dict[str, JsonValue]
    reply: JsonValue
    method: str
    path: str
    query: dict[str, str]
    body: JsonValue = None


@pytest.mark.parametrize(
    "request_case",
    [
        pytest.param(
            Request(
                "core_list_projects",
                {"top": 5, "skip": 2},
                {"value": [{"name": "Alpha"}]},
                "GET",
                "_apis/projects",
                {
                    "stateFilter": "wellFormed",
                    "$top": "5",
                    "$skip": "2",
                    "getDefaultTeamImageUrl": "false",
                    "api-version": "7.2-preview.4",
                },
            ),
            id="core_list_projects",
        ),
        pytest.param(
            Request(
                "core_list_project_teams",
                {"project": "My Project", "mine": True, "top": 3},
                {"value": [{"name": "T"}]},
                "GET",
                "_apis/projects/My%20Project/teams",
                {
                    "$mine": "true",
                    "$top": "3",
                    "$expandIdentity": "false",
                    "api-version": "7.2-preview.3",
                },
            ),
            id="core_list_project_teams",
        ),
        pytest.param(
            Request(
                "core_get_identity_ids",
                {"searchFilter": "ana@example.com"},
                {"value": [{"id": "1", "providerDisplayName": "Ana", "descriptor": "d"}]},
                "GET",
                "_apis/identities",
                {
                    "searchFilter": "General",
                    "filterValue": "ana@example.com",
                    "api-version": WORK_VERSION,
                },
            ),
            id="core_get_identity_ids",
        ),
        pytest.param(
            Request(
                "core_get_current_user",
                {},
                {"authenticatedUser": {"id": "1"}},
                "GET",
                "_apis/connectionData",
                {},
            ),
            id="core_get_current_user",
        ),
        pytest.param(
            Request(
                "work",
                {"action": "list_iterations", "project": "P", "depth": 3},
                {"value": [{"structureType": "iteration", "name": "I"}]},
                "GET",
                "P/_apis/wit/classificationNodes",
                {"$depth": "3", "api-version": "7.1-preview.2"},
            ),
            id="work.list_iterations",
        ),
        pytest.param(
            Request(
                "work",
                {
                    "action": "list_team_iterations",
                    "project": "P",
                    "team": "T",
                    "timeframe": "current",
                },
                {"value": [{"id": "1"}]},
                "GET",
                "P/T/_apis/work/teamsettings/iterations",
                {"$timeframe": "current", "api-version": WORK_VERSION},
            ),
            id="work.list_team_iterations",
        ),
        pytest.param(
            Request(
                "work",
                {
                    "action": "get_team_capacity",
                    "project": "P",
                    "team": "T",
                    "iterationId": "it-1",
                },
                {"teamMembers": [{"teamMember": {"id": "1"}}]},
                "GET",
                "P/T/_apis/work/teamsettings/iterations/it-1/capacities",
                {"api-version": "7.2-preview.3"},
            ),
            id="work.get_team_capacity",
        ),
        pytest.param(
            Request(
                "work",
                {"action": "get_iteration_capacities", "project": "P", "iterationId": "it-1"},
                {"teams": [{"team": "T"}]},
                "GET",
                "P/_apis/work/iterations/it-1/capacities",
                {"api-version": WORK_VERSION},
            ),
            id="work.get_iteration_capacities",
        ),
        pytest.param(
            Request(
                "wit_work_item",
                {
                    "action": "get",
                    "project": "P",
                    "id": 7,
                    "fields": ["System.Title"],
                    "expand": "All",
                    "asOf": "2026-01-02T03:04:05Z",
                },
                {"id": 7},
                "GET",
                "P/_apis/wit/workItems/7",
                {
                    "fields": "System.Title",
                    "asOf": "2026-01-02T03:04:05Z",
                    "$expand": "none",
                    "api-version": WORK_ITEMS_VERSION,
                },
            ),
            id="wit_work_item.get-with-fields",
        ),
        pytest.param(
            Request(
                "wit_work_item",
                {"action": "get", "id": 7},
                {"id": 7},
                "GET",
                "_apis/wit/workItems/7",
                {"api-version": WORK_ITEMS_VERSION},
            ),
            id="wit_work_item.get-collection-scoped",
        ),
        pytest.param(
            Request(
                "wit_work_item",
                {"action": "get_batch", "project": "P", "ids": [1, 2], "fields": ["System.Title"]},
                {"value": []},
                "POST",
                "P/_apis/wit/workItemsBatch",
                {"api-version": "7.1-preview.1"},
                {"ids": [1, 2], "fields": ["System.Title"]},
            ),
            id="wit_work_item.get_batch",
        ),
        pytest.param(
            Request(
                "wit_work_item",
                {
                    "action": "list_comments",
                    "project": "P",
                    "workItemId": 7,
                    "top": 10,
                    "continuationToken": "tok",
                },
                {"comments": []},
                "GET",
                "P/_apis/wit/workItems/7/comments",
                {"$top": "10", "continuationToken": "tok", "api-version": WORK_ITEMS_VERSION},
            ),
            id="wit_work_item.list_comments",
        ),
        pytest.param(
            Request(
                "wit_work_item",
                {"action": "my", "project": "P", "type": "myactivity", "includeCompleted": True},
                {"workItem": []},
                "GET",
                "P/_apis/work/predefinedqueries/myactivity",
                {"$top": "50", "includeCompleted": "true", "api-version": WORK_VERSION},
            ),
            id="wit_work_item.my",
        ),
        pytest.param(
            Request(
                "wit_work_item",
                {
                    "action": "list_revisions",
                    "project": "P",
                    "workItemId": 7,
                    "skip": 1,
                    "expand": "Fields",
                },
                {"value": []},
                "GET",
                "P/_apis/wit/workItems/7/revisions",
                {
                    "$top": "50",
                    "$skip": "1",
                    "$expand": "Fields",
                    "api-version": WORK_ITEMS_VERSION,
                },
            ),
            id="wit_work_item.list_revisions",
        ),
        pytest.param(
            Request(
                "wit_work_item",
                {
                    "action": "list_for_iteration",
                    "project": "P",
                    "team": "T",
                    "iterationId": "it-1",
                },
                {"workItemRelations": []},
                "GET",
                "P/T/_apis/work/teamsettings/iterations/it-1/workitems",
                {"api-version": WORK_VERSION},
            ),
            id="wit_work_item.list_for_iteration",
        ),
        pytest.param(
            Request(
                "wit_work_item",
                {"action": "get_type", "project": "P", "workItemType": "User Story"},
                {"name": "User Story"},
                "GET",
                "P/_apis/wit/workItemTypes/User%20Story",
                {"api-version": "7.1-preview.2"},
            ),
            id="wit_work_item.get_type",
        ),
        pytest.param(
            Request(
                "wit_query",
                {
                    "action": "get",
                    "project": "P",
                    "query": "Shared Queries/Bugs",
                    "depth": 1,
                    "expand": "Wiql",
                },
                {"id": "q"},
                "GET",
                "P/_apis/wit/queries/Shared%20Queries%2FBugs",
                {
                    "$expand": "Wiql",
                    "$depth": "1",
                    "$includeDeleted": "false",
                    "$useIsoDateFormat": "false",
                    "api-version": "7.1-preview.2",
                },
            ),
            id="wit_query.get",
        ),
        pytest.param(
            Request(
                "wit_query",
                {
                    "action": "get_results",
                    "project": "P",
                    "team": "T",
                    "id": "q-1",
                    "timePrecision": True,
                    "top": 5,
                },
                {"workItems": []},
                "GET",
                "P/T/_apis/wit/wiql/q-1",
                {"timePrecision": "true", "$top": "5", "api-version": "7.1-preview.2"},
            ),
            id="wit_query.get_results",
        ),
        pytest.param(
            Request(
                "wit_query",
                {"action": "wiql", "project": "P", "wiql": "SELECT [System.Id] FROM WorkItems"},
                {"workItems": []},
                "POST",
                "P/_apis/wit/wiql",
                {"$top": "50", "api-version": "7.1-preview.2"},
                {"query": "SELECT [System.Id] FROM WorkItems"},
            ),
            id="wit_query.wiql",
        ),
        pytest.param(
            Request(
                "wit_backlog",
                {"action": "list", "project": "P", "team": "T"},
                {"value": []},
                "GET",
                "P/T/_apis/work/backlogs",
                {"api-version": WORK_VERSION},
            ),
            id="wit_backlog.list",
        ),
        pytest.param(
            Request(
                "wit_backlog",
                {
                    "action": "list_work_items",
                    "project": "P",
                    "team": "T",
                    "backlogId": "Microsoft.RequirementCategory",
                },
                {"workItems": []},
                "GET",
                "P/T/_apis/work/backlogs/Microsoft.RequirementCategory/workItems",
                {"api-version": WORK_VERSION},
            ),
            id="wit_backlog.list_work_items",
        ),
        pytest.param(
            Request(
                "search_workitem",
                {"searchText": "login", "project": ["P"], "state": ["Active"], "top": 5},
                {"count": 0, "results": []},
                "POST",
                "_apis/search/workitemsearchresults",
                {"api-version": WORK_VERSION},
                {
                    "searchText": "login",
                    "includeFacets": False,
                    "$skip": 0,
                    "$top": 5,
                    "filters": {"System.TeamProject": ["P"], "System.State": ["Active"]},
                },
            ),
            id="search_workitem",
        ),
    ],
)
async def test_each_read_action_sends_the_documented_request(
    mcp_client: Client, collection: FakeCollection, request_case: Request
) -> None:
    collection.reply(request_case.method, request_case.path, request_case.reply)

    output = await call_tool(mcp_client, request_case.tool, request_case.arguments)

    call = collection.only_call()
    assert output.is_error is False, output.blocks
    assert (call.method, call.path, call.query, call.body) == (
        request_case.method,
        request_case.path,
        request_case.query,
        request_case.body,
    )


async def test_saved_query_and_wiql_reads_allow_an_eventually_consistent_replica(
    mcp_client: Client, collection: FakeCollection
) -> None:
    collection.reply("GET", "P/_apis/wit/wiql/q-1", {"workItems": []})

    await call_tool(mcp_client, "wit_query", {"action": "get_results", "project": "P", "id": "q-1"})

    assert collection.only_call().headers["x-vss-readconsistencylevel"] == "Eventual"


@pytest.mark.parametrize(
    ("tool", "arguments", "method", "path", "reply", "text"),
    [
        ("core_list_projects", {}, "GET", "_apis/projects", {}, "No projects found"),
        (
            "core_list_project_teams",
            {"project": "P"},
            "GET",
            "_apis/projects/P/teams",
            {},
            "No teams found",
        ),
        (
            "core_get_identity_ids",
            {"searchFilter": "x"},
            "GET",
            "_apis/identities",
            {"value": []},
            "No identities found",
        ),
        ("core_get_current_user", {}, "GET", "_apis/connectionData", {}, "No authenticated user"),
        (
            "work",
            {"action": "list_iterations", "project": "P"},
            "GET",
            "P/_apis/wit/classificationNodes",
            {"value": [{"structureType": "area"}]},
            "No iterations were found",
        ),
        (
            "work",
            {"action": "list_team_iterations", "project": "P", "team": "T"},
            "GET",
            "P/T/_apis/work/teamsettings/iterations",
            {},
            "No iterations found",
        ),
        (
            "work",
            {"action": "get_team_settings", "project": "P", "team": "T"},
            "GET",
            "P/T/_apis/work/teamsettings",
            None,
            "No team settings found",
        ),
        (
            "work",
            {"action": "get_team_capacity", "project": "P", "team": "T", "iterationId": "i"},
            "GET",
            "P/T/_apis/work/teamsettings/iterations/i/capacities",
            {"teamMembers": []},
            "No team capacity assigned to the team",
        ),
        (
            "work",
            {"action": "get_iteration_capacities", "project": "P", "iterationId": "i"},
            "GET",
            "P/_apis/work/iterations/i/capacities",
            {"teams": []},
            "No iteration capacity assigned to the teams",
        ),
    ],
    ids=[
        "projects",
        "teams",
        "identities",
        "current-user",
        "iterations",
        "team-iterations",
        "team-settings",
        "team-capacity",
        "iteration-capacities",
    ],
)
async def test_an_empty_answer_is_reported_in_upstreams_plain_words(
    mcp_client: Client,
    collection: FakeCollection,
    tool: str,
    arguments: dict[str, JsonValue],
    method: str,
    path: str,
    reply: JsonValue,
    text: str,
) -> None:
    collection.reply(method, path, reply)

    output = await call_tool(mcp_client, tool, arguments)

    assert (output.is_error, text in output.blocks[0]) == (True, True)


@pytest.mark.parametrize(
    ("tool", "arguments", "message"),
    [
        ("wit_work_item", {"action": "get"}, "id is required for get"),
        ("wit_work_item", {"action": "get_batch", "project": "P"}, "ids is required"),
        ("wit_work_item", {"action": "list_comments", "project": "P"}, "workItemId is required"),
        ("wit_work_item", {"action": "list_for_iteration", "project": "P"}, "iterationId is req"),
        ("wit_work_item", {"action": "get_type", "project": "P"}, "workItemType is required"),
        ("wit_work_item", {"action": "get", "id": 1, "asOf": "yesterday"}, "ISO 8601"),
        ("wit_query", {"action": "get", "project": "P"}, "query is required"),
        ("wit_query", {"action": "get_results", "project": "P"}, "id is required"),
        ("wit_query", {"action": "wiql", "project": "P"}, "wiql is required"),
        (
            "wit_backlog",
            {"action": "list_work_items", "project": "P", "team": "T"},
            "backlogId is required",
        ),
        ("work", {"action": "get_team_capacity", "project": "P"}, "Team is required"),
        ("work", {"action": "get_team_capacity", "project": "P", "team": "T"}, "iterationId"),
        ("work", {"action": "get_iteration_capacities", "project": "P"}, "iterationId"),
    ],
)
async def test_a_missing_required_input_is_invalid_input_before_any_request(
    mcp_client: Client,
    collection: FakeCollection,
    tool: str,
    arguments: dict[str, JsonValue],
    message: str,
) -> None:
    output = await call_tool(mcp_client, tool, arguments)

    error = output.data["error"]
    assert (output.is_error, error["code"]) == (True, "invalid_input")
    assert message in error["message"]
    assert error["operation"].startswith(tool)
    assert collection.calls == []
