# ruff: noqa: N803, N815, A002
# Input names are upstream's camelCase names; they are the public tool schema.
"""Work-item write tools: `wit_work_item_write`, `wit_work_item_comment_write`,
and `wit_work_item_link_write`.

Every write is sent once and never retried.
"""

from collections.abc import Sized
import re
from typing import Annotated, Literal

from fastmcp import Context, FastMCP
from fastmcp.tools import ToolResult
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..client import AdoClient
from ..constants import (
    BATCH_API_VERSION,
    COMMENT_FORMAT_CODES,
    HYPERLINK_TYPE,
    JSON_PATCH_CONTENT_TYPE,
    LINK_TYPES,
    MARKDOWN_COMMENTS_API_VERSION,
    MARKDOWN_FORMAT,
    MAX_CHILD_ITEMS,
    MAX_PAGE_SIZE,
    MUTATING_ANNOTATIONS,
    PARENT_RELATION,
    WIT_WORK_ITEM_COMMENT_WRITE,
    WIT_WORK_ITEM_LINK_WRITE,
    WIT_WORK_ITEM_WRITE,
)
from ..elicitation import resolve_project
from ..exceptions import AdoHttpError, AdoMcpError, InvalidInputError, UnsupportedOnServerError
from ..operations import COMMENTS, WORK_ITEM, WORK_ITEM_BATCH_UPDATE, WORK_ITEM_CREATE
from ..utils import (
    JsonValue,
    encode_markdown_value,
    encode_path_segment,
    escape_html,
    to_json_text,
    work_item_url,
)
from ._shared import (
    ItemId,
    action_label,
    ado_tool,
    get_client,
    get_settings,
    json_result,
    plain_error,
    require,
    search_identities,
    text_result,
)

TextFormat = Literal["Html", "Markdown"]
LinkTypeName = Literal[
    "parent",
    "child",
    "duplicate",
    "duplicate of",
    "related",
    "successor",
    "predecessor",
    "tested by",
    "tests",
    "affects",
    "affected by",
    "hyperlink",
]
UnlinkTypeName = LinkTypeName | Literal["artifact"]

_FIELDS_PREFIX = "/fields"
_MULTILINE_FORMAT_PREFIX = "/multilineFieldsFormat"
_RELATIONS_APPEND = "/relations/-"
_TITLE_PATH = "/fields/System.Title"
_AREA_PATH = "/fields/System.AreaPath"
_ITERATION_PATH = "/fields/System.IterationPath"
_DESCRIPTION_PATH = "/fields/System.Description"
_REPRO_STEPS_PATH = "/fields/Microsoft.VSTS.TCM.ReproSteps"
# Bugs keep their description in Repro Steps instead of System.Description.
_BUG_TYPE = "bug"
_BATCH_ITEM_URI = "/_apis/wit/workitems/{id}?api-version={version}"
_BATCH_CREATE_URI = "/{project}/_apis/wit/workitems/${type}?api-version={version}"
_RELATIONS_EXPAND = "Relations"
# Upstream adds the status text to update errors for these statuses.
_CONCURRENCY_STATUS_TEXT = {409: "Conflict", 412: "Precondition Failed"}
_TOO_MANY_IDS = f"At most {MAX_PAGE_SIZE} distinct work item IDs can be sent in one batch."
_NOT_CREATED = "Work item was not created"
_VALUE_REQUIRED = "value is required for {op}"
_CONCURRENCY_MESSAGE = "[HTTP {status} {text}] {detail}"
_MARKDOWN_UNSUPPORTED = (
    "Markdown comments need comment API {required}; this server offers {offered}. "
    "Pass format 'Html'."
)

# Mentions written as @<email>; a GUID mention is written as @<guid>.
_EMAIL_MENTION = re.compile(r"@<([^<>\s]+@[^<>\s]+)>")
_MENTION_OR_SPECIAL = re.compile(
    r"@<([^<>\s]+@[^<>\s]+)>"
    r"|@<([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})>"
    r"|[&<>]",
    re.IGNORECASE,
)
_HTML_MENTION = '<a href="#" data-vss-mention="version:2.0,{id}">@{name}</a>'


class _StrictModel(BaseModel):
    """Nested tool input: strict types, no unknown keys."""

    model_config = ConfigDict(strict=True, extra="forbid")


class FieldValue(_StrictModel):
    """One field to set when creating a work item."""

    name: str
    value: str
    format: TextFormat | None = None


