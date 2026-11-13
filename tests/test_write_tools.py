from fastmcp import Client
import httpx2
import pytest

from ado_mcp.utils import JsonValue
from tests.fake_collection import COLLECTION_URL, COMMENTS_ID, FakeCollection, call_tool

pytestmark = pytest.mark.anyio

JSON_PATCH = "application/json-patch+json"
BATCH_HEADERS: dict[str, JsonValue] = {"Content-Type": JSON_PATCH}
ANA_ID = "11111111-2222-3333-4444-555555555555"
BATCH_PATH = "_apis/wit/$batch"


def _batch_item(item_id: int, operations: list[JsonValue]) -> dict[str, JsonValue]:
    """The inner request of a `$batch` call that patches one work item."""
    return {
        "method": "PATCH",
        "uri": f"/_apis/wit/workitems/{item_id}?api-version=5.0",
        "headers": BATCH_HEADERS,
        "body": operations,
    }


async def test_create_sends_a_json_patch_document_and_marks_markdown_fields(
    mcp_client: Client, collection: FakeCollection
) -> None:
    collection.reply("POST", "P/_apis/wit/workItems/$Task", {"id": 9})

    output = await call_tool(
        mcp_client,
        "wit_work_item_write",
        {
            "action": "create",
            "project": "P",
            "workItemType": "Task",
            "fields": [
                {"name": "System.Title", "value": "a < b", "format": "Markdown"},
                {"name": "System.Tags", "value": "x"},
            ],
        },
    )

    call = collection.only_call()
    assert (output.data, call.query) == ({"id": 9}, {"api-version": "7.1-preview.3"})
    assert call.headers["content-type"] == JSON_PATCH
    assert call.body == [
        {"op": "add", "path": "/fields/System.Title", "value": "a &lt; b"},
        {"op": "add", "path": "/fields/System.Tags", "value": "x"},
        {"op": "add", "path": "/multilineFieldsFormat/System.Title", "value": "Markdown"},
    ]


async def test_update_patches_one_work_item_with_lower_cased_operations(
    mcp_client: Client, collection: FakeCollection
) -> None:
    collection.reply("PATCH", "_apis/wit/workItems/7", {"id": 7})

    await call_tool(
        mcp_client,
        "wit_work_item_write",
        {
            "action": "update",
            "id": 7,
            "updates": [
                {"op": "Test", "path": "/rev", "value": 3},
                {"op": "Replace", "path": "/fields/System.Title", "value": "New"},
                {"op": "remove", "path": "/fields/System.Tags"},
            ],
        },
    )

    call = collection.only_call()
    assert call.headers["content-type"] == JSON_PATCH
    assert call.body == [
        {"op": "test", "path": "/rev", "value": 3},
        {"op": "replace", "path": "/fields/System.Title", "value": "New"},
        {"op": "remove", "path": "/fields/System.Tags"},
    ]


@pytest.mark.parametrize(
    ("status", "code", "text"),
    [
        (412, "precondition_failed", "[HTTP 412 Precondition Failed] stale"),
        (409, "conflict", "[HTTP 409 Conflict] stale"),
        (500, "request_failed", "stale"),
    ],
)
async def test_update_errors_keep_upstreams_concurrency_signal(
    mcp_client: Client, collection: FakeCollection, status: int, code: str, text: str
) -> None:
    collection.reply("PATCH", "_apis/wit/workItems/7", {"message": "stale"}, status=status)

    output = await call_tool(
        mcp_client,
        "wit_work_item_write",
        {
            "action": "update",
            "id": 7,
            "updates": [{"op": "replace", "path": "/fields/System.Title", "value": "x"}],
        },
    )

    error = output.data["error"]
    assert (output.is_error, error["code"]) == (True, code)
    assert text in error["message"]


async def test_a_write_that_times_out_is_sent_once_and_reported_as_connection_failed(
    mcp_client: Client, collection: FakeCollection
) -> None:
    collection.reply("PATCH", "_apis/wit/workItems/7", error=httpx2.ReadTimeout("slow"))

    output = await call_tool(
        mcp_client,
        "wit_work_item_write",
        {
            "action": "update",
            "id": 7,
            "updates": [{"op": "replace", "path": "/fields/System.Title", "value": "x"}],
        },
    )

    assert output.data["error"]["code"] == "connection_failed"
    assert [call.method for call in collection.work_calls()] == ["PATCH"]


