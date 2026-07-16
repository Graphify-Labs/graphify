from typing import Final
from typing_extensions import CapsuleType

HIGHLIGHTS_QUERY: Final[str]
INJECTIONS_QUERY: Final[str]
LOCALS_QUERY: Final[str]
TAGS_QUERY: Final[str]

def language() -> CapsuleType: ...