class PatchOperation(_StrictModel):
    """One JSON Patch operation for `update`."""

    op: Literal["add", "replace", "remove", "test"] = "add"
    path: str
    value: JsonValue = None

    @field_validator("op", mode="before")
    @staticmethod
    def _lower_op(value: object) -> object:
        """Accept any letter case for `op`, as upstream does: `"Replace"` -> `"replace"`."""
        return value.lower() if isinstance(value, str) else value


class BatchUpdate(_StrictModel):
    """One field update in `update_batch`."""

    op: Literal["Add", "Replace", "Remove"] = "Add"
    id: ItemId
    path: str
    value: str
    format: TextFormat | None = None


class ChildItem(_StrictModel):
    """One child work item to create under a parent."""

    title: str
    description: str
    format: TextFormat = "Markdown"
    areaPath: str | None = None
    iterationPath: str | None = None


class LinkUpdate(_StrictModel):
    """One relation to add in `link`."""

    id: ItemId
    linkToId: ItemId | None = None
    url: str | None = None
    type: LinkTypeName = "related"
    comment: str | None = None


def multiline_format_path(path: str) -> str:
    """Return the format-metadata path for a field path.

    Example: `"/fields/System.Description"` -> `"/multilineFieldsFormat/System.Description"`.
    """
    return f"{_MULTILINE_FORMAT_PREFIX}{path.replace(_FIELDS_PREFIX, '', 1)}"


def _add(path: str, value: JsonValue) -> dict[str, JsonValue]:
    """Build a JSON Patch `add` operation."""
    return {"op": "add", "path": path, "value": value}


def _batch_request(uri: str, operations: list[JsonValue]) -> dict[str, JsonValue]:
    """Build one inner request of a `$batch` call."""
    return {
        "method": "PATCH",
        "uri": uri,
        "headers": {"Content-Type": JSON_PATCH_CONTENT_TYPE},
        "body": operations,
    }


def _check_batch_size(grouped: Sized) -> None:
    """Fail when a batch would touch more distinct work items than one page allows."""
    if len(grouped) > MAX_PAGE_SIZE:
        raise InvalidInputError(_TOO_MANY_IDS)


async def _send_batch(client: AdoClient, label: str, requests: list[JsonValue]) -> ToolResult:
    reply = await client.send(
        WORK_ITEM_BATCH_UPDATE, label=label, method="PATCH", json_body=requests
    )
    return json_result(reply)


async def _create(
    client: AdoClient, label: str, project: str, workItemType: str, fields: list[FieldValue]
) -> ToolResult:
    document: list[JsonValue] = [
        _add(f"{_FIELDS_PREFIX}/{field.name}", encode_markdown_value(field.value, field.format))
        for field in fields
    ]
    document += [
        _add(multiline_format_path(f"{_FIELDS_PREFIX}/{field.name}"), MARKDOWN_FORMAT)
        for field in fields
        if field.format == MARKDOWN_FORMAT
    ]
    reply = await client.send(
        WORK_ITEM_CREATE,
        label=label,
        method="POST",
        route_values={"project": project, "type": workItemType},
        json_body=document,
        content_type=JSON_PATCH_CONTENT_TYPE,
    )
    if reply is None:
        return plain_error(_NOT_CREATED)
    return json_result(reply)


async def _update(
    client: AdoClient, label: str, id: int, updates: list[PatchOperation]
) -> ToolResult:
    # `value` may be JSON null, so "omitted" is read from the fields that were set.
    for update in updates:
        if update.op != "remove" and "value" not in update.model_fields_set:
            raise InvalidInputError(_VALUE_REQUIRED.format(op=update.op))
    document: list[JsonValue] = [
        {"op": update.op, "path": update.path, "value": update.value}
        if "value" in update.model_fields_set
        else {"op": update.op, "path": update.path}
        for update in updates
    ]
    try:
        reply = await client.send(
            WORK_ITEM,
            label=label,
            method="PATCH",
            route_values={"id": id},
            json_body=document,
            content_type=JSON_PATCH_CONTENT_TYPE,
        )
    except AdoHttpError as error:
        status_text = _CONCURRENCY_STATUS_TEXT.get(error.status or 0)
        if status_text is None:
            raise
        # Keeps upstream's concurrency signal, e.g. "[HTTP 412 Precondition Failed]".
        message = _CONCURRENCY_MESSAGE.format(
            status=error.status, text=status_text, detail=error.extra_detail
        )
        raise AdoHttpError(message, label=label, status=error.status) from None
    return json_result(reply)


