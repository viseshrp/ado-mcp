from fastmcp import Client
from mcp_types import ElicitRequestFormParams, ElicitResult
import pytest

from ado_mcp.utils import JsonValue
from tests.fake_collection import FakeCollection, call_tool, make_client

pytestmark = pytest.mark.anyio

ITERATIONS: dict[str, JsonValue] = {"action": "list_team_iterations"}
PROJECTS: list[JsonValue] = [{"name": "Alpha"}, {"name": "Beta"}]
TEAMS: list[JsonValue] = [{"name": "Gamma"}, {"name": "Delta"}]


class Picker:
    """An elicitation handler that answers from a script and records the choices it was offered.

    A `None` answer declines the question.
    """

    offered: list[list[str]]
    _answers: dict[str, str | None]

    def __init__(self, project: str | None = "Beta", team: str | None = "Gamma") -> None:
        self.offered = []
        self._answers = {"project": project, "team": team}

    async def handle(
        self, message: str, _response_type: type, params: ElicitRequestFormParams, context: object
    ) -> dict[str, str] | ElicitResult:
        """Answer one question; the handshake and per-request protocols word the schema alike."""
        field, schema = next(iter(params.requested_schema["properties"].items()))
        choices = (
            schema["enum"] if "enum" in schema else [item["const"] for item in schema["oneOf"]]
        )
        self.offered.append(choices)
        answer = self._answers["project" if "project" in message else "team"]
        if answer is None:
            return ElicitResult(action="decline")
        return {field: answer}


@pytest.fixture(params=["auto", "legacy"])
def era(request: pytest.FixtureRequest) -> str:
    """The protocol era of the connection: the per-request one, then the initialize handshake."""
    return request.param


@pytest.fixture
def listed(collection: FakeCollection) -> FakeCollection:
    """A collection with two projects, and teams under Beta."""
    collection.reply("GET", "_apis/projects", {"value": PROJECTS})
    collection.reply("GET", "_apis/projects/Beta/teams", {"value": TEAMS})
    collection.reply("GET", "Beta/Gamma/_apis/work/teamsettings/iterations", {"value": []})
    return collection


async def test_a_missing_project_and_team_are_picked_by_the_user(
    era: str, listed: FakeCollection
) -> None:
    picker = Picker()

    async with make_client(mode=era, elicitation_handler=picker.handle) as client:
        output = await call_tool(client, "work", ITERATIONS)

    assert output.blocks[0] == "Project: Beta, Team: Gamma"
    assert picker.offered == [["Alpha", "Beta"], ["Gamma", "Delta"]]
    assert listed.calls[1].query["$top"] == "100"
    assert listed.work_calls()[-1].path == "Beta/Gamma/_apis/work/teamsettings/iterations"


@pytest.mark.parametrize(
    ("arguments", "text"),
    [
        pytest.param(ITERATIONS, "Project selection cancelled.", id="project"),
        pytest.param({**ITERATIONS, "project": "Beta"}, "Team selection cancelled.", id="team"),
    ],
)
async def test_a_declined_picker_ends_the_call_with_upstreams_cancel_text(
    era: str, listed: FakeCollection, arguments: dict[str, JsonValue], text: str
) -> None:
    picker = Picker(project=None, team=None)

    async with make_client(mode=era, elicitation_handler=picker.handle) as client:
        output = await call_tool(client, "work", arguments)

    assert (output.is_error, output.blocks) == (False, [text])


async def test_the_picker_offers_each_name_once_and_falls_back_to_the_id(
    listed: FakeCollection,
) -> None:
    entries = [{"name": "A"}, {"id": "b-1"}, {"name": "A"}, {"name": " "}, "junk"]
    listed.reply("GET", "_apis/projects", {"value": entries})
    picker = Picker(project=None)

    async with make_client(elicitation_handler=picker.handle) as client:
        await call_tool(client, "work", ITERATIONS)

    assert picker.offered == [["A", "b-1"]]


@pytest.mark.parametrize(
    ("arguments", "reply", "text"),
    [
        pytest.param(ITERATIONS, {"value": []}, "No projects found to select from.", id="project"),
        pytest.param(
            {**ITERATIONS, "project": "Empty"},
            {"value": []},
            "No teams found to select from.",
            id="team",
        ),
    ],
)
async def test_a_picker_with_nothing_to_choose_from_is_an_error(
    collection: FakeCollection, arguments: dict[str, JsonValue], reply: JsonValue, text: str
) -> None:
    collection.reply("GET", "_apis/projects", reply)
    collection.reply("GET", "_apis/projects/Empty/teams", reply)

    async with make_client(elicitation_handler=Picker().handle) as client:
        output = await call_tool(client, "work", arguments)

    assert (output.is_error, output.blocks) == (True, [text])


@pytest.mark.parametrize(
    ("arguments", "hint"),
    [
        pytest.param(ITERATIONS, "Pass 'project' or set ADO_PROJECT.", id="project"),
        pytest.param({**ITERATIONS, "project": "P"}, "Pass 'team' or set ADO_TEAM.", id="team"),
    ],
)
async def test_without_elicitation_a_missing_project_or_team_is_an_error_naming_the_fix(
    mcp_client: Client,
    collection: FakeCollection,
    arguments: dict[str, JsonValue],
    hint: str,
) -> None:
    output = await call_tool(mcp_client, "work", arguments)

    error = output.data["error"]
    assert (output.is_error, error["code"]) == (True, "missing_project_or_team")
    assert hint in error["message"]
    assert collection.calls == []


@pytest.mark.parametrize(
    ("arguments", "path"),
    [
        pytest.param(ITERATIONS, "DefaultP/DefaultT", id="settings-default"),
        pytest.param({**ITERATIONS, "project": "ArgP", "team": "ArgT"}, "ArgP/ArgT", id="argument"),
    ],
)
async def test_the_default_project_and_team_apply_only_when_no_argument_is_given(
    monkeypatch: pytest.MonkeyPatch,
    collection: FakeCollection,
    arguments: dict[str, JsonValue],
    path: str,
) -> None:
    monkeypatch.setenv("ADO_PROJECT", "DefaultP")
    monkeypatch.setenv("ADO_TEAM", "DefaultT")
    collection.reply("GET", f"{path}/_apis/work/teamsettings/iterations", {"value": []})

    async with make_client() as client:
        output = await call_tool(client, "work", arguments)

    assert output.is_error is False
    assert collection.only_call().path == f"{path}/_apis/work/teamsettings/iterations"
