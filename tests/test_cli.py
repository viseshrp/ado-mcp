from pathlib import Path

from click.testing import CliRunner
from fastmcp import FastMCP
import pytest

from ado_mcp import __version__, cli
from tests.fake_collection import COLLECTION_URL, PAT


@pytest.mark.parametrize("options", [["-h"], ["--help"]])
def test_help(options: list[str]) -> None:
    runner = CliRunner()
    result = runner.invoke(cli.main, options)

    assert result.exit_code == 0, f"Help options {options} failed with exit code {result.exit_code}"
    assert result.output.startswith("Usage: "), (
        f"Help output for {options} did not start with 'Usage:'"
    )
    assert "-h, --help" in result.output, f"Help flags missing from output for {options}"


@pytest.mark.parametrize("options", [["-v"], ["--version"]])
def test_version(options: list[str]) -> None:
    runner = CliRunner()
    result = runner.invoke(cli.main, options)

    assert result.exit_code == 0, (
        f"Version options {options} failed with exit code {result.exit_code}"
    )
    assert __version__ in result.output, (
        f"Expected version {__version__} not found in output for {options}"
    )


def test_port_requires_http() -> None:
    result = CliRunner().invoke(cli.main, ["--port", "9000"])

    assert result.exit_code != 0
    assert "--port requires --http" in result.output


def test_invalid_settings_exit_with_code_1_and_a_plain_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ADO_COLLECTION_URL", raising=False)
    monkeypatch.setenv("ADO_PAT", PAT)

    result = CliRunner().invoke(cli.main, [])

    assert result.exit_code == 1
    assert result.output.startswith("Error: ")
    assert "ADO_COLLECTION_URL" in result.output
    assert "Traceback" not in result.output
    assert PAT not in result.output


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        pytest.param([], {"transport": "stdio"}, id="stdio-by-default"),
        pytest.param(
            ["--http", "--port", "9000"],
            {"transport": "http", "host": "127.0.0.1", "port": 9000, "path": "/mcp"},
            id="loopback-http",
        ),
    ],
)
def test_server_listens_on_stdio_or_on_loopback_http(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    options: list[str],
    expected: dict[str, object],
) -> None:
    started: list[dict[str, object]] = []

    def record_run(self: FastMCP, **kwargs: object) -> None:
        started.append(kwargs)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ADO_COLLECTION_URL", COLLECTION_URL)
    monkeypatch.setenv("ADO_PAT", PAT)
    monkeypatch.setattr(FastMCP, "run", record_run)

    result = CliRunner().invoke(cli.main, options)

    assert result.exit_code == 0
    assert len(started) == 1
    assert expected.items() <= started[0].items()