async def test_update_batch_sends_one_request_per_work_item_in_first_seen_order(
    mcp_client: Client, collection: FakeCollection
) -> None:
    collection.reply("PATCH", BATCH_PATH, {"count": 2})

    await call_tool(
        mcp_client,
        "wit_work_item_write",
        {
            "action": "update_batch",
            "batchUpdates": [
                {"id": 1, "path": "/fields/System.Title", "value": "a<b", "format": "Markdown"},
                {"id": 2, "op": "Replace", "path": "/fields/System.State", "value": "Done"},
                {"id": 1, "path": "/fields/System.Tags", "value": "t"},
            ],
        },
    )

    call = collection.only_call()
    assert call.query == {"api-version": "5.0"}
    assert call.body == [
        _batch_item(
            1,
            [
                {"op": "Add", "path": "/fields/System.Title", "value": "a&lt;b"},
                {"op": "Add", "path": "/fields/System.Tags", "value": "t"},
                {"op": "Add", "path": "/multilineFieldsFormat/System.Title", "value": "Markdown"},
            ],
        ),
        _batch_item(2, [{"op": "Replace", "path": "/fields/System.State", "value": "Done"}]),
    ]


async def test_add_child_links_each_new_item_to_the_parent_and_files_bug_text_as_repro_steps(
    mcp_client: Client, collection: FakeCollection
) -> None:
    collection.reply("PATCH", BATCH_PATH, {"count": 2})

    await call_tool(
        mcp_client,
        "wit_work_item_write",
        {
            "action": "add_child",
            "project": "My P",
            "parentId": 5,
            "workItemType": "Bug",
            "items": [
                {"title": "c1", "description": "d <x>", "areaPath": "A", "iterationPath": "I"},
                {"title": "c2", "description": "plain", "format": "Html"},
            ],
        },
    )

    parent = {
        "rel": "System.LinkTypes.Hierarchy-Reverse",
        "url": f"{COLLECTION_URL}/My%20P/_apis/wit/workItems/5",
    }
    repro = "/fields/Microsoft.VSTS.TCM.ReproSteps"
    uri = "/My%20P/_apis/wit/workitems/$Bug?api-version=5.0"
    requests = collection.only_call().body
    assert [request["uri"] for request in requests] == [uri, uri]
    assert requests[0]["body"] == [
        {"op": "add", "path": "/id", "value": "-1"},
        {"op": "add", "path": "/fields/System.Title", "value": "c1"},
        {"op": "add", "path": "/relations/-", "value": parent},
        {"op": "add", "path": "/fields/System.AreaPath", "value": "A"},
        {"op": "add", "path": "/fields/System.IterationPath", "value": "I"},
        {"op": "add", "path": repro, "value": "d &lt;x&gt;"},
        {
            "op": "add",
            "path": "/multilineFieldsFormat/Microsoft.VSTS.TCM.ReproSteps",
            "value": "Markdown",
        },
    ]
    assert requests[1]["body"][-1] == {"op": "add", "path": repro, "value": "plain"}


async def test_link_adds_relations_grouped_by_work_item(
    mcp_client: Client, collection: FakeCollection
) -> None:
    collection.reply("PATCH", BATCH_PATH, {"count": 1})

    await call_tool(
        mcp_client,
        "wit_work_item_link_write",
        {
            "action": "link",
            "project": "P",
            "updates": [
                {"id": 1, "linkToId": 2, "type": "parent", "comment": "c"},
                {"id": 1, "type": "hyperlink", "url": "https://docs.example.net/a"},
            ],
        },
    )

    assert collection.only_call().body == [
        _batch_item(
            1,
            [
                {
                    "op": "add",
                    "path": "/relations/-",
                    "value": {
                        "rel": "System.LinkTypes.Hierarchy-Reverse",
                        "url": f"{COLLECTION_URL}/P/_apis/wit/workItems/2",
                        "attributes": {"comment": "c"},
                    },
                },
                {
                    "op": "add",
                    "path": "/relations/-",
                    "value": {
                        "rel": "Hyperlink",
                        "url": "https://docs.example.net/a",
                        "attributes": {"comment": ""},
                    },
                },
            ],
        )
    ]


RELATIONS: list[JsonValue] = [
    {"rel": "System.LinkTypes.Related", "url": "u1"},
    {"rel": "System.LinkTypes.Hierarchy-Reverse", "url": "parent"},
    {"rel": "System.LinkTypes.Related", "url": "u2"},
]


