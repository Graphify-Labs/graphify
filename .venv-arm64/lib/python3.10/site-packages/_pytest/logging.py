# mypy: allow-untyped-defs
"""Access and control log capturing."""

from __future__ import annotations

from collections.abc import Generator
from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from contextlib import contextmanager
from contextlib import nullcontext
from datetime import datetime
from datetime import timedelta
from datetime import timezone
import io
from io import StringIO
import logging
from logging import LogRecord
import os
from pathlib import Path
import re
from types import TracebackType
from typing import final
from typing import Generic
from typing import Literal
from typing import TYPE_CHECKING
from typing import TypeVar

from _pytest import nodes
from _pytest._io import TerminalWriter
from _pytest.capture import CaptureManager
from _pytest.config import _strtobool
from _pytest.config import Config
from _pytest.config import create_terminal_writer
from _pytest.config import hookimpl
from _pytest.config import UsageError
from _pytest.config.argparsing import Parser
from _pytest.deprecated import check_ispytest
from _pytest.fixtures import fixture
from _pytest.fixtures import FixtureRequest
from _pytest.main import Session
from _pytest.stash import StashKey
from _pytest.terminal import TerminalReporter


if TYPE_CHECKING:
    logging_StreamHandler = logging.StreamHandler[StringIO]
else:
    logging_StreamHandler = logging.StreamHandler

DEFAULT_LOG_FORMAT = "%(levelname)-8s %(name)s:%(filename)s:%(lineno)d %(message)s"
DEFAULT_LOG_DATE_FORMAT = "%H:%M:%S"
_ANSI_ESCAPE_SEQ = re.compile(r"\x1b\[[\d;]+m")
caplog_handler_key = StashKey["LogCaptureHandler"]()
caplog_records_key = StashKey[dict[str, list[logging.LogRecord]]]()


def _remove_ansi_escape_sequences(text: str) -> str:
    return _ANSI_ESCAPE_SEQ.sub("", text)


class DatetimeFormatter(logging.Formatter):
    """A logging formatter which formats record with
    :func:`datetime.datetime.strftime` formatter instead of
    :func:`time.strftime` in case of microseconds in format string.
    """

    def formatTime(self, record: LogRecord, datefmt: str | None = None) -> str:
        if datefmt and "%f" in datefmt:
            ct = self.converter(record.created)
            tz = timezone(timedelta(seconds=ct.tm_gmtoff), ct.tm_zone)
            # Construct `datetime.datetime` object from `struct_time`
            # and msecs information from `record`
            # Using int() instead of round() to avoid it exceeding 1_000_000 and causing a ValueError (#11861).
            dt = datetime(*ct[0:6], microsecond=int(record.msecs * 1000), tzinfo=tz)
            return dt.strftime(datefmt)
        # Use `logging.Formatter` for non-microsecond formats
        return super().formatTime(record, datefmt)


