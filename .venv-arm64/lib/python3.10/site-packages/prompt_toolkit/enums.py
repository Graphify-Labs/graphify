from __future__ import annotations

from enum import Enum


class EditingMode(Enum):
    # The set of key bindings that is active.
    VI = "VI"
    EMACS = "EMACS"


#: Name of the search buffer.
SEARCH_BUFFER = "SEARCH_BUFFER"

#: Name of the default buffer.
DEFAULT_BUFFER = "DEFAULT_BUFFER"

#: Name of the system buffer.
SYSTEM_BUFFER = "SYSTEM_BUFFER"
