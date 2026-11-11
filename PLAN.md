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
| `work` | `list_iterations`: `GET C/{P}/_apis/wit/classificationnodes/Iterations?$depth=...`; `list_team_iterations`: `GET C/{P}/{T}/_apis/work/teamsettings/iterations?$timeframe=current`; `get_team_settings`: `GET C/{P}/{T}/_apis/work/teamsettings`; `get_team_field_values`: `GET C/{P}/{T}/_apis/work/teamsettings/teamfieldvalues`; `get_team_capacity`: `GET C/{P}/{T}/_apis/work/teamsettings/iterations/{I}/capacities`; `get_iteration_capacities`: `GET C/{P}/_apis/work/iterations/{I}/capacities`. |
| `work_iteration_write` | `create`: `POST C/{P}/_apis/wit/classificationnodes/Iterations` with the iteration node and dates; `assign`: `POST C/{P}/{T}/_apis/work/teamsettings/iterations` with the iteration path/ID. |
| `work_capacity_write` | `update`: `PATCH C/{P}/{T}/_apis/work/teamsettings/iterations/{I}/capacities/{teamMemberId}` with activities and days off. |

### Work Items — 9 tools

| Upstream tool | Actions and REST mapping |
|---|---|
| `wit_work_item` | `get`: `GET C/{P?}/_apis/wit/workItems/{W}` with `fields`, `asOf`, and `$expand`; `get_batch`: `POST C/{P}/_apis/wit/workitemsbatch` with IDs and fields; `list_comments`: `GET C/{P}/_apis/wit/workItems/{W}/comments`; `my`: `GET C/{P}/_apis/work/predefinedqueries/{assignedtome\|myactivity}` with `$top` and `includeCompleted`; `list_revisions`: `GET C/{P}/_apis/wit/workItems/{W}/revisions`; `list_for_iteration`: `GET C/{P}/{T}/_apis/work/teamsettings/iterations/{I}/workitems`; `get_type`: `GET C/{P}/_apis/wit/workitemtypes/{type}`. |
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
| `repo_repository` | `list` and `get`: `GET C/{P}/_apis/git/repositories`; `get` filters the returned list locally in the upstream implementation (there is no separate single-repository GET call). |
| `repo_pull_request` | `get`: `GET GIT(P,R)/pullRequests/{PR}`; optionally `GET .../labels`, then `GET .../iterations` and `GET .../iterations/{iterationId}/changes`; `list`: repository- or project-scoped `GET .../pullRequests` with `searchCriteria.*`; `list_by_commits`: `POST GIT(P,R)/pullRequestQuery` with commit IDs and query type. User-name filters can additionally call identity/current-user helpers. |
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
| `search_code` | `POST C/_apis/search/codesearchresults` with text, project/repository/path/branch filters, facets, and paging; then `GET GIT(P,R)/items` through `gitApi.getItem` for each returned result that can be enriched. |
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

## Complete call-level REST inventory and instance probe status

This ledger supplements the 44-tool inventory above. It traces every explicit
Azure DevOps REST operation issued by a tool handler or shared helper in the
pinned Microsoft source, including conditional follow-up requests. SDK method
versions are the method-specific versions in the audited
`azure-devops-node-api` 15.1.2 reference; the upstream dependency range is
`^15.1.2`. `C` remains the configured collection root. Search and Advanced
Security are exceptions in the upstream code: they hardcode Azure DevOps
Services hosts rather than using the configured connection.

The status column reflects the earlier read-only probe using the user-provided
target and credential. The target URL, PAT, project names, record identifiers,
response contents, and counts are intentionally not included. `Confirmed`
means the recorded probe for that operation or exact route returned HTTP 200.
`Partial` means the route family responded but the exact action or complete
response was not retained. `Not tested` means there is no recorded probe for
that endpoint; it does not mean the endpoint is unsupported. `Write not tested`
means no mutating request was issued.

