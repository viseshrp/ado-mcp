"""All common utility functions and classes used in the code base are defined here."""

import base64
from collections.abc import Mapping
import json
from typing import TypeAlias
from urllib.parse import quote

import pydantic

from .constants import MARKDOWN_FORMAT, WORK_ITEM_URL_PATH

# JSON data as parsed from a reply or sent in a body. Replies are not modelled.
JsonValue: TypeAlias = pydantic.JsonValue
# A query-string value before encoding; `None` means "leave the parameter out".
QueryValue: TypeAlias = str | int | bool | None

# Characters HTML-escaped by `escape_html`, in replacement order (`&` first).
_HTML_ESCAPES = (
    ("&", "&amp;"),
    ("<", "&lt;"),
    (">", "&gt;"),
    ('"', "&quot;"),
    ("'", "&#39;"),
)
# Characters encoded in a Markdown field value, as upstream's encodeFormattedValue.
_MARKDOWN_ESCAPES = (("<", "&lt;"), (">", "&gt;"))


def build_basic_auth_header(pat: str) -> str:
    """Build the Basic `Authorization` value for a raw PAT, with an empty user name.

    Example: `"abc"` -> `"Basic OmFiYw=="` (base64 of `":abc"`).
    """
    token = base64.b64encode(f":{pat}".encode()).decode("ascii")
    return f"Basic {token}"


def encode_path_segment(value: str | int) -> str:
    """Percent-encode a value as one URL path segment, `/` included.

    Example: `"My Project/A"` -> `"My%20Project%2FA"`.
    """
    return quote(str(value), safe="")


def join_collection_url(collection_url: str, path: str) -> str:
    """Append a relative path to the collection URL, keeping the collection's path.

    Example: `("https://ado.example.net/tfs/DefaultCollection", "/_apis/wit")` ->
    `"https://ado.example.net/tfs/DefaultCollection/_apis/wit"`.
    """
    return f"{collection_url.rstrip('/')}/{path.lstrip('/')}"


def build_query(query: Mapping[str, QueryValue]) -> dict[str, str]:
    """Turn query values into strings, dropping `None` and spelling booleans in lower case.

    Example: `{"$top": 5, "mine": None, "includeCompleted": False}` ->
    `{"$top": "5", "includeCompleted": "false"}`.
    """
    params = {}
    for name, value in query.items():
        if value is None:
            continue
        # bool is checked first because it is a subclass of int.
        params[name] = str(value).lower() if isinstance(value, bool) else str(value)
    return params


def work_item_url(collection_url: str, project: str, work_item_id: int) -> str:
    """Build the REST URL of a work item, as used in relation links.

    Example: `("https://ado.example.net/tfs/DefaultCollection", "My Project", 7)` ->
    `"https://ado.example.net/tfs/DefaultCollection/My%20Project/_apis/wit/workItems/7"`.
    """
    path = WORK_ITEM_URL_PATH.format(project=encode_path_segment(project), id=work_item_id)
    return join_collection_url(collection_url, path)


def encode_markdown_value(value: str, value_format: str | None) -> str:
    """Encode `<` and `>` in a Markdown field value; other formats pass through.

    Examples: `("a < b", "Markdown")` -> `"a &lt; b"`; `("a < b", "Html")` -> `"a < b"`;
    `("a < b", None)` -> `"a < b"`.
    """
    if value_format != MARKDOWN_FORMAT:
        return value
    for character, entity in _MARKDOWN_ESCAPES:
        value = value.replace(character, entity)
    return value


def escape_html(value: str) -> str:
    """Escape `&`, `<`, `>`, `"`, and `'` as HTML entities.

    `html.escape` writes `&#x27;` for `'`; upstream writes `&#39;`, so this keeps
    upstream's output.

    Example: `"<a href='x'>&"` -> `"&lt;a href=&#39;x&#39;&gt;&amp;"`.
    """
    for character, entity in _HTML_ESCAPES:
        value = value.replace(character, entity)
    return value


def to_json_text(value: JsonValue) -> str:
    """Serialize a value as indented JSON, keeping non-ASCII text readable.

    Example: `{"a": 1}` -> `"{\\n  \\"a\\": 1\\n}"`.
    """
    return json.dumps(value, indent=2, ensure_ascii=False)
