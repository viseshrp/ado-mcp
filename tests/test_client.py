import base64
from collections.abc import AsyncIterator

import httpx2
import pytest

from ado_mcp.client import AdoClient
from ado_mcp.constants import MAX_RESPONSE_BYTES
from ado_mcp.exceptions import (
    AdoConnectionError,
    AdoHttpError,
    AdoMcpError,
    ResponseTooLargeError,
    UnsupportedOnServerError,
)
from ado_mcp.operations import (
    IDENTITIES,
    PROJECTS,
    WORK_ITEM_BATCH_UPDATE,
    WORK_ITEM_SEARCH,
    Operation,
)
from ado_mcp.settings import load_settings
from tests.fake_collection import COLLECTION_URL, IDENTITIES_ID, PAT, PROJECTS_ID, FakeCollection

pytestmark = pytest.mark.anyio

LABEL = "core_list_projects"


@pytest.fixture
async def ado(collection: FakeCollection) -> AsyncIterator[AdoClient]:
    client = AdoClient(load_settings())
    yield client
    await client.aclose()


async def _send_get(client: AdoClient, operation: Operation = PROJECTS) -> object:
    return await client.send(operation, label=LABEL, method="GET")


async def test_requests_carry_the_pat_only_in_the_basic_header_and_stay_on_the_collection(
    ado: AdoClient, collection: FakeCollection
) -> None:
    collection.reply("GET", "_apis/projects", {"value": []})

    await _send_get(ado)

    expected_header = "Basic " + base64.b64encode(f":{PAT}".encode()).decode()
    assert [call.method for call in collection.calls] == ["OPTIONS", "GET"]
    for call in collection.calls:
        assert call.headers["authorization"] == expected_header
        assert call.url.startswith(f"{COLLECTION_URL}/_apis/")
        assert PAT not in call.url
    assert collection.only_call().query == {"api-version": "7.2-preview.4"}


async def test_a_redirect_is_an_error_and_is_not_followed(
    ado: AdoClient, collection: FakeCollection
) -> None:
    collection.reply(
        "GET", "_apis/projects", status=302, headers={"Location": "https://other.example.net/x"}
    )

    with pytest.raises(AdoConnectionError) as raised:
        await _send_get(ado)

    assert (raised.value.code, raised.value.status) == ("connection_failed", 302)
    assert [call.path for call in collection.work_calls()] == ["_apis/projects"]


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "authentication_failed"),
        (403, "permission_denied"),
        (404, "not_found"),
        (409, "conflict"),
        (412, "precondition_failed"),
        (500, "request_failed"),
    ],
)
async def test_http_error_statuses_map_to_error_codes_with_the_servers_message(
    ado: AdoClient, collection: FakeCollection, status: int, code: str
) -> None:
    collection.reply("GET", "_apis/projects", {"message": "server says no"}, status=status)

    with pytest.raises(AdoHttpError) as raised:
        await _send_get(ado)

    assert (raised.value.code, raised.value.status) == (code, status)
    assert "server says no" in str(raised.value)


async def test_an_error_reply_that_is_not_json_still_maps_to_its_status_code(
    ado: AdoClient, collection: FakeCollection
) -> None:
    collection.reply("GET", "_apis/projects", raw=b"<html>denied</html>", status=401)

    with pytest.raises(AdoHttpError) as raised:
        await _send_get(ado)

    assert (raised.value.code, raised.value.status) == ("authentication_failed", 401)
    assert "<html>" not in str(raised.value)


async def test_a_version_rejection_reply_is_unsupported_on_server(
    ado: AdoClient, collection: FakeCollection
) -> None:
    collection.reply(
        "GET", "_apis/projects", {"typeKey": "VssVersionOutOfRangeException"}, status=400
    )

    with pytest.raises(UnsupportedOnServerError, match=r"API version 7\.2-preview\.4"):
        await _send_get(ado)


async def test_an_unadvertised_location_without_a_fallback_is_unsupported_on_server(
    ado: AdoClient, collection: FakeCollection
) -> None:
    del collection.locations[PROJECTS_ID]

    with pytest.raises(UnsupportedOnServerError, match=LABEL):
        await _send_get(ado)

    assert collection.work_calls() == []


@pytest.mark.parametrize(
    ("operation", "path"),
    [
        pytest.param(WORK_ITEM_SEARCH, "_apis/search/workitemsearchresults", id="search"),
        pytest.param(IDENTITIES, "_apis/identities", id="identities"),
    ],
)
async def test_search_and_identity_fall_back_to_their_fixed_route(
    ado: AdoClient, collection: FakeCollection, operation: Operation, path: str
) -> None:
    collection.reply("GET", path, {"ok": True})
    assert await _send_get(ado, operation) == {"ok": True}
    assert collection.only_call().query == {"api-version": "7.2-preview.1"}

    collection.reply("GET", path, status=404)
    with pytest.raises(UnsupportedOnServerError):
        await _send_get(ado, operation)


