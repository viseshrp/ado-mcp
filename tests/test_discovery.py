import pytest

from ado_mcp.discovery import (
    expand_route_template,
    negotiate_api_version,
    parse_api_version,
    parse_location,
)
from ado_mcp.utils import JsonValue


def _entry(released: str, maximum: str, resource_version: int) -> dict[str, JsonValue]:
    """One discovery-reply entry, as the server sends it."""
    return {
        "id": "ABC",
        "area": "wit",
        "resourceName": "workItems",
        "routeTemplate": "_apis/{area}/{resource}",
        "releasedVersion": released,
        "maxVersion": maximum,
        "resourceVersion": resource_version,
    }


@pytest.mark.parametrize(
    ("requested", "released", "maximum", "resource_version", "expected"),
    [
        pytest.param("7.1-preview.3", "7.1", "7.1", 3, "7.1-preview.3", id="released-keeps"),
        pytest.param("7.2-preview.1", "7.1", "7.1", 1, "7.1", id="newer-than-server"),
        pytest.param("7.2-preview.4", "0.0", "7.1", 3, "7.1-preview.3", id="max-preview-version"),
        pytest.param("7.1-preview.3", "0.0", "7.2", 2, "7.1-preview", id="resource-too-new"),
        pytest.param("7.2-preview.1", "0.0", "7.2", 1, "7.2-preview.1", id="within-resource"),
    ],
)
def test_api_version_is_negotiated_against_the_advertised_location(
    requested: str, released: str, maximum: str, resource_version: int, expected: str
) -> None:
    location = parse_location(_entry(released, maximum, resource_version))

    assert location is not None
    assert negotiate_api_version(requested, location) == expected


def test_api_versions_compare_numerically_not_as_decimals() -> None:
    location = parse_location(_entry("7.1", "7.1", 1))

    assert location is not None
    assert negotiate_api_version("7.10", location) == "7.1"
    assert parse_api_version("7.1-preview.3").resource_version == 3
    with pytest.raises(ValueError, match="seven"):
        parse_api_version("seven")


@pytest.mark.parametrize(
    "broken",
    [
        pytest.param({"releasedVersion": "soon"}, id="unparseable-version"),
        pytest.param({"routeTemplate": None}, id="missing-field"),
        pytest.param({"resourceVersion": True}, id="boolean-resource-version"),
    ],
)
def test_a_malformed_location_is_skipped(broken: dict[str, JsonValue]) -> None:
    assert parse_location({**_entry("7.1", "7.1", 1), **broken}) is None


@pytest.mark.parametrize(
    ("template", "values", "expected"),
    [
        pytest.param(
            "{project}/{team}/_apis/{area}/{resource}",
            {"project": "My Project", "area": "work", "resource": "backlogs"},
            "My%20Project/_apis/work/backlogs",
            id="empty-segment-dropped",
        ),
        pytest.param(
            "{project}/_apis/{area}/{resource}/${type}",
            {"project": "P", "area": "wit", "resource": "workItems", "type": "User Story"},
            "P/_apis/wit/workItems/$User%20Story",
            id="literal-dollar",
        ),
        pytest.param(
            "_apis/{area}/{resource}/{*path}",
            {"area": "wit", "resource": "classificationNodes", "path": "a/b", "id": 42},
            "_apis/wit/classificationNodes/a%2Fb",
            id="wildcard-parameter",
        ),
        pytest.param("{{literal}}/{id}", {"id": 42}, "{literal}/42", id="escaped-braces"),
    ],
)
def test_route_templates_expand_with_encoded_route_values(
    template: str, values: dict[str, str | int | None], expected: str
) -> None:
    assert expand_route_template(template, values) == expected
