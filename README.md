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

## Configuration

| Variable | Required | Meaning |
|---|---|---|
| `ADO_COLLECTION_URL` | Yes | Collection root, such as `https://ado.example.net/tfs/DefaultCollection`. Any path is kept. |
| `ADO_PAT` | Yes | Personal access token, as issued (raw, not base64-encoded). |
| `ADO_PROJECT` | No | Default project for tools that would otherwise ask for one. |
| `ADO_TEAM` | No | Default team for tools that would otherwise ask for one. |

The server reads the process environment first, then a `.env` file in the
current working directory. When a variable is set in both, the environment
wins. A blank value counts as unset, and unrelated keys in `.env` are ignored.

The PAT is sent only as `Authorization: Basic base64(":" + ADO_PAT)`. It never
appears in a URL, a log line, or an error message.

`ADO_COLLECTION_URL` must use `https`, name a host, and carry no user info,
query, or fragment. Azure DevOps Services hosts (`dev.azure.com`,
`visualstudio.com`, and their subdomains) are rejected. A missing or invalid
setting stops the server before it starts, with `Error: ` and a message that
names the setting but not its value, for example:

```text
Error: Invalid configuration :: ADO_PAT: Field required
```

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
