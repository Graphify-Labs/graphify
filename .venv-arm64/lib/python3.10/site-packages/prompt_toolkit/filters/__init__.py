"""
Filters decide whether something is active or not (they decide about a boolean
state). This is used to enable/disable features, like key bindings, parts of
the layout and other stuff. For instance, we could have a `HasSearch` filter
attached to some part of the layout, in order to show that part of the user
interface only while the user is searching.

Filters are made to avoid having to attach callbacks to all event in order to
propagate state. However, they are lazy, they don't automatically propagate the
state of what they are observing. Only when a filter is called (it's actually a
callable), it will calculate its value. So, its not really reactive
programming, but it's made to fit for this framework.

Filters can be chained using ``&`` and ``|`` operations, and inverted using the
``~`` operator, for instance::

    filter = has_focus('default') & ~ has_selection
"""

from __future__ import annotations

from .app import *
from .base import Always, Condition, Filter, FilterOrBool, Never
from .cli import *
from .utils import is_true, to_filter

__all__ = [
    # app
    "has_arg",
    "has_completions",
    "completion_is_selected",
    "has_focus",
    "buffer_has_focus",
    "has_selection",
    "has_validation_error",
    "is_done",
    "is_read_only",
    "is_multiline",
    "renderer_height_is_known",
    "in_editing_mode",
    "in_paste_mode",
    "vi_mode",
    "vi_navigation_mode",
    "vi_insert_mode",
    "vi_insert_multiple_mode",
    "vi_replace_mode",
    "vi_selection_mode",
    "vi_waiting_for_text_object_mode",
    "vi_digraph_mode",
    "vi_recording_macro",
    "emacs_mode",
    "emacs_insert_mode",
    "emacs_selection_mode",
    "shift_selection_mode",
    "is_searching",
    "control_is_searchable",
    "vi_search_direction_reversed",
    # base.
    "Filter",
    "Never",
    "Always",
    "Condition",
    "FilterOrBool",
    # utils.
    "is_true",
    "to_filter",
]

from .cli import __all__ as cli_all

__all__.extend(cli_all)
