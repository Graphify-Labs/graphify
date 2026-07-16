"""Rewrite assertion AST to produce nice error messages."""

from __future__ import annotations

import ast
from collections import defaultdict
from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Iterator
from collections.abc import Sequence
import errno
import functools
import importlib.abc
import importlib.machinery
import importlib.util
import io
import itertools
import marshal
import os
from pathlib import Path
from pathlib import PurePath
import struct
import sys
import tokenize
import types
from typing import IO
from typing import TYPE_CHECKING


if sys.version_info >= (3, 12):
    from importlib.resources.abc import TraversableResources
else:
    from importlib.abc import TraversableResources
if sys.version_info < (3, 11):
    from importlib.readers import FileReader
else:
    from importlib.resources.readers import FileReader


from _pytest._io.saferepr import DEFAULT_REPR_MAX_SIZE
from _pytest._io.saferepr import saferepr
from _pytest._io.saferepr import saferepr_unlimited
from _pytest._version import version
from _pytest.assertion import util
from _pytest.config import Config
from _pytest.fixtures import FixtureFunctionDefinition
from _pytest.main import Session
from _pytest.pathlib import absolutepath
from _pytest.pathlib import fnmatch_ex
from _pytest.stash import StashKey


# fmt: off
from _pytest.assertion.util import format_explanation as _format_explanation  # noqa:F401, isort:skip
# fmt:on

if TYPE_CHECKING:
    from _pytest.assertion import AssertionState


class Sentinel:
    pass


assertstate_key = StashKey["AssertionState"]()

# pytest caches rewritten pycs in pycache dirs
PYTEST_TAG = f"{sys.implementation.cache_tag}-pytest-{version}"
PYC_EXT = ".py" + ((__debug__ and "c") or "o")
PYC_TAIL = "." + PYTEST_TAG + PYC_EXT

# Special marker that denotes we have just left a scope definition
_SCOPE_END_MARKER = Sentinel()


