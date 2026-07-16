# mypy: allow-untyped-defs
"""local path implementation."""

from __future__ import annotations

import atexit
from collections.abc import Callable
from contextlib import contextmanager
import fnmatch
import importlib.util
import io
import os
from os.path import abspath
from os.path import dirname
from os.path import exists
from os.path import isabs
from os.path import isdir
from os.path import isfile
from os.path import islink
from os.path import normpath
import posixpath
from stat import S_ISDIR
from stat import S_ISLNK
from stat import S_ISREG
import sys
from typing import Any
from typing import cast
from typing import Literal
from typing import overload
from typing import TYPE_CHECKING
import uuid
import warnings

from . import error


# Moved from local.py.
iswin32 = sys.platform == "win32" or (getattr(os, "_name", False) == "nt")


class Checkers:
    _depend_on_existence = "exists", "link", "dir", "file"

    def __init__(self, path):
        self.path = path

    def dotfile(self):
        return self.path.basename.startswith(".")

    def ext(self, arg):
        if not arg.startswith("."):
            arg = "." + arg
        return self.path.ext == arg

    def basename(self, arg):
        return self.path.basename == arg

    def basestarts(self, arg):
        return self.path.basename.startswith(arg)

    def relto(self, arg):
        return self.path.relto(arg)

    def fnmatch(self, arg):
        return self.path.fnmatch(arg)

    def endswith(self, arg):
        return str(self.path).endswith(arg)

    def _evaluate(self, kw):
        from .._code.source import getrawcode

        for name, value in kw.items():
            invert = False
            meth = None
            try:
                meth = getattr(self, name)
            except AttributeError:
                if name[:3] == "not":
                    invert = True
                    try:
                        meth = getattr(self, name[3:])
                    except AttributeError:
                        pass
            if meth is None:
                raise TypeError(f"no {name!r} checker available for {self.path!r}")
            try:
                if getrawcode(meth).co_argcount > 1:
                    if (not meth(value)) ^ invert:
                        return False
                else:
                    if bool(value) ^ bool(meth()) ^ invert:
                        return False
            except (error.ENOENT, error.ENOTDIR, error.EBUSY):
                # EBUSY feels not entirely correct,
                # but its kind of necessary since ENOMEDIUM
                # is not accessible in python
                for name in self._depend_on_existence:
                    if name in kw:
                        if kw.get(name):
                            return False
                    name = "not" + name
                    if name in kw:
                        if not kw.get(name):
                            return False
        return True

    _statcache: Stat

    def _stat(self) -> Stat:
        try:
            return self._statcache
        except AttributeError:
            try:
                self._statcache = self.path.stat()
            except error.ELOOP:
                self._statcache = self.path.lstat()
            return self._statcache

    def dir(self):
        return S_ISDIR(self._stat().mode)

    def file(self):
        return S_ISREG(self._stat().mode)

    def exists(self):
        return self._stat()

    def link(self):
        st = self.path.lstat()
        return S_ISLNK(st.mode)


class NeverRaised(Exception):
    pass


class Visitor:
    def __init__(self, fil, rec, ignore, bf, sort):
        if isinstance(fil, (str, bytes)):
            fil = FNMatcher(fil)
        if isinstance(rec, str):
            self.rec: Callable[[LocalPath], bool] = FNMatcher(rec)
        elif not hasattr(rec, "__call__") and rec:
            self.rec = lambda path: True
        else:
            self.rec = rec
        self.fil = fil
        self.ignore = ignore
        self.breadthfirst = bf
        self.optsort = cast(Callable[[Any], Any], sorted) if sort else (lambda x: x)

    def gen(self, path):
        try:
            entries = path.listdir()
        except self.ignore:
            return
        rec = self.rec
        dirs = self.optsort(
            [p for p in entries if p.check(dir=1) and (rec is None or rec(p))]
        )
        if not self.breadthfirst:
            for subdir in dirs:
                yield from self.gen(subdir)
        for p in self.optsort(entries):
            if self.fil is None or self.fil(p):
                yield p
        if self.breadthfirst:
            for subdir in dirs:
                yield from self.gen(subdir)


class FNMatcher:
    def __init__(self, pattern):
        self.pattern = pattern

    def __call__(self, path):
        pattern = self.pattern

        if (
            pattern.find(path.sep) == -1
            and iswin32
            and pattern.find(posixpath.sep) != -1
        ):
            # Running on Windows, the pattern has no Windows path separators,
            # and the pattern has one or more Posix path separators. Replace
            # the Posix path separators with the Windows path separator.
            pattern = pattern.replace(posixpath.sep, path.sep)

        if pattern.find(path.sep) == -1:
            name = path.basename
        else:
            name = str(path)  # path.strpath # XXX svn?
            if not os.path.isabs(pattern):
                pattern = "*" + path.sep + pattern
        return fnmatch.fnmatch(name, pattern)


def map_as_list(func, iter):
    return list(map(func, iter))


