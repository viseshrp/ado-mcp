"""Route discovery helpers: API-version parsing and negotiation, route expansion.

The behavior follows `VsoClient.js` in `azure-devops-node-api` 15.1.2. The SDK
compares versions as floating-point numbers; this module compares
`(major, minor)` integer pairs, which agree for every published version and do
not read `7.10` as `7.1`.
"""

from collections.abc import Mapping
from dataclasses import dataclass
import re

from .utils import encode_path_segment

_API_VERSION_PATTERN = re.compile(r"(\d+)\.(\d+)(-preview(\.(\d+))?)?")
_PREVIEW_SUFFIX = "-preview"
# Characters removed from a route parameter name before lookup, so that a
# wildcard parameter such as `{*path}` matches the route value `path`.
_NON_ALPHANUMERIC = re.compile(r"[^A-Za-z0-9]")


@dataclass(frozen=True)
class ApiVersion:
    """A parsed REST API version, such as `7.1-preview.3`."""

    major: int
    minor: int
    is_preview: bool
    resource_version: int | None


@dataclass(frozen=True)
class ResourceLocation:
    """The fields of one discovery-reply entry that route resolution reads."""

    id: str  # lower-cased
    area: str
    resource_name: str
    route_template: str
    released_version: tuple[int, int]
    max_version: tuple[int, int]
    max_version_text: str
    released_version_text: str
    resource_version: int


def parse_api_version(text: str) -> ApiVersion:
    """Parse `major.minor[-preview[.resource]]`; raise `ValueError` otherwise.

    Examples: `"7.1"` -> `ApiVersion(7, 1, False, None)`;
    `"7.2-preview"` -> `ApiVersion(7, 2, True, None)`;
    `"7.1-preview.3"` -> `ApiVersion(7, 1, True, 3)`.
    """
    match = _API_VERSION_PATTERN.fullmatch(text)
    if match is None:
        raise ValueError(text)
    resource = match.group(5)
    return ApiVersion(
        major=int(match.group(1)),
        minor=int(match.group(2)),
        is_preview=match.group(3) is not None,
        resource_version=int(resource) if resource is not None else None,
    )


def parse_location(raw: Mapping[str, object]) -> ResourceLocation | None:
    """Read one discovery entry, or return `None` when a field is missing or malformed.

    Skipping a bad entry keeps one malformed location from breaking the area.
    """
    location_id = raw.get("id")
    area = raw.get("area")
    resource_name = raw.get("resourceName")
    route_template = raw.get("routeTemplate")
    released_text = raw.get("releasedVersion")
    max_text = raw.get("maxVersion")
    resource_version = raw.get("resourceVersion")
    if not (
        isinstance(location_id, str)
        and isinstance(area, str)
        and isinstance(resource_name, str)
        and isinstance(route_template, str)
        and isinstance(released_text, str)
        and isinstance(max_text, str)
        and isinstance(resource_version, int)
        and not isinstance(resource_version, bool)
    ):
        return None
    try:
        released = parse_api_version(released_text)
        maximum = parse_api_version(max_text)
    except ValueError:
        return None
    return ResourceLocation(
        id=location_id.lower(),
        area=area,
        resource_name=resource_name,
        route_template=route_template,
        released_version=(released.major, released.minor),
        max_version=(maximum.major, maximum.minor),
        max_version_text=max_text,
        released_version_text=released_text,
        resource_version=resource_version,
    )


def negotiate_api_version(requested: str, location: ResourceLocation) -> str:
    """Pick the API version to send for `requested` against a discovered location.

    The requested version is kept when it is released on the server, when it is
    a plain preview within the server's maximum, or when its resource version is
    within the server's. Otherwise the closest version the server offers is used.

    Examples (requested; location released / max / resource -> result):

    - `7.1-preview.3`; `7.1` / `7.1` / `3` -> `7.1-preview.3`
    - `7.2-preview.1`; `7.1` / `7.1` / `1` -> `7.1`
    - `7.2-preview.4`; `0.0` / `7.1` / `3` -> `7.1-preview.3`
    - `7.1-preview.3`; `0.0` / `7.2` / `2` -> `7.1-preview`
    - `7.2-preview.1`; `0.0` / `7.2` / `1` -> `7.2-preview.1`
    """
    version = parse_api_version(requested)
    major_minor = (version.major, version.minor)
    if major_minor <= location.released_version:
        return requested
    within_max = major_minor <= location.max_version
    if version.is_preview and version.resource_version is None and within_max:
        return requested
    if (
        version.resource_version is not None
        and within_max
        and version.resource_version <= location.resource_version
    ):
        return requested
    if major_minor < location.max_version:
        return f"{version.major}.{version.minor}{_PREVIEW_SUFFIX}"
    if location.max_version_text == location.released_version_text:
        return location.max_version_text
    return f"{location.max_version_text}{_PREVIEW_SUFFIX}.{location.resource_version}"


def _route_value(name: str, route_values: Mapping[str, str | int | None]) -> str:
    """Return the encoded value for a route parameter, or `""` when it has none."""
    value = route_values.get(name)
    if value is None or value == "":
        value = route_values.get(_NON_ALPHANUMERIC.sub("", name))
    if value is None or value == "":
        return ""
    return encode_path_segment(value)


def _expand_segment(segment: str, route_values: Mapping[str, str | int | None]) -> str:
    """Replace the `{name}` parameters of one path segment; `{{` and `}}` are literal braces."""
    parts = []
    index = 0
    while index < len(segment):
        pair = segment[index : index + 2]
        if pair in ("{{", "}}"):
            parts.append(pair[0])
            index += 2
            continue
        if segment[index] == "{":
            end = segment.find("}", index + 1)
            if end != -1:
                parts.append(_route_value(segment[index + 1 : end], route_values))
                index = end + 1
                continue
        parts.append(segment[index])
        index += 1
    return "".join(parts)


def expand_route_template(template: str, route_values: Mapping[str, str | int | None]) -> str:
    """Fill a discovered route template with URL-encoded route values.

    A missing, `None`, or empty value produces nothing, and a path segment that
    ends up empty is dropped.

    Examples:

    - `{project}/{team}/_apis/{area}/{resource}` with project `My Project`, area
      `work`, resource `backlogs` -> `My%20Project/_apis/work/backlogs`
    - `{project}/_apis/{area}/{resource}/${type}` with project `P`, area `wit`,
      resource `workItems`, type `User Story` -> `P/_apis/wit/workItems/$User%20Story`
    - `_apis/{area}/{resource}/{id}` with area `wit`, resource `workItems`, id `42`
      -> `_apis/wit/workItems/42`
    """
    segments = (_expand_segment(segment, route_values) for segment in template.split("/"))
    return "/".join(segment for segment in segments if segment)
