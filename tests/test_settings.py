from pathlib import Path

import pytest

from ado_mcp.exceptions import ConfigurationError
from ado_mcp.settings import load_settings

SETTING_NAMES = ("ADO_COLLECTION_URL", "ADO_PAT", "ADO_PROJECT", "ADO_TEAM")
VALID_URL = "https://ado.example.net/tfs/DefaultCollection"
ENV_PAT = "secret-pat-value"


@pytest.fixture
def settings_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """An empty working directory with none of the settings in the environment."""
    for name in SETTING_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_environment_overrides_env_file_and_blank_values_count_as_unset(
    monkeypatch: pytest.MonkeyPatch, settings_dir: Path
) -> None:
    (settings_dir / ".env").write_text(
        f"ADO_COLLECTION_URL={VALID_URL}/\nADO_PAT=file-pat\nADO_PROJECT=\nFASTMCP_LOG_LEVEL=DEBUG\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ADO_PAT", ENV_PAT)
    monkeypatch.setenv("ADO_TEAM", "")

    settings = load_settings()

    assert settings.pat.get_secret_value() == ENV_PAT
    assert settings.collection_url == VALID_URL
    assert (settings.project, settings.team) == (None, None)


@pytest.mark.parametrize(
    ("url", "pat", "expected"),
    [
        pytest.param(None, ENV_PAT, "ADO_COLLECTION_URL: Field required", id="missing-url"),
        pytest.param(VALID_URL, None, "ADO_PAT: Field required", id="missing-pat"),
        pytest.param(VALID_URL, "   ", "ADO_PAT must not be empty", id="blank-pat"),
        pytest.param("http://ado.example.net/tfs", ENV_PAT, "must start with https://", id="http"),
        pytest.param("https:///tfs", ENV_PAT, "must name a host", id="no-host"),
        pytest.param("https://me:pw@ado.example.net/tfs", ENV_PAT, "user info", id="user-info"),
        pytest.param("https://ado.example.net/tfs?a=1", ENV_PAT, "query or fragment", id="query"),
        pytest.param("https://dev.azure.com/org", ENV_PAT, "not Azure DevOps Services", id="cloud"),
        pytest.param("https://dev.azure.com./org", ENV_PAT, "not Azure", id="cloud-trailing-dot"),
        pytest.param("https://Foo.VisualStudio.com/x", ENV_PAT, "not Azure", id="cloud-subdomain"),
        pytest.param("https://org.visualstudio.com./x", ENV_PAT, "not Azure", id="cloud-sub-dot"),
    ],
)
def test_invalid_settings_fail_with_this_projects_error_naming_the_setting(
    monkeypatch: pytest.MonkeyPatch,
    settings_dir: Path,
    url: str | None,
    pat: str | None,
    expected: str,
) -> None:
    for name, value in (("ADO_COLLECTION_URL", url), ("ADO_PAT", pat)):
        if value is not None:
            monkeypatch.setenv(name, value)

    with pytest.raises(ConfigurationError) as raised:
        load_settings()

    message = str(raised.value)
    assert expected in message
    assert ENV_PAT not in message
    assert "pw" not in message
