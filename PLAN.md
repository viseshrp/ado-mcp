# Project Plan: Generic Azure DevOps Server MCP

## Goal and current status

Build an open-source Python MCP server using FastMCP for Azure DevOps Server
and TFS. It must work with a configurable collection and its projects, rather
than embedding one company's host, collection, project names, or work-item data.
This is a new implementation, not a fork of Microsoft's TypeScript server.

The Microsoft Azure DevOps MCP source at
[baseline commit `7f2a6b9fae78903682f4c6328cab17986f3f1cc5`](https://github.com/microsoft/azure-devops-mcp/tree/7f2a6b9fae78903682f4c6328cab17986f3f1cc5)
is the feature and behavior reference. That baseline is version 2.11.0 and
declares `azure-devops-node-api` `^15.1.2`. Its 44 tools cover nine domains:
Core (3), Work (3), Work Items (9), Repositories (11), Pipelines (6), Test
Plans (5), Wiki (2), Search (3), and Advanced Security (2).

**This repository is still a generated project scaffold.** The server, REST
client, authentication, and tools have not been implemented. The inventory
below records the upstream tool names, actions, and REST route families to make
the future implementation scope explicit.

## Product and parity decisions

- Preserve the upstream names, actions, meaningful inputs, and behavior for
  tools with an Azure DevOps Server/TFS equivalent. The endpoint inventory
  summarizes each action; implementation tests must cover the complete input
  schemas and output contracts.
- Use Python and FastMCP with a small, typed HTTP client. Do not copy upstream
  implementation code. Preserve applicable license notices if code is later
  adapted.
- Operate against the configured collection. Project and team parameters are
  supplied by the caller or optional local defaults; no company-specific
  values are built into the package.
- Advanced Security is the known product-level omission: the two upstream
  tools depend on cloud functionality with no Azure DevOps Server equivalent.
  Other uncertain endpoints remain compatibility-gated, not silently removed.
- Do not create or update Azure DevOps work items as project tracking. This
  plan is repository documentation only; no external ADO work items were
  created or changed.
- Do not make live write requests during development or validation unless the
  user separately authorizes a specific test. Write behavior is tested with
  mocked HTTP responses.

## Configuration and PAT handling

| Setting | Requirement |
|---|---|
| `ADO_COLLECTION_URL` | Required collection root, such as `https://ado.example.net/tfs/DefaultCollection`. It may include a reverse-proxy or `/tfs` path. |
| `ADO_PAT` | Required raw PAT. A local, untracked `.env` may define it for development; deployed environments provide it through their secret manager. |
| `ADO_PROJECT` | Optional default project; tool arguments take precedence. |
| `ADO_TEAM` | Optional default team; tool arguments take precedence. |

The existing `.gitignore` excludes `.env`. Keep it that way, provide only blank
placeholders in any future `.env.example`, and never commit or print a token.
The user-facing contract is a **raw** `ADO_PAT`; construct HTTP Basic
authentication as `base64(":" + ADO_PAT)` exactly once. Do not use a PAT in a
URL or query string. The upstream TypeScript server's
`PERSONAL_ACCESS_TOKEN` convention is different: it expects a pre-encoded
credential.

Use the collection URL as the origin and route root for every API request.
Preserve any collection path when building URLs; a leading-slash URL join must
not discard `/tfs/{collection}`. Encode project, team, repository, and other
path parameters as individual path segments. Retain normal TLS certificate
verification. Never forward the PAT to a different host on redirect or when
downloading an artifact.

`GET C/_apis/connectionData` is the upstream preflight/current-user route. It
must use the configured collection and the same PAT transport as other
requests. Do not assume that Azure DevOps Services host aliases such as
`vssps.dev.azure.com` or `almsearch.dev.azure.com` exist on-premises.

## Route and API-version conventions

In the inventory, `C` is `ADO_COLLECTION_URL`; `P` is a project, `T` a team,
`R` a repository, `PR` a pull request, `W` a work item, `I` an iteration,
`PLAN` a test plan, `SUITE` a test suite, and `WIKI` a wiki. For example,
`GIT(P,R)` expands to `C/{P}/_apis/git/repositories/{R}`.

Unless stated otherwise, every REST request includes an endpoint-specific
`api-version` query parameter. The table records the route and meaningful
operation parameters; the implementation will maintain the selected API
version in a per-endpoint compatibility map rather than append one global
version indiscriminately.

### Upstream API-version reference

These are versions observed in the pinned Microsoft baseline, not a claim that
every Azure DevOps Server/TFS release accepts every preview version:

| Upstream operation | Version observed |
|---|---|
| Shared direct-call `apiVersion` | `7.2-preview.1` |
| Work-item `$batch` calls | `5.0` |
| Work-item comment create/update | `7.2-preview.4` |
| Project listing / team listing | `7.2-preview.4` / `7.2-preview.3` |
| Work-item comment listing | `7.1-preview.3` |
| Test-plan and suite listing | `7.2-preview.1` |
| Test-case listing and adding cases | `7.2-preview.3` |
| Test-run listing / test-result listing | `7.2-preview.1` / `7.2-preview.2` |
| Wiki listing / page reads | `7.2-preview.2` / `7.2-preview.1` |
| Wiki upsert and page-ID read | `7.1` |
| Collection-level PR listing | `7.1` |
| Build-stage update | `7.2-preview.1` |

Other operations use method-specific versions selected by the upstream
`azure-devops-node-api` client. The Python client must record those endpoint
versions in tests and select versions that the configured server actually
supports. Prefer stable versions available on the target server; do not assume
cloud preview versions are portable. Version fallback, if needed, is limited
to a known unsupported-version response. Never retry a write after an
ambiguous response.

### REST behavior and compatibility requirements

- Support collection-, project-, and team-scoped routes. A configured
  collection URL may contain a path component, as is common for on-premises
  deployments.
- Use the HTTP verbs and body formats shown below. Work-item mutations use
  `application/json-patch+json`; upload endpoints send binary content; search
  endpoints use JSON `POST` bodies.
- Honor continuation tokens, `$skip`, `$top`, and endpoint-specific paging.
  Bound page counts and response sizes. A previous read-only test-plan probe
  returned a large response even with `$top=1`; test pagination and output
  limits rather than assuming that `$top` bounds every nested payload.
- Preserve the distinction between an empty result and an unsupported
  endpoint. Return an explicit, actionable error for unavailable
  server-version features; do not turn HTTP errors into empty successful
  results.
- Treat URLs returned in API payloads as untrusted. In particular, validate
  artifact download URLs against the configured server before attaching
  credentials or following redirects.

## Upstream tool inventory and on-prem REST mapping

All paths below are relative to `C`. `V(endpoint)` means the version selected
for that endpoint by the compatibility map. The on-prem equivalents of
cloud-hosted routes must be rooted at `C`, not at a cloud alias.

### Core — 3 tools

| Upstream tool | Actions and REST mapping |
|---|---|
| `core_list_project_teams` | List a project's teams with optional `mine`, `$top`, and `$skip`: `GET C/_apis/projects/{P}/teams`. |
| `core_list_projects` | List projects with `stateFilter`, `$top`, `$skip`, and `continuationToken`: `GET C/_apis/projects`. |
| `core_get_identity_ids` | Search by identity filter: candidate on-prem route `GET C/_apis/identities?searchFilter=General&filterValue=...`. Upstream uses the cloud VSSPS identity host; verify the collection-local route before advertising this tool. |

The current-user helper uses `GET C/_apis/connectionData`. Identity lookup is
also used internally by pull-request tools to resolve the authenticated user,
reviewers, and creators.

### Work — 3 tools

| Upstream tool | Actions and REST mapping |
|---|---|
| `work` | `list_iterations`: `GET C/{P}/_apis/wit/classificationnodes/Iterations?$depth=...`; `list_team_iterations`: `GET C/{P}/{T}/_apis/work/teamsettings/iterations?$timeframe=current`; `get_team_settings`: `GET C/{P}/{T}/_apis/work/teamsettings`; `get_team_capacity`: `GET C/{P}/{T}/_apis/work/teamsettings/iterations/{I}/capacities`; `get_iteration_capacities`: `GET C/{P}/_apis/work/iterations/{I}/capacities`. |
| `work_iteration_write` | `create`: `POST C/{P}/_apis/wit/classificationnodes/Iterations` with the iteration node and dates; `assign`: `POST C/{P}/{T}/_apis/work/teamsettings/iterations` with the iteration path/ID. |
| `work_capacity_write` | `update`: `PATCH C/{P}/{T}/_apis/work/teamsettings/iterations/{I}/capacities/{teamMemberId}` with activities and days off. |

### Work Items — 9 tools

| Upstream tool | Actions and REST mapping |
|---|---|
| `wit_work_item` | `get`: `GET C/{P?}/_apis/wit/workItems/{W}` with `fields`, `asOf`, and `$expand`; `get_batch`: `POST C/{P}/_apis/wit/workitemsbatch` with IDs and fields; `list_comments`: `GET C/{P}/_apis/wit/workItems/{W}/comments`; `my`: `GET C/{P}/_apis/work/predefinedqueries/{assignedtome\|myactivity}` with `$top` and `includeCompleted`; `list_revisions`: `GET C/{P}/_apis/wit/workItems/{W}/revisions`; `list_for_iteration`: `GET C/{P}/{T}/_apis/work/iterations/{I}/workitems`; `get_type`: `GET C/{P}/_apis/wit/workitemtypes/{type}`. |
| `wit_query` | `get`: `GET C/{P}/{T?}/_apis/wit/queries/{queryId-or-path}`; `get_results`: `GET C/{P}/{T?}/_apis/wit/wiql/{queryId}`; `wiql`: `POST C/{P}/{T?}/_apis/wit/wiql` with `{ "query": "..." }`. Preserve `timePrecision`, `$top`, query expansion/depth, deleted-query, and ID-only options where supported. |
| `wit_backlog` | `list`: `GET C/{P}/{T}/_apis/work/backlogs`; `list_work_items`: `GET C/{P}/{T}/_apis/work/backlogs/{backlogId}/workItems`; `reorder`: `PATCH C/{P}/{T}/_apis/work/workitemsorder`, or `PATCH C/{P}/{T}/_apis/work/iterations/{I}/workitemsorder` for iteration ordering. The reorder body includes IDs and optional parent/previous/next/path information. |
| `wit_work_item_attachment` | Download: `GET C/_apis/wit/attachments/{attachmentId}` with optional `fileName` and download options. Stream the response and enforce size/path limits for any local save. |
| `wit_work_item_attachment_upload` | Upload: `POST C/_apis/wit/attachments?fileName=...` with decoded binary content; return the attachment reference. |
| `wit_work_item_attachment_link` | Link the uploaded attachment: `PATCH C/{P}/_apis/wit/workItems/{W}` with a JSON Patch `AttachedFile` relation and optional comment. |
| `wit_work_item_write` | `create`: `POST C/{P}/_apis/wit/workItems/${type}` with JSON Patch; `update`: `PATCH C/{P}/_apis/wit/workItems/{W}`; `update_batch` and `add_child`: `PATCH C/_apis/wit/$batch` with per-item JSON Patch requests. Preserve markdown field-format metadata, parent relations, batch limits, and revision/concurrency behavior. |
| `wit_work_item_comment_write` | `add`: `POST C/{P}/_apis/wit/workItems/{W}/comments`; `update`: `PATCH C/{P}/_apis/wit/workItems/{W}/comments/{commentId}`. Preserve Markdown/HTML format and mention resolution where available. This endpoint/version is compatibility-gated. |
| `wit_work_item_link_write` | `link`, `unlink`, `link_to_pull_request`, and `add_artifact_link` mutate the work item's relations through `PATCH C/{P}/_apis/wit/workItems/{W}` or batched `PATCH C/_apis/wit/$batch`. Use relation reads before unlinking; preserve relation types, artifact URIs, and comments. |

### Repositories — 11 tools

Define `GIT(P,R) = C/{P}/_apis/git/repositories/{R}`.

| Upstream tool | Actions and REST mapping |
|---|---|
| `repo_repository` | `list`: `GET C/{P}/_apis/git/repositories`; `get`: `GET C/{P}/_apis/git/repositories/{R}`. |
| `repo_pull_request` | `get`: `GET GIT(P,R)/pullRequests/{PR}`; `list`: `GET GIT(P,R)/pullRequests` with `searchCriteria.*`; `list_by_commits`: `POST GIT(P,R)/pullRequestQuery` with commit IDs and query type. |
| `repo_pull_request_org` | List active PRs for the authenticated user across the collection: `GET C/_apis/git/pullRequests` with `searchCriteria.creatorId` or `searchCriteria.reviewerId`, status, `$skip`, and `$top`. Verify collection-scope support on each server release; do not silently fan out over an unbounded collection if absent. |
| `repo_pull_request_thread` | `list`: `GET GIT(P,R)/pullRequests/{PR}/threads`; `list_comments`: `GET GIT(P,R)/pullRequests/{PR}/threads/{threadId}/comments`. Preserve iteration, status, author, and paging filters. |
| `repo_branch` | `get`, `list`, and `list_mine`: `GET GIT(P,R)/refs` with `filter=heads/...` and any branch/identity filtering. |
| `repo_file` | `get_content` and `list_directory`: `GET GIT(P,R)/items` with `path`, version descriptor, recursion level, and `includeContent` as appropriate. |
| `repo_file_write` | Read the branch head with `GET GIT(P,R)/refs`, then create/update with `POST GIT(P,R)/pushes` containing `refUpdates` and a commit/change. Preserve the expected-old-object-ID guard. |
| `repo_search_commits` | Search: `POST C/_apis/search/commitSearchResults` with search text, project/repository/branch/author/date filters, facets, and paging. The upstream hardcodes the cloud `almsearch` host; local Search service support is unverified and must be feature-gated. |
| `repo_pull_request_write` | `create`: `POST GIT(P,R)/pullRequests`; `update`: `PATCH GIT(P,R)/pullRequests/{PR}`; label changes: `GET`, `POST`, and `DELETE GIT(P,R)/pullRequests/{PR}/labels[/{labelId}]`; reviewer changes: `POST GIT(P,R)/pullRequests/{PR}/reviewers`, `PUT .../reviewers/{reviewerId}`, or `DELETE .../reviewers/{reviewerId}`; `vote` updates the current reviewer's vote. |
| `repo_pull_request_thread_write` | `create`: `POST GIT(P,R)/pullRequests/{PR}/threads`; `reply`: `POST .../threads/{threadId}/comments`; `update`: `PATCH .../threads/{threadId}/comments/{commentId}`; `update_status`: `PATCH .../threads/{threadId}`. Preserve file/iteration context for code-review threads. |
| `repo_create_branch` | Read the source ref with `GET GIT(P,R)/refs`, then create the ref with `POST GIT(P,R)/refs` using a zero old object ID and the selected source commit. |

### Pipelines — 6 tools

Define `BUILD(P) = C/{P}/_apis/build` and
`PIPELINES(P) = C/{P}/_apis/pipelines`.

| Upstream tool | Actions and REST mapping |
|---|---|
| `pipelines_build` | `list`: `GET BUILD(P)/builds` with build/definition/status/result/repository filters; `get_status`: `GET BUILD(P)/builds/{buildId}/report`; `get_changes`: `GET BUILD(P)/builds/{buildId}/changes`. |
| `pipelines_build_log` | `list`: `GET BUILD(P)/builds/{buildId}/logs`; `get_content`: `GET BUILD(P)/builds/{buildId}/logs/{logId}` with optional start/end lines. |
| `pipelines_definition` | `list`: `GET BUILD(P)/definitions`; `list_revisions`: `GET BUILD(P)/definitions/{definitionId}/revisions`. |
| `pipelines_run` | `get`: `GET PIPELINES(P)/{pipelineId}/runs/{runId}`; `list`: `GET PIPELINES(P)/{pipelineId}/runs`. |
| `pipelines_artifact` | `list`/`download`: `GET BUILD(P)/builds/{buildId}/artifacts`, optionally selecting an artifact. Download through its returned resource URL only after same-server validation, with bounded streaming. |
| `pipelines_write` | `run_pipeline`: `POST PIPELINES(P)/{pipelineId}/runs`; `create_pipeline`: `POST PIPELINES(P)`; `rename_pipeline`: `GET` then `PUT BUILD(P)/definitions/{definitionId}`; `update_build_stage`: `PATCH BUILD(P)/builds/{buildId}/stages/{stageName}`. Azure Repos (`TfsGit`) is the baseline on-prem repository type; external provider integrations require explicit compatibility tests. |

### Test Plans — 5 tools

Define `TESTPLAN(P) = C/{P}/_apis/testplan`.

| Upstream tool | Actions and REST mapping |
|---|---|
| `testplan` | `list_plans`: `GET TESTPLAN(P)/Plans`; `list_suites`: `GET TESTPLAN(P)/Plans/{PLAN}/Suites?expand=children`; `list_cases`: `GET TESTPLAN(P)/Plans/{PLAN}/Suites/{SUITE}/TestCase`. Preserve continuation tokens and nested-suite shaping. |
| `testplan_show_test_results_from_build_id` | Find runs with `GET C/{P}/_apis/test/runs?buildUri=vstfs:///Build/Build/{buildId}`; for each run, page results with `GET C/{P}/_apis/test/Runs/{runId}/Results` and optional outcome filters. Keep bounded paging/concurrency. |
| `testplan_test_plan_write` | `create`: `POST TESTPLAN(P)/Plans` with name, iteration, dates, description, and area path. |
| `testplan_test_suite_write` | `create`: `POST TESTPLAN(P)/Plans/{PLAN}/Suites`; `add_test_cases`: `POST C/{P}/_apis/test/Plans/{PLAN}/Suites/{SUITE}/TestCases/{testCaseIds}`. |
| `testplan_test_case_write` | `create`: `POST C/{P}/_apis/wit/workItems/$Test%20Case`; `update_steps`: `PATCH C/{P}/_apis/wit/workItems/{testCaseId}`. Both use JSON Patch for test-case fields/steps. |

The upstream uses test-plan API versions `7.2-preview.1` and
`7.2-preview.3`, and test-results versions `7.2-preview.1` and
`7.2-preview.2`. Earlier read-only probes succeeded for test plans, suites,
runs, and results; test-run reads also succeeded with API versions `5.0` and
`6.0`. These observations are compatibility evidence for one server, not a
universal support guarantee.

### Wiki — 2 tools

Define `WIKI(P,I) = C/{P}/_apis/wiki/wikis/{I}`.

| Upstream tool | Actions and REST mapping |
|---|---|
| `wiki` | `list_wikis`: `GET C/{P?}/_apis/wiki/wikis`; `get_wiki`: `GET C/{P?}/_apis/wiki/wikis/{I}`; `list_pages`: `POST WIKI(P,I)/pagesbatch` with top/token/page-view options; `get_page`: `GET WIKI(P,I)/pages?path=...` with recursion options; `get_page_content`: `GET WIKI(P,I)/pages/{pageId}?includeContent=true` or `GET .../pages?path=...&includeContent=true`. Parse input URLs only when their origin and collection path match `C`. |
| `wiki_upsert_page` | Create/update with `PUT WIKI(P,I)/pages?path=...&versionDescriptor.versionType=branch&versionDescriptor.version=...`. For an existing page, read its ETag and send `If-Match` on the update. |

### Search — 3 tools

The upstream sends these requests to `almsearch.dev.azure.com`. For on-prem,
the candidate route root is the configured collection `C`.

| Upstream tool | Actions and REST mapping |
|---|---|
| `search_code` | `POST C/_apis/search/codesearchresults` with text, project/repository/path/branch filters, facets, and paging. |
| `search_wiki` | `POST C/_apis/search/wikisearchresults` with text, project/wiki filters, facets, and paging. |
| `search_workitem` | `POST C/_apis/search/workitemsearchresults` with text, project/area/type/state/assignee filters, facets, and paging. |

Read-only probing found that Search requests must use `POST` on the tested
on-prem server (`GET` returned HTTP 405); do not implement these operations as
GET requests. Search is version-dependent, so check the specific endpoint and
preserve a clear unsupported-feature error when the target server lacks it.

### Advanced Security — 2 tools, omitted on-prem

| Upstream tool | On-prem decision |
|---|---|
| `advsec_get_alerts` | Omit: the upstream alert-list feature has no Azure DevOps Server/TFS equivalent. |
| `advsec_get_alert_details` | Omit: the upstream alert-detail feature has no Azure DevOps Server/TFS equivalent. |

Do not register cloud-only Advanced Security tools in the on-prem MCP server.
Document the omission in user-facing feature coverage.

## PAT permission model

The following are minimum permission **areas** to validate, not a promise that
scope labels are identical across Azure DevOps Server/TFS releases. A PAT
scope does not replace the user's project, team, repository, build, or test
permissions.

| Tool area | Read permissions | Additional write permissions |
|---|---|---|
| Projects and teams | Project and Team: Read | None |
| Identity lookup | Identity/Graph: Read, if available on the target | None |
| Work items, queries, iterations, backlog | Work Items: Read | Work Items: Read & Write for create/update/link/comment/attachment and iteration/capacity changes |
| Repositories, branches, PRs, code search | Code: Read | Code: Read & Write for pushes, branches, PRs, reviewers, votes, and threads |
| Builds and pipelines | Build: Read | Build: Execute/Read & Execute or equivalent write scope for queue/create/rename/stage changes |
| Test plans and results | Test Management: Read | Test Management: Read & Write for plan/suite/case mutations |
| Wiki | Wiki: Read | Wiki: Read & Write for page upsert |
| Search | The corresponding Code, Work Items, or Wiki read permission and Search service access | None |
| Advanced Security | Not applicable | Not applicable; tool family is omitted |

Use the least-privilege PAT that covers the tools being invoked. Prefer a
read-only PAT for ordinary exploration; write-enabled routes must still be
explicitly called and authorized by the user.

## Compatibility evidence and open questions

Read-only probes performed during earlier planning against one private
on-premises collection succeeded for projects, teams/iterations, work items
and metadata, WIQL/search, repositories/PRs, builds/pipelines, Wiki, and test
plans/suites/runs. This plan intentionally records no private host, collection
or project name, work-item ID, response body, or credential.

| Area | Evidence and implementation requirement |
|---|---|
| Core, Work, WIT, Git, Build/Pipelines, Wiki, Test | Read routes were exercised on one server. Re-test supported operations against the declared compatibility matrix; do not generalize one server's result to every release. |
| Search | POST search worked and GET returned 405 on the tested server. The upstream cloud host must be replaced with a collection-local route. |
| Test APIs | Test-run reads worked with versions `5.0` and `6.0`. Test-plan responses may be large despite a small `$top`; test continuation-token paging and bounded output. |
| Identity | Upstream identity lookup hardcodes `vssps.dev.azure.com`; the collection-local identity route is a candidate that still needs a compatibility test. |
| Commit search | Upstream hardcodes `almsearch.dev.azure.com`; collection-local commit search has not been verified. Gate it by target capability. |
| Collection-wide PR search | Upstream uses `C/_apis/git/pullRequests`; verify its availability and pagination on supported server versions. Do not perform an unbounded project/repository fan-out as an implicit fallback. |
| Mutations | No live write endpoint was tested. Use mocked requests for every write path, including failure/concurrency cases. |
| Advanced Security | Cloud-only for this scope; omit rather than return empty data or pretend support. |

No live Azure DevOps writes were issued as part of this plan. No external ADO
work items were created or modified.

## Implementation roadmap

1. **Configuration and transport:** implement validated collection URL
   handling, raw `ADO_PAT` Basic auth, TLS verification, bounded timeouts,
   redacted logging, endpoint-version mapping, typed request/response helpers,
   and actionable HTTP errors.
2. **Read operations:** implement Core, Work, WIT, Repository, Pipeline,
   Test Plan, Wiki, and supported Search tools. Add pagination and response
   size limits before enabling bulk or nested responses.
3. **Write operations:** implement the on-prem equivalents for WIT,
   iteration/capacity, Git/PR, pipeline, test-plan, and Wiki writes. Never
   automatically replay ambiguous writes; use JSON Patch/ETags/old-object-ID
   guards where applicable.
4. **Compatibility and documentation:** publish a per-server-version matrix
   showing each tool's supported API version and known limitations. Include
   setup, `.env` handling, PAT scope guidance, and the explicit
   Advanced-Security omission.
5. **Release readiness:** run mocked unit tests, static checks, optional
   read-only integration tests against a user-supplied server, and secret
   scanning. No test may perform a live write without separate user approval.

## Test and acceptance criteria

- Tests assert that a raw PAT becomes `Authorization: Basic base64(":" +
  PAT)`, is never placed in a URL, and never appears in logs or error text.
- URL tests cover a collection root with a path prefix (for example
  `/tfs/DefaultCollection`), encoded project/team names, same-origin
  redirects, and rejection of cloud-hosted hardcoded endpoints.
- Mocked HTTP tests cover every registered tool/action, HTTP verb, route,
  `api-version`, request body/content type, pagination token, error response,
  and relevant optimistic-concurrency behavior.
- Tool-registration tests assert the upstream names/actions for all supported
  tools and assert that the two Advanced Security tools are not registered.
- Search tests use POST and cover the observed 405 response for GET.
- Large test-plan, test-result, build-log, and artifact responses remain
  bounded and paginated; artifact downloads cannot send the PAT to an
  unvalidated host.
- Live integration tests, if enabled, are read-only and use a PAT supplied
  through the test environment. All writes remain mocked unless separately
  approved.
- CI and linting must not require a live Azure DevOps service or secret.

## REST references

- [Microsoft Azure DevOps MCP baseline](https://github.com/microsoft/azure-devops-mcp/tree/7f2a6b9fae78903682f4c6328cab17986f3f1cc5)
- [Core REST API](https://learn.microsoft.com/en-us/rest/api/azure/devops/core/)
- [Work REST API](https://learn.microsoft.com/en-us/rest/api/azure/devops/work/)
- [Work Item Tracking REST API](https://learn.microsoft.com/en-us/rest/api/azure/devops/wit/)
- [Git REST API](https://learn.microsoft.com/en-us/rest/api/azure/devops/git/)
- [Build REST API](https://learn.microsoft.com/en-us/rest/api/azure/devops/build/)
- [Pipelines REST API](https://learn.microsoft.com/en-us/rest/api/azure/devops/pipelines/)
- [Test REST API](https://learn.microsoft.com/en-us/rest/api/azure/devops/test/)
- [Test Plan REST API](https://learn.microsoft.com/en-us/rest/api/azure/devops/testplan/)
- [Wiki REST API](https://learn.microsoft.com/en-us/rest/api/azure/devops/wiki/)
- [Search REST API](https://learn.microsoft.com/en-us/rest/api/azure/devops/search/)

Cloud REST documentation often shows a `dev.azure.com/{organization}` root.
For Azure DevOps Server/TFS, retain the API route but substitute the configured
collection root only where that server release implements the endpoint.