| Tool/action or shared call | Explicit REST call(s) and upstream API version | Prior instance probe |
|---|---|---|
| `core_list_projects` | `GET C/_apis/projects` (`7.2-preview.4`); supports `stateFilter`, `$top`, `$skip`, and `continuationToken`. | Confirmed: project discovery returned HTTP 200. |
| `core_list_project_teams` | `GET C/_apis/projects/{P}/teams` (`7.2-preview.3`); supports `mine`, `$top`, and `$skip`. | Confirmed: team listing returned HTTP 200. |
| `core_get_identity_ids` | Upstream calls `GET https://vssps.dev.azure.com/{org}/_apis/identities?api-version=7.2-preview.1&searchFilter=General&filterValue=...`. Candidate on-prem route: `GET C/_apis/identities` with the same query. | Cloud host only in upstream; collection-local identity route not verified. Do not send the PAT to the cloud host. |
| Shared current-user helper | `GET C/_apis/connectionData` with no explicit `api-version`; used by PR filters for “me”, organization-wide PR listing, auto-complete updates, and votes. | Not individually recorded. |
| Upstream auth tenant lookup | Conditional unauthenticated `HEAD https://vssps.dev.azure.com/{org}` when no tenant is supplied and the tenant cache has no valid entry; not an Azure DevOps Server collection API. | Cloud-only startup behavior; no on-prem equivalent or probe. |
| `work.list_iterations` | `GET C/{P}/_apis/wit/classificationnodes/Iterations` (`7.1-preview.2`) with `$depth`. | Not individually recorded; the prior “iterations” result did not retain the exact route. |
| `work.list_team_iterations` | `GET C/{P}/{T}/_apis/work/teamsettings/iterations` (`7.2-preview.1`) with optional timeframe. | Partial: iteration discovery succeeded, but the saved probe record does not identify this exact route. |
| `work.get_team_settings` | `GET C/{P}/{T}/_apis/work/teamsettings` (`7.2-preview.1`). | Not tested. |
| `work.get_team_field_values` | `GET C/{P}/{T}/_apis/work/teamsettings/teamfieldvalues` (`7.2-preview.1`). | Not tested. |
| `work.get_team_capacity` | `GET C/{P}/{T}/_apis/work/teamsettings/iterations/{I}/capacities` (`7.2-preview.3`). | Not tested. |
| `work.get_iteration_capacities` | `GET C/{P}/_apis/work/iterations/{I}/capacities` (`7.2-preview.1`). | Not tested. |
| `work_iteration_write.create` | `POST C/{P}/_apis/wit/classificationnodes/Iterations[/{parentPath}]` (`7.1-preview.2`) with the classification-node body. | Write not tested. |
| `work_iteration_write.assign` | `POST C/{P}/{T}/_apis/work/teamsettings/iterations` (`7.2-preview.1`) with the iteration path or ID. | Write not tested. |
| `work_capacity_write.update` | `PATCH C/{P}/{T}/_apis/work/teamsettings/iterations/{I}/capacities/{teamMemberId}` (`7.2-preview.3`) with a capacity patch. | Write not tested. |
| `wit_work_item.get` | `GET C/{P?}/_apis/wit/workItems/{W}` (`7.1-preview.3`), optionally with `fields`, `asOf`, and `$expand`. | Confirmed: work-item detail returned HTTP 200. |
| `wit_work_item.get_batch` | `POST C/{P}/_apis/wit/workitemsbatch` (`7.1-preview.1`) with IDs and fields. | Not tested. |
| `wit_work_item.list_comments` | `GET C/{P}/_apis/wit/workItems/{W}/comments` (`7.1-preview.3`) with `$top` and continuation token. | Partial: the prior probe recorded an empty result; its HTTP status was not retained. |
| `wit_work_item.my` | `GET C/{P}/_apis/work/predefinedqueries/{assignedtome\|myactivity}` (`7.2-preview.1`) with `$top` and `includeCompleted`. | Not tested. |
| `wit_work_item.list_revisions` | `GET C/{P}/_apis/wit/workItems/{W}/revisions` (`7.1-preview.3`) with `$top`, `$skip`, and optional expansion. | Not individually recorded. |
| `wit_work_item.list_for_iteration` | `GET C/{P}/{T}/_apis/work/teamsettings/iterations/{I}/workitems` (`7.2-preview.1`). | Not tested. |
| `wit_work_item.get_type` | `GET C/{P}/_apis/wit/workitemtypes/{type}` (`7.1-preview.2`). | Partial: work-item type metadata returned HTTP 200, but the large response was not parsed and the exact single-type request was not retained. |
| `wit_query.get` | `GET C/{P}/{T?}/_apis/wit/queries/{queryId-or-path}` (`7.1-preview.2`) with query expansion/depth options. | Partial: query reads succeeded; the exact action and route were not retained. |
| `wit_query.get_results` | `GET C/{P}/{T?}/_apis/wit/wiql/{queryId}` (`7.1-preview.2`) with `timePrecision` and `$top`. | Not individually recorded. |
| `wit_query.wiql` | `POST C/{P}/{T?}/_apis/wit/wiql` (`7.1-preview.2`) with a JSON `{ "query": "..." }` body and optional `timePrecision`/`$top`. | Confirmed: read-only WIQL returned HTTP 200. |
| `wit_backlog.list` / `list_work_items` | `GET C/{P}/{T}/_apis/work/backlogs` and `GET .../backlogs/{backlogId}/workItems` (both `7.2-preview.1`). | Not tested. |
| `wit_backlog.reorder` | `PATCH C/{P}/{T}/_apis/work/workitemsorder` or `PATCH C/{P}/{T}/_apis/work/iterations/{I}/workitemsorder` (`7.2-preview.1`) with a reorder operation. | Write not tested. |
| `wit_work_item_attachment` download | `GET C/{P?}/_apis/wit/attachments/{attachmentId}` (`7.1-preview.3`), optionally with `fileName` and download options. | Not tested. |
| `wit_work_item_attachment_upload` | `POST C/{P?}/_apis/wit/attachments` (`7.1-preview.3`) with `fileName` and binary content. | Write not tested. |
| `wit_work_item_attachment_link` | `PATCH C/{P}/_apis/wit/workItems/{W}` (`7.1-preview.3`) with an `AttachedFile` JSON Patch relation. | Write not tested. |
| `wit_work_item_write.create` / `update` | `POST C/{P}/_apis/wit/workItems/${type}` and `PATCH C/{P}/_apis/wit/workItems/{W}` (both `7.1-preview.3`), using JSON Patch. | Write not tested. |
| `wit_work_item_write.update_batch`, `add_child`; `wit_work_item_link_write.link` | `PATCH C/_apis/wit/$batch?api-version=5.0`; each embedded request has its own `api-version=5.0` and JSON Patch body. Child creation embeds `/{P}/_apis/wit/workItems/${type}`; link operations embed `/_apis/wit/workItems/{W}`. | Write not tested. |
| `wit_work_item_comment_write.add` / `update` | `POST C/{P}/_apis/wit/workItems/{W}/comments` and `PATCH .../comments/{commentId}` (`7.2-preview.4`), with `format` and `{ "text": ... }`. Email-style mentions conditionally call the identity helper above. | Write not tested; mention identity resolution not tested. |
| `wit_work_item_link_write.unlink` | First `GET C/{P}/_apis/wit/workItems/{W}?$expand=Relations` (`7.1-preview.3`), then `PATCH` the same work item with relation removals (`7.1-preview.3`). | Not tested; write not tested. |
| `wit_work_item_link_write.link_to_pull_request` | `PATCH C/{P}/_apis/wit/workItems/{W}` (`7.1-preview.3`) with a `vstfs:///Git/PullRequestId/...` artifact relation; no PR read is made. | Write not tested. |
| `wit_work_item_link_write.add_artifact_link` | `PATCH C/{P}/_apis/wit/workItems/{W}` (`7.1-preview.3`). For a Wiki link supplied by page ID, first `GET C/{P}/_apis/wiki/wikis/{wikiId}/pages/{pageId}?api-version=7.1` to resolve its path. | Not tested; write not tested. |
| `repo_repository.list` / `get` | `GET C/{P}/_apis/git/repositories` (`7.2-preview.2`); upstream `get` filters this list locally instead of calling a single-repository endpoint. | Confirmed: repository listing returned HTTP 200. |
| `repo_pull_request.get` | `GET GIT(P,R)/pullRequests/{PR}` (`7.2-preview.2`); optional `GET .../labels` (`7.2-preview.1`), then `GET .../iterations` (`7.2-preview.2`) and `GET .../iterations/{iterationId}/changes` (`7.2-preview.1`). `includeWorkItemRefs` is a query option on the first request. | Partial: PR listing succeeded; detail, labels, iterations, and changes were not separately recorded. |
| `repo_pull_request.list` | `GET GIT(P,R)/pullRequests` or `GET C/{P}/_apis/git/pullRequests` (`7.2-preview.2`) with `searchCriteria.*`, `$skip`, and `$top`. Email filters call the identity helper; “me” filters call `connectionData`. | Confirmed: PR listing returned HTTP 200; helper routes not individually recorded. |
| `repo_pull_request.list_by_commits` | `POST GIT(P,R)/pullRequestQuery` (`7.2-preview.1`) with commit IDs and query type. | Not tested. |
| `repo_pull_request_org` | `GET C/_apis/git/pullrequests?api-version=7.1` with creator/reviewer, status, `$skip`, and `$top`; preceded by `GET C/_apis/connectionData`. | Not tested. |
| `repo_pull_request_thread.list` / `list_comments` | `GET GIT(P,R)/pullRequests/{PR}/threads` and `GET .../threads/{threadId}/comments` (both `7.2-preview.1`). Thread filtering and paging are then applied locally. | Not tested. |
| `repo_branch.get` / `list` / `list_mine` | `GET GIT(P,R)/refs` (`7.2-preview.2`); `list_mine` uses the SDK's `includeMyBranches` query option. | Not tested. |
| `repo_file.get_content` / `list_directory` | `GET GIT(P,R)/items` (`7.2-preview.1`), via `getItemText` for content and `getItems` for item/directory metadata; path, recursion, and version are query options. | Not individually recorded. |
| `search_code` result enrichment | For eligible code-search hits, `GET GIT(P,R)/items` (`7.2-preview.1`) via `gitApi.getItem`, pinned to the returned commit and requesting content. | Not individually recorded; code-search POST success does not prove this follow-up. |
| `repo_file_write` | First `GET GIT(P,R)/refs` (`7.2-preview.2`), then `POST GIT(P,R)/pushes` (`7.2-preview.3`) with `refUpdates` and a commit/change. | Write not tested. |
| `repo_search_commits` | `POST https://almsearch.dev.azure.com/{org}/_apis/search/commitSearchResults?api-version=7.2-preview.1`. Candidate on-prem route is `POST C/_apis/search/commitSearchResults`. | Not tested; do not assume the cloud host is available on-prem. |
| `repo_pull_request_write.create` | `POST GIT(P,R)/pullRequests` (`7.2-preview.2`); if the response has no PR, a fallback `GET` to the same route searches by source/target/status. | Write not tested. |
| `repo_pull_request_write.update` | `PATCH GIT(P,R)/pullRequests/{PR}` (`7.2-preview.2`); if only labels are changed, the upstream then `GET`s the PR. Auto-complete changes first call `GET C/_apis/connectionData`. | Write not tested. |
| `repo_pull_request_write` labels | `GET .../pullRequests/{PR}/labels`, then one `DELETE .../labels/{labelId}` per existing label and one `POST .../labels` per requested label (all `7.2-preview.1`). | Write not tested. |
| `repo_pull_request_write.update_reviewers` | Add: `POST .../pullRequests/{PR}/reviewers`; remove: one `DELETE .../reviewers/{reviewerId}` per ID (both `7.2-preview.1`). | Write not tested. |
| `repo_pull_request_write.vote` | `GET C/_apis/connectionData`, then `GET .../pullRequests/{PR}/reviewers/{userId}` and `PUT` the same reviewer route (`7.2-preview.1`). | Not tested; write not tested. |
| `repo_pull_request_thread_write` | Create thread: `POST .../pullRequests/{PR}/threads`; reply: `POST .../threads/{threadId}/comments`; update comment: `PATCH .../comments/{commentId}`; update status: `PATCH .../threads/{threadId}` (all `7.2-preview.1`). | Write not tested. |
| `repo_create_branch` | First `GET GIT(P,R)/refs` (`7.2-preview.2`), then `POST GIT(P,R)/refs` (`7.2-preview.2`) to create the branch from a selected source object ID. | Write not tested. |
| `pipelines_build.list` | `GET C/{P}/_apis/build/builds` (`7.2-preview.7`) with build, definition, status/result, repository, and paging filters. | Confirmed: build-run listing returned HTTP 200. |
| `pipelines_build.get_status` / `get_changes` | `GET C/{P}/_apis/build/builds/{buildId}/report` and `GET .../changes` (both `7.2-preview.2`). | Not tested. |
| `pipelines_build_log.list` / `get_content` | `GET C/{P}/_apis/build/builds/{buildId}/logs` and `GET .../logs/{logId}` (`7.2-preview.2`), optionally with start/end line query parameters. | Not tested. |
| `pipelines_definition.list` | `GET C/{P}/_apis/build/definitions` (`7.2-preview.7`). If filtering by a repository name rather than GUID for `TfsGit`, first call `GET C/{P}/_apis/git/repositories` (`7.2-preview.2`) and resolve the ID locally. | Confirmed: build-definition listing returned HTTP 200; repository lookup was confirmed separately. |
| `pipelines_definition.list_revisions` | `GET C/{P}/_apis/build/definitions/{definitionId}/revisions` (`7.2-preview.3`). | Not tested. |
| `pipelines_run.get` / `list` | `GET C/{P}/_apis/pipelines/{pipelineId}/runs/{runId}` and `GET .../runs` (both `7.2-preview.1`). | Partial: pipeline-family reads succeeded, but the saved record does not identify these exact run routes. |
| `pipelines_artifact.list` / `download` | List: `GET C/{P}/_apis/build/builds/{buildId}/artifacts`; download: `GET .../artifacts/{artifactName}` (both `7.2-preview.5`), then `GET` the returned `resource.downloadUrl` (dynamic URL, not a fixed ADO route). | Not tested. |
| `pipelines_write.run_pipeline` / `create_pipeline` | `POST C/{P}/_apis/pipelines/{pipelineId}/runs` and `POST C/{P}/_apis/pipelines` (both `7.2-preview.1`). | Write not tested. |
| `pipelines_write.rename_pipeline` | `GET C/{P}/_apis/build/definitions/{definitionId}`, then `PUT` the same route (`7.2-preview.7`). | Write not tested. |
| `pipelines_write.update_build_stage` | `PATCH C/{P}/_apis/build/builds/{buildId}/stages/{stageName}?api-version=7.2-preview.1`. | Write not tested. |
| `testplan.list_plans` / `list_suites` | `GET C/{P}/_apis/testplan/Plans` and `GET .../Plans/{PLAN}/Suites?expand=children` (both `7.2-preview.1`), with continuation tokens. | Confirmed: plan and suite reads returned HTTP 200; nested responses can be large. |
| `testplan.list_cases` | `GET C/{P}/_apis/testplan/Plans/{PLAN}/Suites/{SUITE}/TestCase` (`7.2-preview.3`). | Not individually recorded. |
| `testplan_show_test_results_from_build_id` | `GET C/{P}/_apis/test/runs?buildUri=...` (`7.2-preview.1`), then `GET C/{P}/_apis/test/Runs/{runId}/Results` (`7.2-preview.2`) for each run, with paging/outcome filters. | Partial: test-run reads succeeded with API versions `5.0` and `6.0`; the upstream `7.2-preview.1` run version and result-page call were not separately verified. |
| `testplan_test_plan_write.create` | `POST C/{P}/_apis/testplan/Plans` (`7.2-preview.1`) with the plan body. | Write not tested. |
| `testplan_test_suite_write.create` / `add_test_cases` | `POST C/{P}/_apis/testplan/Plans/{PLAN}/Suites` (`7.2-preview.1`); `POST C/{P}/_apis/test/Plans/{PLAN}/Suites/{SUITE}/TestCases/{testCaseIds}` (`7.2-preview.3`). | Write not tested. |
| `testplan_test_case_write.create` / `update_steps` | `POST C/{P}/_apis/wit/workItems/$Test%20Case` and `PATCH C/{P}/_apis/wit/workItems/{testCaseId}` (both `7.1-preview.3`), using JSON Patch. | Write not tested. |
| `wiki.list_wikis` / `get_wiki` | `GET C/{P?}/_apis/wiki/wikis` and `GET C/{P?}/_apis/wiki/wikis/{wikiId}` (both `7.2-preview.2`). | Confirmed: wiki discovery returned HTTP 200; individual wiki detail was not separately recorded. |
| `wiki.list_pages` | `POST C/{P}/_apis/wiki/wikis/{wikiId}/pagesbatch` (`7.2-preview.1`) with top, continuation token, and page-view options. | Not tested. |
| `wiki.get_page` | `GET C/{P}/_apis/wiki/wikis/{wikiId}/pages?path=...` (`7.2-preview.1`) with optional recursion level. | Not tested. |
| `wiki.get_page_content` | Path form: `GET .../pages?path=...&includeContent=true` through `getPageText` (`7.2-preview.1`). Page-ID form: `GET .../pages/{pageId}?includeContent=true&api-version=7.1`; if content is absent, it falls back to `getPageText`. | Not tested. |
| `wiki_upsert_page` | `PUT C/{P}/_apis/wiki/wikis/{wikiId}/pages?path=...&versionDescriptor...&api-version=7.1`; on HTTP 409/500 it may `GET` the same route to obtain an ETag, then `PUT` with `If-Match`. | Write not tested. |
| `search_code` | Upstream: `POST https://almsearch.dev.azure.com/{org}/_apis/search/codesearchresults?api-version=7.2-preview.1`; on-prem candidate: `POST C/_apis/search/codesearchresults`. Body contains search text, filters, facets, `$skip`, and `$top`. | Confirmed: collection-local POST returned HTTP 200; GET returned 405 on the tested instance. |
| `search_wiki` | Upstream: `POST https://almsearch.dev.azure.com/{org}/_apis/search/wikisearchresults?api-version=7.2-preview.1`; on-prem candidate: `POST C/_apis/search/wikisearchresults`. | Confirmed: collection-local POST returned HTTP 200; GET returned 405 on the tested instance. |
| `search_workitem` | Upstream: `POST https://almsearch.dev.azure.com/{org}/_apis/search/workitemsearchresults?api-version=7.2-preview.1`; on-prem candidate: `POST C/_apis/search/workitemsearchresults`. | Confirmed: collection-local POST returned HTTP 200; GET returned 405 on the tested instance. |
| `advsec_get_alerts` | Upstream Advanced Security call: `GET https://advsec.dev.azure.com/{org}/{P}/_apis/alert/repositories/{R}/alerts?api-version=7.2-preview.1`. | Cloud-only feature; not tested on-prem and omitted. |
| `advsec_get_alert_details` | Upstream Advanced Security call: `GET https://advsec.dev.azure.com/{org}/{P}/_apis/alert/repositories/{R}/alerts/{alertId}?api-version=7.2-preview.1`. | Cloud-only feature; not tested on-prem and omitted. |

