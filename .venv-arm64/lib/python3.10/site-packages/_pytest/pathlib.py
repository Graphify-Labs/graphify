from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Iterator
import contextlib
from enum import Enum
from errno import EBADF
from errno import ELOOP
from errno import ENOENT
from errno import ENOTDIR
import fnmatch
from functools import partial
from importlib.machinery import ModuleSpec
from importlib.machinery import PathFinder
import importlib.util
import itertools
import os
from os.path import expanduser
from os.path import expandvars
from os.path import isabs
from os.path import sep
from pathlib import Path
from pathlib import PurePath
from posixpath import sep as posix_sep
import shutil
import sys
import types
from types import ModuleType
from typing import Any
from typing import TypeVar
import uuid
import warnings

from _pytest.compat import assert_never
from _pytest.outcomes import skip
from _pytest.warning_types import PytestWarning


if sys.version_info < (3, 11):
    from importlib._bootstrap_external import _NamespaceLoader as NamespaceLoader
else:
    from importlib.machinery import NamespaceLoader

LOCK_TIMEOUT = 60 * 60 * 24 * 3

_AnyPurePath = TypeVar("_AnyPurePath", bound=PurePath)

# The following function, variables and comments were
# copied from cpython 3.9 Lib/pathlib.py file.

# EBADF - guard against macOS `stat` throwing EBADF
_IGNORED_ERRORS = (ENOENT, ENOTDIR, EBADF, ELOOP)

_IGNORED_WINERRORS = (
    21,  # ERROR_NOT_READY - drive exists but is not accessible
    1921,  # ERROR_CANT_RESOLVE_FILENAME - fix for broken symlink pointing to itself
)


def _ignore_error(exception: Exception) -> bool:
    return (
        getattr(exception, "errno", None) in _IGNORED_ERRORS
        or getattr(exception, "winerror", None) in _IGNORED_WINERRORS
    )


def get_lock_path(path: _AnyPurePath) -> _AnyPurePath:
    return path.joinpath(".lock")


def on_rm_rf_error(
    func: Callable[..., Any] | None,
    path: str,
    excinfo: BaseException
    | tuple[type[BaseException], BaseException, types.TracebackType | None],
    *,
    start_path: Path,
) -> bool:
    """Handle known read-only errors during rmtree.

    The returned value is used only by our own tests.
    """
    if isinstance(excinfo, BaseException):
        exc = excinfo
    else:
        exc = excinfo[1]

    # Another process removed the file in the middle of the "rm_rf" (xdist for example).
    # More context: https://github.com/pytest-dev/pytest/issues/5974#issuecomment-543799018
    if isinstance(exc, FileNotFoundError):
        return False

    if not isinstance(exc, PermissionError):
        warnings.warn(
            PytestWarning(f"(rm_rf) error removing {path}\n{type(exc)}: {exc}")
        )
        return False

    if func not in (os.rmdir, os.remove, os.unlink):
        if func not in (os.open,):
            warnings.warn(
                PytestWarning(
                    f"(rm_rf) unknown function {func} when removing {path}:\n{type(exc)}: {exc}"
                )
            )
        return False

    # Chmod + retry.
    import stat

    def chmod_rw(p: str) -> None:
        mode = os.stat(p).st_mode
        os.chmod(p, mode | stat.S_IRUSR | stat.S_IWUSR)

    # For files, we need to recursively go upwards in the directories to
    # ensure they all are also writable.
    p = Path(path)
    if p.is_file():
        for parent in p.parents:
            chmod_rw(str(parent))
            # Stop when we reach the original path passed to rm_rf.
            if parent == start_path:
                break
    chmod_rw(str(path))

    func(path)
    return True


def ensure_extended_length_path(path: Path) -> Path:
    """Get the extended-length version of a path (Windows).

    On Windows, by default, the maximum length of a path (MAX_PATH) is 260
    characters, and operations on paths longer than that fail. But it is possible
    to overcome this by converting the path to "extended-length" form before
    performing the operation:
    https://docs.microsoft.com/en-us/windows/win32/fileio/naming-a-file#maximum-path-length-limitation

    On Windows, this function returns the extended-length absolute version of path.
    On other platforms it returns path unchanged.
    """
    if sys.platform.startswith("win32"):
        path = path.resolve()
        path = Path(get_extended_length_path_str(str(path)))
    return path


