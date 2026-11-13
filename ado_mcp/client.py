"""The HTTP client for one Azure DevOps collection. It is the only code that sends requests."""

from collections.abc import Mapping
import json
import logging
from urllib.parse import urlsplit

import httpx2

from ._version import __version__
from .constants import (
    API_VERSION_PARAM,
    CONNECT_TIMEOUT_SECONDS,
    FIRST_HTTP_ERROR_STATUS,
    MAX_ERROR_MESSAGE_CHARS,
    MAX_RESPONSE_BYTES,
    REQUEST_TIMEOUT_SECONDS,
    SERVER_NAME,
    UNSUPPORTED_VERSION_TYPE_KEYS,
)
from .discovery import (
    ResourceLocation,
    expand_route_template,
    negotiate_api_version,
    parse_location,
)
from .exceptions import (
    AdoConnectionError,
    AdoHttpError,
    ResponseTooLargeError,
    UnsupportedOnServerError,
)
from .operations import Operation
from .settings import Settings
from .utils import (
    JsonValue,
    QueryValue,
    build_basic_auth_header,
    build_query,
    encode_path_segment,
    join_collection_url,
)

logger = logging.getLogger(__name__)

RouteValues = Mapping[str, str | int | None]

_DISCOVERY_METHOD = "OPTIONS"
_DISCOVERY_PATH = "_apis/{area}"
_NOT_FOUND = 404
_METHOD_NOT_ALLOWED = 405
_FIRST_REDIRECT_STATUS = 300
_REDIRECT_MESSAGE = "The server answered with a redirect, which ado-mcp does not follow."
_TIMEOUT_MESSAGE = "The request timed out."
_TRANSPORT_MESSAGE = "Could not connect to the collection."
_SEND_MESSAGE = "The request could not be sent."
_NOT_JSON_MESSAGE = "The server answered with a body that is not JSON."
_NO_ROUTE_MESSAGE = "The collection does not advertise the route that {label} needs."
_BAD_VERSION_MESSAGE = "The server does not support API version {version} for {label}."
_TOO_LARGE_MESSAGE = (
    "The reply exceeds {limit} bytes. Lower `top` or `depth`, name fewer fields, "
    "or narrow the query."
)