@pytest.mark.parametrize(
    ("work_item", "extra", "document"),
    [
        pytest.param(
            {"rev": 4, "relations": RELATIONS},
            {},
            [
                {"op": "test", "path": "/rev", "value": 4},
                {"op": "remove", "path": "/relations/2"},
                {"op": "remove", "path": "/relations/0"},
            ],
            id="revision-guard-and-highest-index-first",
        ),
        pytest.param(
            {"relations": RELATIONS},
            {"url": "u2"},
            [{"op": "remove", "path": "/relations/2"}],
            id="url-filter-without-revision",
        ),
    ],
)
async def test_unlink_removes_the_matching_relations_and_guards_against_a_changed_item(
    mcp_client: Client,
    collection: FakeCollection,
    work_item: JsonValue,
    extra: dict[str, JsonValue],
    document: JsonValue,
) -> None:
    collection.reply("GET", "P/_apis/wit/workItems/7", work_item)
    collection.reply("PATCH", "P/_apis/wit/workItems/7", {"id": 7})

    output = await call_tool(
        mcp_client,
        "wit_work_item_link_write",
        {"action": "unlink", "project": "P", "id": 7, "type": "related", **extra},
    )

    read, patch = collection.work_calls()
    assert read.query["$expand"] == "Relations"
    assert patch.body == document
    assert "Removed" in output.blocks[0]


async def test_unlink_reports_the_relations_when_none_match_and_changes_nothing(
    mcp_client: Client, collection: FakeCollection
) -> None:
    collection.reply("GET", "P/_apis/wit/workItems/7", {"rev": 1, "relations": RELATIONS})

    output = await call_tool(
        mcp_client,
        "wit_work_item_link_write",
        {"action": "unlink", "project": "P", "id": 7, "type": "tests"},
    )

    assert output.is_error is True
    assert "No matching relations found for link type 'tests'" in output.blocks[0]
    assert [call.method for call in collection.work_calls()] == ["GET"]


@pytest.mark.parametrize(
    ("text", "fmt", "identities", "sent", "format_code"),
    [
        pytest.param(
            "cc @<ana@example.com> a < b & c",
            "Markdown",
            [{"id": ANA_ID, "providerDisplayName": "Ana"}],
            f"cc @<{ANA_ID}> a &lt; b &amp; c",
            "0",
            id="markdown-resolved-mention",
        ),
        pytest.param(
            "cc @<ana@example.com> a < b",
            "Html",
            [{"id": ANA_ID, "providerDisplayName": "Ana"}],
            f'cc <a href="#" data-vss-mention="version:2.0,{ANA_ID}">@Ana</a> a < b',
            "1",
            id="html-resolved-mention",
        ),
        pytest.param(
            f"cc @<{ANA_ID}>",
            "Markdown",
            [],
            f"cc @<{ANA_ID}>",
            "0",
            id="guid-mention-kept",
        ),
        pytest.param(
            "cc @<nobody@example.com>",
            "Markdown",
            [],
            "cc @&lt;nobody@example.com&gt;",
            "0",
            id="unresolved-mention-escaped",
        ),
    ],
)
async def test_comment_text_is_encoded_for_its_format_and_mentions_are_resolved(
    mcp_client: Client,
    collection: FakeCollection,
    text: str,
    fmt: str,
    identities: list[JsonValue],
    sent: str,
    format_code: str,
) -> None:
    collection.reply("GET", "_apis/identities", {"value": identities})
    collection.reply("POST", "P/_apis/wit/workItems/7/comments", {"id": 1})

    await call_tool(
        mcp_client,
        "wit_work_item_comment_write",
        {"action": "add", "project": "P", "workItemId": 7, "text": text, "format": fmt},
    )

    post = collection.work_calls()[-1]
    assert post.body == {"text": sent}
    assert post.query == {"format": format_code, "api-version": "7.2-preview.4"}


async def test_update_comment_patches_the_comment_by_id(
    mcp_client: Client, collection: FakeCollection
) -> None:
    collection.reply("PATCH", "P/_apis/wit/workItems/7/comments/3", {"id": 3})

    await call_tool(
        mcp_client,
        "wit_work_item_comment_write",
        {"action": "update", "project": "P", "workItemId": 7, "commentId": 3, "text": "edit"},
    )

    assert collection.only_call().body == {"text": "edit"}


def _offer_only_the_older_comment_api(collection: FakeCollection) -> None:
    """Make the server offer comment API 7.1-preview.3 as its newest version."""
    collection.locations[COMMENTS_ID].update({"maxVersion": "7.1", "resourceVersion": 3})
    collection.reply("POST", "P/_apis/wit/workItems/7/comments", {"id": 1})


async def test_a_markdown_comment_is_refused_when_the_server_cannot_take_the_format_parameter(
    mcp_client: Client, collection: FakeCollection
) -> None:
    _offer_only_the_older_comment_api(collection)

    output = await call_tool(
        mcp_client,
        "wit_work_item_comment_write",
        {"action": "add", "project": "P", "workItemId": 7, "text": "hi"},
    )

    assert output.data["error"]["code"] == "unsupported_on_server"
    assert collection.work_calls() == []


