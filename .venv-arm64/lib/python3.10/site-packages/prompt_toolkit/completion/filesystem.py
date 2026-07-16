from __future__ import annotations

import os
from typing import Callable, Iterable

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

__all__ = [
    "PathCompleter",
    "ExecutableCompleter",
]


class PathCompleter(Completer):
    """
    Complete for Path variables.

    :param get_paths: Callable which returns a list of directories to look into
                      when the user enters a relative path.
    :param file_filter: Callable which takes a filename and returns whether
                        this file should show up in the completion. ``None``
                        when no filtering has to be done.
    :param min_input_len: Don't do autocompletion when the input string is shorter.
    """

    def __init__(
        self,
        only_directories: bool = False,
        get_paths: Callable[[], list[str]] | None = None,
        file_filter: Callable[[str], bool] | None = None,
        min_input_len: int = 0,
        expanduser: bool = False,
    ) -> None:
        self.only_directories = only_directories
        self.get_paths = get_paths or (lambda: ["."])
        self.file_filter = file_filter or (lambda _: True)
        self.min_input_len = min_input_len
        self.expanduser = expanduser

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        text = document.text_before_cursor

        # Complete only when we have at least the minimal input length,
        # otherwise, we can too many results and autocompletion will become too
        # heavy.
        if len(text) < self.min_input_len:
            return

        try:
            # Do tilde expansion.
            if self.expanduser:
                text = os.path.expanduser(text)

            # Directories where to look.
            dirname = os.path.dirname(text)
            if dirname:
                directories = [
                    os.path.dirname(os.path.join(p, text)) for p in self.get_paths()
                ]
            else:
                directories = self.get_paths()

            # Start of current file.
            prefix = os.path.basename(text)

            # Get all filenames.
            filenames = []
            for directory in directories:
                # Look for matches in this directory.
                if os.path.isdir(directory):
                    for filename in os.listdir(directory):
                        if filename.startswith(prefix):
                            filenames.append((directory, filename))

            # Sort
            filenames = sorted(filenames, key=lambda k: k[1])

            # Yield them.
            for directory, filename in filenames:
                completion = filename[len(prefix) :]
                full_name = os.path.join(directory, filename)

                if os.path.isdir(full_name):
                    # For directories, add a slash to the filename.
                    # (We don't add them to the `completion`. Users can type it
                    # to trigger the autocompletion themselves.)
                    filename += "/"
                elif self.only_directories:
                    continue

                if not self.file_filter(full_name):
                    continue

                yield Completion(
                    text=completion,
                    start_position=0,
                    display=filename,
                )
        except OSError:
            pass


class ExecutableCompleter(PathCompleter):
    """
    Complete only executable files in the current path.
    """

    def __init__(self) -> None:
        super().__init__(
            only_directories=False,
            min_input_len=1,
            get_paths=lambda: os.environ.get("PATH", "").split(os.pathsep),
            file_filter=lambda name: os.access(name, os.X_OK),
            expanduser=True,
        )