async def _update_batch(
    client: AdoClient, label: str, batchUpdates: list[BatchUpdate]
) -> ToolResult:
    # Group by ID in one pass, keeping the first-seen order of IDs.
    grouped: dict[int, list[BatchUpdate]] = {}
    for update in batchUpdates:
        grouped.setdefault(update.id, []).append(update)
    _check_batch_size(grouped)
    requests: list[JsonValue] = []
    for item_id, updates in grouped.items():
        operations: list[JsonValue] = [
            {
                "op": update.op,
                "path": update.path,
                "value": encode_markdown_value(update.value, update.format),
            }
            for update in updates
        ]
        operations += [
            {"op": "Add", "path": multiline_format_path(update.path), "value": MARKDOWN_FORMAT}
            for update in updates
            if update.format == MARKDOWN_FORMAT
        ]
        uri = _BATCH_ITEM_URI.format(id=item_id, version=BATCH_API_VERSION)
        requests.append(_batch_request(uri, operations))
    return await _send_batch(client, label, requests)


def _child_operations(
    item: ChildItem, number: int, parent_url: str, is_bug: bool
) -> list[JsonValue]:
    """Build the JSON Patch document for child item `number` (1-based)."""
    operations: list[JsonValue] = [
        _add("/id", f"-{number}"),
        _add(_TITLE_PATH, item.title),
        _add(_RELATIONS_APPEND, {"rel": PARENT_RELATION, "url": parent_url}),
    ]
    if item.areaPath and item.areaPath.strip():
        operations.append(_add(_AREA_PATH, item.areaPath))
    if item.iterationPath and item.iterationPath.strip():
        operations.append(_add(_ITERATION_PATH, item.iterationPath))
    description_path = _REPRO_STEPS_PATH if is_bug else _DESCRIPTION_PATH
    operations.append(_add(description_path, encode_markdown_value(item.description, item.format)))
    if item.format == MARKDOWN_FORMAT:
        operations.append(_add(multiline_format_path(description_path), MARKDOWN_FORMAT))
    return operations


async def _add_child(
    client: AdoClient,
    label: str,
    collection_url: str,
    project: str,
    parentId: int,
    workItemType: str,
    items: list[ChildItem],
) -> ToolResult:
    parent_url = work_item_url(collection_url, project, parentId)
    is_bug = workItemType.lower() == _BUG_TYPE
    uri = _BATCH_CREATE_URI.format(
        project=encode_path_segment(project),
        type=encode_path_segment(workItemType),
        version=BATCH_API_VERSION,
    )
    requests: list[JsonValue] = [
        _batch_request(uri, _child_operations(item, number, parent_url, is_bug))
        for number, item in enumerate(items, start=1)
    ]
    return await _send_batch(client, label, requests)


@ado_tool
async def wit_work_item_write(
    ctx: Context,
    action: Literal["create", "update", "update_batch", "add_child"],
    project: str | None = None,
    id: ItemId | None = None,
    workItemType: str | None = None,
    fields: list[FieldValue] | None = None,
    updates: list[PatchOperation] | None = None,
    batchUpdates: list[BatchUpdate] | None = None,
    parentId: ItemId | None = None,
    items: Annotated[list[ChildItem], Field(max_length=MAX_CHILD_ITEMS)] | None = None,
) -> ToolResult:
    """Create, update, batch-update, or add child work items."""
    client = get_client(ctx)
    settings = get_settings(ctx)
    label = action_label(WIT_WORK_ITEM_WRITE, action)
    if action == "update":
        # `update` and `update_batch` never resolve a project: they are collection-scoped.
        work_item_id = require(id, "id is required for update")
        operations = require(updates, "updates is required for update")
        return await _update(client, label, work_item_id, operations)
    if action == "update_batch":
        batch = require(batchUpdates, "batchUpdates is required for update_batch")
        return await _update_batch(client, label, batch)
    if action == "create":
        item_type = require(workItemType, "workItemType is required for create")
        field_values = require(fields, "fields is required for create")
        resolved = await resolve_project(
            ctx,
            client,
            settings,
            project,
            "Select the Azure DevOps project to create the work item in.",
        )
        return await _create(client, label, resolved, item_type, field_values)
    parent = require(parentId, "parentId is required for add_child")
    item_type = require(workItemType, "workItemType is required for add_child")
    children = require(items, "items is required for add_child")
    resolved = await resolve_project(
        ctx,
        client,
        settings,
        project,
        "Select the Azure DevOps project to create child work items in.",
    )
    return await _add_child(
        client, label, settings.collection_url, resolved, parent, item_type, children
    )