class Stat:
    if TYPE_CHECKING:

        @property
        def size(self) -> int: ...

        @property
        def mtime(self) -> float: ...

    def __getattr__(self, name: str) -> Any:
        return getattr(self._osstatresult, "st_" + name)

    def __init__(self, path, osstatresult):
        self.path = path
        self._osstatresult = osstatresult

    @property
    def owner(self):
        if iswin32:
            raise NotImplementedError("XXX win32")
        import pwd

        entry = error.checked_call(pwd.getpwuid, self.uid)  # type:ignore[attr-defined,unused-ignore]
        return entry[0]

    @property
    def group(self):
        """Return group name of file."""
        if iswin32:
            raise NotImplementedError("XXX win32")
        import grp

        entry = error.checked_call(grp.getgrgid, self.gid)  # type:ignore[attr-defined,unused-ignore]
        return entry[0]

    def isdir(self):
        return S_ISDIR(self._osstatresult.st_mode)

    def isfile(self):
        return S_ISREG(self._osstatresult.st_mode)

    def islink(self):
        self.path.lstat()
        return S_ISLNK(self._osstatresult.st_mode)


def getuserid(user):
    import pwd

    if not isinstance(user, int):
        user = pwd.getpwnam(user)[2]  # type:ignore[attr-defined,unused-ignore]
    return user


def getgroupid(group):
    import grp

    if not isinstance(group, int):
        group = grp.getgrnam(group)[2]  # type:ignore[attr-defined,unused-ignore]
    return group


