# Contributing

Start with the [README](README.md) for installation and usage. The
[project plan](PLAN.md) records design decisions, compatibility evidence, and
deferred features; it is not a list of everything the server implements.

## Bugs, questions, and feature requests

Use the [GitHub issue templates](https://github.com/viseshrp/ado-mcp/issues/new/choose).
For a bug, include the package, Python, MCP client, and Azure DevOps Server/TFS
versions, the failing tool/action, a minimal reproduction, and the redacted
error. State whether you use stdio or HTTP.

Never attach a PAT, an Authorization header, a `.env` file, or private work-item
data. Redact collection hosts, project names, and screenshots where necessary.
For a feature request, describe the workflow and target server version before
proposing an implementation.

## Development setup

You need Python 3.11 or newer, Git, and [uv](https://docs.astral.sh/uv/).
Fork the repository if you do not have push access, then clone your fork:

```bash
git clone https://github.com/YOUR_NAME/ado-mcp.git
cd ado-mcp
uv sync --locked
uv run pre-commit install
git switch -c describe-your-change
```

`uv sync` creates the project's `.venv`; `uv run` uses it without a separate
activation step. The tag-helper tests also need Bash (Git Bash on Windows).
Use `uv run git commit` or activate `.venv` before committing so Git's hooks
can find Ruff and the other development tools.

### Checks and tests

Run these from the repository root:

```bash
uv lock --locked
uv run pre-commit run --all-files
uv run python -m pytest
```

The test suite uses a fake HTTP collection and needs no Azure DevOps credentials.
Release-helper tests create and push tags only in temporary local Git
repositories, never on GitHub.

For the full Python 3.11-3.15 matrix, make those interpreters available and run:

```bash
uv run tox
```

CI runs the same matrix on Linux, macOS, and Windows. The Makefile provides
shortcuts: `make check` runs lock and pre-commit checks, `make test-local` uses
the current interpreter, and `make test` runs tox. Makefile commands assume
Bash; on Windows, run them from Git Bash.

## Change guidelines

- Keep changes focused. Check existing helpers and tests before adding code.
- Add focused tests for behavior you introduce or fix. Documentation-only
  changes do not need new Python tests.
- Preserve upstream tool/action names and meaningful inputs. Do not expose
  deferred actions or silently accept inputs the implementation ignores.
- Keep server-specific routes and versions discoverable where the API allows
  it, and report unsupported behavior explicitly.
- Update the README for user-visible changes and the changelog for releases.
  Update the plan when compatibility evidence or scope decisions change.
- Never use Azure DevOps work items to track this repository's development.

### Live validation

Ordinary development and CI must not need a real collection. A live write test
requires separate, explicit authorization for that test. Use uniquely marked,
disposable resources only, never modify existing work items or shared team
configuration, and verify cleanup. Do not retry an ambiguous write just because
its response was lost.

Report mocked and live evidence separately. A successful call on one collection
does not establish compatibility with every Azure DevOps Server/TFS release.

## Pull requests

Open a pull request against `main` with a clear summary and the exact validation
commands and results. Explain any untested behavior or compatibility limitation.
For user-facing fixes, include the expected result and the behavior before the
change. Keep credentials and private collection data out of patches, logs, and
screenshots.

## Releasing

The first release was **0.1.0**. Versions come from Git tags, not a manually
maintained version constant. An exact, clean `vX.Y.Z` tag produces package
version `X.Y.Z`; an untagged commit reports a timestamped development version
(`.dev<TIMESTAMP>`), which is not a release target. Before the first tag
existed, `uv run hatch version` reported `0.0.1.dev<TIMESTAMP>`. The steps
below use `0.1.1` to illustrate the next patch release; substitute the version
you are releasing.

1. Configure the GitHub environments `test-pypi` and `pypi`, with
   `TEST_PYPI_TOKEN` and `PYPI_TOKEN` respectively. The tokens need permission
   to upload the `ado-mcp-server` distribution on their respective indexes.
   Never put tokens in tracked files.
2. Update `CHANGELOG.md` with the release version, actual release date, and
   user-visible changes. Update the date again if the release is postponed:
   the tag helper requires today's date.
3. Validate the release candidate from Bash (Git Bash on Windows):

    ```bash
    make check
    make test
    make build
    make check-dist
    uv run python scripts/check_changelog_date.py 0.1.1
    ```

    The tests are mocked and need no Azure DevOps credentials. Do not run live
    writes as part of releasing. Review the CI matrix results for all supported
    Python versions and operating systems.
4. Merge the preparation changes to `main` and sync with its upstream.
   From a clean checkout of `main`, explicitly select the version:

    ```bash
    make tag VERSION=0.1.1
    ```

    This validates the version and changelog, creates an annotated `v0.1.1`
    tag, and pushes it. It does not update or commit files. Without `VERSION`,
    the helper infers the next patch version from the latest tag; use an
    explicit version for a minor or major release.
5. Wait for the tag's Main workflow to pass quality checks and the test matrix.
   It checks the tag against the computed version, builds and validates the
   wheel and source distribution, and attaches them to a **draft** GitHub
   release. Review its notes and artifacts before publishing the draft.
6. Publishing the draft starts the Release workflow. It reruns quality checks
   and tests, downloads the attached artifacts, validates them, and uploads
   those same artifacts to PyPI without rebuilding.
7. Verify installation from PyPI in a fresh environment and check both command
   aliases with `--version` and `--help`. Keep the documented compatibility
   limits and instance-specific validation evidence in the release notes.

### Workflow triggers

| Action | Result after quality checks and tests pass |
|---|---|
| Push to `main` | Automatically builds a timestamped development version and publishes it to **TestPyPI**. |
| Push a `v*` tag | Builds verified artifacts and creates a **draft** GitHub release. |
| Publish the GitHub release | Uploads the draft's verified artifacts to production **PyPI**, without rebuilding. |

A branch push is not a production release. Do not run `make tag`, publish a
draft, or use the manual publish targets unless you intend to start the
corresponding release operation.