async def _resolve_mention(client: AdoClient, email: str, label: str) -> tuple[str, str] | None:
    """Look up an email mention; return `(id, display name)` or `None` when unresolved."""
    try:
        identities = await search_identities(client, email, label)
    except AdoMcpError:
        return None
    first = identities[0] if identities else None
    identity_id = first.get("id") if isinstance(first, dict) else None
    if not isinstance(first, dict) or not isinstance(identity_id, str):
        return None
    name = first.get("providerDisplayName")
    return identity_id, name if isinstance(name, str) and name else email


async def prepare_comment_text(client: AdoClient, text: str, text_format: str, label: str) -> str:
    """Resolve `@<email>` mentions and encode a comment for its format.

    Each distinct email is looked up once. In one pass over the text: a GUID
    mention is kept; a bare `&`, `<`, or `>` becomes an entity in Markdown and is
    kept in Html; an unresolved email mention is HTML-escaped; a resolved one
    becomes `@<{id}>` (Markdown) or a mention anchor (Html).

    Examples, with `ana@example.com` resolving to id
    `11111111-2222-3333-4444-555555555555` and display name `Ana`:

    - `a < b & c`, Markdown -> `a &lt; b &amp; c`
    - `a < b`, Html -> `a < b`
    - `cc @<ana@example.com>`, Markdown -> `cc @<11111111-2222-3333-4444-555555555555>`
    - `cc @<ana@example.com>`, Html -> `cc <a href="#"
      data-vss-mention="version:2.0,11111111-2222-3333-4444-555555555555">@Ana</a>`
    - `cc @<nobody@example.com>`, either -> `cc @&lt;nobody@example.com&gt;`
    """
    identities = {}
    for email in dict.fromkeys(_EMAIL_MENTION.findall(text)):
        resolved = await _resolve_mention(client, email, label)
        if resolved is not None:
            identities[email] = resolved
    markdown = text_format == MARKDOWN_FORMAT

    def replace(match: re.Match[str]) -> str:
        email, guid = match.group(1), match.group(2)
        if guid:
            return match.group(0)
        if not email:
            return escape_html(match.group(0)) if markdown else match.group(0)
        identity = identities.get(email)
        if identity is None:
            return escape_html(match.group(0))
        identity_id, name = identity
        if markdown:
            return f"@<{identity_id}>"
        return _HTML_MENTION.format(id=identity_id, name=escape_html(name))

    return _MENTION_OR_SPECIAL.sub(replace, text)


@ado_tool
async def wit_work_item_comment_write(
    ctx: Context,
    action: Literal["add", "update"],
    project: str | None = None,
    workItemId: ItemId | None = None,
    text: str | None = None,
    commentId: ItemId | None = None,
    format: TextFormat = "Markdown",
) -> ToolResult:
    """Add or update a work-item comment in Markdown or Html."""
    client = get_client(ctx)
    label = action_label(WIT_WORK_ITEM_COMMENT_WRITE, action)
    purpose = "add a work item comment in" if action == "add" else "update the work item comment in"
    resolved = await resolve_project(
        ctx, client, get_settings(ctx), project, f"Select the Azure DevOps project to {purpose}."
    )
    work_item_id = require(workItemId, "workItemId is required")
    comment_text = require(text, "text is required")
    comment_id = (
        require(commentId, "commentId is required for update") if action == "update" else None
    )
    negotiated = await client.negotiated_version(
        COMMENTS, MARKDOWN_COMMENTS_API_VERSION, label=label
    )
    # Only comment API 7.2-preview.4 takes the `format` parameter.
    supports_format = negotiated in (None, MARKDOWN_COMMENTS_API_VERSION)
    if format == MARKDOWN_FORMAT and not supports_format:
        message = _MARKDOWN_UNSUPPORTED.format(
            required=MARKDOWN_COMMENTS_API_VERSION, offered=negotiated
        )
        raise UnsupportedOnServerError(message, label=label)
    prepared = await prepare_comment_text(client, comment_text, format, label)
    reply = await client.send(
        COMMENTS,
        label=label,
        method="POST" if comment_id is None else "PATCH",
        route_values={"project": resolved, "workItemId": work_item_id, "commentId": comment_id},
        query={"format": COMMENT_FORMAT_CODES[format] if supports_format else None},
        json_body={"text": prepared},
        version_override=MARKDOWN_COMMENTS_API_VERSION,
    )
    return json_result(reply)


