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

## Development

Requires Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
make check
make test-local
```

## License

MIT. See [LICENSE](LICENSE).
