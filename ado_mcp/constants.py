"""All constants used in the code base are defined here."""

from types import MappingProxyType

# Settings
ENV_PREFIX = "ADO_"
ENV_FILE_NAME = ".env"
# Azure DevOps Services (cloud) hosts. The host itself and every subdomain are
# rejected, because this server only talks to on-premises collections.
CLOUD_HOST_SUFFIXES = ("dev.azure.com", "visualstudio.com")

# Server and transports
SERVER_NAME = "ado-mcp"
HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8000
HTTP_PATH = "/mcp"

# Limits
MAX_PAGE_SIZE = 200
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_ERROR_MESSAGE_CHARS = 1000
MAX_CHILD_ITEMS = 50
MAX_WIQL_LENGTH = 32768
ELICITATION_PROJECT_LIMIT = 100
DEFAULT_PAGE_SIZE = 50
DEFAULT_SEARCH_PAGE_SIZE = 10
DEFAULT_ITERATION_DEPTH = 2
REQUEST_TIMEOUT_SECONDS = 60.0
CONNECT_TIMEOUT_SECONDS = 10.0

# REST conventions
API_VERSION_PARAM = "api-version"
BATCH_API_VERSION = "5.0"
MARKDOWN_COMMENTS_API_VERSION = "7.2-preview.4"
DIRECT_CALL_API_VERSION = "7.2-preview.1"
JSON_PATCH_CONTENT_TYPE = "application/json-patch+json"
READ_CONSISTENCY_HEADER = ("X-VSS-ReadConsistencyLevel", "Eventual")
# Text formats accepted by work-item fields and comments.
MARKDOWN_FORMAT = "Markdown"
HTML_FORMAT = "Html"
# Numeric values of the comment API's `format` query parameter.
COMMENT_FORMAT_CODES = MappingProxyType({MARKDOWN_FORMAT: 0, HTML_FORMAT: 1})
# Relative REST path of a work item, used in relation URLs.
WORK_ITEM_URL_PATH = "{project}/_apis/wit/workItems/{id}"

# Tool annotation sets, matching upstream `src/shared/tool-annotations.ts`.
READ_ONLY_ANNOTATIONS = MappingProxyType(
    {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    }
)
MUTATING_ANNOTATIONS = MappingProxyType(
    {
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }
)

# Tool names
CORE_LIST_PROJECTS = "core_list_projects"
CORE_LIST_PROJECT_TEAMS = "core_list_project_teams"
CORE_GET_IDENTITY_IDS = "core_get_identity_ids"
CORE_GET_CURRENT_USER = "core_get_current_user"
WORK = "work"
WIT_WORK_ITEM = "wit_work_item"
WIT_QUERY = "wit_query"
WIT_BACKLOG = "wit_backlog"
SEARCH_WORKITEM = "search_workitem"
WIT_WORK_ITEM_WRITE = "wit_work_item_write"
WIT_WORK_ITEM_COMMENT_WRITE = "wit_work_item_comment_write"
WIT_WORK_ITEM_LINK_WRITE = "wit_work_item_link_write"

# Domain of each tool, used for the untrusted-content source label
# ("Azure DevOps {domain}").
TOOL_DOMAINS = MappingProxyType(
    {
        CORE_LIST_PROJECTS: "core",
        CORE_LIST_PROJECT_TEAMS: "core",
        CORE_GET_IDENTITY_IDS: "core",
        CORE_GET_CURRENT_USER: "core",
        WORK: "work",
        WIT_WORK_ITEM: "work-items",
        WIT_QUERY: "work-items",
        WIT_BACKLOG: "work-items",
        WIT_WORK_ITEM_WRITE: "work-items",
        WIT_WORK_ITEM_COMMENT_WRITE: "work-items",
        WIT_WORK_ITEM_LINK_WRITE: "work-items",
        SEARCH_WORKITEM: "search",
    }
)
# Source labels that upstream sets explicitly, keyed by (tool, action).
SOURCE_LABEL_OVERRIDES = MappingProxyType(
    {
        (WIT_QUERY, "wiql"): "wiql query results",
        (SEARCH_WORKITEM, None): "work item search results",
    }
)

# Work-item link type names and their relation types.
LINK_TYPES = MappingProxyType(
    {
        "parent": "System.LinkTypes.Hierarchy-Reverse",
        "child": "System.LinkTypes.Hierarchy-Forward",
        "duplicate": "System.LinkTypes.Duplicate-Forward",
        "duplicate of": "System.LinkTypes.Duplicate-Reverse",
        "related": "System.LinkTypes.Related",
        "successor": "System.LinkTypes.Dependency-Forward",
        "predecessor": "System.LinkTypes.Dependency-Reverse",
        "tested by": "Microsoft.VSTS.Common.TestedBy-Forward",
        "tests": "Microsoft.VSTS.Common.TestedBy-Reverse",
        "affects": "Microsoft.VSTS.Common.Affects-Forward",
        "affected by": "Microsoft.VSTS.Common.Affects-Reverse",
        "artifact": "ArtifactLink",
        "hyperlink": "Hyperlink",
    }
)
HYPERLINK_TYPE = "hyperlink"
PARENT_RELATION = LINK_TYPES["parent"]

# Work-item fields
DEFAULT_BATCH_FIELDS = (
    "System.Id",
    "System.WorkItemType",
    "System.Title",
    "System.State",
    "System.Parent",
    "System.Tags",
    "Microsoft.VSTS.Common.StackRank",
    "System.AssignedTo",
)
IDENTITY_FIELDS = (
    "System.AssignedTo",
    "System.CreatedBy",
    "System.ChangedBy",
    "System.AuthorizedAs",
    "Microsoft.VSTS.Common.ActivatedBy",
    "Microsoft.VSTS.Common.ResolvedBy",
    "Microsoft.VSTS.Common.ClosedBy",
)

# Errors
HTTP_ERROR_CODES = MappingProxyType(
    {
        401: "authentication_failed",
        403: "permission_denied",
        404: "not_found",
        409: "conflict",
        412: "precondition_failed",
    }
)
DEFAULT_HTTP_ERROR_CODE = "request_failed"
# Code for a success reply whose body is not JSON.
INVALID_RESPONSE_CODE = "invalid_response"
FIRST_HTTP_ERROR_STATUS = 400
# `typeKey` values of the server's "API version not supported" error replies.
UNSUPPORTED_VERSION_TYPE_KEYS = frozenset(
    {"VssVersionOutOfRangeException", "VssInvalidPreviewVersionException"}
)