async def test_a_404_on_an_advertised_route_is_not_found_even_when_it_matches_the_fallback(
    ado: AdoClient, collection: FakeCollection
) -> None:
    collection.locations[IDENTITIES_ID] = {
        "id": IDENTITIES_ID,
        "area": "IMS",
        "resourceName": "identities",
        "routeTemplate": "_apis/{resource}",
        "releasedVersion": "0.0",
        "maxVersion": "7.2",
        "resourceVersion": 1,
    }
    collection.reply("GET", "_apis/identities", status=404)

    with pytest.raises(AdoHttpError) as raised:
        await _send_get(ado, IDENTITIES)

    assert raised.value.code == "not_found"


async def test_a_collection_with_no_discovery_endpoint_is_asked_again_on_the_next_call(
    ado: AdoClient, collection: FakeCollection
) -> None:
    collection.reply("OPTIONS", "_apis/core", status=404)

    for _ in range(2):
        with pytest.raises(UnsupportedOnServerError):
            await _send_get(ado)

    assert [call.method for call in collection.calls] == ["OPTIONS", "OPTIONS"]


async def test_discovery_runs_once_per_area(ado: AdoClient, collection: FakeCollection) -> None:
    collection.reply("GET", "_apis/projects", {"value": []})

    await _send_get(ado)
    await _send_get(ado)

    assert [call.method for call in collection.calls] == ["OPTIONS", "GET", "GET"]


async def test_a_failed_discovery_is_an_http_error_not_an_unsupported_route(
    ado: AdoClient, collection: FakeCollection
) -> None:
    collection.reply("OPTIONS", "_apis/core", status=401)

    with pytest.raises(AdoHttpError) as raised:
        await _send_get(ado)

    assert raised.value.code == "authentication_failed"


async def _chunks() -> AsyncIterator[bytes]:
    """A reply of unknown length that goes over the limit while it streams."""
    yield b"x" * MAX_RESPONSE_BYTES
    yield b"x"


@pytest.mark.parametrize(
    "reply",
    [
        pytest.param({"raw": b"x" * (MAX_RESPONSE_BYTES + 1)}, id="declared-length"),
        pytest.param({"raw": _chunks()}, id="streamed"),
    ],
)
async def test_a_reply_over_the_size_limit_is_an_error_not_a_truncation(
    ado: AdoClient, collection: FakeCollection, reply: dict[str, object]
) -> None:
    collection.reply("GET", "_apis/projects", **reply)

    with pytest.raises(ResponseTooLargeError) as raised:
        await _send_get(ado)

    assert raised.value.code == "response_too_large"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [pytest.param(b"", None, id="empty"), pytest.param(b'{"a": 1}', {"a": 1}, id="json")],
)
async def test_a_success_reply_is_parsed_and_an_empty_one_is_none(
    ado: AdoClient, collection: FakeCollection, raw: bytes, expected: object
) -> None:
    collection.reply("GET", "_apis/projects", raw=raw)

    assert await _send_get(ado) == expected


async def test_a_success_reply_that_is_not_json_is_an_invalid_response(
    ado: AdoClient, collection: FakeCollection
) -> None:
    collection.reply("GET", "_apis/projects", raw=b"<html>login</html>")

    with pytest.raises(AdoHttpError) as raised:
        await _send_get(ado)

    assert raised.value.code == "invalid_response"


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(httpx2.ConnectTimeout("slow"), id="timeout"),
        pytest.param(httpx2.ConnectError("refused"), id="transport"),
        pytest.param(httpx2.DecodingError("bad"), id="not-sent"),
    ],
)
async def test_a_failed_write_is_reported_as_connection_failed_and_sent_once(
    ado: AdoClient,
    collection: FakeCollection,
    caplog: pytest.LogCaptureFixture,
    failure: Exception,
) -> None:
    collection.reply("PATCH", "_apis/wit/$batch", error=failure)

    with pytest.raises(AdoMcpError) as raised:
        await ado.send(WORK_ITEM_BATCH_UPDATE, label="w", method="PATCH", json_body=[])

    assert raised.value.code == "connection_failed"
    assert PAT not in str(raised.value)
    assert PAT not in caplog.text
    assert [call.method for call in collection.calls] == ["PATCH"]