class AdoClient:
    """Sends REST requests to the configured collection with the PAT.

    Routes and API versions come from per-area discovery (`OPTIONS
    {collection}/_apis/{area}`), cached for the life of the client. Nothing is
    retried: a write is sent once, and so is every read.
    """

    _collection_url: str
    _http: httpx2.AsyncClient
    # Discovered locations per resource area, keyed by lower-cased location ID.
    _locations: dict[str, dict[str, ResourceLocation]]

    def __init__(self, settings: Settings) -> None:
        self._collection_url = settings.collection_url
        # The Authorization value is built once here and lives only in the
        # client's default headers. Certificate verification and proxy
        # environment variables keep their library defaults (on).
        self._http = httpx2.AsyncClient(
            headers={
                "Authorization": build_basic_auth_header(settings.pat.get_secret_value()),
                "Accept": "application/json",
                "User-Agent": f"{SERVER_NAME}/{__version__}",
            },
            timeout=httpx2.Timeout(REQUEST_TIMEOUT_SECONDS, connect=CONNECT_TIMEOUT_SECONDS),
            follow_redirects=False,
        )
        self._locations = {}

    async def send(
        self,
        operation: Operation,
        *,
        label: str,
        method: str,
        route_values: RouteValues | None = None,
        query: Mapping[str, QueryValue] | None = None,
        json_body: JsonValue = None,
        content_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        version_override: str | None = None,
    ) -> JsonValue:
        """Send one request and return the parsed JSON reply (`None` for an empty body).

        `label` names the tool action, for example `wit_work_item.get`, in
        errors and logs.
        """
        path, version, on_fallback = await self._resolve(
            operation, route_values or {}, version_override, label
        )
        params = build_query(query or {})
        if version is not None:
            params[API_VERSION_PARAM] = version
        return await self._request(
            method,
            join_collection_url(self._collection_url, path),
            label=label,
            params=params,
            json_body=json_body,
            content_type=content_type,
            headers=headers,
            on_fallback=on_fallback,
            version=version,
        )

    async def negotiated_version(
        self, operation: Operation, requested: str, *, label: str
    ) -> str | None:
        """Return the version `send` would use for `requested`, or `None` with no location."""
        if operation.area is None or operation.location_id is None:
            return None
        locations = await self._area_locations(operation.area, label)
        location = locations.get(operation.location_id)
        if location is None:
            return None
        return negotiate_api_version(requested, location)

    async def aclose(self) -> None:
        """Close the underlying HTTP connections."""
        await self._http.aclose()

    async def _resolve(
        self,
        operation: Operation,
        route_values: RouteValues,
        version_override: str | None,
        label: str,
    ) -> tuple[str, str | None, bool]:
        """Return the relative path, the API version, and whether the path is the fixed fallback.

        The flag is true only when the operation's `fallback_path` is used, so a 404
        or 405 is read as "route absent" only for that fixed route, never for a
        discovered route that happens to expand to the same text.
        """
        requested = version_override or operation.requested_version
        if operation.area is None or operation.location_id is None or requested is None:
            # A fixed-route operation; every such entry in `operations.py` has a path.
            if operation.fallback_path is None:
                raise UnsupportedOnServerError(_NO_ROUTE_MESSAGE.format(label=label), label=label)
            return operation.fallback_path, operation.fallback_version, True
        locations = await self._area_locations(operation.area, label)
        location = locations.get(operation.location_id)
        if location is not None:
            # `area` and `resource` default to the location's own names.
            values = {"area": location.area, "resource": location.resource_name, **route_values}
            path = expand_route_template(location.route_template, values)
            return path, negotiate_api_version(requested, location), False
        if operation.fallback_path is not None:
            return operation.fallback_path, operation.fallback_version, True
        raise UnsupportedOnServerError(_NO_ROUTE_MESSAGE.format(label=label), label=label)

    async def _area_locations(self, area: str, label: str) -> dict[str, ResourceLocation]:
        """Return the discovered locations of a resource area, discovering them on first use.

        A 404 or an empty reply means "no locations" and is not cached, so a later
        call tries again. Any other failure is raised, so an authentication error
        never looks like an unsupported route. Two concurrent first calls may both
        discover; the results are identical.
        """
        cached = self._locations.get(area)
        if cached is not None:
            return cached
        path = _DISCOVERY_PATH.format(area=encode_path_segment(area))
        reply = await self._request(
            _DISCOVERY_METHOD,
            join_collection_url(self._collection_url, path),
            label=label,
            params={},
            allow_not_found=True,
        )
        entries = reply.get("value") if isinstance(reply, dict) else None
        if not isinstance(entries, list):
            return {}
        locations = {}
        for entry in entries:
            location = parse_location(entry) if isinstance(entry, dict) else None
            if location is not None:
                locations[location.id] = location
        self._locations[area] = locations
        return locations

    async def _request(
        self,
        method: str,
        url: str,
        *,
        label: str,
        params: dict[str, str],
        json_body: JsonValue = None,
        content_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        on_fallback: bool = False,
        version: str | None = None,
        allow_not_found: bool = False,
    ) -> JsonValue:
        """Send one request, bound the reply size, and map failures to this project's errors.

        `allow_not_found` returns `None` for a 404 instead of raising; discovery
        uses it. The query string, headers, and bodies are never logged.
        """
        path = urlsplit(url).path
        request_headers = dict(headers or {})
        content = None
        if content_type is not None:
            request_headers["Content-Type"] = content_type
            content = json.dumps(json_body)
        try:
            async with self._http.stream(
                method,
                url,
                params=params,
                content=content,
                json=json_body if content is None else None,
                headers=request_headers,
                follow_redirects=False,
            ) as response:
                status = response.status_code
                logger.debug("%s %s %s -> %s", label, method, path, status)
                if status == _NOT_FOUND and allow_not_found:
                    return None
                body = await self._read_body(response, label=label, status=status)
        except ResponseTooLargeError:
            logger.exception("%s %s %s failed: reply too large", label, method, path)
            raise
        except httpx2.TimeoutException:
            logger.exception("%s %s %s failed: timeout", label, method, path)
            raise AdoConnectionError(_TIMEOUT_MESSAGE, label=label) from None
        except httpx2.TransportError:
            logger.exception("%s %s %s failed: transport", label, method, path)
            raise AdoConnectionError(_TRANSPORT_MESSAGE, label=label) from None
        except (httpx2.HTTPError, httpx2.InvalidURL):
            logger.exception("%s %s %s failed: request not sent", label, method, path)
            raise AdoConnectionError(_SEND_MESSAGE, label=label) from None
        if status >= _FIRST_REDIRECT_STATUS:
            error = self._error_from_response(status, body, label, on_fallback, version)
            logger.error("%s %s %s failed: %s", label, method, path, error.code)
            raise error
        return self._parse_success(body, label=label, status=status)

    @staticmethod
    async def _read_body(response: httpx2.Response, *, label: str, status: int) -> bytes:
        """Read the reply body, stopping once it exceeds `MAX_RESPONSE_BYTES`."""
        too_large = _TOO_LARGE_MESSAGE.format(limit=MAX_RESPONSE_BYTES)
        declared = response.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > MAX_RESPONSE_BYTES:
            raise ResponseTooLargeError(too_large, label=label, status=status)
        chunks = []
        received = 0
        async for chunk in response.aiter_bytes():
            received += len(chunk)
            if received > MAX_RESPONSE_BYTES:
                raise ResponseTooLargeError(too_large, label=label, status=status)
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _parse_success(body: bytes, *, label: str, status: int) -> JsonValue:
        """Parse a success reply; an empty body is `None`, a non-JSON body is an error."""
        if not body.strip():
            return None
        try:
            return json.loads(body)
        except ValueError:
            logger.exception("%s reply is not JSON (HTTP %s)", label, status)
            raise AdoHttpError(_NOT_JSON_MESSAGE, label=label, status=status) from None

    @staticmethod
    def _error_from_response(
        status: int,
        body: bytes,
        label: str,
        on_fallback: bool,
        version: str | None,
    ) -> AdoConnectionError | AdoHttpError | UnsupportedOnServerError:
        """Map a redirect or error reply to the error the caller sees."""
        if status < FIRST_HTTP_ERROR_STATUS:
            # Redirects are never followed, so the PAT never reaches another URL.
            return AdoConnectionError(_REDIRECT_MESSAGE, label=label, status=status)
        try:
            payload = json.loads(body) if body.strip() else None
        except ValueError:
            payload = None
        details = payload if isinstance(payload, dict) else {}
        if details.get("typeKey") in UNSUPPORTED_VERSION_TYPE_KEYS:
            return UnsupportedOnServerError(
                _BAD_VERSION_MESSAGE.format(version=version, label=label),
                label=label,
                status=status,
            )
        if on_fallback and status in (_NOT_FOUND, _METHOD_NOT_ALLOWED):
            # A fixed route has no entity in its path, so 404 or 405 means the
            # route itself is absent on this server.
            return UnsupportedOnServerError(
                _NO_ROUTE_MESSAGE.format(label=label), label=label, status=status
            )
        message = details.get("message")
        text = message[:MAX_ERROR_MESSAGE_CHARS] if isinstance(message, str) else f"HTTP {status}"
        return AdoHttpError(text, label=label, status=status)
