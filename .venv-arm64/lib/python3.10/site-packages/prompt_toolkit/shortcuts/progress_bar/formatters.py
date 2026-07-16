"""
Formatter classes for the progress bar.
Each progress bar consists of a list of these formatters.
"""

from __future__ import annotations

import datetime
import time
from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING

from prompt_toolkit.formatted_text import (
    HTML,
    AnyFormattedText,
    StyleAndTextTuples,
    to_formatted_text,
)
from prompt_toolkit.formatted_text.utils import fragment_list_width
from prompt_toolkit.layout.dimension import AnyDimension, D
from prompt_toolkit.layout.utils import explode_text_fragments
from prompt_toolkit.utils import get_cwidth

if TYPE_CHECKING:
    from .base import ProgressBar, ProgressBarCounter

__all__ = [
    "Formatter",
    "Text",
    "Label",
    "Percentage",
    "Bar",
    "Progress",
    "TimeElapsed",
    "TimeLeft",
    "IterationsPerSecond",
    "SpinningWheel",
    "Rainbow",
    "create_default_formatters",
]


class Formatter(metaclass=ABCMeta):
    """
    Base class for any formatter.
    """

    @abstractmethod
    def format(
        self,
        progress_bar: ProgressBar,
        progress: ProgressBarCounter[object],
        width: int,
    ) -> AnyFormattedText:
        pass

    def get_width(self, progress_bar: ProgressBar) -> AnyDimension:
        return D()


class Text(Formatter):
    """
    Display plain text.
    """

    def __init__(self, text: AnyFormattedText, style: str = "") -> None:
        self.text = to_formatted_text(text, style=style)

    def format(
        self,
        progress_bar: ProgressBar,
        progress: ProgressBarCounter[object],
        width: int,
    ) -> AnyFormattedText:
        return self.text

    def get_width(self, progress_bar: ProgressBar) -> AnyDimension:
        return fragment_list_width(self.text)


class Label(Formatter):
    """
    Display the name of the current task.

    :param width: If a `width` is given, use this width. Scroll the text if it
        doesn't fit in this width.
    :param suffix: String suffix to be added after the task name, e.g. ': '.
        If no task name was given, no suffix will be added.
    """

    def __init__(self, width: AnyDimension = None, suffix: str = "") -> None:
        self.width = width
        self.suffix = suffix

    def _add_suffix(self, label: AnyFormattedText) -> StyleAndTextTuples:
        label = to_formatted_text(label, style="class:label")
        return label + [("", self.suffix)]

    def format(
        self,
        progress_bar: ProgressBar,
        progress: ProgressBarCounter[object],
        width: int,
    ) -> AnyFormattedText:
        label = self._add_suffix(progress.label)
        cwidth = fragment_list_width(label)

        if cwidth > width:
            # It doesn't fit -> scroll task name.
            label = explode_text_fragments(label)
            max_scroll = cwidth - width
            current_scroll = int(time.time() * 3 % max_scroll)
            label = label[current_scroll:]

        return label

    def get_width(self, progress_bar: ProgressBar) -> AnyDimension:
        if self.width:
            return self.width

        all_labels = [self._add_suffix(c.label) for c in progress_bar.counters]
        if all_labels:
            max_widths = max(fragment_list_width(l) for l in all_labels)
            return D(preferred=max_widths, max=max_widths)
        else:
            return D()


class Percentage(Formatter):
    """
    Display the progress as a percentage.
    """

    template = HTML("<percentage>{percentage:>5}%</percentage>")

    def format(
        self,
        progress_bar: ProgressBar,
        progress: ProgressBarCounter[object],
        width: int,
    ) -> AnyFormattedText:
        return self.template.format(percentage=round(progress.percentage, 1))

    def get_width(self, progress_bar: ProgressBar) -> AnyDimension:
        return D.exact(6)


