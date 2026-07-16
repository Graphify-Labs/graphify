from __future__ import annotations

import dataclasses
from datetime import datetime
from datetime import timedelta
from typing import Any
from typing import TYPE_CHECKING

from _pytest import nodes
from _pytest.cacheprovider import Cache
from _pytest.config import Config
from _pytest.config.argparsing import Parser
from _pytest.main import Session
from _pytest.reports import TestReport


if TYPE_CHECKING:
    from typing_extensions import Self

STEPWISE_CACHE_DIR = "cache/stepwise"


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup("general")
    group.addoption(
        "--sw",
        "--stepwise",
        action="store_true",
        default=False,
        dest="stepwise",
        help="Exit on test failure and continue from last failing test next time",
    )
    group.addoption(
        "--sw-skip",
        "--stepwise-skip",
        action="store_true",
        default=False,
        dest="stepwise_skip",
        help="Ignore the first failing test but stop on the next failing test. "
        "Implicitly enables --stepwise.",
    )
    group.addoption(
        "--sw-reset",
        "--stepwise-reset",
        action="store_true",
        default=False,
        dest="stepwise_reset",
        help="Resets stepwise state, restarting the stepwise workflow. "
        "Implicitly enables --stepwise.",
    )


def pytest_configure(config: Config) -> None:
    # --stepwise-skip/--stepwise-reset implies stepwise.
    if config.option.stepwise_skip or config.option.stepwise_reset:
        config.option.stepwise = True
    if config.getoption("stepwise"):
        config.pluginmanager.register(StepwisePlugin(config), "stepwiseplugin")


def pytest_sessionfinish(session: Session) -> None:
    if not session.config.getoption("stepwise"):
        assert session.config.cache is not None
        if hasattr(session.config, "workerinput"):
            # Do not update cache if this process is a xdist worker to prevent
            # race conditions (#10641).
            return


@dataclasses.dataclass
class StepwiseCacheInfo:
    # The nodeid of the last failed test.
    last_failed: str | None

    # The number of tests in the last time --stepwise was run.
    # We use this information as a simple way to invalidate the cache information, avoiding
    # confusing behavior in case the cache is stale.
    last_test_count: int | None

    # The date when the cache was last updated, for information purposes only.
    last_cache_date_str: str

    @property
    def last_cache_date(self) -> datetime:
        return datetime.fromisoformat(self.last_cache_date_str)

    @classmethod
    def empty(cls) -> Self:
        return cls(
            last_failed=None,
            last_test_count=None,
            last_cache_date_str=datetime.now().isoformat(),
        )

    def update_date_to_now(self) -> None:
        self.last_cache_date_str = datetime.now().isoformat()


class StepwisePlugin:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.session: Session | None = None
        self.report_status: list[str] = []
        assert config.cache is not None
        self.cache: Cache = config.cache
        self.skip: bool = config.getoption("stepwise_skip")
        self.reset: bool = config.getoption("stepwise_reset")
        self.cached_info = self._load_cached_info()

    def _load_cached_info(self) -> StepwiseCacheInfo:
        cached_dict: dict[str, Any] | None = self.cache.get(STEPWISE_CACHE_DIR, None)
        if cached_dict:
            try:
                return StepwiseCacheInfo(
                    cached_dict["last_failed"],
                    cached_dict["last_test_count"],
                    cached_dict["last_cache_date_str"],
                )
            except (KeyError, TypeError) as e:
                error = f"{type(e).__name__}: {e}"
                self.report_status.append(f"error reading cache, discarding ({error})")

        # Cache not found or error during load, return a new cache.
        return StepwiseCacheInfo.empty()

    def pytest_sessionstart(self, session: Session) -> None:
        self.session = session

    def pytest_collection_modifyitems(
        self, config: Config, items: list[nodes.Item]
    ) -> None:
        last_test_count = self.cached_info.last_test_count
        self.cached_info.last_test_count = len(items)

        if self.reset:
            self.report_status.append("resetting state, not skipping.")
            self.cached_info.last_failed = None
            return

        if not self.cached_info.last_failed:
            self.report_status.append("no previously failed tests, not skipping.")
            return

        if last_test_count is not None and last_test_count != len(items):
            self.report_status.append(
                f"test count changed, not skipping (now {len(items)} tests, previously {last_test_count})."
            )
            self.cached_info.last_failed = None
            return

        # Check all item nodes until we find a match on last failed.
        failed_index = None
        for index, item in enumerate(items):
            if item.nodeid == self.cached_info.last_failed:
                failed_index = index
                break

        # If the previously failed test was not found among the test items,
        # do not skip any tests.
        if failed_index is None:
            self.report_status.append("previously failed test not found, not skipping.")
        else:
            cache_age = datetime.now() - self.cached_info.last_cache_date
            # Round up to avoid showing microseconds.
            cache_age = timedelta(seconds=int(cache_age.total_seconds()))
            self.report_status.append(
                f"skipping {failed_index} already passed items (cache from {cache_age} ago,"
                f" use --sw-reset to discard)."
            )
            deselected = items[:failed_index]
            del items[:failed_index]
            config.hook.pytest_deselected(items=deselected)

    def pytest_runtest_logreport(self, report: TestReport) -> None:
        if report.failed:
            if self.skip:
                # Remove test from the failed ones (if it exists) and unset the skip option
                # to make sure the following tests will not be skipped.
                if report.nodeid == self.cached_info.last_failed:
                    self.cached_info.last_failed = None

                self.skip = False
            else:
                # Mark test as the last failing and interrupt the test session.
                self.cached_info.last_failed = report.nodeid
                assert self.session is not None
                self.session.shouldstop = (
                    "Test failed, continuing from this test next run."
                )

        else:
            # If the test was actually run and did pass.
            if report.when == "call":
                # Remove test from the failed ones, if exists.
                if report.nodeid == self.cached_info.last_failed:
                    self.cached_info.last_failed = None

    def pytest_report_collectionfinish(self) -> list[str] | None:
        if self.config.get_verbosity() >= 0 and self.report_status:
            return [f"stepwise: {x}" for x in self.report_status]
        return None

    def pytest_sessionfinish(self) -> None:
        if hasattr(self.config, "workerinput"):
            # Do not update cache if this process is a xdist worker to prevent
            # race conditions (#10641).
            return
        self.cached_info.update_date_to_now()
        self.cache.set(STEPWISE_CACHE_DIR, dataclasses.asdict(self.cached_info))
