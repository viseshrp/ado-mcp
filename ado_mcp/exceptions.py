"""All exceptions used in the code base are defined here."""

from __future__ import annotations

from typing import ClassVar

from fastmcp.tools import ToolResult
from mcp_types import InputRequiredResult
from pydantic import BaseModel, ConfigDict

from .constants import (
    DEFAULT_HTTP_ERROR_CODE,
    FIRST_HTTP_ERROR_STATUS,
    HTTP_ERROR_CODES,
    INVALID_RESPONSE_CODE,
)
from .utils import to_json_text


class CustomError(Exception):
    """
    Base exception. All other exceptions
    inherit from here.
    """

    detail = "An error occurred."

    def __init__(self, extra_detail: str | None = None) -> None:
        super().__init__()
        self.extra_detail = extra_detail

    def __str__(self) -> str:
        if self.extra_detail:
            return f"{self.detail} :: {self.extra_detail}"
        return self.detail


class ErrorDetail(BaseModel):
    """One field-level problem in an invalid tool input."""

    model_config = ConfigDict(strict=True, extra="forbid")

    field: str
    problem: str


class ErrorPayload(BaseModel):
    """The JSON body of every error result a tool returns."""

    model_config = ConfigDict(strict=True, extra="forbid")

    code: str
    message: str
    operation: str | None = None
    status: int | None = None
    details: list[ErrorDetail] | None = None

    def to_text(self) -> str:
        """Render the payload as the error result text: `{"error": {...}}`, indented."""
        return to_json_text({"error": self.model_dump(exclude_none=True)})


class AdoMcpError(CustomError):
    """Base for every error this server reports to an MCP client.

    `label` names the tool action that failed, for example `wit_work_item.get`.
    `status` is the HTTP status of the server reply, when there was one.
    """

    detail: str = "The Azure DevOps operation failed."
    # Each subclass sets its fixed code here; `code` reads it, and
    # `AdoHttpError` overrides `code` to derive it from the HTTP status.
    _code: ClassVar[str] = "error"
    label: str | None
    status: int | None

    def __init__(
        self,
        extra_detail: str | None = None,
        *,
        label: str | None = None,
        status: int | None = None,
    ) -> None:
        super().__init__(extra_detail)
        self.label = label
        self.status = status

    @property
    def code(self) -> str:
        """The machine-readable error code, for example `invalid_input`."""
        return self._code

    def to_payload(self) -> ErrorPayload:
        """Build the error payload; the message keeps `CustomError`'s format."""
        return ErrorPayload(
            code=self.code,
            message=str(self),
            operation=self.label,
            status=self.status,
        )


class ConfigurationError(AdoMcpError):
    """A setting is missing or invalid."""

    detail = "Invalid configuration"
    _code = "configuration_error"


class InvalidInputError(AdoMcpError):
    """A tool input fails validation or a per-action requirement."""

    detail = "The tool input is invalid."
    _code = "invalid_input"


class MissingContextError(AdoMcpError):
    """No project or team could be resolved for the call."""

    detail = "A project or team is required."
    _code = "missing_project_or_team"


class UnsupportedOnServerError(AdoMcpError):
    """A route location, API version, or feature is absent on the server."""

    detail = "This operation is unsupported on this server."
    _code = "unsupported_on_server"


class AdoHttpError(AdoMcpError):
    """The server answered with an error status, or with a success body that is not JSON."""

    detail = "The Azure DevOps server answered with an error."

    @property
    def code(self) -> str:
        """The error code for the HTTP status, for example 404 -> `not_found`.

        A success status means the reply body could not be read as JSON, so the
        code is `invalid_response`.
        """
        if self.status is None:
            return DEFAULT_HTTP_ERROR_CODE
        if self.status < FIRST_HTTP_ERROR_STATUS:
            return INVALID_RESPONSE_CODE
        return HTTP_ERROR_CODES.get(self.status, DEFAULT_HTTP_ERROR_CODE)


class AdoConnectionError(AdoMcpError):
    """The request did not complete, or a redirect was refused."""

    detail = "The request to Azure DevOps did not complete."
    _code = "connection_failed"


class ResponseTooLargeError(AdoMcpError):
    """A server reply exceeds the size limit."""

    detail = "The Azure DevOps reply is too large."
    _code = "response_too_large"


class ToolInterrupt(Exception):  # noqa: N818 - control flow, not an error condition
    """Ends a tool call early with a ready-made result.

    The project and team resolvers raise it, and the tool decorator returns
    `result` as the tool's answer. It is not an `AdoMcpError`.
    """

    result: ToolResult | InputRequiredResult

    def __init__(self, result: ToolResult | InputRequiredResult) -> None:
        super().__init__()
        self.result = result
