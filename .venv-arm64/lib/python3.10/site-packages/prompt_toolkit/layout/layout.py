"""
Wrapper for the layout.
"""

from __future__ import annotations

from typing import Generator, Iterable, Union

from prompt_toolkit.buffer import Buffer

from .containers import (
    AnyContainer,
    ConditionalContainer,
    Container,
    Window,
    to_container,
)
from .controls import BufferControl, SearchBufferControl, UIControl

__all__ = [
    "Layout",
    "InvalidLayoutError",
    "walk",
]

FocusableElement = Union[str, Buffer, UIControl, AnyContainer]


class Layout:
    """
    The layout for a prompt_toolkit
    :class:`~prompt_toolkit.application.Application`.
    This also keeps track of which user control is focused.

    :param container: The "root" container for the layout.
    :param focused_element: element to be focused initially. (Can be anything
        the `focus` function accepts.)
    """

    def __init__(
        self,
        container: AnyContainer,
        focused_element: FocusableElement | None = None,
    ) -> None:
        self.container = to_container(container)
        self._stack: list[Window] = []

        # Map search BufferControl back to the original BufferControl.
        # This is used to keep track of when exactly we are searching, and for
        # applying the search.
        # When a link exists in this dictionary, that means the search is
        # currently active.
        # Map: search_buffer_control -> original buffer control.
        self.search_links: dict[SearchBufferControl, BufferControl] = {}

        # Mapping that maps the children in the layout to their parent.
        # This relationship is calculated dynamically, each time when the UI
        # is rendered.  (UI elements have only references to their children.)
        self._child_to_parent: dict[Container, Container] = {}

        if focused_element is None:
            try:
                self._stack.append(next(self.find_all_windows()))
            except StopIteration as e:
                raise InvalidLayoutError(
                    "Invalid layout. The layout does not contain any Window object."
                ) from e
        else:
            self.focus(focused_element)

        # List of visible windows.
        self.visible_windows: list[Window] = []  # List of `Window` objects.

    def __repr__(self) -> str:
        return f"Layout({self.container!r}, current_window={self.current_window!r})"

    def find_all_windows(self) -> Generator[Window, None, None]:
        """
        Find all the :class:`.UIControl` objects in this layout.
        """
        for item in self.walk():
            if isinstance(item, Window):
                yield item

    def find_all_controls(self) -> Iterable[UIControl]:
        for container in self.find_all_windows():
            yield container.content

    def focus(self, value: FocusableElement) -> None:
        """
        Focus the given UI element.

        `value` can be either:

        - a :class:`.UIControl`
        - a :class:`.Buffer` instance or the name of a :class:`.Buffer`
        - a :class:`.Window`
        - Any container object. In this case we will focus the :class:`.Window`
          from this container that was focused most recent, or the very first
          focusable :class:`.Window` of the container.
        """
        # BufferControl by buffer name.
        if isinstance(value, str):
            for control in self.find_all_controls():
                if isinstance(control, BufferControl) and control.buffer.name == value:
                    self.focus(control)
                    return
            raise ValueError(f"Couldn't find Buffer in the current layout: {value!r}.")

        # BufferControl by buffer object.
        elif isinstance(value, Buffer):
            for control in self.find_all_controls():
                if isinstance(control, BufferControl) and control.buffer == value:
                    self.focus(control)
                    return
            raise ValueError(f"Couldn't find Buffer in the current layout: {value!r}.")

        # Focus UIControl.
        elif isinstance(value, UIControl):
            if value not in self.find_all_controls():
                raise ValueError(
                    "Invalid value. Container does not appear in the layout."
                )
            if not value.is_focusable():
                raise ValueError("Invalid value. UIControl is not focusable.")

            self.current_control = value

        # Otherwise, expecting any Container object.
        else:
            value = to_container(value)

            if isinstance(value, Window):
                # This is a `Window`: focus that.
                if value not in self.find_all_windows():
                    raise ValueError(
                        f"Invalid value. Window does not appear in the layout: {value!r}"
                    )

                self.current_window = value
            else:
                # Focus a window in this container.
                # If we have many windows as part of this container, and some
                # of them have been focused before, take the last focused
                # item. (This is very useful when the UI is composed of more
                # complex sub components.)
                windows = []
                for c in walk(value, skip_hidden=True):
                    if isinstance(c, Window) and c.content.is_focusable():
                        windows.append(c)

                # Take the first one that was focused before.
                for w in reversed(self._stack):
                    if w in windows:
                        self.current_window = w
                        return

                # None was focused before: take the very first focusable window.
                if windows:
                    self.current_window = windows[0]
                    return

                raise ValueError(
                    f"Invalid value. Container cannot be focused: {value!r}"
                )

    def has_focus(self, value: FocusableElement) -> bool:
        """
        Check whether the given control has the focus.
        :param value: :class:`.UIControl` or :class:`.Window` instance.
        """
        if isinstance(value, str):
            if self.current_buffer is None:
                return False
            return self.current_buffer.name == value
        if isinstance(value, Buffer):
            return self.current_buffer == value
        if isinstance(value, UIControl):
            return self.current_control == value
        else:
            value = to_container(value)
            if isinstance(value, Window):
                return self.current_window == value
            else:
                # Check whether this "container" is focused. This is true if
                # one of the elements inside is focused.
                for element in walk(value):
                    if element == self.current_window:
                        return True
                return False

    @property
    def current_control(self) -> UIControl:
        """
        Get the :class:`.UIControl` to currently has the focus.
        """
        return self._stack[-1].content

    @current_control.setter
    def current_control(self, control: UIControl) -> None:
        """
        Set the :class:`.UIControl` to receive the focus.
        """
        for window in self.find_all_windows():
            if window.content == control:
                self.current_window = window
                return

        raise ValueError("Control not found in the user interface.")

    @property
    def current_window(self) -> Window:
        "Return the :class:`.Window` object that is currently focused."
        return self._stack[-1]

    @current_window.setter
    def current_window(self, value: Window) -> None:
        "Set the :class:`.Window` object to be currently focused."
        self._stack.append(value)

    @property
    def is_searching(self) -> bool:
        "True if we are searching right now."
        return self.current_control in self.search_links

    @property
    def search_target_buffer_control(self) -> BufferControl | None:
        """
        Return the :class:`.BufferControl` in which we are searching or `None`.
        """
        # Not every `UIControl` is a `BufferControl`. This only applies to
        # `BufferControl`.
        control = self.current_control

        if isinstance(control, SearchBufferControl):
            return self.search_links.get(control)
        else:
            return None

    def get_focusable_windows(self) -> Iterable[Window]:
        """
        Return all the :class:`.Window` objects which are focusable (in the
        'modal' area).
        """
        for w in self.walk_through_modal_area():
            if isinstance(w, Window) and w.content.is_focusable():
                yield w

    def get_visible_focusable_windows(self) -> list[Window]:
        """
        Return a list of :class:`.Window` objects that are focusable.
        """
        # focusable windows are windows that are visible, but also part of the
        # modal container. Make sure to keep the ordering.
        visible_windows = self.visible_windows
        return [w for w in self.get_focusable_windows() if w in visible_windows]

    @property
    def current_buffer(self) -> Buffer | None:
        """
        The currently focused :class:`~.Buffer` or `None`.
        """
        ui_control = self.current_control
        if isinstance(ui_control, BufferControl):
            return ui_control.buffer
        return None

    def get_buffer_by_name(self, buffer_name: str) -> Buffer | None:
        """
        Look in the layout for a buffer with the given name.
        Return `None` when nothing was found.
        """
        for w in self.walk():
            if isinstance(w, Window) and isinstance(w.content, BufferControl):
                if w.content.buffer.name == buffer_name:
                    return w.content.buffer
        return None

    @property
    def buffer_has_focus(self) -> bool:
        """
        Return `True` if the currently focused control is a
        :class:`.BufferControl`. (For instance, used to determine whether the
        default key bindings should be active or not.)
        """
        ui_control = self.current_control
        return isinstance(ui_control, BufferControl)

    @property
    def previous_control(self) -> UIControl:
        """
        Get the :class:`.UIControl` to previously had the focus.
        """
        try:
            return self._stack[-2].content
        except IndexError:
            return self._stack[-1].content

    def focus_last(self) -> None:
        """
        Give the focus to the last focused control.
        """
        if len(self._stack) > 1:
            self._stack = self._stack[:-1]

    def focus_next(self) -> None:
        """
        Focus the next visible/focusable Window.
        """
        windows = self.get_visible_focusable_windows()

        if len(windows) > 0:
            try:
                index = windows.index(self.current_window)
            except ValueError:
                index = 0
            else:
                index = (index + 1) % len(windows)

            self.focus(windows[index])

    def focus_previous(self) -> None:
        """
        Focus the previous visible/focusable Window.
        """
        windows = self.get_visible_focusable_windows()

        if len(windows) > 0:
            try:
                index = windows.index(self.current_window)
            except ValueError:
                index = 0
            else:
                index = (index - 1) % len(windows)

            self.focus(windows[index])

    def walk(self) -> Iterable[Container]:
        """
        Walk through all the layout nodes (and their children) and yield them.
        """
        yield from walk(self.container)

    def walk_through_modal_area(self) -> Iterable[Container]:
        """
        Walk through all the containers which are in the current 'modal' part
        of the layout.
        """
        # Go up in the tree, and find the root. (it will be a part of the
        # layout, if the focus is in a modal part.)
        root: Container = self.current_window
        while not root.is_modal() and root in self._child_to_parent:
            root = self._child_to_parent[root]

        yield from walk(root)

    def update_parents_relations(self) -> None:
        """
        Update child->parent relationships mapping.
        """
        parents = {}

        def walk(e: Container) -> None:
            for c in e.get_children():
                parents[c] = e
                walk(c)

        walk(self.container)

        self._child_to_parent = parents

    def reset(self) -> None:
        # Remove all search links when the UI starts.
        # (Important, for instance when control-c is been pressed while
        #  searching. The prompt cancels, but next `run()` call the search
        #  links are still there.)
        self.search_links.clear()

        self.container.reset()

    def get_parent(self, container: Container) -> Container | None:
        """
        Return the parent container for the given container, or ``None``, if it
        wasn't found.
        """
        try:
            return self._child_to_parent[container]
        except KeyError:
            return None


class InvalidLayoutError(Exception):
    pass


def walk(container: Container, skip_hidden: bool = False) -> Iterable[Container]:
    """
    Walk through layout, starting at this container.
    """
    # When `skip_hidden` is set, don't go into disabled ConditionalContainer containers.
    if (
        skip_hidden
        and isinstance(container, ConditionalContainer)
        and not container.filter()
    ):
        return

    yield container

    for c in container.get_children():
        # yield from walk(c)
        yield from walk(c, skip_hidden=skip_hidden)