async def test_an_html_comment_is_sent_without_the_format_parameter_to_an_older_server(
    mcp_client: Client, collection: FakeCollection
) -> None:
    _offer_only_the_older_comment_api(collection)

    await call_tool(
        mcp_client,
        "wit_work_item_comment_write",
        {"action": "add", "project": "P", "workItemId": 7, "text": "hi", "format": "Html"},
    )

    assert collection.only_call().query == {"api-version": "7.1-preview.3"}


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        pytest.param({"action": "update", "id": 7}, "updates is required", id="update-no-updates"),
        pytest.param({"action": "update", "updates": [{"path": "/rev"}]}, "id", id="update-no-id"),
        pytest.param(
            {"action": "update", "id": 7, "updates": [{"op": "add", "path": "/fields/A"}]},
            "value is required for add",
            id="update-add-without-value",
        ),
        pytest.param({"action": "update_batch"}, "batchUpdates is required", id="batch-empty"),
        pytest.param(
            {
                "action": "update_batch",
                "batchUpdates": [
                    {"id": number, "path": "/fields/A", "value": "x"} for number in range(1, 202)
                ],
            },
            "At most 200",
            id="batch-over-200-ids",
        ),
        pytest.param(
            {"action": "create", "project": "P", "fields": [{"name": "A", "value": "x"}]},
            "workItemType is required",
            id="create-no-type",
        ),
        pytest.param(
            {"action": "add_child", "project": "P", "parentId": 1, "workItemType": "Task"},
            "items is required",
            id="add-child-no-items",
        ),
        pytest.param(
            {
                "action": "add_child",
                "project": "P",
                "parentId": 1,
                "workItemType": "Task",
                "items": [{"title": "t", "description": "d"}] * 51,
            },
            "items",
            id="add-child-over-50-items",
        ),
    ],
)
async def test_invalid_work_item_writes_are_rejected_before_any_request(
    mcp_client: Client,
    collection: FakeCollection,
    arguments: dict[str, JsonValue],
    message: str,
) -> None:
    output = await call_tool(mcp_client, "wit_work_item_write", arguments)

    error = output.data["error"]
    assert (output.is_error, error["code"]) == (True, "invalid_input")
    assert message in str(error)
    assert collection.calls == []


@pytest.mark.parametrize(
    ("tool", "arguments", "message"),
    [
        pytest.param(
            "wit_work_item_comment_write",
            {"action": "update", "project": "P", "workItemId": 7, "text": "x"},
            "commentId is required",
            id="comment-update-no-id",
        ),
        pytest.param(
            "wit_work_item_comment_write",
            {"action": "add", "project": "P", "workItemId": 7},
            "text is required",
            id="comment-no-text",
        ),
        pytest.param(
            "wit_work_item_link_write",
            {"action": "link", "project": "P", "updates": [{"id": 1, "type": "hyperlink"}]},
            "url is required",
            id="hyperlink-no-url",
        ),
        pytest.param(
            "wit_work_item_link_write",
            {"action": "link", "project": "P", "updates": [{"id": 1}]},
            "linkToId is required",
            id="link-no-target",
        ),
        pytest.param(
            "wit_work_item_link_write",
            {"action": "unlink", "project": "P", "id": 7},
            "type is required",
            id="unlink-no-type",
        ),
    ],
)
async def test_invalid_comment_and_link_writes_are_rejected_before_any_request(
    mcp_client: Client,
    collection: FakeCollection,
    tool: str,
    arguments: dict[str, JsonValue],
    message: str,
) -> None:
    output = await call_tool(mcp_client, tool, arguments)

    assert (output.is_error, output.data["error"]["code"]) == (True, "invalid_input")
    assert message in output.data["error"]["message"]
    assert collection.calls == []


async def test_a_create_that_returns_no_work_item_is_reported(
    mcp_client: Client, collection: FakeCollection
) -> None:
    collection.reply("POST", "P/_apis/wit/workItems/$Task", raw=b"")

    output = await call_tool(
        mcp_client,
        "wit_work_item_write",
        {
            "action": "create",
            "project": "P",
            "workItemType": "Task",
            "fields": [{"name": "System.Title", "value": "x"}],
        },
    )

    assert (output.is_error, output.blocks) == (True, ["Work item was not created"])


async def test_a_comment_is_still_sent_when_the_mention_lookup_fails(
    mcp_client: Client, collection: FakeCollection
) -> None:
    collection.reply("GET", "_apis/identities", {"message": "down"}, status=500)
    collection.reply("POST", "P/_apis/wit/workItems/7/comments", {"id": 1})

    output = await call_tool(
        mcp_client,
        "wit_work_item_comment_write",
        {"action": "add", "project": "P", "workItemId": 7, "text": "hi @<ana@example.com>"},
    )

    assert output.is_error is False
    assert collection.work_calls()[-1].body == {"text": "hi @&lt;ana@example.com&gt;"}
