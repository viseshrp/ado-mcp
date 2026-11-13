from fastmcp import Client
import pytest

from ado_mcp.utils import JsonValue
from tests.fake_collection import FakeCollection, call_tool

pytestmark = pytest.mark.anyio


async def test_identity_lookup_returns_only_id_display_name_and_descriptor(
    mcp_client: Client, collection: FakeCollection
) -> None:
    collection.reply(
        "GET",
        "_apis/identities",
        {"value": [{"id": "1", "providerDisplayName": "Ana", "descriptor": "d", "extra": "x"}]},
    )

    output = await call_tool(mcp_client, "core_get_identity_ids", {"searchFilter": "ana"})

    assert output.data == [{"id": "1", "displayName": "Ana", "descriptor": "d"}]


@pytest.mark.parametrize(
    ("properties", "unique_name"),
    [
        pytest.param(
            {"Domain": {"$value": "CORP"}, "Account": {"$value": "ana"}}, "CORP\\ana", id="domain"
        ),
        pytest.param({"Account": {"$value": "ana"}}, "ana", id="account-only"),
    ],
)
async def test_current_user_has_the_unique_name_that_assigned_to_accepts(
    mcp_client: Client,
    collection: FakeCollection,
    properties: dict[str, JsonValue],
    unique_name: str,
) -> None:
    user = {"id": "u1", "providerDisplayName": "Ana", "properties": properties}
    collection.reply("GET", "_apis/connectionData", {"authenticatedUser": user})

    output = await call_tool(mcp_client, "core_get_current_user")

    assert output.data == {"id": "u1", "displayName": "Ana", "uniqueName": unique_name}


async def test_project_name_filter_matches_a_substring_ignoring_case(
    mcp_client: Client, collection: FakeCollection
) -> None:
    collection.reply("GET", "_apis/projects", {"value": [{"name": "Alpha"}, {"name": "Beta"}]})

    output = await call_tool(mcp_client, "core_list_projects", {"projectNameFilter": "ALP"})

    assert output.data == [{"name": "Alpha"}]


async def test_list_iterations_keeps_iterations_and_drops_excluded_ones_with_their_children(
    mcp_client: Client, collection: FakeCollection
) -> None:
    nodes = [
        {"structureType": "iteration", "id": 1, "children": [{"id": 2}, {"id": 3}]},
        {"structureType": 1, "id": 4},
        {"structureType": "area", "id": 5},
    ]
    collection.reply("GET", "P/_apis/wit/classificationNodes", {"value": nodes})

    output = await call_tool(
        mcp_client,
        "work",
        {"action": "list_iterations", "project": "P", "excludedIds": [3, 4]},
    )

    assert output.data == [{"structureType": "iteration", "id": 1, "children": [{"id": 2}]}]


async def test_team_settings_merge_the_settings_and_the_team_field_values(
    mcp_client: Client, collection: FakeCollection
) -> None:
    collection.reply(
        "GET",
        "P/T/_apis/work/teamsettings",
        {"backlogIteration": {"id": "b"}, "workingDays": ["monday"], "unrelated": 1},
    )
    collection.reply(
        "GET",
        "P/T/_apis/work/teamsettings/teamfieldvalues",
        {"defaultValue": "P\\Area", "field": {"referenceName": "System.AreaPath"}, "values": []},
    )

    output = await call_tool(
        mcp_client, "work", {"action": "get_team_settings", "project": "P", "team": "T"}
    )

    assert output.blocks[0] == "Project: P, Team: T"
    assert output.data == {
        "backlogIteration": {"id": "b"},
        "defaultIteration": None,
        "defaultIterationMacro": None,
        "backlogVisibilities": None,
        "bugsBehavior": None,
        "workingDays": ["monday"],
        "defaultAreaPath": "P\\Area",
        "areaPathField": {"referenceName": "System.AreaPath"},
        "areaPaths": [],
    }


async def test_team_capacity_trims_each_members_url_and_identity(
    mcp_client: Client, collection: FakeCollection
) -> None:
    member = {
        "url": "u",
        "activities": [],
        "teamMember": {"displayName": "A", "id": "1", "uniqueName": "a", "imageUrl": "i"},
    }
    collection.reply(
        "GET", "P/T/_apis/work/teamsettings/iterations/i/capacities", {"teamMembers": [member]}
    )

    output = await call_tool(
        mcp_client,
        "work",
        {"action": "get_team_capacity", "project": "P", "team": "T", "iterationId": "i"},
    )

    trimmed = {"displayName": "A", "id": "1", "uniqueName": "a"}
    assert output.data == {"teamMembers": [{"activities": [], "teamMember": trimmed}]}


async def test_batch_read_flattens_identity_fields_to_a_name_and_account(
    mcp_client: Client, collection: FakeCollection
) -> None:
    fields = {
        "System.AssignedTo": {"displayName": "Ana", "uniqueName": "CORP\\ana", "id": "x"},
        "System.Title": "T",
    }
    collection.reply("POST", "P/_apis/wit/workItemsBatch", {"value": [{"id": 1, "fields": fields}]})

    output = await call_tool(
        mcp_client, "wit_work_item", {"action": "get_batch", "project": "P", "ids": [1]}
    )

    flattened = {"System.AssignedTo": "Ana <CORP\\ana>", "System.Title": "T"}
    assert output.data == [{"id": 1, "fields": flattened}]


async def test_revisions_keep_only_the_display_name_of_identity_values(
    mcp_client: Client, collection: FakeCollection
) -> None:
    identity = {"displayName": "Ana", "uniqueName": "a", "url": "u", "id": "x", "imageUrl": "i"}
    revision = {"fields": {"System.AssignedTo": identity, "System.Title": "T"}}
    collection.reply("GET", "P/_apis/wit/workItems/7/revisions", {"value": [revision]})

    output = await call_tool(
        mcp_client,
        "wit_work_item",
        {"action": "list_revisions", "project": "P", "workItemId": 7},
    )

    assert output.data == [
        {"fields": {"System.AssignedTo": {"displayName": "Ana"}, "System.Title": "T"}}
    ]


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        pytest.param(
            {"workItems": [{"id": 1}, {"id": 2}, {"id": 1}]},
            {"ids": [1, 2], "count": 2},
            id="flat-query",
        ),
        pytest.param(
            {
                "workItemRelations": [
                    {"source": None, "target": {"id": 3}},
                    {"source": {"id": 3}, "target": {"id": 4}},
                ]
            },
            {"ids": [3, 4], "count": 2},
            id="linked-query-source-and-target",
        ),
        pytest.param(None, {"ids": [], "count": 0}, id="no-reply"),
    ],
)
async def test_ids_only_results_list_each_work_item_id_once(
    mcp_client: Client, collection: FakeCollection, reply: JsonValue, expected: JsonValue
) -> None:
    collection.reply("GET", "P/_apis/wit/wiql/q-1", reply)

    output = await call_tool(
        mcp_client,
        "wit_query",
        {"action": "get_results", "project": "P", "id": "q-1", "responseType": "ids"},
    )

    assert output.data == expected


async def test_unknown_fields_in_a_reply_pass_through_unchanged(
    mcp_client: Client, collection: FakeCollection
) -> None:
    reply = {"id": 7, "fields": {"System.Title": "T"}, "futureField": {"nested": [1, 2]}}
    collection.reply("GET", "_apis/wit/workItems/7", reply)

    output = await call_tool(mcp_client, "wit_work_item", {"action": "get", "id": 7})

    assert output.data == reply