def get_extended_length_path_str(path: str) -> str:
    """Convert a path to a Windows extended length path."""
    long_path_prefix = "\\\\?\\"
    unc_long_path_prefix = "\\\\?\\UNC\\"
    if path.startswith((long_path_prefix, unc_long_path_prefix)):
        return path
    # UNC
    if path.startswith("\\\\"):
        return unc_long_path_prefix + path[2:]
    return long_path_prefix + path


def rm_rf(path: Path) -> None:
    """Remove the path contents recursively, even if some elements
    are read-only."""
    path = ensure_extended_length_path(path)
    onerror = partial(on_rm_rf_error, start_path=path)
    if sys.version_info >= (3, 12):
        shutil.rmtree(str(path), onexc=onerror)
    else:
        shutil.rmtree(str(path), onerror=onerror)


def find_prefixed(root: Path, prefix: str) -> Iterator[os.DirEntry[str]]:
    """Find all elements in root that begin with the prefix, case-insensitive."""
    l_prefix = prefix.lower()
    for x in os.scandir(root):
        if x.name.lower().startswith(l_prefix):
            yield x


def extract_suffixes(iter: Iterable[os.DirEntry[str]], prefix: str) -> Iterator[str]:
    """Return the parts of the paths following the prefix.

    :param iter: Iterator over path names.
    :param prefix: Expected prefix of the path names.
    """
    p_len = len(prefix)
    for entry in iter:
        yield entry.name[p_len:]


def find_suffixes(root: Path, prefix: str) -> Iterator[str]:
    """Combine find_prefixes and extract_suffixes."""
    return extract_suffixes(find_prefixed(root, prefix), prefix)


def parse_num(maybe_num: str) -> int:
    """Parse number path suffixes, returns -1 on error."""
    try:
        return int(maybe_num)
    except ValueError:
        return -1


def _force_symlink(root: Path, target: str | PurePath, link_to: str | Path) -> None:
    """Helper to create the current symlink.

    It's full of race conditions that are reasonably OK to ignore
    for the context of best effort linking to the latest test run.

    The presumption being that in case of much parallelism
    the inaccuracy is going to be acceptable.
    """
    current_symlink = root.joinpath(target)
    try:
        current_symlink.unlink()
    except OSError:
        pass
    try:
        current_symlink.symlink_to(link_to)
    except Exception:
        pass


def make_numbered_dir(root: Path, prefix: str, mode: int = 0o700) -> Path:
    """Create a directory with an increased number as suffix for the given prefix."""
    for i in range(10):
        # try up to 10 times to create the directory
        max_existing = max(map(parse_num, find_suffixes(root, prefix)), default=-1)
        new_number = max_existing + 1
        new_path = root.joinpath(f"{prefix}{new_number}")
        try:
            new_path.mkdir(mode=mode)
        except Exception:
            pass
        else:
            _force_symlink(root, prefix + "current", new_path)
            return new_path
    else:
        raise OSError(
            "could not create numbered dir with prefix "
            f"{prefix} in {root} after 10 tries"
        )