class AssertionRewritingHook(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """PEP302/PEP451 import hook which rewrites asserts."""

    def __init__(self, config: Config) -> None:
        self.config = config
        try:
            self.fnpats = config.getini("python_files")
        except ValueError:
            self.fnpats = ["test_*.py", "*_test.py"]
        self.session: Session | None = None
        self._rewritten_names: dict[str, Path] = {}
        self._must_rewrite: set[str] = set()
        # flag to guard against trying to rewrite a pyc file while we are already writing another pyc file,
        # which might result in infinite recursion (#3506)
        self._writing_pyc = False
        self._basenames_to_check_rewrite = {"conftest"}
        self._marked_for_rewrite_cache: dict[str, bool] = {}
        self._session_paths_checked = False

    def set_session(self, session: Session | None) -> None:
        self.session = session
        self._session_paths_checked = False

    # Indirection so we can mock calls to find_spec originated from the hook during testing
    _find_spec = importlib.machinery.PathFinder.find_spec

    def find_spec(
        self,
        name: str,
        path: Sequence[str | bytes] | None = None,
        target: types.ModuleType | None = None,
    ) -> importlib.machinery.ModuleSpec | None:
        if self._writing_pyc:
            return None
        state = self.config.stash[assertstate_key]
        if self._early_rewrite_bailout(name, state):
            return None
        state.trace(f"find_module called for: {name}")

        # Type ignored because mypy is confused about the `self` binding here.
        spec = self._find_spec(name, path)  # type: ignore

        if (
            # the import machinery could not find a file to import
            spec is None
            # this is a namespace package (without `__init__.py`)
            # there's nothing to rewrite there
            or spec.origin is None
            # we can only rewrite source files
            or not isinstance(spec.loader, importlib.machinery.SourceFileLoader)
            # if the file doesn't exist, we can't rewrite it
            or not os.path.exists(spec.origin)
        ):
            return None
        else:
            fn = spec.origin

        if not self._should_rewrite(name, fn, state):
            return None

        return importlib.util.spec_from_file_location(
            name,
            fn,
            loader=self,
            submodule_search_locations=spec.submodule_search_locations,
        )

    def create_module(
        self, spec: importlib.machinery.ModuleSpec
    ) -> types.ModuleType | None:
        return None  # default behaviour is fine

    def exec_module(self, module: types.ModuleType) -> None:
        assert module.__spec__ is not None
        assert module.__spec__.origin is not None
        fn = Path(module.__spec__.origin)
        state = self.config.stash[assertstate_key]

        self._rewritten_names[module.__name__] = fn

        # The requested module looks like a test file, so rewrite it. This is
        # the most magical part of the process: load the source, rewrite the
        # asserts, and load the rewritten source. We also cache the rewritten
        # module code in a special pyc. We must be aware of the possibility of
        # concurrent pytest processes rewriting and loading pycs. To avoid
        # tricky race conditions, we maintain the following invariant: The
        # cached pyc is always a complete, valid pyc. Operations on it must be
        # atomic. POSIX's atomic rename comes in handy.
        write = not sys.dont_write_bytecode
        cache_dir = get_cache_dir(fn)
        if write:
            ok = try_makedirs(cache_dir)
            if not ok:
                write = False
                state.trace(f"read only directory: {cache_dir}")

        cache_name = fn.name[:-3] + PYC_TAIL
        pyc = cache_dir / cache_name
        # Notice that even if we're in a read-only directory, I'm going
        # to check for a cached pyc. This may not be optimal...
        co = _read_pyc(fn, pyc, state.trace)
        if co is None:
            state.trace(f"rewriting {fn!r}")
            source_stat, co = _rewrite_test(fn, self.config)
            if write:
                self._writing_pyc = True
                try:
                    _write_pyc(state, co, source_stat, pyc)
                finally:
                    self._writing_pyc = False
        else:
            state.trace(f"found cached rewritten pyc for {fn}")
        exec(co, module.__dict__)

    def _early_rewrite_bailout(self, name: str, state: AssertionState) -> bool:
        """A fast way to get out of rewriting modules.

        Profiling has shown that the call to PathFinder.find_spec (inside of
        the find_spec from this class) is a major slowdown, so, this method
        tries to filter what we're sure won't be rewritten before getting to
        it.
        """
        if self.session is not None and not self._session_paths_checked:
            self._session_paths_checked = True
            for initial_path in self.session._initialpaths:
                # Make something as c:/projects/my_project/path.py ->
                #     ['c:', 'projects', 'my_project', 'path.py']
                parts = str(initial_path).split(os.sep)
                # add 'path' to basenames to be checked.
                self._basenames_to_check_rewrite.add(os.path.splitext(parts[-1])[0])

        # Note: conftest already by default in _basenames_to_check_rewrite.
        parts = name.split(".")
        if parts[-1] in self._basenames_to_check_rewrite:
            return False

        # For matching the name it must be as if it was a filename.
        path = PurePath(*parts).with_suffix(".py")

        for pat in self.fnpats:
            # if the pattern contains subdirectories ("tests/**.py" for example) we can't bail out based
            # on the name alone because we need to match against the full path
            if os.path.dirname(pat):
                return False
            if fnmatch_ex(pat, path):
                return False

        if self._is_marked_for_rewrite(name, state):
            return False

        state.trace(f"early skip of rewriting module: {name}")
        return True

    def _should_rewrite(self, name: str, fn: str, state: AssertionState) -> bool:
        # always rewrite conftest files
        if os.path.basename(fn) == "conftest.py":
            state.trace(f"rewriting conftest file: {fn!r}")
            return True

        if self.session is not None:
            if self.session.isinitpath(absolutepath(fn)):
                state.trace(f"matched test file (was specified on cmdline): {fn!r}")
                return True

        # modules not passed explicitly on the command line are only
        # rewritten if they match the naming convention for test files
        fn_path = PurePath(fn)
        for pat in self.fnpats:
            if fnmatch_ex(pat, fn_path):
                state.trace(f"matched test file {fn!r}")
                return True

        return self._is_marked_for_rewrite(name, state)

    def _is_marked_for_rewrite(self, name: str, state: AssertionState) -> bool:
        try:
            return self._marked_for_rewrite_cache[name]
        except KeyError:
            for marked in self._must_rewrite:
                if name == marked or name.startswith(marked + "."):
                    state.trace(f"matched marked file {name!r} (from {marked!r})")
                    self._marked_for_rewrite_cache[name] = True
                    return True

            self._marked_for_rewrite_cache[name] = False
            return False

    def mark_rewrite(self, *names: str) -> None:
        """Mark import names as needing to be rewritten.

        The named module or package as well as any nested modules will
        be rewritten on import.
        """
        already_imported = (
            set(names).intersection(sys.modules).difference(self._rewritten_names)
        )
        for name in already_imported:
            mod = sys.modules[name]
            if not AssertionRewriter.is_rewrite_disabled(
                mod.__doc__ or ""
            ) and not isinstance(mod.__loader__, type(self)):
                self._warn_already_imported(name)
        self._must_rewrite.update(names)
        self._marked_for_rewrite_cache.clear()

    def _warn_already_imported(self, name: str) -> None:
        from _pytest.warning_types import PytestAssertRewriteWarning

        self.config.issue_config_time_warning(
            PytestAssertRewriteWarning(
                f"Module already imported so cannot be rewritten; {name}"
            ),
            stacklevel=5,
        )

    def get_data(self, pathname: str | bytes) -> bytes:
        """Optional PEP302 get_data API."""
        with open(pathname, "rb") as f:
            return f.read()

    def get_resource_reader(self, name: str) -> TraversableResources:
        return FileReader(types.SimpleNamespace(path=self._rewritten_names[name]))  # type: ignore[arg-type]


def _write_pyc_fp(
    fp: IO[bytes], source_stat: os.stat_result, co: types.CodeType
) -> None:
    # Technically, we don't have to have the same pyc format as
    # (C)Python, since these "pycs" should never be seen by builtin
    # import. However, there's little reason to deviate.
    fp.write(importlib.util.MAGIC_NUMBER)
    # https://www.python.org/dev/peps/pep-0552/
    flags = b"\x00\x00\x00\x00"
    fp.write(flags)
    # as of now, bytecode header expects 32-bit numbers for size and mtime (#4903)
    mtime = int(source_stat.st_mtime) & 0xFFFFFFFF
    size = source_stat.st_size & 0xFFFFFFFF
    # "<LL" stands for 2 unsigned longs, little-endian.
    fp.write(struct.pack("<LL", mtime, size))
    fp.write(marshal.dumps(co))


def _write_pyc(
    state: AssertionState,
    co: types.CodeType,
    source_stat: os.stat_result,
    pyc: Path,
) -> bool:
    proc_pyc = f"{pyc}.{os.getpid()}"
    try:
        with open(proc_pyc, "wb") as fp:
            _write_pyc_fp(fp, source_stat, co)
    except OSError as e:
        state.trace(f"error writing pyc file at {proc_pyc}: errno={e.errno}")
        return False

    try:
        os.replace(proc_pyc, pyc)
    except OSError as e:
        state.trace(f"error writing pyc file at {pyc}: {e}")
        # we ignore any failure to write the cache file
        # there are many reasons, permission-denied, pycache dir being a
        # file etc.
        return False
    return True


def _rewrite_test(fn: Path, config: Config) -> tuple[os.stat_result, types.CodeType]:
    """Read and rewrite *fn* and return the code object."""
    stat = os.stat(fn)
    source = fn.read_bytes()
    strfn = str(fn)
    tree = ast.parse(source, filename=strfn)
    rewrite_asserts(tree, source, strfn, config)
    co = compile(tree, strfn, "exec", dont_inherit=True)
    return stat, co


def _read_pyc(
    source: Path, pyc: Path, trace: Callable[[str], None] = lambda x: None
) -> types.CodeType | None:
    """Possibly read a pytest pyc containing rewritten code.

    Return rewritten code if successful or None if not.
    """
    try:
        fp = open(pyc, "rb")
    except OSError:
        return None
    with fp:
        try:
            stat_result = os.stat(source)
            mtime = int(stat_result.st_mtime)
            size = stat_result.st_size
            data = fp.read(16)
        except OSError as e:
            trace(f"_read_pyc({source}): OSError {e}")
            return None
        # Check for invalid or out of date pyc file.
        if len(data) != (16):
            trace(f"_read_pyc({source}): invalid pyc (too short)")
            return None
        if data[:4] != importlib.util.MAGIC_NUMBER:
            trace(f"_read_pyc({source}): invalid pyc (bad magic number)")
            return None
        if data[4:8] != b"\x00\x00\x00\x00":
            trace(f"_read_pyc({source}): invalid pyc (unsupported flags)")
            return None
        mtime_data = data[8:12]
        if int.from_bytes(mtime_data, "little") != mtime & 0xFFFFFFFF:
            trace(f"_read_pyc({source}): out of date")
            return None
        size_data = data[12:16]
        if int.from_bytes(size_data, "little") != size & 0xFFFFFFFF:
            trace(f"_read_pyc({source}): invalid pyc (incorrect size)")
            return None
        try:
            co = marshal.load(fp)
        except Exception as e:
            trace(f"_read_pyc({source}): marshal.load error {e}")
            return None
        if not isinstance(co, types.CodeType):
            trace(f"_read_pyc({source}): not a code object")
            return None
        return co


def rewrite_asserts(
    mod: ast.Module,
    source: bytes,
    module_path: str | None = None,
    config: Config | None = None,
) -> None:
    """Rewrite the assert statements in mod."""
    AssertionRewriter(module_path, config, source).run(mod)


def _saferepr(obj: object) -> str:
    r"""Get a safe repr of an object for assertion error messages.

    The assertion formatting (util.format_explanation()) requires
    newlines to be escaped since they are a special character for it.
    Normally assertion.util.format_explanation() does this but for a
    custom repr it is possible to contain one of the special escape
    sequences, especially '\n{' and '\n}' are likely to be present in
    JSON reprs.
    """
    if isinstance(obj, types.MethodType):
        # for bound methods, skip redundant <bound method ...> information
        return obj.__name__

    maxsize = _get_maxsize_for_saferepr(util._config)
    if not maxsize:
        return saferepr_unlimited(obj).replace("\n", "\\n")
    return saferepr(obj, maxsize=maxsize).replace("\n", "\\n")


def _get_maxsize_for_saferepr(config: Config | None) -> int | None:
    """Get `maxsize` configuration for saferepr based on the given config object."""
    if config is None:
        verbosity = 0
    else:
        verbosity = config.get_verbosity(Config.VERBOSITY_ASSERTIONS)
    if verbosity >= 2:
        return None
    if verbosity >= 1:
        return DEFAULT_REPR_MAX_SIZE * 10
    return DEFAULT_REPR_MAX_SIZE


def _format_assertmsg(obj: object) -> str:
    r"""Format the custom assertion message given.

    For strings this simply replaces newlines with '\n~' so that
    util.format_explanation() will preserve them instead of escaping
    newlines.  For other objects saferepr() is used first.
    """
    # reprlib appears to have a bug which means that if a string
    # contains a newline it gets escaped, however if an object has a
    # .__repr__() which contains newlines it does not get escaped.
    # However in either case we want to preserve the newline.
    replaces = [("\n", "\n~"), ("%", "%%")]
    if not isinstance(obj, str):
        obj = saferepr(obj, _get_maxsize_for_saferepr(util._config))
        replaces.append(("\\n", "\n~"))

    for r1, r2 in replaces:
        obj = obj.replace(r1, r2)

    return obj


def _should_repr_global_name(obj: object) -> bool:
    if callable(obj):
        # For pytest fixtures the __repr__ method provides more information than the function name.
        return isinstance(obj, FixtureFunctionDefinition)

    try:
        return not hasattr(obj, "__name__")
    except Exception:
        return True


def _format_boolop(explanations: Iterable[str], is_or: bool) -> str:
    explanation = "(" + ((is_or and " or ") or " and ").join(explanations) + ")"
    return explanation.replace("%", "%%")


def _call_reprcompare(
    ops: Sequence[str],
    results: Sequence[bool],
    expls: Sequence[str],
    each_obj: Sequence[object],
) -> str:
    for i, res, expl in zip(range(len(ops)), results, expls, strict=True):
        try:
            done = not res
        except Exception:
            done = True
        if done:
            break
    if util._reprcompare is not None:
        custom = util._reprcompare(ops[i], each_obj[i], each_obj[i + 1])
        if custom is not None:
            return custom
    return expl


def _call_assertion_pass(lineno: int, orig: str, expl: str) -> None:
    if util._assertion_pass is not None:
        util._assertion_pass(lineno, orig, expl)


def _check_if_assertion_pass_impl() -> bool:
    """Check if any plugins implement the pytest_assertion_pass hook
    in order not to generate explanation unnecessarily (might be expensive)."""
    return True if util._assertion_pass else False


UNARY_MAP = {ast.Not: "not %s", ast.Invert: "~%s", ast.USub: "-%s", ast.UAdd: "+%s"}

BINOP_MAP = {
    ast.BitOr: "|",
    ast.BitXor: "^",
    ast.BitAnd: "&",
    ast.LShift: "<<",
    ast.RShift: ">>",
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.FloorDiv: "//",
    ast.Mod: "%%",  # escaped for string formatting
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Pow: "**",
    ast.Is: "is",
    ast.IsNot: "is not",
    ast.In: "in",
    ast.NotIn: "not in",
    ast.MatMult: "@",
}


def traverse_node(node: ast.AST) -> Iterator[ast.AST]:
    """Recursively yield node and all its children in depth-first order."""
    yield node
    for child in ast.iter_child_nodes(node):
        yield from traverse_node(child)


@functools.lru_cache(maxsize=1)
def _get_assertion_exprs(src: bytes) -> dict[int, str]:
    """Return a mapping from {lineno: "assertion test expression"}."""
    ret: dict[int, str] = {}

    depth = 0
    lines: list[str] = []
    assert_lineno: int | None = None
    seen_lines: set[int] = set()

    def _write_and_reset() -> None:
        nonlocal depth, lines, assert_lineno, seen_lines
        assert assert_lineno is not None
        ret[assert_lineno] = "".join(lines).rstrip().rstrip("\\")
        depth = 0
        lines = []
        assert_lineno = None
        seen_lines = set()

    tokens = tokenize.tokenize(io.BytesIO(src).readline)
    for tp, source, (lineno, offset), _, line in tokens:
        if tp == tokenize.NAME and source == "assert":
            assert_lineno = lineno
        elif assert_lineno is not None:
            # keep track of depth for the assert-message `,` lookup
            if tp == tokenize.OP and source in "([{":
                depth += 1
            elif tp == tokenize.OP and source in ")]}":
                depth -= 1

            if not lines:
                lines.append(line[offset:])
                seen_lines.add(lineno)
            # a non-nested comma separates the expression from the message
            elif depth == 0 and tp == tokenize.OP and source == ",":
                # one line assert with message
                if lineno in seen_lines and len(lines) == 1:
                    offset_in_trimmed = offset + len(lines[-1]) - len(line)
                    lines[-1] = lines[-1][:offset_in_trimmed]
                # multi-line assert with message
                elif lineno in seen_lines:
                    lines[-1] = lines[-1][:offset]
                # multi line assert with escaped newline before message
                else:
                    lines.append(line[:offset])
                _write_and_reset()
            elif tp in {tokenize.NEWLINE, tokenize.ENDMARKER}:
                _write_and_reset()
            elif lines and lineno not in seen_lines:
                lines.append(line)
                seen_lines.add(lineno)

    return ret


class AssertionRewriter(ast.NodeVisitor):
    """Assertion rewriting implementation.

    The main entrypoint is to call .run() with an ast.Module instance,
    this will then find all the assert statements and rewrite them to
    provide intermediate values and a detailed assertion error.  See
    http://pybites.blogspot.be/2011/07/behind-scenes-of-pytests-new-assertion.html
    for an overview of how this works.

    The entry point here is .run() which will iterate over all the
    statements in an ast.Module and for each ast.Assert statement it
    finds call .visit() with it.  Then .visit_Assert() takes over and
    is responsible for creating new ast statements to replace the
    original assert statement: it rewrites the test of an assertion
    to provide intermediate values and replace it with an if statement
    which raises an assertion error with a detailed explanation in
    case the expression is false and calls pytest_assertion_pass hook
    if expression is true.

    For this .visit_Assert() uses the visitor pattern to visit all the
    AST nodes of the ast.Assert.test field, each visit call returning
    an AST node and the corresponding explanation string.  During this
    state is kept in several instance attributes:

    :statements: All the AST statements which will replace the assert
       statement.

    :variables: This is populated by .variable() with each variable
       used by the statements so that they can all be set to None at
       the end of the statements.

    :variable_counter: Counter to create new unique variables needed
       by statements.  Variables are created using .variable() and
       have the form of "@py_assert0".

    :expl_stmts: The AST statements which will be executed to get
       data from the assertion.  This is the code which will construct
       the detailed assertion message that is used in the AssertionError
       or for the pytest_assertion_pass hook.

    :explanation_specifiers: A dict filled by .explanation_param()
       with %-formatting placeholders and their corresponding
       expressions to use in the building of an assertion message.
       This is used by .pop_format_context() to build a message.

    :stack: A stack of the explanation_specifiers dicts maintained by
       .push_format_context() and .pop_format_context() which allows
       to build another %-formatted string while already building one.

    :scope: A tuple containing the current scope used for variables_overwrite.

    :variables_overwrite: A dict filled with references to variables
       that change value within an assert. This happens when a variable is
       reassigned with the walrus operator

    This state, except the variables_overwrite,  is reset on every new assert
    statement visited and used by the other visitors.
    """

    def __init__(
        self, module_path: str | None, config: Config | None, source: bytes
    ) -> None:
        super().__init__()
        self.module_path = module_path
        self.config = config
        if config is not None:
            self.enable_assertion_pass_hook = config.getini(
                "enable_assertion_pass_hook"
            )
        else:
            self.enable_assertion_pass_hook = False
        self.source = source
        self.scope: tuple[ast.AST, ...] = ()
        self.variables_overwrite: defaultdict[tuple[ast.AST, ...], dict[str, str]] = (
            defaultdict(dict)
        )

    def run(self, mod: ast.Module) -> None:
        """Find all assert statements in *mod* and rewrite them."""
        if not mod.body:
            # Nothing to do.
            return

        # We'll insert some special imports at the top of the module, but after any
        # docstrings and __future__ imports, so first figure out where that is.
        doc = getattr(mod, "docstring", None)
        expect_docstring = doc is None
        if doc is not None and self.is_rewrite_disabled(doc):
            return
        pos = 0
        for item in mod.body:
            match item:
                case ast.Expr(value=ast.Constant(value=str() as doc)) if (
                    expect_docstring
                ):
                    if self.is_rewrite_disabled(doc):
                        return
                    expect_docstring = False
                case ast.ImportFrom(level=0, module="__future__"):
                    pass
                case _:
                    break
            pos += 1
        # Special case: for a decorated function, set the lineno to that of the
        # first decorator, not the `def`. Issue #4984.
        if isinstance(item, ast.FunctionDef) and item.decorator_list:
            lineno = item.decorator_list[0].lineno
        else:
            lineno = item.lineno
        # Now actually insert the special imports.
        aliases = [
            ast.alias("builtins", "@py_builtins", lineno=lineno, col_offset=0),
            ast.alias(
                "_pytest.assertion.rewrite",
                "@pytest_ar",
                lineno=lineno,
                col_offset=0,
            ),
        ]
        imports = [
            ast.Import([alias], lineno=lineno, col_offset=0) for alias in aliases
        ]
        mod.body[pos:pos] = imports

        # Collect asserts.
        self.scope = (mod,)
        nodes: list[ast.AST | Sentinel] = [mod]
        while nodes:
            node = nodes.pop()
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                self.scope = tuple((*self.scope, node))
                nodes.append(_SCOPE_END_MARKER)
            if node == _SCOPE_END_MARKER:
                self.scope = self.scope[:-1]
                continue
            assert isinstance(node, ast.AST)
            for name, field in ast.iter_fields(node):
                if isinstance(field, list):
                    new: list[ast.AST] = []
                    for i, child in enumerate(field):
                        if isinstance(child, ast.Assert):
                            # Transform assert.
                            new.extend(self.visit(child))
                        else:
                            new.append(child)
                            if isinstance(child, ast.AST):
                                nodes.append(child)
                    setattr(node, name, new)
                elif (
                    isinstance(field, ast.AST)
                    # Don't recurse into expressions as they can't contain
                    # asserts.
                    and not isinstance(field, ast.expr)
                ):
                    nodes.append(field)

    @staticmethod
    def is_rewrite_disabled(docstring: str) -> bool:
        return "PYTEST_DONT_REWRITE" in docstring

    def variable(self) -> str:
        """Get a new variable."""
        # Use a character invalid in python identifiers to avoid clashing.
        name = "@py_assert" + str(next(self.variable_counter))
        self.variables.append(name)
        return name

    def assign(self, expr: ast.expr) -> ast.Name:
        """Give *expr* a name."""
        name = self.variable()
        self.statements.append(ast.Assign([ast.Name(name, ast.Store())], expr))
        return ast.copy_location(ast.Name(name, ast.Load()), expr)

    def display(self, expr: ast.expr) -> ast.expr:
        """Call saferepr on the expression."""
        return self.helper("_saferepr", expr)

    def helper(self, name: str, *args: ast.expr) -> ast.expr:
        """Call a helper in this module."""
        py_name = ast.Name("@pytest_ar", ast.Load())
        attr = ast.Attribute(py_name, name, ast.Load())
        return ast.Call(attr, list(args), [])

    def builtin(self, name: str) -> ast.Attribute:
        """Return the builtin called *name*."""
        builtin_name = ast.Name("@py_builtins", ast.Load())
        return ast.Attribute(builtin_name, name, ast.Load())

    def explanation_param(self, expr: ast.expr) -> str:
        """Return a new named %-formatting placeholder for expr.

        This creates a %-formatting placeholder for expr in the
        current formatting context, e.g. ``%(py0)s``.  The placeholder
        and expr are placed in the current format context so that it
        can be used on the next call to .pop_format_context().
        """
        specifier = "py" + str(next(self.variable_counter))
        self.explanation_specifiers[specifier] = expr
        return "%(" + specifier + ")s"

    def push_format_context(self) -> None:
        """Create a new formatting context.

        The format context is used for when an explanation wants to
        have a variable value formatted in the assertion message.  In
        this case the value required can be added using
        .explanation_param().  Finally .pop_format_context() is used
        to format a string of %-formatted values as added by
        .explanation_param().
        """
        self.explanation_specifiers: dict[str, ast.expr] = {}
        self.stack.append(self.explanation_specifiers)

    def pop_format_context(self, expl_expr: ast.expr) -> ast.Name:
        """Format the %-formatted string with current format context.

        The expl_expr should be an str ast.expr instance constructed from
        the %-placeholders created by .explanation_param().  This will
        add the required code to format said string to .expl_stmts and
        return the ast.Name instance of the formatted string.
        """
        current = self.stack.pop()
        if self.stack:
            self.explanation_specifiers = self.stack[-1]
        keys: list[ast.expr | None] = [ast.Constant(key) for key in current.keys()]
        format_dict = ast.Dict(keys, list(current.values()))
        form = ast.BinOp(expl_expr, ast.Mod(), format_dict)
        name = "@py_format" + str(next(self.variable_counter))
        if self.enable_assertion_pass_hook:
            self.format_variables.append(name)
        self.expl_stmts.append(ast.Assign([ast.Name(name, ast.Store())], form))
        return ast.Name(name, ast.Load())

    def generic_visit(self, node: ast.AST) -> tuple[ast.Name, str]:
        """Handle expressions we don't have custom code for."""
        assert isinstance(node, ast.expr)
        res = self.assign(node)
        return res, self.explanation_param(self.display(res))

    def visit_Assert(self, assert_: ast.Assert) -> list[ast.stmt]:
        """Return the AST statements to replace the ast.Assert instance.

        This rewrites the test of an assertion to provide
        intermediate values and replace it with an if statement which
        raises an assertion error with a detailed explanation in case
        the expression is false.
        """
        if isinstance(assert_.test, ast.Tuple) and len(assert_.test.elts) >= 1:
            import warnings

            from _pytest.warning_types import PytestAssertRewriteWarning

            # TODO: This assert should not be needed.
            assert self.module_path is not None
            warnings.warn_explicit(
                PytestAssertRewriteWarning(
                    "assertion is always true, perhaps remove parentheses?"
                ),
                category=None,
                filename=self.module_path,
                lineno=assert_.lineno,
            )

        self.statements: list[ast.stmt] = []
        self.variables: list[str] = []
        self.variable_counter = itertools.count()

        if self.enable_assertion_pass_hook:
            self.format_variables: list[str] = []

        self.stack: list[dict[str, ast.expr]] = []
        self.expl_stmts: list[ast.stmt] = []
        self.push_format_context()
        # Rewrite assert into a bunch of statements.
        top_condition, explanation = self.visit(assert_.test)

        negation = ast.UnaryOp(ast.Not(), top_condition)

        if self.enable_assertion_pass_hook:  # Experimental pytest_assertion_pass hook
            msg = self.pop_format_context(ast.Constant(explanation))

            # Failed
            if assert_.msg:
                assertmsg = self.helper("_format_assertmsg", assert_.msg)
                gluestr = "\n>assert "
            else:
                assertmsg = ast.Constant("")
                gluestr = "assert "
            err_explanation = ast.BinOp(ast.Constant(gluestr), ast.Add(), msg)
            err_msg = ast.BinOp(assertmsg, ast.Add(), err_explanation)
            err_name = ast.Name("AssertionError", ast.Load())
            fmt = self.helper("_format_explanation", err_msg)
            exc = ast.Call(err_name, [fmt], [])
            raise_ = ast.Raise(exc, None)
            statements_fail = []
            statements_fail.extend(self.expl_stmts)
            statements_fail.append(raise_)

            # Passed
            fmt_pass = self.helper("_format_explanation", msg)
            orig = _get_assertion_exprs(self.source)[assert_.lineno]
            hook_call_pass = ast.Expr(
                self.helper(
                    "_call_assertion_pass",
                    ast.Constant(assert_.lineno),
                    ast.Constant(orig),
                    fmt_pass,
                )
            )
            # If any hooks implement assert_pass hook
            hook_impl_test = ast.If(
                self.helper("_check_if_assertion_pass_impl"),
                [*self.expl_stmts, hook_call_pass],
                [],
            )
            statements_pass: list[ast.stmt] = [hook_impl_test]

            # Test for assertion condition
            main_test = ast.If(negation, statements_fail, statements_pass)
            self.statements.append(main_test)
            if self.format_variables:
                variables: list[ast.expr] = [
                    ast.Name(name, ast.Store()) for name in self.format_variables
                ]
                clear_format = ast.Assign(variables, ast.Constant(None))
                self.statements.append(clear_format)

        else:  # Original assertion rewriting
            # Create failure message.
            body = self.expl_stmts
            self.statements.append(ast.If(negation, body, []))
            if assert_.msg:
                assertmsg = self.helper("_format_assertmsg", assert_.msg)
                explanation = "\n>assert " + explanation
            else:
                assertmsg = ast.Constant("")
                explanation = "assert " + explanation
            template = ast.BinOp(assertmsg, ast.Add(), ast.Constant(explanation))
            msg = self.pop_format_context(template)
            fmt = self.helper("_format_explanation", msg)
            err_name = ast.Name("AssertionError", ast.Load())
            exc = ast.Call(err_name, [fmt], [])
            raise_ = ast.Raise(exc, None)

            body.append(raise_)

        # Clear temporary variables by setting them to None.
        if self.variables:
            variables = [ast.Name(name, ast.Store()) for name in self.variables]
            clear = ast.Assign(variables, ast.Constant(None))
            self.statements.append(clear)
        # Fix locations (line numbers/column offsets).
        for stmt in self.statements:
            for node in traverse_node(stmt):
                if getattr(node, "lineno", None) is None:
                    # apply the assertion location to all generated ast nodes without source location
                    # and preserve the location of existing nodes or generated nodes with an correct location.
                    ast.copy_location(node, assert_)
        return self.statements

    def visit_NamedExpr(self, name: ast.NamedExpr) -> tuple[ast.NamedExpr, str]:
        # This method handles the 'walrus operator' repr of the target
        # name if it's a local variable or _should_repr_global_name()
        # thinks it's acceptable.
        locs = ast.Call(self.builtin("locals"), [], [])
        target_id = name.target.id
        inlocs = ast.Compare(ast.Constant(target_id), [ast.In()], [locs])
        dorepr = self.helper("_should_repr_global_name", name)
        test = ast.BoolOp(ast.Or(), [inlocs, dorepr])
        expr = ast.IfExp(test, self.display(name), ast.Constant(target_id))
        return name, self.explanation_param(expr)

    def visit_Name(self, name: ast.Name) -> tuple[ast.Name, str]:
        # Display the repr of the name if it's a local variable or
        # _should_repr_global_name() thinks it's acceptable.
        locs = ast.Call(self.builtin("locals"), [], [])
        inlocs = ast.Compare(ast.Constant(name.id), [ast.In()], [locs])
        dorepr = self.helper("_should_repr_global_name", name)
        test = ast.BoolOp(ast.Or(), [inlocs, dorepr])
        expr = ast.IfExp(test, self.display(name), ast.Constant(name.id))
        return name, self.explanation_param(expr)

    def visit_BoolOp(self, boolop: ast.BoolOp) -> tuple[ast.Name, str]:
        res_var = self.variable()
        expl_list = self.assign(ast.List([], ast.Load()))
        app = ast.Attribute(expl_list, "append", ast.Load())
        is_or = int(isinstance(boolop.op, ast.Or))
        body = save = self.statements
        fail_save = self.expl_stmts
        levels = len(boolop.values) - 1
        self.push_format_context()
        # Process each operand, short-circuiting if needed.
        for i, v in enumerate(boolop.values):
            if i:
                fail_inner: list[ast.stmt] = []
                # cond is set in a prior loop iteration below
                self.expl_stmts.append(ast.If(cond, fail_inner, []))  # noqa: F821
                self.expl_stmts = fail_inner
                match v:
                    # Check if the left operand is an ast.NamedExpr and the value has already been visited
                    case ast.Compare(
                        left=ast.NamedExpr(target=ast.Name(id=target_id))
                    ) if target_id in [
                        e.id for e in boolop.values[:i] if hasattr(e, "id")
                    ]:
                        pytest_temp = self.variable()
                        self.variables_overwrite[self.scope][target_id] = v.left  # type:ignore[assignment]
                        # mypy's false positive, we're checking that the 'target' attribute exists.
                        v.left.target.id = pytest_temp  # type:ignore[attr-defined]
            self.push_format_context()
            res, expl = self.visit(v)
            body.append(ast.Assign([ast.Name(res_var, ast.Store())], res))
            expl_format = self.pop_format_context(ast.Constant(expl))
            call = ast.Call(app, [expl_format], [])
            self.expl_stmts.append(ast.Expr(call))
            if i < levels:
                cond: ast.expr = res
                if is_or:
                    cond = ast.UnaryOp(ast.Not(), cond)
                inner: list[ast.stmt] = []
                self.statements.append(ast.If(cond, inner, []))
                self.statements = body = inner
        self.statements = save
        self.expl_stmts = fail_save
        expl_template = self.helper("_format_boolop", expl_list, ast.Constant(is_or))
        expl = self.pop_format_context(expl_template)
        return ast.Name(res_var, ast.Load()), self.explanation_param(expl)

    def visit_UnaryOp(self, unary: ast.UnaryOp) -> tuple[ast.Name, str]:
        pattern = UNARY_MAP[unary.op.__class__]
        operand_res, operand_expl = self.visit(unary.operand)
        res = self.assign(ast.copy_location(ast.UnaryOp(unary.op, operand_res), unary))
        return res, pattern % (operand_expl,)

    def visit_BinOp(self, binop: ast.BinOp) -> tuple[ast.Name, str]:
        symbol = BINOP_MAP[binop.op.__class__]
        left_expr, left_expl = self.visit(binop.left)
        right_expr, right_expl = self.visit(binop.right)
        explanation = f"({left_expl} {symbol} {right_expl})"
        res = self.assign(
            ast.copy_location(ast.BinOp(left_expr, binop.op, right_expr), binop)
        )
        return res, explanation

    def visit_Call(self, call: ast.Call) -> tuple[ast.Name, str]:
        new_func, func_expl = self.visit(call.func)
        arg_expls = []
        new_args = []
        new_kwargs = []
        for arg in call.args:
            if isinstance(arg, ast.Name) and arg.id in self.variables_overwrite.get(
                self.scope, {}
            ):
                arg = self.variables_overwrite[self.scope][arg.id]  # type:ignore[assignment]
            res, expl = self.visit(arg)
            arg_expls.append(expl)
            new_args.append(res)
        for keyword in call.keywords:
            match keyword.value:
                case ast.Name(id=id) if id in self.variables_overwrite.get(
                    self.scope, {}
                ):
                    keyword.value = self.variables_overwrite[self.scope][id]  # type:ignore[assignment]
            res, expl = self.visit(keyword.value)
            new_kwargs.append(ast.keyword(keyword.arg, res))
            if keyword.arg:
                arg_expls.append(keyword.arg + "=" + expl)
            else:  # **args have `arg` keywords with an .arg of None
                arg_expls.append("**" + expl)

        expl = "{}({})".format(func_expl, ", ".join(arg_expls))
        new_call = ast.copy_location(ast.Call(new_func, new_args, new_kwargs), call)
        res = self.assign(new_call)
        res_expl = self.explanation_param(self.display(res))
        outer_expl = f"{res_expl}\n{{{res_expl} = {expl}\n}}"
        return res, outer_expl

    def visit_Starred(self, starred: ast.Starred) -> tuple[ast.Starred, str]:
        # A Starred node can appear in a function call.
        res, expl = self.visit(starred.value)
        new_starred = ast.Starred(res, starred.ctx)
        return new_starred, "*" + expl

    def visit_Attribute(self, attr: ast.Attribute) -> tuple[ast.Name, str]:
        if not isinstance(attr.ctx, ast.Load):
            return self.generic_visit(attr)
        value, value_expl = self.visit(attr.value)
        res = self.assign(
            ast.copy_location(ast.Attribute(value, attr.attr, ast.Load()), attr)
        )
        res_expl = self.explanation_param(self.display(res))
        pat = "%s\n{%s = %s.%s\n}"
        expl = pat % (res_expl, res_expl, value_expl, attr.attr)
        return res, expl

    def visit_Compare(self, comp: ast.Compare) -> tuple[ast.expr, str]:
        self.push_format_context()
        # We first check if we have overwritten a variable in the previous assert
        match comp.left:
            case ast.Name(id=name_id) if name_id in self.variables_overwrite.get(
                self.scope, {}
            ):
                comp.left = self.variables_overwrite[self.scope][name_id]  # type: ignore[assignment]
            case ast.NamedExpr(target=ast.Name(id=target_id)):
                self.variables_overwrite[self.scope][target_id] = comp.left  # type: ignore[assignment]
        left_res, left_expl = self.visit(comp.left)
        if isinstance(comp.left, ast.Compare | ast.BoolOp):
            left_expl = f"({left_expl})"
        res_variables = [self.variable() for i in range(len(comp.ops))]
        load_names: list[ast.expr] = [ast.Name(v, ast.Load()) for v in res_variables]
        store_names = [ast.Name(v, ast.Store()) for v in res_variables]
        it = zip(range(len(comp.ops)), comp.ops, comp.comparators, strict=True)
        expls: list[ast.expr] = []
        syms: list[ast.expr] = []
        results = [left_res]
        for i, op, next_operand in it:
            match (next_operand, left_res):
                case (
                    ast.NamedExpr(target=ast.Name(id=target_id)),
                    ast.Name(id=name_id),
                ) if target_id == name_id:
                    next_operand.target.id = self.variable()
                    self.variables_overwrite[self.scope][name_id] = next_operand  # type: ignore[assignment]

            next_res, next_expl = self.visit(next_operand)
            if isinstance(next_operand, ast.Compare | ast.BoolOp):
                next_expl = f"({next_expl})"
            results.append(next_res)
            sym = BINOP_MAP[op.__class__]
            syms.append(ast.Constant(sym))
            expl = f"{left_expl} {sym} {next_expl}"
            expls.append(ast.Constant(expl))
            res_expr = ast.copy_location(ast.Compare(left_res, [op], [next_res]), comp)
            self.statements.append(ast.Assign([store_names[i]], res_expr))
            left_res, left_expl = next_res, next_expl
        # Use pytest.assertion.util._reprcompare if that's available.
        expl_call = self.helper(
            "_call_reprcompare",
            ast.Tuple(syms, ast.Load()),
            ast.Tuple(load_names, ast.Load()),
            ast.Tuple(expls, ast.Load()),
            ast.Tuple(results, ast.Load()),
        )
        if len(comp.ops) > 1:
            res: ast.expr = ast.BoolOp(ast.And(), load_names)
        else:
            res = load_names[0]

        return res, self.explanation_param(self.pop_format_context(expl_call))


def try_makedirs(cache_dir: Path) -> bool:
    """Attempt to create the given directory and sub-directories exist.

    Returns True if successful or if it already exists.
    """
    try:
        os.makedirs(cache_dir, exist_ok=True)
    except (FileNotFoundError, NotADirectoryError, FileExistsError):
        # One of the path components was not a directory:
        # - we're in a zip file
        # - it is a file
        return False
    except PermissionError:
        return False
    except OSError as e:
        # as of now, EROFS doesn't have an equivalent OSError-subclass
        #
        # squashfuse_ll returns ENOSYS "OSError: [Errno 38] Function not
        # implemented" for a read-only error
        if e.errno in {errno.EROFS, errno.ENOSYS}:
            return False
        raise
    return True


def get_cache_dir(file_path: Path) -> Path:
    """Return the cache directory to write .pyc files for the given .py file path."""
    if sys.pycache_prefix:
        # given:
        #   prefix = '/tmp/pycs'
        #   path = '/home/user/proj/test_app.py'
        # we want:
        #   '/tmp/pycs/home/user/proj'
        return Path(sys.pycache_prefix) / Path(*file_path.parts[1:-1])
    else:
        # classic pycache directory
        return file_path.parent / "__pycache__"