class ColoredLevelFormatter(DatetimeFormatter):
    """A logging formatter which colorizes the %(levelname)..s part of the
    log format passed to __init__."""

    LOGLEVEL_COLOROPTS: Mapping[int, AbstractSet[str]] = {
        logging.CRITICAL: {"red"},
        logging.ERROR: {"red", "bold"},
        logging.WARNING: {"yellow"},
        logging.WARN: {"yellow"},
        logging.INFO: {"green"},
        logging.DEBUG: {"purple"},
        logging.NOTSET: set(),
    }
    LEVELNAME_FMT_REGEX = re.compile(r"%\(levelname\)([+-.]?\d*(?:\.\d+)?s)")

    def __init__(self, terminalwriter: TerminalWriter, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._terminalwriter = terminalwriter
        self._original_fmt = self._style._fmt
        self._level_to_fmt_mapping: dict[int, str] = {}

        for level, color_opts in self.LOGLEVEL_COLOROPTS.items():
            self.add_color_level(level, *color_opts)

    def add_color_level(self, level: int, *color_opts: str) -> None:
        """Add or update color opts for a log level.

        :param level:
            Log level to apply a style to, e.g. ``logging.INFO``.
        :param color_opts:
            ANSI escape sequence color options. Capitalized colors indicates
            background color, i.e. ``'green', 'Yellow', 'bold'`` will give bold
            green text on yellow background.

        .. warning::
            This is an experimental API.
        """
        assert self._fmt is not None
        levelname_fmt_match = self.LEVELNAME_FMT_REGEX.search(self._fmt)
        if not levelname_fmt_match:
            return
        levelname_fmt = levelname_fmt_match.group()

        formatted_levelname = levelname_fmt % {"levelname": logging.getLevelName(level)}

        # add ANSI escape sequences around the formatted levelname
        color_kwargs = {name: True for name in color_opts}
        colorized_formatted_levelname = self._terminalwriter.markup(
            formatted_levelname, **color_kwargs
        )
        self._level_to_fmt_mapping[level] = self.LEVELNAME_FMT_REGEX.sub(
            colorized_formatted_levelname, self._fmt
        )

    def format(self, record: logging.LogRecord) -> str:
        fmt = self._level_to_fmt_mapping.get(record.levelno, self._original_fmt)
        self._style._fmt = fmt
        return super().format(record)


class PercentStyleMultiline(logging.PercentStyle):
    """A logging style with special support for multiline messages.

    If the message of a record consists of multiple lines, this style
    formats the message as if each line were logged separately.
    """

    def __init__(self, fmt: str, auto_indent: int | str | bool | None) -> None:
        super().__init__(fmt)
        self._auto_indent = self._get_auto_indent(auto_indent)

    @staticmethod
    def _get_auto_indent(auto_indent_option: int | str | bool | None) -> int:
        """Determine the current auto indentation setting.

        Specify auto indent behavior (on/off/fixed) by passing in
        extra={"auto_indent": [value]} to the call to logging.log() or
        using a --log-auto-indent [value] command line or the
        log_auto_indent [value] config option.

        Default behavior is auto-indent off.

        Using the string "True" or "on" or the boolean True as the value
        turns auto indent on, using the string "False" or "off" or the
        boolean False or the int 0 turns it off, and specifying a
        positive integer fixes the indentation position to the value
        specified.

        Any other values for the option are invalid, and will silently be
        converted to the default.

        :param None|bool|int|str auto_indent_option:
            User specified option for indentation from command line, config
            or extra kwarg. Accepts int, bool or str. str option accepts the
            same range of values as boolean config options, as well as
            positive integers represented in str form.

        :returns:
            Indentation value, which can be
            -1 (automatically determine indentation) or
            0 (auto-indent turned off) or
            >0 (explicitly set indentation position).
        """
        match auto_indent_option:
            case None | False:
                return 0
            case True:
                return -1
            case int():
                return auto_indent_option
            case str():
                try:
                    return int(auto_indent_option)
                except ValueError:
                    pass
                try:
                    if _strtobool(auto_indent_option):
                        return -1
                except ValueError:
                    return 0
                return 0

    def format(self, record: logging.LogRecord) -> str:
        if "\n" in record.message:
            if hasattr(record, "auto_indent"):
                # Passed in from the "extra={}" kwarg on the call to logging.log().
                auto_indent = self._get_auto_indent(record.auto_indent)
            else:
                auto_indent = self._auto_indent

            if auto_indent:
                lines = record.message.splitlines()
                formatted = self._fmt % {**record.__dict__, "message": lines[0]}

                if auto_indent < 0:
                    indentation = _remove_ansi_escape_sequences(formatted).find(
                        lines[0]
                    )
                else:
                    # Optimizes logging by allowing a fixed indentation.
                    indentation = auto_indent
                lines[0] = formatted
                return ("\n" + " " * indentation).join(lines)
        return self._fmt % record.__dict__


def get_option_ini(config: Config, *names: str):
    for name in names:
        ret = config.getoption(name)  # 'default' arg won't work as expected
        if ret is None:
            ret = config.getini(name)
        if ret:
            return ret


def pytest_addoption(parser: Parser) -> None:
    """Add options to control log capturing."""
    group = parser.getgroup("logging")

    def add_option_ini(option, dest, default=None, type=None, **kwargs):
        parser.addini(
            dest, default=default, type=type, help="Default value for " + option
        )
        group.addoption(option, dest=dest, **kwargs)

    add_option_ini(
        "--log-level",
        dest="log_level",
        default=None,
        metavar="LEVEL",
        help=(
            "Level of messages to catch/display."
            " Not set by default, so it depends on the root/parent log handler's"
            ' effective level, where it is "WARNING" by default.'
        ),
    )
    add_option_ini(
        "--log-format",
        dest="log_format",
        default=DEFAULT_LOG_FORMAT,
        help="Log format used by the logging module",
    )
    add_option_ini(
        "--log-date-format",
        dest="log_date_format",
        default=DEFAULT_LOG_DATE_FORMAT,
        help="Log date format used by the logging module",
    )
    parser.addini(
        "log_cli",
        default=False,
        type="bool",
        help='Enable log display during test run (also known as "live logging")',
    )
    add_option_ini(
        "--log-cli-level", dest="log_cli_level", default=None, help="CLI logging level"
    )
    add_option_ini(
        "--log-cli-format",
        dest="log_cli_format",
        default=None,
        help="Log format used by the logging module",
    )
    add_option_ini(
        "--log-cli-date-format",
        dest="log_cli_date_format",
        default=None,
        help="Log date format used by the logging module",
    )
    add_option_ini(
        "--log-file",
        dest="log_file",
        default=None,
        help="Path to a file when logging will be written to",
    )
    add_option_ini(
        "--log-file-mode",
        dest="log_file_mode",
        default="w",
        choices=["w", "a"],
        help="Log file open mode",
    )
    add_option_ini(
        "--log-file-level",
        dest="log_file_level",
        default=None,
        help="Log file logging level",
    )
    add_option_ini(
        "--log-file-format",
        dest="log_file_format",
        default=None,
        help="Log format used by the logging module",
    )
    add_option_ini(
        "--log-file-date-format",
        dest="log_file_date_format",
        default=None,
        help="Log date format used by the logging module",
    )
    add_option_ini(
        "--log-auto-indent",
        dest="log_auto_indent",
        default=None,
        help="Auto-indent multiline messages passed to the logging module. Accepts true|on, false|off or an integer.",
    )
    group.addoption(
        "--log-disable",
        action="append",
        default=[],
        dest="logger_disable",
        help="Disable a logger by name. Can be passed multiple times.",
    )


_HandlerType = TypeVar("_HandlerType", bound=logging.Handler)


# Not using @contextmanager for performance reasons.
class catching_logs(Generic[_HandlerType]):
    """Context manager that prepares the whole logging machinery properly."""

    __slots__ = ("attached_loggers", "handler", "level", "orig_level")

    def __init__(self, handler: _HandlerType, level: int | None = None) -> None:
        self.handler = handler
        self.level = level
        self.attached_loggers: list[logging.Logger] = []

    def __enter__(self) -> _HandlerType:
        root_logger = logging.getLogger()
        if self.level is not None:
            self.handler.setLevel(self.level)
        # Attach to root logger.
        root_logger.addHandler(self.handler)
        self.attached_loggers.append(root_logger)
        # Attach to all non-propagating loggers (won't reach root).
        # Note that will miss loggers that *become* non-propagating
        # after the `__enter__`. Not worth the trouble for now.
        for logger in root_logger.manager.loggerDict.values():
            if (
                isinstance(logger, logging.Logger)
                and not logger.propagate
                and logger is not root_logger
            ):
                logger.addHandler(self.handler)
                self.attached_loggers.append(logger)
        if self.level is not None:
            # Non-propagating loggers still inherit the level (unless a logger
            # explicitly set level), so only do this on the root logger.
            self.orig_level = root_logger.level
            root_logger.setLevel(min(self.orig_level, self.level))
        return self.handler

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        root_logger = logging.getLogger()
        if self.level is not None:
            root_logger.setLevel(self.orig_level)
        for logger in self.attached_loggers:
            logger.removeHandler(self.handler)
        self.attached_loggers.clear()


class LogCaptureHandler(logging_StreamHandler):
    """A logging handler that stores log records and the log text."""

    def __init__(self) -> None:
        """Create a new log handler."""
        super().__init__(StringIO())
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Keep the log records in a list in addition to the log text."""
        self.records.append(record)
        super().emit(record)

    def reset(self) -> None:
        self.records = []
        self.stream = StringIO()

    def clear(self) -> None:
        self.records.clear()
        self.stream = StringIO()

    def handleError(self, record: logging.LogRecord) -> None:
        if logging.raiseExceptions:
            # Fail the test if the log message is bad (emit failed).
            # The default behavior of logging is to print "Logging error"
            # to stderr with the call stack and some extra details.
            # pytest wants to make such mistakes visible during testing.
            raise  # noqa: PLE0704


@final
class LogCaptureFixture:
    """Provides access and control of log capturing."""

    def __init__(self, item: nodes.Node, *, _ispytest: bool = False) -> None:
        check_ispytest(_ispytest)
        self._item = item
        self._initial_handler_level: int | None = None
        # Dict of log name -> log level.
        self._initial_logger_levels: dict[str | None, int] = {}
        self._initial_disabled_logging_level: int | None = None

    def _finalize(self) -> None:
        """Finalize the fixture.

        This restores the log levels and the disabled logging levels changed by :meth:`set_level`.
        """
        # Restore log levels.
        if self._initial_handler_level is not None:
            self.handler.setLevel(self._initial_handler_level)
        for logger_name, level in self._initial_logger_levels.items():
            logger = logging.getLogger(logger_name)
            logger.setLevel(level)
        # Disable logging at the original disabled logging level.
        if self._initial_disabled_logging_level is not None:
            logging.disable(self._initial_disabled_logging_level)
            self._initial_disabled_logging_level = None

    @property
    def handler(self) -> LogCaptureHandler:
        """Get the logging handler used by the fixture."""
        return self._item.stash[caplog_handler_key]

    def get_records(
        self, when: Literal["setup", "call", "teardown"]
    ) -> list[logging.LogRecord]:
        """Get the logging records for one of the possible test phases.

        :param when:
            Which test phase to obtain the records from.
            Valid values are: "setup", "call" and "teardown".

        :returns: The list of captured records at the given stage.

        .. versionadded:: 3.4
        """
        return self._item.stash[caplog_records_key].get(when, [])

    @property
    def text(self) -> str:
        """The formatted log text."""
        return _remove_ansi_escape_sequences(self.handler.stream.getvalue())

    @property
    def records(self) -> list[logging.LogRecord]:
        """The list of log records."""
        return self.handler.records

    @property
    def record_tuples(self) -> list[tuple[str, int, str]]:
        """A list of a stripped down version of log records intended
        for use in assertion comparison.

        The format of the tuple is:

            (logger_name, log_level, message)
        """
        return [(r.name, r.levelno, r.getMessage()) for r in self.records]

    @property
    def messages(self) -> list[str]:
        """A list of format-interpolated log messages.

        Unlike 'records', which contains the format string and parameters for
        interpolation, log messages in this list are all interpolated.

        Unlike 'text', which contains the output from the handler, log
        messages in this list are unadorned with levels, timestamps, etc,
        making exact comparisons more reliable.

        Note that traceback or stack info (from :func:`logging.exception` or
        the `exc_info` or `stack_info` arguments to the logging functions) is
        not included, as this is added by the formatter in the handler.

        .. versionadded:: 3.7
        """
        return [r.getMessage() for r in self.records]

    def clear(self) -> None:
        """Reset the list of log records and the captured log text."""
        self.handler.clear()

    def _force_enable_logging(
        self, level: int | str, logger_obj: logging.Logger
    ) -> int:
        """Enable the desired logging level if the global level was disabled via ``logging.disabled``.

        Only enables logging levels greater than or equal to the requested ``level``.

        Does nothing if the desired ``level`` wasn't disabled.

        :param level:
            The logger level caplog should capture.
            All logging is enabled if a non-standard logging level string is supplied.
            Valid level strings are in :data:`logging._nameToLevel`.
        :param logger_obj: The logger object to check.

        :return: The original disabled logging level.
        """
        original_disable_level: int = logger_obj.manager.disable

        if isinstance(level, str):
            # Try to translate the level string to an int for `logging.disable()`
            level = logging.getLevelName(level)  # type: ignore[deprecated]

        if not isinstance(level, int):
            # The level provided was not valid, so just un-disable all logging.
            logging.disable(logging.NOTSET)
        elif not logger_obj.isEnabledFor(level):
            # Each level is `10` away from other levels.
            # https://docs.python.org/3/library/logging.html#logging-levels
            disable_level = max(level - 10, logging.NOTSET)
            logging.disable(disable_level)

        return original_disable_level

    def set_level(self, level: int | str, logger: str | None = None) -> None:
        """Set the threshold level of a logger for the duration of a test.

        Logging messages which are less severe than this level will not be captured.

        .. versionchanged:: 3.4
            The levels of the loggers changed by this function will be
            restored to their initial values at the end of the test.

        Will enable the requested logging level if it was disabled via :func:`logging.disable`.

        :param level: The level.
        :param logger: The logger to update. If not given, the root logger.
        """
        logger_obj = logging.getLogger(logger)
        # Save the original log-level to restore it during teardown.
        self._initial_logger_levels.setdefault(logger, logger_obj.level)
        logger_obj.setLevel(level)
        if self._initial_handler_level is None:
            self._initial_handler_level = self.handler.level
        self.handler.setLevel(level)
        initial_disabled_logging_level = self._force_enable_logging(level, logger_obj)
        if self._initial_disabled_logging_level is None:
            self._initial_disabled_logging_level = initial_disabled_logging_level

    @contextmanager
    def at_level(self, level: int | str, logger: str | None = None) -> Generator[None]:
        """Context manager that sets the level for capturing of logs. After
        the end of the 'with' statement the level is restored to its original
        value.

        Will enable the requested logging level if it was disabled via :func:`logging.disable`.

        :param level: The level.
        :param logger: The logger to update. If not given, the root logger.
        """
        logger_obj = logging.getLogger(logger)
        orig_level = logger_obj.level
        logger_obj.setLevel(level)
        handler_orig_level = self.handler.level
        self.handler.setLevel(level)
        original_disable_level = self._force_enable_logging(level, logger_obj)
        try:
            yield
        finally:
            logger_obj.setLevel(orig_level)
            self.handler.setLevel(handler_orig_level)
            logging.disable(original_disable_level)

    @contextmanager
    def filtering(self, filter_: logging.Filter) -> Generator[None]:
        """Context manager that temporarily adds the given filter to the caplog's
        :meth:`handler` for the 'with' statement block, and removes that filter at the
        end of the block.

        :param filter_: A custom :class:`logging.Filter` object.

        .. versionadded:: 7.5
        """
        self.handler.addFilter(filter_)
        try:
            yield
        finally:
            self.handler.removeFilter(filter_)


@fixture
def caplog(request: FixtureRequest) -> Generator[LogCaptureFixture]:
    """Access and control log capturing.

    Captured logs are available through the following properties/methods::

    * caplog.messages        -> list of format-interpolated log messages
    * caplog.text            -> string containing formatted log output
    * caplog.records         -> list of logging.LogRecord instances
    * caplog.record_tuples   -> list of (logger_name, level, message) tuples
    * caplog.clear()         -> clear captured records and formatted log output string
    """
    result = LogCaptureFixture(request.node, _ispytest=True)
    yield result
    result._finalize()


def get_log_level_for_setting(config: Config, *setting_names: str) -> int | None:
    for setting_name in setting_names:
        log_level = config.getoption(setting_name)
        if log_level is None:
            log_level = config.getini(setting_name)
        if log_level:
            break
    else:
        return None

    if isinstance(log_level, str):
        log_level = log_level.upper()
    try:
        return int(getattr(logging, log_level, log_level))
    except ValueError as e:
        # Python logging does not recognise this as a logging level
        raise UsageError(
            f"'{log_level}' is not recognized as a logging level name for "
            f"'{setting_name}'. Please consider passing the "
            "logging level num instead."
        ) from e


# run after terminalreporter/capturemanager are configured
@hookimpl(trylast=True)
def pytest_configure(config: Config) -> None:
    config.pluginmanager.register(LoggingPlugin(config), "logging-plugin")


class LoggingPlugin:
    """Attaches to the logging module and captures log messages for each test."""

    def __init__(self, config: Config) -> None:
        """Create a new plugin to capture log messages.

        The formatter can be safely shared across all handlers so
        create a single one for the entire test session here.
        """
        self._config = config

        # Report logging.
        self.formatter = self._create_formatter(
            get_option_ini(config, "log_format"),
            get_option_ini(config, "log_date_format"),
            get_option_ini(config, "log_auto_indent"),
        )
        self.log_level = get_log_level_for_setting(config, "log_level")
        self.caplog_handler = LogCaptureHandler()
        self.caplog_handler.setFormatter(self.formatter)
        self.report_handler = LogCaptureHandler()
        self.report_handler.setFormatter(self.formatter)

        # File logging.
        self.log_file_level = get_log_level_for_setting(
            config, "log_file_level", "log_level"
        )
        log_file = get_option_ini(config, "log_file") or os.devnull
        if log_file != os.devnull:
            directory = os.path.dirname(os.path.abspath(log_file))
            if not os.path.isdir(directory):
                os.makedirs(directory)

        self.log_file_mode = get_option_ini(config, "log_file_mode") or "w"
        self.log_file_handler = _FileHandler(
            log_file, mode=self.log_file_mode, encoding="UTF-8"
        )
        log_file_format = get_option_ini(config, "log_file_format", "log_format")
        log_file_date_format = get_option_ini(
            config, "log_file_date_format", "log_date_format"
        )

        log_file_formatter = DatetimeFormatter(
            log_file_format, datefmt=log_file_date_format
        )
        self.log_file_handler.setFormatter(log_file_formatter)

        # CLI/live logging.
        self.log_cli_level = get_log_level_for_setting(
            config, "log_cli_level", "log_level"
        )
        if self._log_cli_enabled():
            terminal_reporter = config.pluginmanager.get_plugin("terminalreporter")
            # Guaranteed by `_log_cli_enabled()`.
            assert terminal_reporter is not None
            capture_manager = config.pluginmanager.get_plugin("capturemanager")
            # if capturemanager plugin is disabled, live logging still works.
            self.log_cli_handler: (
                _LiveLoggingStreamHandler | _LiveLoggingNullHandler
            ) = _LiveLoggingStreamHandler(terminal_reporter, capture_manager)
        else:
            self.log_cli_handler = _LiveLoggingNullHandler()
        log_cli_formatter = self._create_formatter(
            get_option_ini(config, "log_cli_format", "log_format"),
            get_option_ini(config, "log_cli_date_format", "log_date_format"),
            get_option_ini(config, "log_auto_indent"),
        )
        self.log_cli_handler.setFormatter(log_cli_formatter)
        self._disable_loggers(loggers_to_disable=config.option.logger_disable)

    def _disable_loggers(self, loggers_to_disable: list[str]) -> None:
        if not loggers_to_disable:
            return

        for name in loggers_to_disable:
            logger = logging.getLogger(name)
            logger.disabled = True

    def _create_formatter(self, log_format, log_date_format, auto_indent):
        # Color option doesn't exist if terminal plugin is disabled.
        color = getattr(self._config.option, "color", "no")
        if color != "no" and ColoredLevelFormatter.LEVELNAME_FMT_REGEX.search(
            log_format
        ):
            formatter: logging.Formatter = ColoredLevelFormatter(
                create_terminal_writer(self._config), log_format, log_date_format
            )
        else:
            formatter = DatetimeFormatter(log_format, log_date_format)

        formatter._style = PercentStyleMultiline(
            formatter._style._fmt, auto_indent=auto_indent
        )

        return formatter

    def set_log_path(self, fname: str) -> None:
        """Set the filename parameter for Logging.FileHandler().

        Creates parent directory if it does not exist.

        .. warning::
            This is an experimental API.
        """
        fpath = Path(fname)

        if not fpath.is_absolute():
            fpath = self._config.rootpath / fpath

        if not fpath.parent.exists():
            fpath.parent.mkdir(exist_ok=True, parents=True)

        # https://github.com/python/mypy/issues/11193
        stream: io.TextIOWrapper = fpath.open(mode=self.log_file_mode, encoding="UTF-8")  # type: ignore[assignment]
        old_stream = self.log_file_handler.setStream(stream)
        if old_stream:
            old_stream.close()

    def _log_cli_enabled(self) -> bool:
        """Return whether live logging is enabled."""
        enabled = self._config.getoption(
            "--log-cli-level"
        ) is not None or self._config.getini("log_cli")
        if not enabled:
            return False

        terminal_reporter = self._config.pluginmanager.get_plugin("terminalreporter")
        if terminal_reporter is None:
            # terminal reporter is disabled e.g. by pytest-xdist.
            return False

        return True

    @hookimpl(wrapper=True, tryfirst=True)
    def pytest_sessionstart(self) -> Generator[None]:
        self.log_cli_handler.set_when("sessionstart")

        with catching_logs(self.log_cli_handler, level=self.log_cli_level):
            with catching_logs(self.log_file_handler, level=self.log_file_level):
                return (yield)

    @hookimpl(wrapper=True, tryfirst=True)
    def pytest_collection(self) -> Generator[None]:
        self.log_cli_handler.set_when("collection")

        with catching_logs(self.log_cli_handler, level=self.log_cli_level):
            with catching_logs(self.log_file_handler, level=self.log_file_level):
                return (yield)

    @hookimpl(wrapper=True)
    def pytest_runtestloop(self, session: Session) -> Generator[None, object, object]:
        if session.config.option.collectonly:
            return (yield)

        if self._log_cli_enabled() and self._config.get_verbosity() < 1:
            # The verbose flag is needed to avoid messy test progress output.
            self._config.option.verbose = 1

        with catching_logs(self.log_cli_handler, level=self.log_cli_level):
            with catching_logs(self.log_file_handler, level=self.log_file_level):
                return (yield)  # Run all the tests.

    @hookimpl
    def pytest_runtest_logstart(self) -> None:
        self.log_cli_handler.reset()
        self.log_cli_handler.set_when("start")

    @hookimpl
    def pytest_runtest_logreport(self) -> None:
        self.log_cli_handler.set_when("logreport")

    @contextmanager
    def _runtest_for(self, item: nodes.Item, when: str) -> Generator[None]:
        """Implement the internals of the pytest_runtest_xxx() hooks."""
        with (
            catching_logs(
                self.caplog_handler,
                level=self.log_level,
            ) as caplog_handler,
            catching_logs(
                self.report_handler,
                level=self.log_level,
            ) as report_handler,
        ):
            caplog_handler.reset()
            report_handler.reset()
            item.stash[caplog_records_key][when] = caplog_handler.records
            item.stash[caplog_handler_key] = caplog_handler

            try:
                yield
            finally:
                log = report_handler.stream.getvalue().strip()
                item.add_report_section(when, "log", log)

    @hookimpl(wrapper=True)
    def pytest_runtest_setup(self, item: nodes.Item) -> Generator[None]:
        self.log_cli_handler.set_when("setup")

        empty: dict[str, list[logging.LogRecord]] = {}
        item.stash[caplog_records_key] = empty
        with self._runtest_for(item, "setup"):
            yield

    @hookimpl(wrapper=True)
    def pytest_runtest_call(self, item: nodes.Item) -> Generator[None]:
        self.log_cli_handler.set_when("call")

        with self._runtest_for(item, "call"):
            yield

    @hookimpl(wrapper=True)
    def pytest_runtest_teardown(self, item: nodes.Item) -> Generator[None]:
        self.log_cli_handler.set_when("teardown")

        try:
            with self._runtest_for(item, "teardown"):
                yield
        finally:
            del item.stash[caplog_records_key]
            del item.stash[caplog_handler_key]

    @hookimpl
    def pytest_runtest_logfinish(self) -> None:
        self.log_cli_handler.set_when("finish")

    @hookimpl(wrapper=True, tryfirst=True)
    def pytest_sessionfinish(self) -> Generator[None]:
        self.log_cli_handler.set_when("sessionfinish")

        with catching_logs(self.log_cli_handler, level=self.log_cli_level):
            with catching_logs(self.log_file_handler, level=self.log_file_level):
                return (yield)

    @hookimpl
    def pytest_unconfigure(self) -> None:
        # Close the FileHandler explicitly.
        # (logging.shutdown might have lost the weakref?!)
        self.log_file_handler.close()


class _FileHandler(logging.FileHandler):
    """A logging FileHandler with pytest tweaks."""

    def handleError(self, record: logging.LogRecord) -> None:
        # Handled by LogCaptureHandler.
        pass


class _LiveLoggingStreamHandler(logging_StreamHandler):
    """A logging StreamHandler used by the live logging feature: it will
    write a newline before the first log message in each test.

    During live logging we must also explicitly disable stdout/stderr
    capturing otherwise it will get captured and won't appear in the
    terminal.
    """

    # Officially stream needs to be a IO[str], but TerminalReporter
    # isn't. So force it.
    stream: TerminalReporter = None  # type: ignore

    def __init__(
        self,
        terminal_reporter: TerminalReporter,
        capture_manager: CaptureManager | None,
    ) -> None:
        super().__init__(stream=terminal_reporter)  # type: ignore[arg-type]
        self.capture_manager = capture_manager
        self.reset()
        self.set_when(None)
        self._test_outcome_written = False

    def reset(self) -> None:
        """Reset the handler; should be called before the start of each test."""
        self._first_record_emitted = False

    def set_when(self, when: str | None) -> None:
        """Prepare for the given test phase (setup/call/teardown)."""
        self._when = when
        self._section_name_shown = False
        if when == "start":
            self._test_outcome_written = False

    def emit(self, record: logging.LogRecord) -> None:
        ctx_manager = (
            self.capture_manager.global_and_fixture_disabled()
            if self.capture_manager
            else nullcontext()
        )
        with ctx_manager:
            if not self._first_record_emitted:
                self.stream.write("\n")
                self._first_record_emitted = True
            elif self._when in ("teardown", "finish"):
                if not self._test_outcome_written:
                    self._test_outcome_written = True
                    self.stream.write("\n")
            if not self._section_name_shown and self._when:
                self.stream.section("live log " + self._when, sep="-", bold=True)
                self._section_name_shown = True
            super().emit(record)

    def handleError(self, record: logging.LogRecord) -> None:
        # Handled by LogCaptureHandler.
        pass


class _LiveLoggingNullHandler(logging.NullHandler):
    """A logging handler used when live logging is disabled."""

    def reset(self) -> None:
        pass

    def set_when(self, when: str) -> None:
        pass

    def handleError(self, record: logging.LogRecord) -> None:
        # Handled by LogCaptureHandler.
        pass
