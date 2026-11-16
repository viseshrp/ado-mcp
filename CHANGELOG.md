# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-16

### Added

- Initial beta release of `ado-mcp-server`, a Python MCP server for on-premises
  Azure DevOps Server and TFS.
- Twelve tools with 30 actions for projects, teams, identities, work items,
  queries, backlogs, iterations, capacity, and work-item Search.
- Work-item creation, updates, batch and child operations, comments, and
  work-item links, with revision checks where supported and no automatic retries.
- Runtime REST route discovery and API-version negotiation, with explicit
  errors for unsupported server capabilities.
- Stdio and loopback-only HTTP transports, plus the `ado-mcp` and
  `ado-mcp-server` command aliases.
- Environment and `.env` configuration, raw PAT authentication, project/team
  elicitation, strict input validation, bounded replies, and untrusted-content
  delimiters.
- Mocked tests, instance-specific live MCP validation evidence, PAT permission
  guidance, and documented compatibility and safe-write limits.
- Explicit release-version selection with `make tag VERSION=0.1.0`, while
  retaining automatic next-version inference for later patch releases.

### Fixed

- Resolve the current user's full identity by exact ID when connection data
  omits the domain, so its unique name can be used for assignment. Preserve
  already qualified accounts and report unresolved identities explicitly.

[0.1.0]: https://github.com/viseshrp/ado-mcp/releases/tag/v0.1.0
