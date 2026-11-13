"""The Azure DevOps REST operations the tools call.

Each operation names a resource area and location ID for route discovery and
the API version upstream requests. Location IDs and versions for the `core`,
`wit`, and `work` areas come from `azure-devops-node-api` 15.1.2
(`CoreApi.js`, `WorkItemTrackingApi.js`, `WorkApi.js`). The search and identity
location IDs come from Microsoft's `azure-devops-python-api` (`v7_1`); their
area names are unconfirmed, so both carry upstream's fixed route as a fallback.
"""

from dataclasses import dataclass

from .constants import BATCH_API_VERSION, DIRECT_CALL_API_VERSION


@dataclass(frozen=True)
class Operation:
    """One REST operation.

    With `area` set, the route and version come from discovery, falling back to
    `fallback_path` and `fallback_version` when the server does not advertise
    the location. With `area` unset, the fixed fallback route is always used.
    """

    area: str | None
    location_id: str | None
    requested_version: str | None
    fallback_path: str | None = None
    fallback_version: str | None = None


PROJECTS = Operation("core", "603fe2ac-9723-48b9-88ad-09305aa6c6e1", "7.2-preview.4")
TEAMS = Operation("core", "d30a3dd1-f8ba-442a-b86a-bd0c0c383e59", "7.2-preview.3")
CLASSIFICATION_NODES = Operation("wit", "a70579d1-f53a-48ee-a5be-7be8659023b9", "7.1-preview.2")
WORK_ITEM = Operation("wit", "72c7ddf8-2cdc-4f60-90cd-ab71c14a399b", "7.1-preview.3")
WORK_ITEM_CREATE = Operation("wit", "62d3d110-0047-428c-ad3c-4fe872c91c74", "7.1-preview.3")
WORK_ITEMS_BATCH = Operation("wit", "908509b6-4248-4475-a1cd-829139ba419f", "7.1-preview.1")
# Shared by comment listing, add, and update; add and update override the version.
COMMENTS = Operation("wit", "608aac0a-32e1-4493-a863-b9cf4566d257", "7.1-preview.3")
REVISIONS = Operation("wit", "a00c85a5-80fa-4565-99c3-bcd2181434bb", "7.1-preview.3")
WORK_ITEM_TYPE = Operation("wit", "7c8d7a76-4a09-43e8-b5df-bd792f4ac6aa", "7.1-preview.2")
QUERY = Operation("wit", "a67d190c-c41f-424b-814d-0e906f659301", "7.1-preview.2")
QUERY_BY_ID = Operation("wit", "a02355f5-5f8a-4671-8e32-369d23aac83d", "7.1-preview.2")
QUERY_BY_WIQL = Operation("wit", "1a9c53f7-f243-4447-b110-35ef023636e4", "7.1-preview.2")
TEAM_ITERATIONS = Operation("work", "c9175577-28a1-4b06-9197-8636af9f64ad", "7.2-preview.1")
TEAM_SETTINGS = Operation("work", "c3c1012b-bea7-49d7-b45e-1664e566f84c", "7.2-preview.1")
TEAM_FIELD_VALUES = Operation("work", "07ced576-58ed-49e6-9c1e-5cb53ab8bf2a", "7.2-preview.1")
TEAM_CAPACITIES = Operation("work", "74412d15-8c1a-4352-a48d-ef1ed5587d57", "7.2-preview.3")
ITERATION_CAPACITIES = Operation("work", "1e385ce0-396b-4273-8171-d64562c18d37", "7.2-preview.1")
PREDEFINED_QUERY = Operation("work", "9cbba37c-6cc6-4f70-b903-709be86acbf0", "7.2-preview.1")
ITERATION_WORK_ITEMS = Operation("work", "5b3ef1a6-d3ab-44cd-bafd-c7f45db850fa", "7.2-preview.1")
BACKLOGS = Operation("work", "a93726f9-7867-4e38-b4f2-0bfafc2f6a94", "7.2-preview.1")
BACKLOG_WORK_ITEMS = Operation("work", "7c468d96-ab1d-4294-a360-92f07e9ccd98", "7.2-preview.1")
WORK_ITEM_SEARCH = Operation(
    "search",
    "73b2c9e2-ff9e-4447-8cda-5f5b21ff7cae",
    DIRECT_CALL_API_VERSION,
    fallback_path="_apis/search/workitemsearchresults",
    fallback_version=DIRECT_CALL_API_VERSION,
)
IDENTITIES = Operation(
    "IMS",
    "28010c54-d0c0-4c89-a5b0-1c9e188b9fb7",
    DIRECT_CALL_API_VERSION,
    fallback_path="_apis/identities",
    fallback_version=DIRECT_CALL_API_VERSION,
)
# Sent with no api-version, as upstream sends it; every server accepts that.
CONNECTION_DATA = Operation(None, None, None, fallback_path="_apis/connectionData")
# No SDK publishes a location for $batch, so upstream's fixed version is kept.
WORK_ITEM_BATCH_UPDATE = Operation(
    None, None, None, fallback_path="_apis/wit/$batch", fallback_version=BATCH_API_VERSION
)