class LocalPath:
    """Object oriented interface to os.path and other local filesystem
    related information.
    """

    class ImportMismatchError(ImportError):
        """raised on pyimport() if there is a mismatch of __file__'s"""

    sep = os.sep

    def __init__(self, path=None, expanduser=False):
        """Initialize and return a local Path instance.

        Path can be relative to the current directory.
        If path is None it defaults to the current working directory.
        If expanduser is True, tilde-expansion is performed.
        Note that Path instances always carry an absolute path.
        Note also that passing in a local path object will simply return
        the exact same path object. Use new() to get a new copy.
        """
        if path is None:
            self.strpath = error.checked_call(os.getcwd)
        else:
            try:
                path = os.fspath(path)
            except TypeError:
                raise ValueError(
                    "can only pass None, Path instances "
                    "or non-empty strings to LocalPath"
                )
            if expanduser:
                path = os.path.expanduser(path)
            self.strpath = abspath(path)

    if sys.platform != "win32":

        def chown(self, user, group, rec=0):
            """Change ownership to the given user and group.
            user and group may be specified by a number or
            by a name.  if rec is True change ownership
            recursively.
            """
            uid = getuserid(user)
            gid = getgroupid(group)
            if rec:
                for x in self.visit(rec=lambda x: x.check(link=0)):
                    if x.check(link=0):
                        error.checked_call(os.chown, str(x), uid, gid)
            error.checked_call(os.chown, str(self), uid, gid)

        def readlink(self) -> str:
            """Return value of a symbolic link."""
            # https://github.com/python/mypy/issues/12278
            return error.checked_call(os.readlink, self.strpath)  # type: ignore[arg-type,return-value,unused-ignore]

        def mklinkto(self, oldname):
            """Posix style hard link to another name."""
            error.checked_call(os.link, str(oldname), str(self))

        def mksymlinkto(self, value, absolute=1):
            """Create a symbolic link with the given value (pointing to another name)."""
            if absolute:
                error.checked_call(os.symlink, str(value), self.strpath)
            else:
                base = self.common(value)
                # with posix local paths '/' is always a common base
                relsource = self.__class__(value).relto(base)
                reldest = self.relto(base)
                n = reldest.count(self.sep)
                target = self.sep.join(("..",) * n + (relsource,))
                error.checked_call(os.symlink, target, self.strpath)

    def __div__(self, other):
        return self.join(os.fspath(other))

    __truediv__ = __div__  # py3k

    @property
    def basename(self):
        """Basename part of path."""
        return self._getbyspec("basename")[0]

    @property
    def dirname(self):
        """Dirname part of path."""
        return self._getbyspec("dirname")[0]

    @property
    def purebasename(self):
        """Pure base name of the path."""
        return self._getbyspec("purebasename")[0]

    @property
    def ext(self):
        """Extension of the path (including the '.')."""
        return self._getbyspec("ext")[0]

    def read_binary(self):
        """Read and return a bytestring from reading the path."""
        with self.open("rb") as f:
            return f.read()

    def read_text(self, encoding):
        """Read and return a Unicode string from reading the path."""
        with self.open("r", encoding=encoding) as f:
            return f.read()

    def read(self, mode="r"):
        """Read and return a bytestring from reading the path."""
        with self.open(mode) as f:
            return f.read()

    def readlines(self, cr=1):
        """Read and return a list of lines from the path. if cr is False, the
        newline will be removed from the end of each line."""
        mode = "r"

        if not cr:
            content = self.read(mode)
            return content.split("\n")
        else:
            f = self.open(mode)
            try:
                return f.readlines()
            finally:
                f.close()

    def load(self):
        """(deprecated) return object unpickled from self.read()"""
        f = self.open("rb")
        try:
            import pickle

            return error.checked_call(pickle.load, f)
        finally:
            f.close()

    def move(self, target):
        """Move this path to target."""
        if target.relto(self):
            raise error.EINVAL(target, "cannot move path into a subdirectory of itself")
        try:
            self.rename(target)
        except error.EXDEV:  # invalid cross-device link
            self.copy(target)
            self.remove()

    def fnmatch(self, pattern):
        """Return true if the basename/fullname matches the glob-'pattern'.

        valid pattern characters::

            *       matches everything
            ?       matches any single character
            [seq]   matches any character in seq
            [!seq]  matches any char not in seq

        If the pattern contains a path-separator then the full path
        is used for pattern matching and a '*' is prepended to the
        pattern.

        if the pattern doesn't contain a path-separator the pattern
        is only matched against the basename.
        """
        return FNMatcher(pattern)(self)

    def relto(self, relpath):
        """Return a string which is the relative part of the path
        to the given 'relpath'.
        """
        if not isinstance(relpath, str | LocalPath):
            raise TypeError(f"{relpath!r}: not a string or path object")
        strrelpath = str(relpath)
        if strrelpath and strrelpath[-1] != self.sep:
            strrelpath += self.sep
        # assert strrelpath[-1] == self.sep
        # assert strrelpath[-2] != self.sep
        strself = self.strpath
        if sys.platform == "win32" or getattr(os, "_name", None) == "nt":
            if os.path.normcase(strself).startswith(os.path.normcase(strrelpath)):
                return strself[len(strrelpath) :]
        elif strself.startswith(strrelpath):
            return strself[len(strrelpath) :]
        return ""

    def ensure_dir(self, *args):
        """Ensure the path joined with args is a directory."""
        return self.ensure(*args, dir=True)

    def bestrelpath(self, dest):
        """Return a string which is a relative path from self
        (assumed to be a directory) to dest such that
        self.join(bestrelpath) == dest and if not such
        path can be determined return dest.
        """
        try:
            if self == dest:
                return os.curdir
            base = self.common(dest)
            if not base:  # can be the case on windows
                return str(dest)
            self2base = self.relto(base)
            reldest = dest.relto(base)
            if self2base:
                n = self2base.count(self.sep) + 1
            else:
                n = 0
            lst = [os.pardir] * n
            if reldest:
                lst.append(reldest)
            target = dest.sep.join(lst)
            return target
        except AttributeError:
            return str(dest)

    def exists(self):
        return self.check()

    def isdir(self):
        return self.check(dir=1)

    def isfile(self):
        return self.check(file=1)

    def parts(self, reverse=False):
        """Return a root-first list of all ancestor directories
        plus the path itself.
        """
        current = self
        lst = [self]
        while 1:
            last = current
            current = current.dirpath()
            if last == current:
                break
            lst.append(current)
        if not reverse:
            lst.reverse()
        return lst

    def common(self, other):
        """Return the common part shared with the other path
        or None if there is no common part.
        """
        last = None
        for x, y in zip(self.parts(), other.parts()):
            if x != y:
                return last
            last = x
        return last

    def __add__(self, other):
        """Return new path object with 'other' added to the basename"""
        return self.new(basename=self.basename + str(other))

    def visit(self, fil=None, rec=None, ignore=NeverRaised, bf=False, sort=False):
        """Yields all paths below the current one

        fil is a filter (glob pattern or callable), if not matching the
        path will not be yielded, defaulting to None (everything is
        returned)

        rec is a filter (glob pattern or callable) that controls whether
        a node is descended, defaulting to None

        ignore is an Exception class that is ignoredwhen calling dirlist()
        on any of the paths (by default, all exceptions are reported)

        bf if True will cause a breadthfirst search instead of the
        default depthfirst. Default: False

        sort if True will sort entries within each directory level.
        """
        yield from Visitor(fil, rec, ignore, bf, sort).gen(self)

    def _sortlist(self, res, sort):
        if sort:
            if hasattr(sort, "__call__"):
                warnings.warn(
                    DeprecationWarning(
                        "listdir(sort=callable) is deprecated and breaks on python3"
                    ),
                    stacklevel=3,
                )
                res.sort(sort)
            else:
                res.sort()

    def __fspath__(self):
        return self.strpath

    def __hash__(self):
        s = self.strpath
        if iswin32:
            s = s.lower()
        return hash(s)

    def __eq__(self, other):
        s1 = os.fspath(self)
        try:
            s2 = os.fspath(other)
        except TypeError:
            return False
        if iswin32:
            s1 = s1.lower()
            try:
                s2 = s2.lower()
            except AttributeError:
                return False
        return s1 == s2

    def __ne__(self, other):
        return not (self == other)

    def __lt__(self, other):
        return os.fspath(self) < os.fspath(other)

    def __gt__(self, other):
        return os.fspath(self) > os.fspath(other)

    def samefile(self, other):
        """Return True if 'other' references the same file as 'self'."""
        other = os.fspath(other)
        if not isabs(other):
            other = abspath(other)
        if self == other:
            return True
        if not hasattr(os.path, "samefile"):
            return False
        return error.checked_call(os.path.samefile, self.strpath, other)

    def remove(self, rec=1, ignore_errors=False):
        """Remove a file or directory (or a directory tree if rec=1).
        if ignore_errors is True, errors while removing directories will
        be ignored.
        """
        if self.check(dir=1, link=0):
            if rec:
                # force remove of readonly files on windows
                if iswin32:
                    self.chmod(0o700, rec=1)
                import shutil

                error.checked_call(
                    shutil.rmtree, self.strpath, ignore_errors=ignore_errors
                )
            else:
                error.checked_call(os.rmdir, self.strpath)
        else:
            if iswin32:
                self.chmod(0o700)
            error.checked_call(os.remove, self.strpath)

    def computehash(self, hashtype="md5", chunksize=524288):
        """Return hexdigest of hashvalue for this file."""
        try:
            try:
                import hashlib as mod
            except ImportError:
                if hashtype == "sha1":
                    hashtype = "sha"
                mod = __import__(hashtype)
            hash = getattr(mod, hashtype)()
        except (AttributeError, ImportError):
            raise ValueError(f"Don't know how to compute {hashtype!r} hash")
        f = self.open("rb")
        try:
            while 1:
                buf = f.read(chunksize)
                if not buf:
                    return hash.hexdigest()
                hash.update(buf)
        finally:
            f.close()

    def new(self, **kw):
        """Create a modified version of this path.
        the following keyword arguments modify various path parts::

          a:/some/path/to/a/file.ext
          xx                           drive
          xxxxxxxxxxxxxxxxx            dirname
                            xxxxxxxx   basename
                            xxxx       purebasename
                                 xxx   ext
        """
        obj = object.__new__(self.__class__)
        if not kw:
            obj.strpath = self.strpath
            return obj
        drive, dirname, _basename, purebasename, ext = self._getbyspec(
            "drive,dirname,basename,purebasename,ext"
        )
        if "basename" in kw:
            if "purebasename" in kw or "ext" in kw:
                raise ValueError(f"invalid specification {kw!r}")
        else:
            pb = kw.setdefault("purebasename", purebasename)
            try:
                ext = kw["ext"]
            except KeyError:
                pass
            else:
                if ext and not ext.startswith("."):
                    ext = "." + ext
            kw["basename"] = pb + ext

        if "dirname" in kw and not kw["dirname"]:
            kw["dirname"] = drive
        else:
            kw.setdefault("dirname", dirname)
        kw.setdefault("sep", self.sep)
        obj.strpath = normpath("{dirname}{sep}{basename}".format(**kw))
        return obj

    def _getbyspec(self, spec: str) -> list[str]:
        """See new for what 'spec' can be."""
        res = []
        parts = self.strpath.split(self.sep)

        args = filter(None, spec.split(","))
        for name in args:
            if name == "drive":
                res.append(parts[0])
            elif name == "dirname":
                res.append(self.sep.join(parts[:-1]))
            else:
                basename = parts[-1]
                if name == "basename":
                    res.append(basename)
                else:
                    i = basename.rfind(".")
                    if i == -1:
                        purebasename, ext = basename, ""
                    else:
                        purebasename, ext = basename[:i], basename[i:]
                    if name == "purebasename":
                        res.append(purebasename)
                    elif name == "ext":
                        res.append(ext)
                    else:
                        raise ValueError(f"invalid part specification {name!r}")
        return res

    def dirpath(self, *args, **kwargs):
        """Return the directory path joined with any given path arguments."""
        if not kwargs:
            path = object.__new__(self.__class__)
            path.strpath = dirname(self.strpath)
            if args:
                path = path.join(*args)
            return path
        return self.new(basename="").join(*args, **kwargs)

    def join(self, *args: os.PathLike[str], abs: bool = False) -> LocalPath:
        """Return a new path by appending all 'args' as path
        components.  if abs=1 is used restart from root if any
        of the args is an absolute path.
        """
        sep = self.sep
        strargs = [os.fspath(arg) for arg in args]
        strpath = self.strpath
        if abs:
            newargs: list[str] = []
            for arg in reversed(strargs):
                if isabs(arg):
                    strpath = arg
                    strargs = newargs
                    break
                newargs.insert(0, arg)
        # special case for when we have e.g. strpath == "/"
        actual_sep = "" if strpath.endswith(sep) else sep
        for arg in strargs:
            arg = arg.strip(sep)
            if iswin32:
                # allow unix style paths even on windows.
                arg = arg.strip("/")
                arg = arg.replace("/", sep)
            strpath = strpath + actual_sep + arg
            actual_sep = sep
        obj = object.__new__(self.__class__)
        obj.strpath = normpath(strpath)
        return obj

    def open(self, mode="r", ensure=False, encoding=None):
        """Return an opened file with the given mode.

        If ensure is True, create parent directories if needed.
        """
        if ensure:
            self.dirpath().ensure(dir=1)
        if encoding:
            return error.checked_call(
                io.open,
                self.strpath,
                mode,
                encoding=encoding,
            )
        return error.checked_call(open, self.strpath, mode)

    def _fastjoin(self, name):
        child = object.__new__(self.__class__)
        child.strpath = self.strpath + self.sep + name
        return child

    def islink(self):
        return islink(self.strpath)

    def check(self, **kw):
        """Check a path for existence and properties.

        Without arguments, return True if the path exists, otherwise False.

        valid checkers::

            file = 1  # is a file
            file = 0  # is not a file (may not even exist)
            dir = 1  # is a dir
            link = 1  # is a link
            exists = 1  # exists

        You can specify multiple checker definitions, for example::

            path.check(file=1, link=1)  # a link pointing to a file
        """
        if not kw:
            return exists(self.strpath)
        if len(kw) == 1:
            if "dir" in kw:
                return not kw["dir"] ^ isdir(self.strpath)
            if "file" in kw:
                return not kw["file"] ^ isfile(self.strpath)
        if not kw:
            kw = {"exists": 1}
        return Checkers(self)._evaluate(kw)

    _patternchars = set("*?[" + os.sep)

    def listdir(self, fil=None, sort=None):
        """List directory contents, possibly filter by the given fil func
        and possibly sorted.
        """
        if fil is None and sort is None:
            names = error.checked_call(os.listdir, self.strpath)
            return map_as_list(self._fastjoin, names)
        if isinstance(fil, str):
            if not self._patternchars.intersection(fil):
                child = self._fastjoin(fil)
                if exists(child.strpath):
                    return [child]
                return []
            fil = FNMatcher(fil)
        names = error.checked_call(os.listdir, self.strpath)
        res = []
        for name in names:
            child = self._fastjoin(name)
            if fil is None or fil(child):
                res.append(child)
        self._sortlist(res, sort)
        return res

    def size(self) -> int:
        """Return size of the underlying file object"""
        return self.stat().size

    def mtime(self) -> float:
        """Return last modification time of the path."""
        return self.stat().mtime

    def copy(self, target, mode=False, stat=False):
        """Copy path to target.

        If mode is True, will copy permission from path to target.
        If stat is True, copy permission, last modification
        time, last access time, and flags from path to target.
        """
        if self.check(file=1):
            if target.check(dir=1):
                target = target.join(self.basename)
            assert self != target
            copychunked(self, target)
            if mode:
                copymode(self.strpath, target.strpath)
            if stat:
                copystat(self, target)
        else:

            def rec(p):
                return p.check(link=0)

            for x in self.visit(rec=rec):
                relpath = x.relto(self)
                newx = target.join(relpath)
                newx.dirpath().ensure(dir=1)
                if x.check(link=1):
                    newx.mksymlinkto(x.readlink())
                    continue
                elif x.check(file=1):
                    copychunked(x, newx)
                elif x.check(dir=1):
                    newx.ensure(dir=1)
                if mode:
                    copymode(x.strpath, newx.strpath)
                if stat:
                    copystat(x, newx)

    def rename(self, target):
        """Rename this path to target."""
        target = os.fspath(target)
        return error.checked_call(os.rename, self.strpath, target)

    def dump(self, obj, bin=1):
        """Pickle object into path location"""
        f = self.open("wb")
        import pickle

        try:
            error.checked_call(pickle.dump, obj, f, bin)
        finally:
            f.close()

    def mkdir(self, *args):
        """Create & return the directory joined with args."""
        p = self.join(*args)
        error.checked_call(os.mkdir, os.fspath(p))
        return p

    def write_binary(self, data, ensure=False):
        """Write binary data into path.   If ensure is True create
        missing parent directories.
        """
        if ensure:
            self.dirpath().ensure(dir=1)
        with self.open("wb") as f:
            f.write(data)

    def write_text(self, data, encoding, ensure=False):
        """Write text data into path using the specified encoding.
        If ensure is True create missing parent directories.
        """
        if ensure:
            self.dirpath().ensure(dir=1)
        with self.open("w", encoding=encoding) as f:
            f.write(data)

    def write(self, data, mode="w", ensure=False):
        """Write data into path.   If ensure is True create
        missing parent directories.
        """
        if ensure:
            self.dirpath().ensure(dir=1)
        if "b" in mode:
            if not isinstance(data, bytes):
                raise ValueError("can only process bytes")
        else:
            if not isinstance(data, str):
                if not isinstance(data, bytes):
                    data = str(data)
                else:
                    data = data.decode(sys.getdefaultencoding())
        f = self.open(mode)
        try:
            f.write(data)
        finally:
            f.close()

    def _ensuredirs(self):
        parent = self.dirpath()
        if parent == self:
            return self
        if parent.check(dir=0):
            parent._ensuredirs()
        if self.check(dir=0):
            try:
                self.mkdir()
            except error.EEXIST:
                # race condition: file/dir created by another thread/process.
                # complain if it is not a dir
                if self.check(dir=0):
                    raise
        return self

    def ensure(self, *args, **kwargs):
        """Ensure that an args-joined path exists (by default as
        a file). if you specify a keyword argument 'dir=True'
        then the path is forced to be a directory path.
        """
        p = self.join(*args)
        if kwargs.get("dir", 0):
            return p._ensuredirs()
        else:
            p.dirpath()._ensuredirs()
            if not p.check(file=1):
                p.open("wb").close()
            return p

    @overload
    def stat(self, raising: Literal[True] = ...) -> Stat: ...

    @overload
    def stat(self, raising: Literal[False]) -> Stat | None: ...

    def stat(self, raising: bool = True) -> Stat | None:
        """Return an os.stat() tuple."""
        if raising:
            return Stat(self, error.checked_call(os.stat, self.strpath))
        try:
            return Stat(self, os.stat(self.strpath))
        except KeyboardInterrupt:
            raise
        except Exception:
            return None

    def lstat(self) -> Stat:
        """Return an os.lstat() tuple."""
        return Stat(self, error.checked_call(os.lstat, self.strpath))

    def setmtime(self, mtime=None):
        """Set modification time for the given path.  if 'mtime' is None
        (the default) then the file's mtime is set to current time.

        Note that the resolution for 'mtime' is platform dependent.
        """
        if mtime is None:
            return error.checked_call(os.utime, self.strpath, mtime)
        try:
            return error.checked_call(os.utime, self.strpath, (-1, mtime))
        except error.EINVAL:
            return error.checked_call(os.utime, self.strpath, (self.atime(), mtime))

    def chdir(self):
        """Change directory to self and return old current directory"""
        try:
            old = self.__class__()
        except error.ENOENT:
            old = None
        error.checked_call(os.chdir, self.strpath)
        return old

    @contextmanager
    def as_cwd(self):
        """
        Return a context manager, which changes to the path's dir during the
        managed "with" context.
        On __enter__ it returns the old dir, which might be ``None``.
        """
        old = self.chdir()
        try:
            yield old
        finally:
            if old is not None:
                old.chdir()

    def realpath(self):
        """Return a new path which contains no symbolic links."""
        return self.__class__(os.path.realpath(self.strpath))

    def atime(self):
        """Return last access time of the path."""
        return self.stat().atime

    def __repr__(self):
        return f"local({self.strpath!r})"

    def __str__(self):
        """Return string representation of the Path."""
        return self.strpath

    def chmod(self, mode, rec=0):
        """Change permissions to the given mode. If mode is an
        integer it directly encodes the os-specific modes.
        if rec is True perform recursively.
        """
        if not isinstance(mode, int):
            raise TypeError(f"mode {mode!r} must be an integer")
        if rec:
            for x in self.visit(rec=rec):
                error.checked_call(os.chmod, str(x), mode)
        error.checked_call(os.chmod, self.strpath, mode)

    def pypkgpath(self):
        """Return the Python package path by looking for the last
        directory upwards which still contains an __init__.py.
        Return None if a pkgpath cannot be determined.
        """
        pkgpath = None
        for parent in self.parts(reverse=True):
            if parent.isdir():
                if not parent.join("__init__.py").exists():
                    break
                if not isimportable(parent.basename):
                    break
                pkgpath = parent
        return pkgpath

    def _ensuresyspath(self, ensuremode, path):
        if ensuremode:
            s = str(path)
            if ensuremode == "append":
                if s not in sys.path:
                    sys.path.append(s)
            else:
                if s != sys.path[0]:
                    sys.path.insert(0, s)

    def pyimport(self, modname=None, ensuresyspath=True):
        """Return path as an imported python module.

        If modname is None, look for the containing package
        and construct an according module name.
        The module will be put/looked up in sys.modules.
        if ensuresyspath is True then the root dir for importing
        the file (taking __init__.py files into account) will
        be prepended to sys.path if it isn't there already.
        If ensuresyspath=="append" the root dir will be appended
        if it isn't already contained in sys.path.
        if ensuresyspath is False no modification of syspath happens.

        Special value of ensuresyspath=="importlib" is intended
        purely for using in pytest, it is capable only of importing
        separate .py files outside packages, e.g. for test suite
        without any __init__.py file. It effectively allows having
        same-named test modules in different places and offers
        mild opt-in via this option. Note that it works only in
        recent versions of python.
        """
        if not self.check():
            raise error.ENOENT(self)

        if ensuresyspath == "importlib":
            if modname is None:
                modname = self.purebasename
            spec = importlib.util.spec_from_file_location(modname, str(self))
            if spec is None or spec.loader is None:
                raise ImportError(f"Can't find module {modname} at location {self!s}")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod

        pkgpath = None
        if modname is None:
            pkgpath = self.pypkgpath()
            if pkgpath is not None:
                pkgroot = pkgpath.dirpath()
                names = self.new(ext="").relto(pkgroot).split(self.sep)
                if names[-1] == "__init__":
                    names.pop()
                modname = ".".join(names)
            else:
                pkgroot = self.dirpath()
                modname = self.purebasename

            self._ensuresyspath(ensuresyspath, pkgroot)
            __import__(modname)
            mod = sys.modules[modname]
            if self.basename == "__init__.py":
                return mod  # we don't check anything as we might
                # be in a namespace package ... too icky to check
            modfile = mod.__file__
            assert modfile is not None
            if modfile[-4:] in (".pyc", ".pyo"):
                modfile = modfile[:-1]
            elif modfile.endswith("$py.class"):
                modfile = modfile[:-9] + ".py"
            if modfile.endswith(os.sep + "__init__.py"):
                if self.basename != "__init__.py":
                    modfile = modfile[:-12]
            try:
                issame = self.samefile(modfile)
            except error.ENOENT:
                issame = False
            if not issame:
                ignore = os.getenv("PY_IGNORE_IMPORTMISMATCH")
                if ignore != "1":
                    raise self.ImportMismatchError(modname, modfile, self)
            return mod
        else:
            try:
                return sys.modules[modname]
            except KeyError:
                # we have a custom modname, do a pseudo-import
                import types

                mod = types.ModuleType(modname)
                mod.__file__ = str(self)
                sys.modules[modname] = mod
                try:
                    with open(str(self), "rb") as f:
                        exec(f.read(), mod.__dict__)
                except BaseException:
                    del sys.modules[modname]
                    raise
                return mod

    def sysexec(self, *argv: os.PathLike[str], **popen_opts: Any) -> str:
        """Return stdout text from executing a system child process,
        where the 'self' path points to executable.
        The process is directly invoked and not through a system shell.
        """
        from subprocess import PIPE
        from subprocess import Popen

        popen_opts.pop("stdout", None)
        popen_opts.pop("stderr", None)
        proc = Popen(
            [str(self)] + [str(arg) for arg in argv],
            **popen_opts,
            stdout=PIPE,
            stderr=PIPE,
        )
        stdout: str | bytes
        stdout, stderr = proc.communicate()
        ret = proc.wait()
        if isinstance(stdout, bytes):
            stdout = stdout.decode(sys.getdefaultencoding())
        if ret != 0:
            if isinstance(stderr, bytes):
                stderr = stderr.decode(sys.getdefaultencoding())
            raise RuntimeError(
                ret,
                ret,
                str(self),
                stdout,
                stderr,
            )
        return stdout

    @classmethod
    def sysfind(cls, name, checker=None, paths=None):
        """Return a path object found by looking at the systems
        underlying PATH specification. If the checker is not None
        it will be invoked to filter matching paths.  If a binary
        cannot be found, None is returned
        Note: This is probably not working on plain win32 systems
        but may work on cygwin.
        """
        if isabs(name):
            p = local(name)
            if p.check(file=1):
                return p
        else:
            if paths is None:
                if iswin32:
                    paths = os.environ["Path"].split(";")
                    if "" not in paths and "." not in paths:
                        paths.append(".")
                    try:
                        systemroot = os.environ["SYSTEMROOT"]
                    except KeyError:
                        pass
                    else:
                        paths = [
                            path.replace("%SystemRoot%", systemroot) for path in paths
                        ]
                else:
                    paths = os.environ["PATH"].split(":")
            tryadd = []
            if iswin32:
                tryadd += os.environ["PATHEXT"].split(os.pathsep)
            tryadd.append("")

            for x in paths:
                for addext in tryadd:
                    p = local(x).join(name, abs=True) + addext
                    try:
                        if p.check(file=1):
                            if checker:
                                if not checker(p):
                                    continue
                            return p
                    except error.EACCES:
                        pass
        return None

    @classmethod
    def _gethomedir(cls):
        try:
            x = os.environ["HOME"]
        except KeyError:
            try:
                x = os.environ["HOMEDRIVE"] + os.environ["HOMEPATH"]
            except KeyError:
                return None
        return cls(x)

    # """
    # special class constructors for local filesystem paths
    # """
    @classmethod
    def get_temproot(cls):
        """Return the system's temporary directory
        (where tempfiles are usually created in)
        """
        import tempfile

        return local(tempfile.gettempdir())

    @classmethod
    def mkdtemp(cls, rootdir=None):
        """Return a Path object pointing to a fresh new temporary directory
        (which we created ourselves).
        """
        import tempfile

        if rootdir is None:
            rootdir = cls.get_temproot()
        path = error.checked_call(tempfile.mkdtemp, dir=str(rootdir))
        return cls(path)

    @classmethod
    def make_numbered_dir(
        cls, prefix="session-", rootdir=None, keep=3, lock_timeout=172800
    ):  # two days
        """Return unique directory with a number greater than the current
        maximum one.  The number is assumed to start directly after prefix.
        if keep is true directories with a number less than (maxnum-keep)
        will be removed. If .lock files are used (lock_timeout non-zero),
        algorithm is multi-process safe.
        """
        if rootdir is None:
            rootdir = cls.get_temproot()

        nprefix = prefix.lower()

        def parse_num(path):
            """Parse the number out of a path (if it matches the prefix)"""
            nbasename = path.basename.lower()
            if nbasename.startswith(nprefix):
                try:
                    return int(nbasename[len(nprefix) :])
                except ValueError:
                    pass

        def create_lockfile(path):
            """Exclusively create lockfile. Throws when failed"""
            mypid = os.getpid()
            lockfile = path.join(".lock")
            if hasattr(lockfile, "mksymlinkto"):
                lockfile.mksymlinkto(str(mypid))
            else:
                fd = error.checked_call(
                    os.open, str(lockfile), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644
                )
                with os.fdopen(fd, "w") as f:
                    f.write(str(mypid))
            return lockfile

        def atexit_remove_lockfile(lockfile):
            """Ensure lockfile is removed at process exit"""
            mypid = os.getpid()

            def try_remove_lockfile():
                # in a fork() situation, only the last process should
                # remove the .lock, otherwise the other processes run the
                # risk of seeing their temporary dir disappear.  For now
                # we remove the .lock in the parent only (i.e. we assume
                # that the children finish before the parent).
                if os.getpid() != mypid:
                    return
                try:
                    lockfile.remove()
                except error.Error:
                    pass

            atexit.register(try_remove_lockfile)

        # compute the maximum number currently in use with the prefix
        lastmax = None
        while True:
            maxnum = -1
            for path in rootdir.listdir():
                num = parse_num(path)
                if num is not None:
                    maxnum = max(maxnum, num)

            # make the new directory
            try:
                udir = rootdir.mkdir(prefix + str(maxnum + 1))
                if lock_timeout:
                    lockfile = create_lockfile(udir)
                    atexit_remove_lockfile(lockfile)
            except (error.EEXIST, error.ENOENT, error.EBUSY):
                # race condition (1): another thread/process created the dir
                #                     in the meantime - try again
                # race condition (2): another thread/process spuriously acquired
                #                     lock treating empty directory as candidate
                #                     for removal - try again
                # race condition (3): another thread/process tried to create the lock at
                #                     the same time (happened in Python 3.3 on Windows)
                # https://ci.appveyor.com/project/pytestbot/py/build/1.0.21/job/ffi85j4c0lqwsfwa
                if lastmax == maxnum:
                    raise
                lastmax = maxnum
                continue
            break

        def get_mtime(path):
            """Read file modification time"""
            try:
                return path.lstat().mtime
            except error.Error:
                pass

        garbage_prefix = prefix + "garbage-"

        def is_garbage(path):
            """Check if path denotes directory scheduled for removal"""
            bn = path.basename
            return bn.startswith(garbage_prefix)

        # prune old directories
        udir_time = get_mtime(udir)
        if keep and udir_time:
            for path in rootdir.listdir():
                num = parse_num(path)
                if num is not None and num <= (maxnum - keep):
                    try:
                        # try acquiring lock to remove directory as exclusive user
                        if lock_timeout:
                            create_lockfile(path)
                    except (error.EEXIST, error.ENOENT, error.EBUSY):
                        path_time = get_mtime(path)
                        if not path_time:
                            # assume directory doesn't exist now
                            continue
                        if abs(udir_time - path_time) < lock_timeout:
                            # assume directory with lockfile exists
                            # and lock timeout hasn't expired yet
                            continue

                    # path dir locked for exclusive use
                    # and scheduled for removal to avoid another thread/process
                    # treating it as a new directory or removal candidate
                    garbage_path = rootdir.join(garbage_prefix + str(uuid.uuid4()))
                    try:
                        path.rename(garbage_path)
                        garbage_path.remove(rec=1)
                    except KeyboardInterrupt:
                        raise
                    except Exception:  # this might be error.Error, WindowsError ...
                        pass
                if is_garbage(path):
                    try:
                        path.remove(rec=1)
                    except KeyboardInterrupt:
                        raise
                    except Exception:  # this might be error.Error, WindowsError ...
                        pass

        # make link...
        try:
            username = os.environ["USER"]  # linux, et al
        except KeyError:
            try:
                username = os.environ["USERNAME"]  # windows
            except KeyError:
                username = "current"

        src = str(udir)
        dest = src[: src.rfind("-")] + "-" + username
        try:
            os.unlink(dest)
        except OSError:
            pass
        try:
            os.symlink(src, dest)
        except (OSError, AttributeError, NotImplementedError):
            pass

        return udir


def copymode(src, dest):
    """Copy permission from src to dst."""
    import shutil

    shutil.copymode(src, dest)


def copystat(src, dest):
    """Copy permission,  last modification time,
    last access time, and flags from src to dst."""
    import shutil

    shutil.copystat(str(src), str(dest))


def copychunked(src, dest):
    chunksize = 524288  # half a meg of bytes
    fsrc = src.open("rb")
    try:
        fdest = dest.open("wb")
        try:
            while 1:
                buf = fsrc.read(chunksize)
                if not buf:
                    break
                fdest.write(buf)
        finally:
            fdest.close()
    finally:
        fsrc.close()


def isimportable(name):
    if name and (name[0].isalpha() or name[0] == "_"):
        name = name.replace("_", "")
        return not name or name.isalnum()


local = LocalPath