def create_cleanup_lock(p: Path) -> Path:
    """Create a lock to prevent premature directory cleanup."""
    lock_path = get_lock_path(p)
    try:
        fd = os.open(str(lock_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as e:
        raise OSError(f"cannot create lockfile in {p}") from e
    else:
        pid = os.getpid()
        spid = str(pid).encode()
        os.write(fd, spid)
        os.close(fd)
        if not lock_path.is_file():
            raise OSError("lock path got renamed after successful creation")
        return lock_path


def register_cleanup_lock_removal(lock_path: Path, register: Any) -> Any:
    """Register a cleanup function for removing a lock."""
    pid = os.getpid()

    def cleanup_on_exit(lock_path: Path = lock_path, original_pid: int = pid) -> None:
        current_pid = os.getpid()
        if current_pid != original_pid:
            # fork
            return
        try:
            lock_path.unlink()
        except OSError:
            pass

    return register(cleanup_on_exit)


def maybe_delete_a_numbered_dir(path: Path) -> None:
    """Remove a numbered directory if its lock can be obtained and it does
    not seem to be in use."""
    path = ensure_extended_length_path(path)
    lock_path = None
    try:
        lock_path = create_cleanup_lock(path)
        parent = path.parent

        garbage = parent.joinpath(f"garbage-{uuid.uuid4()}")
        path.rename(garbage)
        rm_rf(garbage)
    except OSError:
        #  known races:
        #  * other process did a cleanup at the same time
        #  * deletable directory was found
        #  * process cwd (Windows)
        return
    finally:
        # If we created the lock, ensure we remove it even if we failed
        # to properly remove the numbered dir.
        if lock_path is not None:
            try:
                lock_path.unlink()
            except OSError:
                pass


def ensure_deletable(path: Path, consider_lock_dead_if_created_before: float) -> bool:
    """Check if `path` is deletable based on whether the lock file is expired."""
    if path.is_symlink():
        return False
    lock = get_lock_path(path)
    try:
        if not lock.is_file():
            return True
    except OSError:
        # we might not have access to the lock file at all, in this case assume
        # we don't have access to the entire directory (#7491).
        return False
    try:
        lock_time = lock.stat().st_mtime
    except Exception:
        return False
    else:
        if lock_time < consider_lock_dead_if_created_before:
            # We want to ignore any errors while trying to remove the lock such as:
            # - PermissionDenied, like the file permissions have changed since the lock creation;
            # - FileNotFoundError, in case another pytest process got here first;
            # and any other cause of failure.
            with contextlib.suppress(OSError):
                lock.unlink()
                return True
        return False


def try_cleanup(path: Path, consider_lock_dead_if_created_before: float) -> None:
    """Try to cleanup a directory if we can ensure it's deletable."""
    if ensure_deletable(path, consider_lock_dead_if_created_before):
        maybe_delete_a_numbered_dir(path)


def cleanup_candidates(root: Path, prefix: str, keep: int) -> Iterator[Path]:
    """List candidates for numbered directories to be removed - follows py.path."""
    max_existing = max(map(parse_num, find_suffixes(root, prefix)), default=-1)
    max_delete = max_existing - keep
    entries = find_prefixed(root, prefix)
    entries, entries2 = itertools.tee(entries)
    numbers = map(parse_num, extract_suffixes(entries2, prefix))
    for entry, number in zip(entries, numbers, strict=True):
        if number <= max_delete:
            yield Path(entry)


def cleanup_dead_symlinks(root: Path) -> None:
    for left_dir in root.iterdir():
        if left_dir.is_symlink():
            if not left_dir.resolve().exists():
                left_dir.unlink()


def cleanup_numbered_dir(
    root: Path, prefix: str, keep: int, consider_lock_dead_if_created_before: float
) -> None:
    """Cleanup for lock driven numbered directories."""
    if not root.exists():
        return
    for path in cleanup_candidates(root, prefix, keep):
        try_cleanup(path, consider_lock_dead_if_created_before)
    for path in root.glob("garbage-*"):
        try_cleanup(path, consider_lock_dead_if_created_before)

    cleanup_dead_symlinks(root)


def make_numbered_dir_with_cleanup(
    *,
    root: Path,
    prefix: str,
    mode: int,
    keep: int,
    lock_timeout: float,
    register: Any,
) -> Path:
    """Create a numbered dir and register its cleanup.

    Similar to make_numbered_dir, but also maintains a lock file indicating that
    the directory is currently in use, and registers the cleanup of the lock and
    of stale numbered directories.

    :param keep:
        The number of sessions to retain the directory.
    :param lock_timeout:
        In case of a crash, the lock remains "stuck". The timeout is a time
        limit after which the lock is considered stale and can be removed.
    :param register:
        Called as register(cleanup_func, params...). Should schedule to call
        passed cleanup functions on session finish.
    """
    e = None
    for i in range(10):
        try:
            p = make_numbered_dir(root, prefix, mode)
            # Only lock the current dir when keep is not 0
            if keep != 0:
                lock_path = create_cleanup_lock(p)
                register_cleanup_lock_removal(lock_path, register)
        except Exception as exc:
            e = exc
        else:
            consider_lock_dead_if_created_before = p.stat().st_mtime - lock_timeout
            # Register a cleanup for program exit
            register(
                cleanup_numbered_dir,
                root,
                prefix,
                keep,
                consider_lock_dead_if_created_before,
            )
            return p
    assert e is not None
    raise e


def resolve_from_str(input: str, rootpath: Path) -> Path:
    input = expanduser(input)
    input = expandvars(input)
    if isabs(input):
        return Path(input)
    else:
        return rootpath.joinpath(input)


def fnmatch_ex(pattern: str, path: str | os.PathLike[str]) -> bool:
    """A port of FNMatcher from py.path.common which works with PurePath() instances.

    The difference between this algorithm and PurePath.match() is that the
    latter matches "**" glob expressions for each part of the path, while
    this algorithm uses the whole path instead.

    For example:
        "tests/foo/bar/doc/test_foo.py" matches pattern "tests/**/doc/test*.py"
        with this algorithm, but not with PurePath.match().

    This algorithm was ported to keep backward-compatibility with existing
    settings which assume paths match according this logic.

    References:
    * https://bugs.python.org/issue29249
    * https://bugs.python.org/issue34731
    """
    path = PurePath(path)
    iswin32 = sys.platform.startswith("win")

    if iswin32 and sep not in pattern and posix_sep in pattern:
        # Running on Windows, the pattern has no Windows path separators,
        # and the pattern has one or more Posix path separators. Replace
        # the Posix path separators with the Windows path separator.
        pattern = pattern.replace(posix_sep, sep)

    if sep not in pattern:
        name = path.name
    else:
        name = str(path)
        if path.is_absolute() and not os.path.isabs(pattern):
            pattern = f"*{os.sep}{pattern}"
    return fnmatch.fnmatch(name, pattern)


def parts(s: str) -> set[str]:
    parts = s.split(sep)
    return {sep.join(parts[: i + 1]) or sep for i in range(len(parts))}


def symlink_or_skip(
    src: os.PathLike[str] | str,
    dst: os.PathLike[str] | str,
    **kwargs: Any,
) -> None:
    """Make a symlink, or skip the test in case symlinks are not supported."""
    try:
        os.symlink(src, dst, **kwargs)
    except OSError as e:
        skip(f"symlinks not supported: {e}")


class ImportMode(Enum):
    """Possible values for `mode` parameter of `import_path`."""

    prepend = "prepend"
    append = "append"
    importlib = "importlib"


class ImportPathMismatchError(ImportError):
    """Raised on import_path() if there is a mismatch of __file__'s.

    This can happen when `import_path` is called multiple times with different filenames that has
    the same basename but reside in packages
    (for example "/tests1/test_foo.py" and "/tests2/test_foo.py").
    """


def import_path(
    path: str | os.PathLike[str],
    *,
    mode: str | ImportMode = ImportMode.prepend,
    root: Path,
    consider_namespace_packages: bool,
) -> ModuleType:
    """
    Import and return a module from the given path, which can be a file (a module) or
    a directory (a package).

    :param path:
        Path to the file to import.

    :param mode:
        Controls the underlying import mechanism that will be used:

        * ImportMode.prepend: the directory containing the module (or package, taking
          `__init__.py` files into account) will be put at the *start* of `sys.path` before
          being imported with `importlib.import_module`.

        * ImportMode.append: same as `prepend`, but the directory will be appended
          to the end of `sys.path`, if not already in `sys.path`.

        * ImportMode.importlib: uses more fine control mechanisms provided by `importlib`
          to import the module, which avoids having to muck with `sys.path` at all. It effectively
          allows having same-named test modules in different places.

    :param root:
        Used as an anchor when mode == ImportMode.importlib to obtain
        a unique name for the module being imported so it can safely be stored
        into ``sys.modules``.

    :param consider_namespace_packages:
        If True, consider namespace packages when resolving module names.

    :raises ImportPathMismatchError:
        If after importing the given `path` and the module `__file__`
        are different. Only raised in `prepend` and `append` modes.
    """
    path = Path(path)
    mode = ImportMode(mode)

    if not path.exists():
        raise ImportError(path)

    if mode is ImportMode.importlib:
        # Try to import this module using the standard import mechanisms, but
        # without touching sys.path.
        try:
            _, module_name = resolve_pkg_root_and_module_name(
                path, consider_namespace_packages=consider_namespace_packages
            )
        except CouldNotResolvePathError:
            pass
        else:
            # If the given module name is already in sys.modules, do not import it again.
            with contextlib.suppress(KeyError):
                return sys.modules[module_name]

            mod = _import_module_using_spec(module_name, path, insert_modules=False)
            if mod is not None:
                return mod

        # Could not import the module with the current sys.path, so we fall back
        # to importing the file as a single module, not being a part of a package.
        module_name = module_name_from_path(path, root)
        with contextlib.suppress(KeyError):
            return sys.modules[module_name]

        mod = _import_module_using_spec(module_name, path, insert_modules=True)
        if mod is None:
            raise ImportError(f"Can't find module {module_name} at location {path}")
        return mod

    try:
        pkg_root, module_name = resolve_pkg_root_and_module_name(
            path, consider_namespace_packages=consider_namespace_packages
        )
    except CouldNotResolvePathError:
        pkg_root, module_name = path.parent, path.stem

    # Change sys.path permanently: restoring it at the end of this function would cause surprising
    # problems because of delayed imports: for example, a conftest.py file imported by this function
    # might have local imports, which would fail at runtime if we restored sys.path.
    if mode is ImportMode.append:
        if str(pkg_root) not in sys.path:
            sys.path.append(str(pkg_root))
    elif mode is ImportMode.prepend:
        if str(pkg_root) != sys.path[0]:
            sys.path.insert(0, str(pkg_root))
    else:
        assert_never(mode)

    importlib.import_module(module_name)

    mod = sys.modules[module_name]
    if path.name == "__init__.py":
        return mod

    ignore = os.environ.get("PY_IGNORE_IMPORTMISMATCH", "")
    if ignore != "1":
        module_file = mod.__file__
        if module_file is None:
            raise ImportPathMismatchError(module_name, module_file, path)

        if module_file.endswith((".pyc", ".pyo")):
            module_file = module_file[:-1]
        if module_file.endswith(os.sep + "__init__.py"):
            module_file = module_file[: -(len(os.sep + "__init__.py"))]

        try:
            is_same = _is_same(str(path), module_file)
        except FileNotFoundError:
            is_same = False

        if not is_same:
            raise ImportPathMismatchError(module_name, module_file, path)

    return mod


def _import_module_using_spec(
    module_name: str, module_path: Path, *, insert_modules: bool
) -> ModuleType | None:
    """
    Tries to import a module by its canonical name, path, and its parent location.

    :param module_name:
        The expected module name, will become the key of `sys.modules`.

    :param module_path:
        The file path of the module, for example `/foo/bar/test_demo.py`.
        If module is a package, pass the path to the  `__init__.py` of the package.
        If module is a namespace package, pass directory path.

    :param insert_modules:
        If True, will call `insert_missing_modules` to create empty intermediate modules
        with made-up module names (when importing test files not reachable from `sys.path`).

    Example 1 of parent_module_*:

        module_name:        "a.b.c.demo"
        module_path:        Path("a/b/c/demo.py")
        if "a.b.c" is package ("a/b/c/__init__.py" exists), then
            parent_module_name:         "a.b.c"
            parent_module_path:         Path("a/b/c/__init__.py")
        else:
            parent_module_name:         "a.b.c"
            parent_module_path:         Path("a/b/c")

    Example 2 of parent_module_*:

        module_name:        "a.b.c"
        module_path:        Path("a/b/c/__init__.py")
        if  "a.b" is package ("a/b/__init__.py" exists), then
            parent_module_name:         "a.b"
            parent_module_path:         Path("a/b/__init__.py")
        else:
            parent_module_name:         "a.b"
            parent_module_path:         Path("a/b/")
    """
    # Attempt to import the parent module, seems is our responsibility:
    # https://github.com/python/cpython/blob/73906d5c908c1e0b73c5436faeff7d93698fc074/Lib/importlib/_bootstrap.py#L1308-L1311
    parent_module_name, _, name = module_name.rpartition(".")
    parent_module: ModuleType | None = None
    if parent_module_name:
        parent_module = sys.modules.get(parent_module_name)
        # If the parent_module lacks the `__path__` attribute, AttributeError when finding a submodule's spec,
        # requiring re-import according to the path.
        need_reimport = not hasattr(parent_module, "__path__")
        if parent_module is None or need_reimport:
            # Get parent_location based on location, get parent_path based on path.
            if module_path.name == "__init__.py":
                # If the current module is in a package,
                # need to leave the package first and then enter the parent module.
                parent_module_path = module_path.parent.parent
            else:
                parent_module_path = module_path.parent

            if (parent_module_path / "__init__.py").is_file():
                # If the parent module is a package, loading by  __init__.py file.
                parent_module_path = parent_module_path / "__init__.py"

            parent_module = _import_module_using_spec(
                parent_module_name,
                parent_module_path,
                insert_modules=insert_modules,
            )

    # Checking with sys.meta_path first in case one of its hooks can import this module,
    # such as our own assertion-rewrite hook.
    find_spec_path = [str(module_path.parent)]
    for meta_importer in sys.meta_path:
        spec = meta_importer.find_spec(module_name, find_spec_path)

        if spec_matches_module_path(spec, module_path):
            break
    else:
        loader = None
        if module_path.is_dir():
            # The `spec_from_file_location` matches a loader based on the file extension by default.
            # For a namespace package, need to manually specify a loader.
            loader = NamespaceLoader(name, module_path, PathFinder())  # type: ignore[arg-type]

        spec = importlib.util.spec_from_file_location(
            module_name, str(module_path), loader=loader
        )

    if spec_matches_module_path(spec, module_path):
        assert spec is not None
        # Find spec and import this module.
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

        # Set this module as an attribute of the parent module (#12194).
        if parent_module is not None:
            setattr(parent_module, name, mod)

        if insert_modules:
            insert_missing_modules(sys.modules, module_name)
        return mod

    return None


def spec_matches_module_path(module_spec: ModuleSpec | None, module_path: Path) -> bool:
    """Return true if the given ModuleSpec can be used to import the given module path."""
    if module_spec is None:
        return False

    if module_spec.origin:
        return Path(module_spec.origin) == module_path

    # Compare the path with the `module_spec.submodule_Search_Locations` in case
    # the module is part of a namespace package.
    # https://docs.python.org/3/library/importlib.html#importlib.machinery.ModuleSpec.submodule_search_locations
    if module_spec.submodule_search_locations:  # can be None.
        for path in module_spec.submodule_search_locations:
            if Path(path) == module_path:
                return True

    return False


# Implement a special _is_same function on Windows which returns True if the two filenames
# compare equal, to circumvent os.path.samefile returning False for mounts in UNC (#7678).
if sys.platform.startswith("win"):

    def _is_same(f1: str, f2: str) -> bool:
        return Path(f1) == Path(f2) or os.path.samefile(f1, f2)

else:

    def _is_same(f1: str, f2: str) -> bool:
        return os.path.samefile(f1, f2)


def module_name_from_path(path: Path, root: Path) -> str:
    """
    Return a dotted module name based on the given path, anchored on root.

    For example: path="projects/src/tests/test_foo.py" and root="/projects", the
    resulting module name will be "src.tests.test_foo".
    """
    path = path.with_suffix("")
    try:
        relative_path = path.relative_to(root)
    except ValueError:
        # If we can't get a relative path to root, use the full path, except
        # for the first part ("d:\\" or "/" depending on the platform, for example).
        path_parts = path.parts[1:]
    else:
        # Use the parts for the relative path to the root path.
        path_parts = relative_path.parts

    # Module name for packages do not contain the __init__ file, unless
    # the `__init__.py` file is at the root.
    if len(path_parts) >= 2 and path_parts[-1] == "__init__":
        path_parts = path_parts[:-1]

    # Module names cannot contain ".", normalize them to "_". This prevents
    # a directory having a "." in the name (".env.310" for example) causing extra intermediate modules.
    # Also, important to replace "." at the start of paths, as those are considered relative imports.
    path_parts = tuple(x.replace(".", "_") for x in path_parts)

    return ".".join(path_parts)


def insert_missing_modules(modules: dict[str, ModuleType], module_name: str) -> None:
    """
    Used by ``import_path`` to create intermediate modules when using mode=importlib.

    When we want to import a module as "src.tests.test_foo" for example, we need
    to create empty modules "src" and "src.tests" after inserting "src.tests.test_foo",
    otherwise "src.tests.test_foo" is not importable by ``__import__``.
    """
    module_parts = module_name.split(".")
    while module_name:
        parent_module_name, _, child_name = module_name.rpartition(".")
        if parent_module_name:
            parent_module = modules.get(parent_module_name)
            if parent_module is None:
                try:
                    # If sys.meta_path is empty, calling import_module will issue
                    # a warning and raise ModuleNotFoundError. To avoid the
                    # warning, we check sys.meta_path explicitly and raise the error
                    # ourselves to fall back to creating a dummy module.
                    if not sys.meta_path:
                        raise ModuleNotFoundError
                    parent_module = importlib.import_module(parent_module_name)
                except ModuleNotFoundError:
                    parent_module = ModuleType(
                        module_name,
                        doc="Empty module created by pytest's importmode=importlib.",
                    )
                modules[parent_module_name] = parent_module

            # Add child attribute to the parent that can reference the child
            # modules.
            if not hasattr(parent_module, child_name):
                setattr(parent_module, child_name, modules[module_name])

        module_parts.pop(-1)
        module_name = ".".join(module_parts)


def resolve_package_path(path: Path) -> Path | None:
    """Return the Python package path by looking for the last
    directory upwards which still contains an __init__.py.

    Returns None if it cannot be determined.
    """
    result = None
    for parent in itertools.chain((path,), path.parents):
        if parent.is_dir():
            if not (parent / "__init__.py").is_file():
                break
            if not parent.name.isidentifier():
                break
            result = parent
    return result


def resolve_pkg_root_and_module_name(
    path: Path, *, consider_namespace_packages: bool = False
) -> tuple[Path, str]:
    """
    Return the path to the directory of the root package that contains the
    given Python file, and its module name:

        src/
            app/
                __init__.py
                core/
                    __init__.py
                    models.py

    Passing the full path to `models.py` will yield Path("src") and "app.core.models".

    If consider_namespace_packages is True, then we additionally check upwards in the hierarchy
    for namespace packages:

    https://packaging.python.org/en/latest/guides/packaging-namespace-packages

    Raises CouldNotResolvePathError if the given path does not belong to a package (missing any __init__.py files).
    """
    pkg_root: Path | None = None
    pkg_path = resolve_package_path(path)
    if pkg_path is not None:
        pkg_root = pkg_path.parent
    if consider_namespace_packages:
        start = pkg_root if pkg_root is not None else path.parent
        for candidate in (start, *start.parents):
            module_name = compute_module_name(candidate, path)
            if module_name and is_importable(module_name, path):
                # Point the pkg_root to the root of the namespace package.
                pkg_root = candidate
                break

    if pkg_root is not None:
        module_name = compute_module_name(pkg_root, path)
        if module_name:
            return pkg_root, module_name

    raise CouldNotResolvePathError(f"Could not resolve for {path}")


def is_importable(module_name: str, module_path: Path) -> bool:
    """
    Return if the given module path could be imported normally by Python, akin to the user
    entering the REPL and importing the corresponding module name directly, and corresponds
    to the module_path specified.

    :param module_name:
        Full module name that we want to check if is importable.
        For example, "app.models".

    :param module_path:
        Full path to the python module/package we want to check if is importable.
        For example, "/projects/src/app/models.py".
    """
    try:
        # Note this is different from what we do in ``_import_module_using_spec``, where we explicitly search through
        # sys.meta_path to be able to pass the path of the module that we want to import (``meta_importer.find_spec``).
        # Using importlib.util.find_spec() is different, it gives the same results as trying to import
        # the module normally in the REPL.
        spec = importlib.util.find_spec(module_name)
    except (ImportError, ValueError, ImportWarning):
        return False
    else:
        return spec_matches_module_path(spec, module_path)


def compute_module_name(root: Path, module_path: Path) -> str | None:
    """Compute a module name based on a path and a root anchor."""
    try:
        path_without_suffix = module_path.with_suffix("")
    except ValueError:
        # Empty paths (such as Path.cwd()) might break meta_path hooks (like our own assertion rewriter).
        return None

    try:
        relative = path_without_suffix.relative_to(root)
    except ValueError:  # pragma: no cover
        return None
    names = list(relative.parts)
    if not names:
        return None
    if names[-1] == "__init__":
        names.pop()
    return ".".join(names)


class CouldNotResolvePathError(Exception):
    """Custom exception raised by resolve_pkg_root_and_module_name."""


def scandir(
    path: str | os.PathLike[str],
    sort_key: Callable[[os.DirEntry[str]], object] = lambda entry: entry.name,
) -> list[os.DirEntry[str]]:
    """Scan a directory recursively, in breadth-first order.

    The returned entries are sorted according to the given key.
    The default is to sort by name.
    If the directory does not exist, return an empty list.
    """
    entries = []
    # Attempt to create a scandir iterator for the given path.
    try:
        scandir_iter = os.scandir(path)
    except FileNotFoundError:
        # If the directory does not exist, return an empty list.
        return []
    # Use the scandir iterator in a context manager to ensure it is properly closed.
    with scandir_iter as s:
        for entry in s:
            try:
                entry.is_file()
            except OSError as err:
                if _ignore_error(err):
                    continue
                # Reraise non-ignorable errors to avoid hiding issues.
                raise
            entries.append(entry)
    entries.sort(key=sort_key)  # type: ignore[arg-type]
    return entries


def visit(
    path: str | os.PathLike[str], recurse: Callable[[os.DirEntry[str]], bool]
) -> Iterator[os.DirEntry[str]]:
    """Walk a directory recursively, in breadth-first order.

    The `recurse` predicate determines whether a directory is recursed.

    Entries at each directory level are sorted.
    """
    entries = scandir(path)
    yield from entries
    for entry in entries:
        if entry.is_dir() and recurse(entry):
            yield from visit(entry.path, recurse)


def absolutepath(path: str | os.PathLike[str]) -> Path:
    """Convert a path to an absolute path using os.path.abspath.

    Prefer this over Path.resolve() (see #6523).
    Prefer this over Path.absolute() (not public, doesn't normalize).
    """
    return Path(os.path.abspath(path))


def commonpath(path1: Path, path2: Path) -> Path | None:
    """Return the common part shared with the other path, or None if there is
    no common part.

    If one path is relative and one is absolute, returns None.
    """
    try:
        return Path(os.path.commonpath((str(path1), str(path2))))
    except ValueError:
        return None


def bestrelpath(directory: Path, dest: Path) -> str:
    """Return a string which is a relative path from directory to dest such
    that directory/bestrelpath == dest.

    The paths must be either both absolute or both relative.

    If no such path can be determined, returns dest.
    """
    assert isinstance(directory, Path)
    assert isinstance(dest, Path)
    if dest == directory:
        return os.curdir
    # Find the longest common directory.
    base = commonpath(directory, dest)
    # Can be the case on Windows for two absolute paths on different drives.
    # Can be the case for two relative paths without common prefix.
    # Can be the case for a relative path and an absolute path.
    if not base:
        return str(dest)
    reldirectory = directory.relative_to(base)
    reldest = dest.relative_to(base)
    return os.path.join(
        # Back from directory to base.
        *([os.pardir] * len(reldirectory.parts)),
        # Forward from base to dest.
        *reldest.parts,
    )


def safe_exists(p: Path) -> bool:
    """Like Path.exists(), but account for input arguments that might be too long (#11394)."""
    try:
        return p.exists()
    except (ValueError, OSError):
        # ValueError: stat: path too long for Windows
        # OSError: [WinError 123] The filename, directory name, or volume label syntax is incorrect
        return False


def samefile_nofollow(p1: Path, p2: Path) -> bool:
    """Test whether two paths reference the same actual file or directory.

    Unlike Path.samefile(), does not resolve symlinks.
    """
    return os.path.samestat(p1.lstat(), p2.lstat())