def _link_operation(update: LinkUpdate, collection_url: str, project: str) -> dict[str, JsonValue]:
    """Build the `add /relations/-` operation for one link update."""
    if update.type == HYPERLINK_TYPE:
        url = require(update.url, "url is required for hyperlink links")
    else:
        target = require(update.linkToId, "linkToId is required for work item links")
        url = work_item_url(collection_url, project, target)
    return _add(
        _RELATIONS_APPEND,
        {
            "rel": LINK_TYPES[update.type],
            "url": url,
            "attributes": {"comment": update.comment or ""},
        },
    )


async def _link(
    client: AdoClient, label: str, collection_url: str, project: str, updates: list[LinkUpdate]
) -> ToolResult:
    grouped: dict[int, list[JsonValue]] = {}
    for update in updates:
        grouped.setdefault(update.id, []).append(_link_operation(update, collection_url, project))
    _check_batch_size(grouped)
    requests: list[JsonValue] = [
        _batch_request(_BATCH_ITEM_URI.format(id=item_id, version=BATCH_API_VERSION), operations)
        for item_id, operations in grouped.items()
    ]
    return await _send_batch(client, label, requests)


async def _unlink(
    client: AdoClient, label: str, project: str, id: int, type: str, url: str | None
) -> ToolResult:
    route_values = {"project": project, "id": id}
    work_item = await client.send(
        WORK_ITEM,
        label=label,
        method="GET",
        route_values=route_values,
        query={"$expand": _RELATIONS_EXPAND},
    )
    relations = work_item.get("relations") if isinstance(work_item, dict) else None
    relations = relations if isinstance(relations, list) else []
    relation_type = LINK_TYPES[type]
    match_url = url if url and url.strip() else None
    indexes = [
        index
        for index, relation in enumerate(relations)
        if isinstance(relation, dict)
        and relation.get("rel") == relation_type
        and (match_url is None or relation.get("url") == match_url)
    ]
    if not indexes:
        url_note = f" and URL '{url}'" if url else ""
        return plain_error(
            f"No matching relations found for link type '{type}'{url_note}.\n"
            f"{to_json_text(relations)}"
        )
    removed: list[JsonValue] = [relations[index] for index in indexes]
    # Highest index first, so earlier removals do not shift later ones.
    document: list[JsonValue] = [
        {"op": "remove", "path": f"/relations/{index}"} for index in sorted(indexes, reverse=True)
    ]
    reply = await client.send(
        WORK_ITEM,
        label=label,
        method="PATCH",
        route_values=route_values,
        json_body=document,
        content_type=JSON_PATCH_CONTENT_TYPE,
    )
    return text_result(
        f"Removed {len(removed)} link(s) of type '{type}':\n{to_json_text(removed)}"
        f"\n\nUpdated work item result:\n{to_json_text(reply)}"
    )


@ado_tool
async def wit_work_item_link_write(
    ctx: Context,
    action: Literal["link", "unlink"],
    project: str | None = None,
    updates: list[LinkUpdate] | None = None,
    id: ItemId | None = None,
    type: UnlinkTypeName | None = None,
    url: str | None = None,
) -> ToolResult:
    """Add relations between work items, or remove relations of one type."""
    client = get_client(ctx)
    settings = get_settings(ctx)
    label = action_label(WIT_WORK_ITEM_LINK_WRITE, action)
    if action == "link":
        link_updates = require(updates, "updates is required for link")
        resolved = await resolve_project(
            ctx, client, settings, project, "Select the Azure DevOps project to link work items in."
        )
        return await _link(client, label, settings.collection_url, resolved, link_updates)
    work_item_id = require(id, "id is required for unlink")
    link_type = require(type, "type is required for unlink")
    resolved = await resolve_project(
        ctx, client, settings, project, "Select the Azure DevOps project to unlink work items in."
    )
    return await _unlink(client, label, resolved, work_item_id, link_type, url)


def register(mcp: FastMCP) -> None:
    """Register the three work-item write tools with the mutating annotation set."""
    annotations = dict(MUTATING_ANNOTATIONS)
    mcp.tool(
        wit_work_item_write,
        name=WIT_WORK_ITEM_WRITE,
        description=(
            "Write operations for work items. Use the action parameter to specify the operation."
        ),
        annotations=annotations,
    )
    mcp.tool(
        wit_work_item_comment_write,
        name=WIT_WORK_ITEM_COMMENT_WRITE,
        description=(
            "Write operations for work item comments. Use the action parameter to specify the "
            "operation."
        ),
        annotations=annotations,
    )
    mcp.tool(
        wit_work_item_link_write,
        name=WIT_WORK_ITEM_LINK_WRITE,
        description=(
            "Write operations for work item links. Use the action parameter to specify the "
            "operation."
        ),
        annotations=annotations,
    )
