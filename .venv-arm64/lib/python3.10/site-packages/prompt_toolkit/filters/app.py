"""
Filters that accept a `Application` as argument.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from prompt_toolkit.application.current import get_app
from prompt_toolkit.cache import memoized
from prompt_toolkit.enums import EditingMode

from .base import Condition

if TYPE_CHECKING:
    from prompt_toolkit.layout.layout import FocusableElement


__all__ = [
    "has_arg",
    "has_completions",
    "completion_is_selected",
    "has_focus",
    "buffer_has_focus",
    "has_selection",
    "has_suggestion",
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
]


# NOTE: `has_focus` below should *not* be `memoized`. It can reference any user
#       control. For instance, if we would continuously create new
#       `PromptSession` instances, then previous instances won't be released,
#       because this memoize (which caches results in the global scope) will
#       still refer to each instance.
def has_focus(value: FocusableElement) -> Condition:
    """
    Enable when this buffer has the focus.
    """
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.layout import walk
    from prompt_toolkit.layout.containers import Window, to_container
    from prompt_toolkit.layout.controls import UIControl

    if isinstance(value, str):

        def test() -> bool:
            return get_app().current_buffer.name == value

    elif isinstance(value, Buffer):

        def test() -> bool:
            return get_app().current_buffer == value

    elif isinstance(value, UIControl):

        def test() -> bool:
            return get_app().layout.current_control == value

    else:
        value = to_container(value)

        if isinstance(value, Window):

            def test() -> bool:
                return get_app().layout.current_window == value

        else:

            def test() -> bool:
                # Consider focused when any window inside this container is
                # focused.
                current_window = get_app().layout.current_window

                for c in walk(value):
                    if isinstance(c, Window) and c == current_window:
                        return True
                return False

    @Condition
    def has_focus_filter() -> bool:
        return test()

    return has_focus_filter


@Condition
def buffer_has_focus() -> bool:
    """
    Enabled when the currently focused control is a `BufferControl`.
    """
    return get_app().layout.buffer_has_focus


@Condition
def has_selection() -> bool:
    """
    Enable when the current buffer has a selection.
    """
    return bool(get_app().current_buffer.selection_state)


@Condition
def has_suggestion() -> bool:
    """
    Enable when the current buffer has a suggestion.
    """
    buffer = get_app().current_buffer
    return buffer.suggestion is not None and buffer.suggestion.text != ""


@Condition
def has_completions() -> bool:
    """
    Enable when the current buffer has completions.
    """
    state = get_app().current_buffer.complete_state
    return state is not None and len(state.completions) > 0


@Condition
def completion_is_selected() -> bool:
    """
    True when the user selected a completion.
    """
    complete_state = get_app().current_buffer.complete_state
    return complete_state is not None and complete_state.current_completion is not None


@Condition
def is_read_only() -> bool:
    """
    True when the current buffer is read only.
    """
    return get_app().current_buffer.read_only()


@Condition
def is_multiline() -> bool:
    """
    True when the current buffer has been marked as multiline.
    """
    return get_app().current_buffer.multiline()


@Condition
def has_validation_error() -> bool:
    "Current buffer has validation error."
    return get_app().current_buffer.validation_error is not None


@Condition
def has_arg() -> bool:
    "Enable when the input processor has an 'arg'."
    return get_app().key_processor.arg is not None


@Condition
def is_done() -> bool:
    """
    True when the CLI is returning, aborting or exiting.
    """
    return get_app().is_done


@Condition
def renderer_height_is_known() -> bool:
    """
    Only True when the renderer knows it's real height.

    (On VT100 terminals, we have to wait for a CPR response, before we can be
    sure of the available height between the cursor position and the bottom of
    the terminal. And usually it's nicer to wait with drawing bottom toolbars
    until we receive the height, in order to avoid flickering -- first drawing
    somewhere in the middle, and then again at the bottom.)
    """
    return get_app().renderer.height_is_known


@memoized()
def in_editing_mode(editing_mode: EditingMode) -> Condition:
    """
    Check whether a given editing mode is active. (Vi or Emacs.)
    """

    @Condition
    def in_editing_mode_filter() -> bool:
        return get_app().editing_mode == editing_mode

    return in_editing_mode_filter


@Condition
def in_paste_mode() -> bool:
    return get_app().paste_mode()


@Condition
def vi_mode() -> bool:
    return get_app().editing_mode == EditingMode.VI


@Condition
def vi_navigation_mode() -> bool:
    """
    Active when the set for Vi navigation key bindings are active.
    """
    from prompt_toolkit.key_binding.vi_state import InputMode

    app = get_app()

    if (
        app.editing_mode != EditingMode.VI
        or app.vi_state.operator_func
        or app.vi_state.waiting_for_digraph
        or app.current_buffer.selection_state
    ):
        return False

    return (
        app.vi_state.input_mode == InputMode.NAVIGATION
        or app.vi_state.temporary_navigation_mode
        or app.current_buffer.read_only()
    )


@Condition
def vi_insert_mode() -> bool:
    from prompt_toolkit.key_binding.vi_state import InputMode

    app = get_app()

    if (
        app.editing_mode != EditingMode.VI
        or app.vi_state.operator_func
        or app.vi_state.waiting_for_digraph
        or app.current_buffer.selection_state
        or app.vi_state.temporary_navigation_mode
        or app.current_buffer.read_only()
    ):
        return False

    return app.vi_state.input_mode == InputMode.INSERT


@Condition
def vi_insert_multiple_mode() -> bool:
    from prompt_toolkit.key_binding.vi_state import InputMode

    app = get_app()

    if (
        app.editing_mode != EditingMode.VI
        or app.vi_state.operator_func
        or app.vi_state.waiting_for_digraph
        or app.current_buffer.selection_state
        or app.vi_state.temporary_navigation_mode
        or app.current_buffer.read_only()
    ):
        return False

    return app.vi_state.input_mode == InputMode.INSERT_MULTIPLE


@Condition
def vi_replace_mode() -> bool:
    from prompt_toolkit.key_binding.vi_state import InputMode

    app = get_app()

    if (
        app.editing_mode != EditingMode.VI
        or app.vi_state.operator_func
        or app.vi_state.waiting_for_digraph
        or app.current_buffer.selection_state
        or app.vi_state.temporary_navigation_mode
        or app.current_buffer.read_only()
    ):
        return False

    return app.vi_state.input_mode == InputMode.REPLACE


@Condition
def vi_replace_single_mode() -> bool:
    from prompt_toolkit.key_binding.vi_state import InputMode

    app = get_app()

    if (
        app.editing_mode != EditingMode.VI
        or app.vi_state.operator_func
        or app.vi_state.waiting_for_digraph
        or app.current_buffer.selection_state
        or app.vi_state.temporary_navigation_mode
        or app.current_buffer.read_only()
    ):
        return False

    return app.vi_state.input_mode == InputMode.REPLACE_SINGLE


@Condition
def vi_selection_mode() -> bool:
    app = get_app()
    if app.editing_mode != EditingMode.VI:
        return False

    return bool(app.current_buffer.selection_state)


@Condition
def vi_waiting_for_text_object_mode() -> bool:
    app = get_app()
    if app.editing_mode != EditingMode.VI:
        return False

    return app.vi_state.operator_func is not None


@Condition
def vi_digraph_mode() -> bool:
    app = get_app()
    if app.editing_mode != EditingMode.VI:
        return False

    return app.vi_state.waiting_for_digraph


@Condition
def vi_recording_macro() -> bool:
    "When recording a Vi macro."
    app = get_app()
    if app.editing_mode != EditingMode.VI:
        return False

    return app.vi_state.recording_register is not None


@Condition
def emacs_mode() -> bool:
    "When the Emacs bindings are active."
    return get_app().editing_mode == EditingMode.EMACS


@Condition
def emacs_insert_mode() -> bool:
    app = get_app()
    if (
        app.editing_mode != EditingMode.EMACS
        or app.current_buffer.selection_state
        or app.current_buffer.read_only()
    ):
        return False
    return True


@Condition
def emacs_selection_mode() -> bool:
    app = get_app()
    return bool(
        app.editing_mode == EditingMode.EMACS and app.current_buffer.selection_state
    )


@Condition
def shift_selection_mode() -> bool:
    app = get_app()
    return bool(
        app.current_buffer.selection_state
        and app.current_buffer.selection_state.shift_mode
    )


@Condition
def is_searching() -> bool:
    "When we are searching."
    app = get_app()
    return app.layout.is_searching


@Condition
def control_is_searchable() -> bool:
    "When the current UIControl is searchable."
    from prompt_toolkit.layout.controls import BufferControl

    control = get_app().layout.current_control

    return (
        isinstance(control, BufferControl) and control.search_buffer_control is not None
    )


@Condition
def vi_search_direction_reversed() -> bool:
    "When the '/' and '?' key bindings for Vi-style searching have been reversed."
    return get_app().reverse_vi_search_direction()
