"""
Default key bindings.::

    key_bindings = load_key_bindings()
    app = Application(key_bindings=key_bindings)
"""

from __future__ import annotations

from prompt_toolkit.filters import buffer_has_focus
from prompt_toolkit.key_binding.bindings.basic import load_basic_bindings
from prompt_toolkit.key_binding.bindings.cpr import load_cpr_bindings
from prompt_toolkit.key_binding.bindings.emacs import (
    load_emacs_bindings,
    load_emacs_search_bindings,
    load_emacs_shift_selection_bindings,
)
from prompt_toolkit.key_binding.bindings.mouse import load_mouse_bindings
from prompt_toolkit.key_binding.bindings.vi import (
    load_vi_bindings,
    load_vi_search_bindings,
)
from prompt_toolkit.key_binding.key_bindings import (
    ConditionalKeyBindings,
    KeyBindingsBase,
    merge_key_bindings,
)

__all__ = [
    "load_key_bindings",
]


def load_key_bindings() -> KeyBindingsBase:
    """
    Create a KeyBindings object that contains the default key bindings.
    """
    all_bindings = merge_key_bindings(
        [
            # Load basic bindings.
            load_basic_bindings(),
            # Load emacs bindings.
            load_emacs_bindings(),
            load_emacs_search_bindings(),
            load_emacs_shift_selection_bindings(),
            # Load Vi bindings.
            load_vi_bindings(),
            load_vi_search_bindings(),
        ]
    )

    return merge_key_bindings(
        [
            # Make sure that the above key bindings are only active if the
            # currently focused control is a `BufferControl`. For other controls, we
            # don't want these key bindings to intervene. (This would break "ptterm"
            # for instance, which handles 'Keys.Any' in the user control itself.)
            ConditionalKeyBindings(all_bindings, buffer_has_focus),
            # Active, even when no buffer has been focused.
            load_mouse_bindings(),
            load_cpr_bindings(),
        ]
    )