class Bar(Formatter):
    """
    Display the progress bar itself.
    """

    template = HTML(
        "<bar>{start}<bar-a>{bar_a}</bar-a><bar-b>{bar_b}</bar-b><bar-c>{bar_c}</bar-c>{end}</bar>"
    )

    def __init__(
        self,
        start: str = "[",
        end: str = "]",
        sym_a: str = "=",
        sym_b: str = ">",
        sym_c: str = " ",
        unknown: str = "#",
    ) -> None:
        assert len(sym_a) == 1 and get_cwidth(sym_a) == 1
        assert len(sym_c) == 1 and get_cwidth(sym_c) == 1

        self.start = start
        self.end = end
        self.sym_a = sym_a
        self.sym_b = sym_b
        self.sym_c = sym_c
        self.unknown = unknown

    def format(
        self,
        progress_bar: ProgressBar,
        progress: ProgressBarCounter[object],
        width: int,
    ) -> AnyFormattedText:
        if progress.done or progress.total or progress.stopped:
            sym_a, sym_b, sym_c = self.sym_a, self.sym_b, self.sym_c

            # Compute pb_a based on done, total, or stopped states.
            if progress.done:
                # 100% completed irrelevant of how much was actually marked as completed.
                percent = 1.0
            else:
                # Show percentage completed.
                percent = progress.percentage / 100
        else:
            # Total is unknown and bar is still running.
            sym_a, sym_b, sym_c = self.sym_c, self.unknown, self.sym_c

            # Compute percent based on the time.
            percent = time.time() * 20 % 100 / 100

        # Subtract left, sym_b, and right.
        width -= get_cwidth(self.start + sym_b + self.end)

        # Scale percent by width
        pb_a = int(percent * width)
        bar_a = sym_a * pb_a
        bar_b = sym_b
        bar_c = sym_c * (width - pb_a)

        return self.template.format(
            start=self.start, end=self.end, bar_a=bar_a, bar_b=bar_b, bar_c=bar_c
        )

    def get_width(self, progress_bar: ProgressBar) -> AnyDimension:
        return D(min=9)


class Progress(Formatter):
    """
    Display the progress as text.  E.g. "8/20"
    """

    template = HTML("<current>{current:>3}</current>/<total>{total:>3}</total>")

    def format(
        self,
        progress_bar: ProgressBar,
        progress: ProgressBarCounter[object],
        width: int,
    ) -> AnyFormattedText:
        return self.template.format(
            current=progress.items_completed, total=progress.total or "?"
        )

    def get_width(self, progress_bar: ProgressBar) -> AnyDimension:
        all_lengths = [
            len("{:>3}".format(c.total or "?")) for c in progress_bar.counters
        ]
        all_lengths.append(1)
        return D.exact(max(all_lengths) * 2 + 1)


def _format_timedelta(timedelta: datetime.timedelta) -> str:
    """
    Return hh:mm:ss, or mm:ss if the amount of hours is zero.
    """
    result = f"{timedelta}".split(".")[0]
    if result.startswith("0:"):
        result = result[2:]
    return result


class TimeElapsed(Formatter):
    """
    Display the elapsed time.
    """

    template = HTML("<time-elapsed>{time_elapsed}</time-elapsed>")

    def format(
        self,
        progress_bar: ProgressBar,
        progress: ProgressBarCounter[object],
        width: int,
    ) -> AnyFormattedText:
        text = _format_timedelta(progress.time_elapsed).rjust(width)
        return self.template.format(time_elapsed=text)

    def get_width(self, progress_bar: ProgressBar) -> AnyDimension:
        all_values = [
            len(_format_timedelta(c.time_elapsed)) for c in progress_bar.counters
        ]
        if all_values:
            return max(all_values)
        return 0


