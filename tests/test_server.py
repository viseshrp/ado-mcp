from fastmcp import Client
import pytest

from ado_mcp.utils import JsonValue
from tests.fake_collection import FakeCollection, call_tool

pytestmark = pytest.mark.anyio

READ_ONLY_TOOLS: set[str] = {
    "core_list_projects",
    "core_list_project_teams",
    "core_get_identity_ids",
    "core_get_current_user",
    "work",
    "wit_work_item",
    "wit_query",
    "wit_backlog",
    "search_workitem",
}
WRITE_TOOLS: set[str] = {
    "wit_work_item_write",
    "wit_work_item_comment_write",
    "wit_work_item_link_write",
}
ACTION_COUNTS: dict[str, int] = {
    "work": 5,
    "wit_work_item": 7,
    "wit_query": 3,
    "wit_backlog": 2,
    "wit_work_item_write": 4,
    "wit_work_item_comment_write": 2,
    "wit_work_item_link_write": 2,
}


async def test_server_registers_the_v1_tools_with_their_actions(mcp_client: Client) -> None:
    tools = {tool.name: tool for tool in await mcp_client.list_tools()}

    assert set(tools) == READ_ONLY_TOOLS | WRITE_TOOLS
    for name, count in ACTION_COUNTS.items():
        assert len(tools[name].input_schema["properties"]["action"]["enum"]) == count, name
    # Inputs of the deferred actions (reorder, pull-request and artifact links) are absent.
    assert "ids" not in tools["wit_backlog"].input_schema["properties"]
    assert "pullRequestId" not in tools["wit_work_item_link_write"].input_schema["properties"]


async def test_server_marks_read_tools_read_only_and_write_tools_mutating(
    mcp_client: Client,
) -> None:
    tools = {tool.name: tool for tool in await mcp_client.list_tools()}

    for name in READ_ONLY_TOOLS:
        hints = tools[name].annotations
        assert (hints.read_only_hint, hints.destructive_hint) == (True, False), name
    for name in WRITE_TOOLS:
        hints = tools[name].annotations
        assert (hints.read_only_hint, hints.destructive_hint) == (False, True), name


async def test_every_result_text_block_is_wrapped_once_with_a_fresh_nonce(
    mcp_client: Client, collection: FakeCollection
) -> None:
    collection.reply("GET", "_apis/projects", {"value": [{"name": "Alpha"}]})
    ok = await call_tool(mcp_client, "core_list_projects")
    collection.reply("GET", "_apis/projects", {"message": "denied"}, status=403)
    failed = await call_tool(mcp_client, "core_list_projects")

    assert [ok.is_error, failed.is_error] == [False, True]
    assert ok.raw[0].startswith("<<") and "AZURE DEVOPS CORE" in ok.raw[0]
    assert "UNTRUSTED" not in ok.blocks[0] and "UNTRUSTED" not in failed.blocks[0]
    assert ok.raw[0].split("\n")[0] != failed.raw[0].split("\n")[0]
    assert ok.data == [{"name": "Alpha"}]
    assert failed.data["error"]["code"] == "permission_denied"


@pytest.mark.parametrize(
    ("arguments", "field"),
    [
        pytest.param({"action": "my", "top": 201}, "top", id="over-the-page-limit"),
        pytest.param({"action": "my", "top": "10"}, "top", id="string-for-integer"),
        pytest.param({"action": "my", "bogus": 1}, "bogus", id="unknown-input"),
        pytest.param({"action": "reorder"}, "action", id="unknown-action"),
        pytest.param(
            {"action": "get_batch", "ids": list(range(1, 202))}, "ids", id="over-200-batch-ids"
        ),
    ],
)
async def test_invalid_tool_input_is_reported_without_a_request(
    mcp_client: Client,
    collection: FakeCollection,
    arguments: dict[str, JsonValue],
    field: str,
) -> None:
    output = await call_tool(mcp_client, "wit_work_item", arguments)

    error = output.data["error"]
    assert (output.is_error, error["code"]) == (True, "invalid_input")
    assert field in [detail["field"] for detail in error["details"]]
    assert collection.calls == []
