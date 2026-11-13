"""Server configuration, read from the environment and a local `.env` file."""

from collections.abc import Mapping
from urllib.parse import urlsplit

from pydantic import SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .constants import CLOUD_HOST_SUFFIXES, ENV_FILE_NAME, ENV_PREFIX
from .exceptions import ConfigurationError

# Validation messages. They name the setting and never echo its value.
_NOT_HTTPS = "ADO_COLLECTION_URL must start with https://"
_NO_HOST = "ADO_COLLECTION_URL must name a host"
_HAS_USER_INFO = "ADO_COLLECTION_URL must not contain user info"
_HAS_QUERY = "ADO_COLLECTION_URL must not contain a query or fragment"
_CLOUD_HOST = (
    "ADO_COLLECTION_URL must point to Azure DevOps Server or TFS, not Azure DevOps Services"
)
_EMPTY_PAT = "ADO_PAT must not be empty"


class Settings(BaseSettings):
    """The four `ADO_*` settings.

    Values come from the process environment first, then from `.env` in the
    current working directory. A blank value counts as unset.
    """

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file=ENV_FILE_NAME,
        env_file_encoding="utf-8",
        # The same `.env` may hold FASTMCP_* or unrelated keys.
        extra="ignore",
        env_ignore_empty=True,
        strict=True,
        frozen=True,
        str_strip_whitespace=True,
        # Keeps setting values, the PAT included, out of validation messages.
        hide_input_in_errors=True,
    )

    collection_url: str
    pat: SecretStr
    project: str | None = None
    team: str | None = None

    @field_validator("collection_url")
    @staticmethod
    def _check_collection_url(value: str) -> str:
        """Accept only an on-premises `https` collection URL.

        Trailing slashes are removed, for example
        `https://ado.example.net/tfs/DefaultCollection/` ->
        `https://ado.example.net/tfs/DefaultCollection`.
        """
        parts = urlsplit(value)
        if parts.scheme != "https":
            raise ValueError(_NOT_HTTPS)
        # A trailing dot names the same DNS host ("dev.azure.com." is
        # "dev.azure.com"), so it is removed before the cloud-host check.
        host = (parts.hostname or "").rstrip(".")
        if not host:
            raise ValueError(_NO_HOST)
        if parts.username is not None or parts.password is not None:
            raise ValueError(_HAS_USER_INFO)
        if parts.query or parts.fragment:
            raise ValueError(_HAS_QUERY)
        if any(host == suffix or host.endswith(f".{suffix}") for suffix in CLOUD_HOST_SUFFIXES):
            raise ValueError(_CLOUD_HOST)
        return value.rstrip("/")

    @field_validator("pat")
    @staticmethod
    def _check_pat(value: SecretStr) -> SecretStr:
        """Reject a token that is empty or only whitespace."""
        if not value.get_secret_value().strip():
            raise ValueError(_EMPTY_PAT)
        return value


def load_settings() -> Settings:
    """Load and validate the settings.

    Raises `ConfigurationError` naming each failing setting by its environment
    name, for example `Invalid configuration :: ADO_PAT: Field required`. No
    setting value appears in the message.
    """
    try:
        return Settings()
    except ValidationError as error:
        problems = "; ".join(
            f"{ENV_PREFIX}{'.'.join(str(part) for part in item['loc']).upper()}: {_problem(item)}"
            for item in error.errors(include_input=False, include_url=False)
        )
        raise ConfigurationError(problems) from None


def _problem(item: Mapping[str, object]) -> str:
    """Return a validation problem in this project's words.

    A validator's own `ValueError` is reported by its message alone, without
    pydantic's "Value error, " prefix, for example
    `"ADO_COLLECTION_URL must start with https://"`. Other problems keep
    pydantic's message, such as `"Field required"`.
    """
    context = item.get("ctx")
    cause = context.get("error") if isinstance(context, dict) else None
    if item.get("type") == "value_error" and cause is not None:
        return str(cause)
    return str(item.get("msg"))