class TimeLeft(Formatter):
    """
    Display the time left.
    """

    template = HTML("<time-left>{time_left}</time-left>")
    unknown = "?:??:??"

    def format(
        self,
        progress_bar: ProgressBar,
        progress: ProgressBarCounter[object],
        width: int,
    ) -> AnyFormattedText:
        time_left = progress.time_left
        if time_left is not None:
            formatted_time_left = _format_timedelta(time_left)
        else:
            formatted_time_left = self.unknown

        return self.template.format(time_left=formatted_time_left.rjust(width))

    def get_width(self, progress_bar: ProgressBar) -> AnyDimension:
        all_values = [
            len(_format_timedelta(c.time_left)) if c.time_left is not None else 7
            for c in progress_bar.counters
        ]
        if all_values:
            return max(all_values)
        return 0


class IterationsPerSecond(Formatter):
    """
    Display the iterations per second.
    """

    template = HTML(
        "<iterations-per-second>{iterations_per_second:.2f}</iterations-per-second>"
    )

    def format(
        self,
        progress_bar: ProgressBar,
        progress: ProgressBarCounter[object],
        width: int,
    ) -> AnyFormattedText:
        value = progress.items_completed / progress.time_elapsed.total_seconds()
        return self.template.format(iterations_per_second=value)

    def get_width(self, progress_bar: ProgressBar) -> AnyDimension:
        all_values = [
            len(f"{c.items_completed / c.time_elapsed.total_seconds():.2f}")
            for c in progress_bar.counters
        ]
        if all_values:
            return max(all_values)
        return 0


class SpinningWheel(Formatter):
    """
    Display a spinning wheel.
    """

    template = HTML("<spinning-wheel>{0}</spinning-wheel>")
    characters = r"/-\|"

    def format(
        self,
        progress_bar: ProgressBar,
        progress: ProgressBarCounter[object],
        width: int,
    ) -> AnyFormattedText:
        index = int(time.time() * 3) % len(self.characters)
        return self.template.format(self.characters[index])

    def get_width(self, progress_bar: ProgressBar) -> AnyDimension:
        return D.exact(1)


def _hue_to_rgb(hue: float) -> tuple[int, int, int]:
    """
    Take hue between 0 and 1, return (r, g, b).
    """
    i = int(hue * 6.0)
    f = (hue * 6.0) - i

    q = int(255 * (1.0 - f))
    t = int(255 * (1.0 - (1.0 - f)))

    i %= 6

    return [
        (255, t, 0),
        (q, 255, 0),
        (0, 255, t),
        (0, q, 255),
        (t, 0, 255),
        (255, 0, q),
    ][i]


class Rainbow(Formatter):
    """
    For the fun. Add rainbow colors to any of the other formatters.
    """

    colors = ["#%.2x%.2x%.2x" % _hue_to_rgb(h / 100.0) for h in range(0, 100)]

    def __init__(self, formatter: Formatter) -> None:
        self.formatter = formatter

    def format(
        self,
        progress_bar: ProgressBar,
        progress: ProgressBarCounter[object],
        width: int,
    ) -> AnyFormattedText:
        # Get formatted text from nested formatter, and explode it in
        # text/style tuples.
        result = self.formatter.format(progress_bar, progress, width)
        result = explode_text_fragments(to_formatted_text(result))

        # Insert colors.
        result2: StyleAndTextTuples = []
        shift = int(time.time() * 3) % len(self.colors)

        for i, (style, text, *_) in enumerate(result):
            result2.append(
                (style + " " + self.colors[(i + shift) % len(self.colors)], text)
            )
        return result2

    def get_width(self, progress_bar: ProgressBar) -> AnyDimension:
        return self.formatter.get_width(progress_bar)


def create_default_formatters() -> list[Formatter]:
    """
    Return the list of default formatters.
    """
    return [
        Label(),
        Text(" "),
        Percentage(),
        Text(" "),
        Bar(),
        Text(" "),
        Progress(),
        Text(" "),
        Text("eta [", style="class:time-left"),
        TimeLeft(),
        Text("]", style="class:time-left"),
        Text(" "),
    ]
