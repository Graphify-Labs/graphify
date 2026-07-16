"""create errno-specific classes for IO or os calls."""

from __future__ import annotations

from collections.abc import Callable
import errno
import os
import sys
from typing import TYPE_CHECKING
from typing import TypeVar


if TYPE_CHECKING:
    from typing_extensions import ParamSpec

    P = ParamSpec("P")

R = TypeVar("R")


class Error(EnvironmentError):
    def __repr__(self) -> str:
        return "{}.{} {!r}: {} ".format(
            self.__class__.__module__,
            self.__class__.__name__,
            self.__class__.__doc__,
            " ".join(map(str, self.args)),
            # repr(self.args)
        )

    def __str__(self) -> str:
        s = "[{}]: {}".format(
            self.__class__.__doc__,
            " ".join(map(str, self.args)),
        )
        return s


_winerrnomap = {
    2: errno.ENOENT,
    3: errno.ENOENT,
    17: errno.EEXIST,
    18: errno.EXDEV,
    13: errno.EBUSY,  # empty cd drive, but ENOMEDIUM seems unavailable
    22: errno.ENOTDIR,
    20: errno.ENOTDIR,
    267: errno.ENOTDIR,
    5: errno.EACCES,  # anything better?
}


class ErrorMaker:
    """lazily provides Exception classes for each possible POSIX errno
    (as defined per the 'errno' module).  All such instances
    subclass EnvironmentError.
    """

    _errno2class: dict[int, type[Error]] = {}

    def __getattr__(self, name: str) -> type[Error]:
        if name[0] == "_":
            raise AttributeError(name)
        eno = getattr(errno, name)
        cls = self._geterrnoclass(eno)
        setattr(self, name, cls)
        return cls

    def _geterrnoclass(self, eno: int) -> type[Error]:
        try:
            return self._errno2class[eno]
        except KeyError:
            clsname = errno.errorcode.get(eno, f"UnknownErrno{eno}")
            errorcls = type(
                clsname,
                (Error,),
                {"__module__": "py.error", "__doc__": os.strerror(eno)},
            )
            self._errno2class[eno] = errorcls
            return errorcls

    def checked_call(
        self, func: Callable[P, R], *args: P.args, **kwargs: P.kwargs
    ) -> R:
        """Call a function and raise an errno-exception if applicable."""
        __tracebackhide__ = True
        try:
            return func(*args, **kwargs)
        except Error:
            raise
        except OSError as value:
            if not hasattr(value, "errno"):
                raise
            if sys.platform == "win32":
                try:
                    # error: Invalid index type "Optional[int]" for "dict[int, int]"; expected type "int"  [index]
                    # OK to ignore because we catch the KeyError below.
                    cls = self._geterrnoclass(_winerrnomap[value.errno])  # type:ignore[index]
                except KeyError:
                    raise value
            else:
                # we are not on Windows, or we got a proper OSError
                if value.errno is None:
                    cls = type(
                        "UnknownErrnoNone",
                        (Error,),
                        {"__module__": "py.error", "__doc__": None},
                    )
                else:
                    cls = self._geterrnoclass(value.errno)

            raise cls(f"{func.__name__}{args!r}")


_error_maker = ErrorMaker()
checked_call = _error_maker.checked_call


def __getattr__(attr: str) -> type[Error]:
    return getattr(_error_maker, attr)  # type: ignore[no-any-return]
