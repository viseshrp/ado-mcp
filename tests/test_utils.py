from collections.abc import Callable

import pytest

from ado_mcp import utils

COLLECTION = "https://ado.example.net/tfs/DefaultCollection"


@pytest.mark.parametrize(
    ("function", "arguments", "expected"),
    [
        pytest.param(utils.build_basic_auth_header, ("abc",), "Basic OmFiYw==", id="basic-auth"),
        pytest.param(
            utils.encode_path_segment, ("My Project/A",), "My%20Project%2FA", id="path-segment"
        ),
        pytest.param(
            utils.join_collection_url,
            (COLLECTION, "/_apis/wit"),
            f"{COLLECTION}/_apis/wit",
            id="join-keeps-collection-path",
        ),
        pytest.param(
            utils.build_query,
            ({"$top": 5, "mine": None, "includeCompleted": False},),
            {"$top": "5", "includeCompleted": "false"},
            id="query-drops-none-and-lowercases-booleans",
        ),
        pytest.param(
            utils.work_item_url,
            (COLLECTION, "My Project", 7),
            f"{COLLECTION}/My%20Project/_apis/wit/workItems/7",
            id="work-item-url",
        ),
        pytest.param(
            utils.encode_markdown_value, ("a < b", "Markdown"), "a &lt; b", id="markdown-encoded"
        ),
        pytest.param(utils.encode_markdown_value, ("a < b", "Html"), "a < b", id="html-untouched"),
        pytest.param(utils.encode_markdown_value, ("a < b", None), "a < b", id="no-format"),
        pytest.param(
            utils.escape_html,
            ("<a href='x'>&",),
            "&lt;a href=&#39;x&#39;&gt;&amp;",
            id="escape-html",
        ),
        pytest.param(utils.to_json_text, ({"a": "é"},), '{\n  "a": "é"\n}', id="json-text"),
    ],
)
def test_string_helpers_follow_their_documented_examples(
    function: Callable[..., object], arguments: tuple[object, ...], expected: object
) -> None:
    assert function(*arguments) == expected
