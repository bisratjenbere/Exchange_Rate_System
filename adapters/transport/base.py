
from enum import Enum
class FetchKind(str, Enum):
    """How to fetch content from source."""
    HTTP_GET = "http_get"
    HTTP_POST = "http_post"
    BROWSER = "browser"
