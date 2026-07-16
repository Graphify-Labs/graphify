"""Indirection for time functions.

We intentionally grab some "time" functions internally to avoid tests mocking "time" to affect
pytest runtime information (issue #185).

Fixture "mock_timing" also interacts with this module for pytest's own tests.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from datetime import timezone
from time import perf_counter
from time import sleep
from time import time
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pytest import MonkeyPatch


@dataclasses.dataclass(frozen=True)
class Instant:
    """
    Represents an instant in time, used to both get the timestamp value and to measure
    the duration of a time span.

    Inspired by Rust's `std::time::Instant`.
    """

    # Creation time of this instant, using time.time(), to measure actual time.
    # Note: using a `lambda` to correctly get the mocked time via `MockTiming`.
    # pylint: disable-next=lambda-assignment
    time: float = dataclasses.field(default_factory=lambda: time(), init=False)  # noqa: PLW0108

    # Performance counter tick of the instant, used to measure precise elapsed time.
    # Note: using a `lambda` to correctly get the mocked time via `MockTiming`.
    perf_count: float = dataclasses.field(
        default_factory=lambda: perf_counter(),  # noqa: PLW0108
        init=False,
    )

    def elapsed(self) -> Duration:
        """Measure the duration since `Instant` was created."""
        return Duration(start=self, stop=Instant())

    def as_utc(self) -> datetime:
        """Instant as UTC datetime."""
        return datetime.fromtimestamp(self.time, timezone.utc)


@dataclasses.dataclass(frozen=True)
class Duration:
    """A span of time as measured by `Instant.elapsed()`."""

    start: Instant
    stop: Instant

    @property
    def seconds(self) -> float:
        """Elapsed time of the duration in seconds, measured using a performance counter for precise timing."""
        return self.stop.perf_count - self.start.perf_count


@dataclasses.dataclass
class MockTiming:
    """Mocks _pytest.timing with a known object that can be used to control timing in tests
    deterministically.

    pytest itself should always use functions from `_pytest.timing` instead of `time` directly.

    This then allows us more control over time during testing, if testing code also
    uses `_pytest.timing` functions.

    Time is static, and only advances through `sleep` calls, thus tests might sleep over large
    numbers and obtain accurate time() calls at the end, making tests reliable and instant."""

    _current_time: float = datetime(2020, 5, 22, 14, 20, 50).timestamp()

    def sleep(self, seconds: float) -> None:
        self._current_time += seconds

    def time(self) -> float:
        return self._current_time

    def patch(self, monkeypatch: MonkeyPatch) -> None:
        # pylint: disable-next=import-self
        from _pytest import timing  # noqa: PLW0406

        monkeypatch.setattr(timing, "sleep", self.sleep)
        monkeypatch.setattr(timing, "time", self.time)
        monkeypatch.setattr(timing, "perf_counter", self.time)


__all__ = ["perf_counter", "sleep", "time"]
