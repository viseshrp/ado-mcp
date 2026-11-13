# ado-mcp

[![CI](https://github.com/viseshrp/ado-mcp/actions/workflows/main.yml/badge.svg)](https://github.com/viseshrp/ado-mcp/actions/workflows/main.yml)
[![License: MIT](https://img.shields.io/github/license/viseshrp/ado-mcp)](LICENSE)

Python MCP server for on-premises Azure DevOps Server and TFS.

## Status

This repository currently contains a Python project scaffold generated from
[viseshrp/yapc](https://github.com/viseshrp/yapc) with Cruft. The MCP server,
Azure DevOps API client, and tools have not been implemented yet.

See [PLAN.md](PLAN.md) for the intended scope, compatibility goals, and roadmap.

## Planned scope

- Support Azure DevOps Server/TFS with a configurable collection URL and optional project/team.
- Read the personal access token from `ADO_PAT`; keep TLS verification enabled.
- Provide tools for upstream Microsoft Azure DevOps MCP features that have on-prem API equivalents.
- Omit cloud-only tools and features that have no on-prem equivalent.

## Errors

A failed tool call returns an error result whose text is a JSON object:

```json
{
  "error": {
    "code": "unsupported_on_server",
    "message": "This operation is unsupported on this server. :: Markdown comments need comment API 7.2-preview.4; this server offers 7.1-preview.3. Pass format 'Html'.",
    "operation": "wit_work_item_comment_write.add"
  }
}
```

`operation` names the tool action, `status` carries the HTTP status when the
server answered, and `details` lists the fields of an invalid input.

| Code | Meaning |
|---|---|
| `configuration_error` | A setting is missing or invalid. The server does not start. |
| `invalid_input` | A tool input failed validation or a per-action requirement. |
| `missing_project_or_team` | No project or team was given, configured, or picked. |
| `unsupported_on_server` | The server lacks the route, API version, or feature. |
| `authentication_failed` | HTTP 401: the PAT was rejected. |
| `permission_denied` | HTTP 403: the PAT or user lacks permission. |
| `not_found` | HTTP 404 on a route that names an entity. |
| `conflict` | HTTP 409. |
| `precondition_failed` | HTTP 412, for example a stale `/rev` test operation. |
| `request_failed` | Any other HTTP error status. |
| `connection_failed` | The request did not complete, timed out, or was redirected. |
| `response_too_large` | A reply exceeded 2 MiB. |

Some empty results return a plain error text instead, as upstream does, for
example `No teams found`.

## Development

Requires Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
make check
make test-local
```

## License

MIT. See [LICENSE](LICENSE).
