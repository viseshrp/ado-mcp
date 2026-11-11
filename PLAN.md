# Project Plan

## Goal

Build a generic Python/FastMCP server for Azure DevOps Server/TFS. The project is
for self-hosted Azure DevOps deployments, not a particular company or collection.

The goal is behavioral and tool parity with the on-prem-compatible parts of the
Microsoft Azure DevOps MCP toolset. The baseline reviewed during planning was
Microsoft's `7f2a6b9fae78903682f4c6328cab17986f3f1cc5` commit. Preserve tool
names, input schemas, and semantics where the on-prem REST APIs support them.

## Feature coverage

The upstream toolset has these domains:

- Core
- Work
- Work Items
- Repositories
- Pipelines
- Test Plans
- Wiki
- Search
- Advanced Security

The implementation will inventory the upstream tools and map each to Azure
DevOps Server/TFS endpoints and API versions. Tools with no on-prem equivalent
will be omitted from the MCP server and documented as unsupported. This includes
cloud-only Advanced Security functionality.

## Configuration and security

- Accept the collection URL and optional project/team as runtime configuration.
- Read the personal access token from the `ADO_PAT` environment variable.
- Use Basic authentication and normal TLS certificate verification.
- Never commit credentials or `.env` files, log tokens, or hard-code a company
  URL or private work-item data.
- Do not test write operations against a live company instance. Cover write
  behavior with mocked API tests; use read-only calls for any live validation.

## Roadmap

1. Inventory upstream tools and document on-prem endpoint/API-version coverage.
2. Implement generic configuration, authentication, REST transport, pagination,
   API-version handling, and actionable error reporting.
3. Implement FastMCP tools for the supported upstream domains, preserving
   behavior where Azure DevOps Server/TFS provides an equivalent API.
4. Add mocked unit tests, read-only integration tests, compatibility guidance,
   and setup documentation.
5. Document unsupported features and supported Azure DevOps Server/TFS versions.

## Current status

This repository is currently only a YAPC/Cruft-generated project scaffold.
The MCP server, API client, authentication, and tools are not implemented.

## Licensing

The scaffold uses the MIT-licensed YAPC template. Microsoft Azure DevOps MCP is
also MIT-licensed and is a feature/behavior reference. Preserve applicable
copyright and license notices if any upstream source code is adapted. Do not
copy implementation code from unrelated repositories.