### SDK-internal route discovery

The pinned `azure-devops-node-api` makes additional requests before the
tool-level calls above. When an API client is first acquired on a `WebApi`
connection, it resolves the resource-area URL by calling the Locations API:

1. `OPTIONS C/_apis/Location` (no `api-version`) discovers the Locations API
   route.
2. `GET C/_apis/resourceAreas?api-version=7.2-preview.1` retrieves resource
   area URLs. The tested on-prem collection returned the empty-area
   representation, so the SDK uses the collection URL `C`.
3. Before the first method call for each resource area on that connection,
   `OPTIONS C/_apis/{area}` (no `api-version`) discovers route templates and
   supported API versions. The SDK caches these locations per area and
   connection.

The upstream client factory creates a new `WebApi` connection for each client
provider call, so these caches do not persist across separate connections.
The discovered areas and results below are specific to the tested collection.
Successful discovery does not prove that every tool operation or API version
in an area is supported.

| SDK resource area | Upstream use | Prior instance probe |
|---|---|---|
| `Location` | Resolve the `resourceAreas` endpoint. | Confirmed: `OPTIONS` found the route, and the versioned `GET` returned HTTP 200 with the on-prem empty-area representation. |
| `Test`, `build`, `core`, `git`, `pipelines`, `testplan`, `testresults`, `wiki`, `wit`, `work` | Route/version discovery for tool API methods. | Confirmed: each `OPTIONS` request returned HTTP 200 with resource-location metadata. This is discovery evidence only, not operation-level coverage. |
| `Alert` | Advanced Security API methods. | `OPTIONS` returned HTTP 200 with no resource locations. The pinned SDK cannot resolve the upstream Alert route on this collection; Advanced Security remains omitted. |

This is an instance-specific compatibility record, not a server-version
guarantee. The previous probe was read-only; no write endpoint above has been
called live. A successful response for one route does not establish support
for neighboring routes, preview API versions, or other Azure DevOps Server
releases. The ledger records explicit tool/helper calls, and this section
records the additional SDK-internal discovery requests. The Python collection
client must either reproduce the relevant discovery behavior or replace it
with explicit collection-local routes and equivalent compatibility tests.

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
