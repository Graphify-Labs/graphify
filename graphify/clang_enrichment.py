"""Bounded compiler confirmation for unresolved C and C++ graph calls.

Clang is deliberately an edge verifier, not a second source of graph nodes. The
tree-sitter graph remains usable when Clang is missing or reports diagnostics;
only a uniquely matched caller, call site, declaration and existing graph target
may contribute a compiler-confirmed edge.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import shlex
from typing import Callable

from graphify.analyzer_runtime import AnalyzerProcessRequest, AnalyzerRuntime
from graphify.symbol_names import normalize_symbol_name


@dataclass(frozen=True)
class ProcessResult:
    """Normalized result returned by the injected compiler boundary."""

    returncode: int
    stdout: dict | str
    stderr: str


@dataclass(frozen=True)
class _Candidate:
    caller_id: str
    caller_name: str
    callee: str
    receiver_type: str
    source_file: str
    line: int


@dataclass(frozen=True)
class _Declaration:
    name: str
    owners: tuple[str, ...]
    source_file: str
    line: int


@dataclass(frozen=True)
class _Call:
    caller_decl: str
    target_decl: str
    callee: str
    source_file: str
    line: int


@dataclass(frozen=True)
class _Invocation:
    command: tuple[str, ...]
    cwd: Path
    from_compile_database: bool


_FUNCTION_KINDS = frozenset({
    "FunctionDecl", "CXXMethodDecl", "CXXConstructorDecl",
    "CXXDestructorDecl", "FunctionTemplateDecl", "CXXConversionDecl",
})
_OWNER_KINDS = frozenset({
    "NamespaceDecl", "CXXRecordDecl", "RecordDecl", "ClassTemplateDecl",
})
_TU_SUFFIXES = frozenset({".c", ".C", ".cc", ".cpp", ".cxx"})
_HEADER_SUFFIXES = frozenset({".h", ".hh", ".hpp", ".hxx"})
_INCLUDE_RE = re.compile(r'^[ \t]*#[ \t]*include[ \t]*[<"]([^>"]+)[>"]', re.MULTILINE)
_COMPILER_LAUNCHERS = frozenset({"ccache", "sccache", "distcc", "icecc"})
_COMPILER_EXECUTABLE_RE = re.compile(
    r"^(?:[a-z0-9_.+-]+-)?"
    r"(?:clang(?:\+\+|-cl)?|gcc|g\+\+|cc|c\+\+|cl|icx|icpx)"
    r"(?:-\d+(?:\.\d+)*)?(?:\.exe)?$",
    re.IGNORECASE,
)


def _line(value: object) -> int | None:
    match = re.fullmatch(r"L?(\d+)", str(value or "").strip())
    return int(match.group(1)) if match else None


def _display_byte_limit(value: int) -> str:
    if value % (1024 * 1024) == 0:
        return f"{value // (1024 * 1024)} MiB"
    if value % 1024 == 0:
        return f"{value // 1024} KiB"
    return f"{value} bytes"


def run_clang_command(
    command: tuple[str, ...],
    cwd: Path,
    timeout: float,
    *,
    max_stdout_bytes: int = 128 * 1024 * 1024,
) -> ProcessResult:
    """Run Clang without a shell and stop it when its JSON AST exceeds the cap."""

    completed = AnalyzerRuntime(cwd).run(AnalyzerProcessRequest(
        command=command,
        cwd=cwd,
        timeout_seconds=timeout,
        max_stdout_bytes=max_stdout_bytes,
        max_stderr_bytes=32 * 1024,
    ))
    if completed.timed_out:
        raise TimeoutError(f"clang exceeded {timeout:.0f}s")
    if completed.stdout_limit_exceeded or (
        completed.output_limit_exceeded and not completed.stderr_limit_exceeded
    ):
        limit = _display_byte_limit(max_stdout_bytes)
        return ProcessResult(
            completed.returncode,
            "",
            f"clang JSON AST exceeded {limit}",
        )
    raw_stdout = completed.stdout
    raw_stderr = completed.stderr.decode("utf-8", "replace")
    if completed.stderr_limit_exceeded:
        limit = _display_byte_limit(32 * 1024)
        raw_stderr = f"clang stderr exceeded {limit}; output truncated\n{raw_stderr}"
    if completed.cleanup_error:
        raw_stderr = (
            f"analyzer process-tree cleanup failed: {completed.cleanup_error}\n{raw_stderr}"
        )
    try:
        payload: dict | str = json.loads(raw_stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        payload = ""
    return ProcessResult(
        completed.returncode if not completed.cleanup_error else (completed.returncode or 1),
        payload,
        raw_stderr,
    )


def split_windows_commandline(command: str) -> list[str]:
    """Split a Windows command line using the CommandLineToArgvW rules.

    ``shlex`` implements POSIX quoting and can silently remove path
    backslashes. This small parser covers the quoting contract used by JSON
    compilation databases without invoking a shell or platform API.
    """

    arguments: list[str] = []
    index = 0
    while index < len(command):
        while index < len(command) and command[index] in " \t":
            index += 1
        if index >= len(command):
            break
        value: list[str] = []
        quoted = False
        while index < len(command):
            if command[index] in " \t" and not quoted:
                break
            backslashes = 0
            while index < len(command) and command[index] == "\\":
                backslashes += 1
                index += 1
            if index < len(command) and command[index] == '"':
                value.extend("\\" * (backslashes // 2))
                if backslashes % 2:
                    value.append('"')
                else:
                    quoted = not quoted
                index += 1
                continue
            value.extend("\\" * backslashes)
            if index < len(command):
                value.append(command[index])
                index += 1
        arguments.append("".join(value))
    return arguments


def _split_compile_command(command: str) -> list[str]:
    return split_windows_commandline(command) if os.name == "nt" else shlex.split(command)


class _ClangArgumentPolicy:
    """Reconstruct a parse-only argv from untrusted compilation metadata.

    A strict allowlist is intentionally smaller than Clang's driver surface.
    Unknown flags are omitted instead of forwarded because new driver options
    can acquire plugin, helper-process, output, or indirection behavior without
    Graphify changing. The deterministic AST remains the fallback when a
    dropped build flag prevents compiler confirmation.
    """

    _VALUE_OPTIONS = frozenset({
        "-D", "-U", "-I", "-F", "-isystem", "-iquote", "-idirafter",
        "-iframework", "-isysroot", "--sysroot", "-resource-dir", "-x",
        "-std", "-stdlib", "-target", "--target", "-arch", "-objc-isystem",
    })
    _JOINED_PREFIXES = (
        "-D", "-U", "-I", "-F", "-isystem", "-iquote", "-idirafter",
        "-iframework", "-isysroot", "--sysroot=", "-resource-dir=",
        "-std=", "--std=", "-stdlib=", "-target=", "--target=",
    )
    _EXACT_OPTIONS = frozenset({
        "-ansi", "-ffreestanding", "-fno-builtin", "-fblocks",
        "-fcoroutines-ts", "-fdeclspec", "-fexceptions", "-fno-exceptions",
        "-fms-compatibility", "-fms-extensions", "-fdelayed-template-parsing",
        "-fno-delayed-template-parsing", "-foperator-names",
        "-fno-operator-names", "-frtti", "-fno-rtti", "-fshort-wchar",
        "-fchar8_t", "-fno-char8_t", "-pthread", "-nostdinc", "-nostdinc++",
        "/permissive-", "/TP", "/TC", "/EHsc", "/EHs", "/EHa",
    })
    _MSVC_PREFIXES = ("/D", "/U", "/I", "/std:", "/Zc:")

    @classmethod
    def filter(cls, arguments: list[str]) -> tuple[str, ...]:
        logical = [cls._logical(argument) for argument in arguments]
        safe: list[str] = []
        index = cls._first_driver_argument(arguments)
        while index < len(arguments):
            argument, original = logical[index]
            if argument in cls._VALUE_OPTIONS:
                if index + 1 < len(arguments):
                    value, original_value = logical[index + 1]
                    # An option-looking value is ambiguous and could otherwise
                    # re-enter Clang's option parser with a different arity.
                    if value and not value.startswith(("-", "/clang:")):
                        safe.extend((original, original_value))
                index += 2
                continue
            if cls._is_joined_safe(argument) or argument in cls._EXACT_OPTIONS:
                safe.append(original)
            index += 1
        return tuple(safe)

    @staticmethod
    def _logical(argument: str) -> tuple[str, str]:
        if argument.lower().startswith("/clang:"):
            return argument[7:], argument
        return argument, argument

    @classmethod
    def _is_joined_safe(cls, argument: str) -> bool:
        if any(
            argument.startswith(prefix) and argument != prefix
            for prefix in cls._JOINED_PREFIXES
        ):
            return True
        return any(
            argument.startswith(prefix) and len(argument) > len(prefix)
            for prefix in cls._MSVC_PREFIXES
        )

    @staticmethod
    def _first_driver_argument(arguments: list[str]) -> int:
        if not arguments:
            return 0
        if Path(arguments[0]).name.lower() not in _COMPILER_LAUNCHERS:
            return 1
        for index, candidate in enumerate(arguments[1:], 1):
            name = candidate.replace("\\", "/").rsplit("/", 1)[-1]
            if _COMPILER_EXECUTABLE_RE.fullmatch(name):
                return index + 1
        return len(arguments)


class ClangSemanticEnricher:
    """Confirm unresolved graph calls with Clang without replacing AST facts."""

    def __init__(
        self,
        project_root: Path | str,
        *,
        executable: str,
        runner: Callable[[tuple[str, ...], Path, float], ProcessResult],
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.executable = executable
        self.runner = runner

    def enrich(self, extraction: dict) -> dict:
        """Add only call edges that Clang resolves to grounded graph nodes."""

        nodes = [dict(node) for node in extraction.get("nodes", []) if isinstance(node, dict)]
        edges = [dict(edge) for edge in extraction.get("edges", []) if isinstance(edge, dict)]
        candidates = self._candidates(nodes)
        report = {
            "candidate_calls": len(candidates),
            "translation_units": 0,
            "analyzer_runs": 0,
            "parsed_translation_units": 0,
            "resolved_calls": 0,
            "upgraded_calls": 0,
            "compile_database_translation_units": 0,
            "diagnostics": [],
        }
        if not candidates:
            return self._result(extraction, nodes, edges, report)

        targets = self._target_index(nodes, edges)
        existing = {
            (str(edge.get("source", "")), str(edge.get("target", "")), str(edge.get("relation", ""))): edge
            for edge in edges
        }
        by_file: dict[str, list[_Candidate]] = defaultdict(list)
        for candidate in candidates:
            by_file[candidate.source_file].append(candidate)
        header_files = tuple(sorted({
            str(node.get("source_file"))
            for node in nodes
            if Path(str(node.get("source_file") or "")).suffix in _HEADER_SUFFIXES
        }))

        for source_file, file_candidates in sorted(by_file.items()):
            source_path = self._inside_root(source_file)
            if source_path is None or source_path.suffix not in _TU_SUFFIXES or not source_path.is_file():
                report["diagnostics"].append(f"{source_file}: no eligible translation unit")
                continue
            report["translation_units"] += 1
            invocation = self._invocation(source_path, header_files)
            if invocation.from_compile_database:
                report["compile_database_translation_units"] += 1
            try:
                completed = self.runner(
                    invocation.command, invocation.cwd, 30.0,
                )
                report["analyzer_runs"] += 1
            except (OSError, TimeoutError) as exc:
                report["diagnostics"].append(f"{source_file}: {type(exc).__name__}: {exc}")
                continue
            if completed.stderr:
                report["diagnostics"].append(f"{source_file}: {completed.stderr.strip()[:500]}")
            # Clang can emit a partial JSON AST while returning an error. Such
            # output is diagnostic evidence, not confirmation strong enough to
            # upgrade a graph edge to EXTRACTED confidence.
            if completed.returncode != 0:
                report["diagnostics"].append(
                    f"{source_file}: clang exited with status {completed.returncode}",
                )
                continue
            if not isinstance(completed.stdout, dict):
                report["diagnostics"].append(f"{source_file}: clang returned no JSON AST")
                continue
            report["parsed_translation_units"] += 1
            declarations, calls = self._read_ast(completed.stdout, source_file)
            for candidate in file_candidates:
                target_id = self._confirmed_target(candidate, declarations, calls, targets)
                edge_key = (candidate.caller_id, target_id or "", "calls")
                if target_id is None:
                    continue
                confirmed = {
                    "source": candidate.caller_id,
                    "target": target_id,
                    "relation": "calls",
                    "context": "compiler_resolved_call",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": candidate.source_file,
                    "source_location": f"L{candidate.line}",
                    "weight": 1.0,
                    "semantic_provider": "clang",
                }
                current = existing.get(edge_key)
                if current is not None:
                    if current.get("semantic_provider") == "clang":
                        continue
                    previous_context = current.get("context")
                    current.update(confirmed)
                    if previous_context and previous_context != confirmed["context"]:
                        current["previous_context"] = previous_context
                    current.pop("_cross_repo_call", None)
                    current.pop("_partition_call", None)
                    report["upgraded_calls"] += 1
                    continue
                edges.append(confirmed)
                existing[edge_key] = confirmed
                report["resolved_calls"] += 1
        return self._result(extraction, nodes, edges, report)

    def enrich_node_link(self, graph: dict) -> dict:
        """Enrich a persisted NetworkX node-link graph without changing its shape."""

        extraction = dict(graph)
        extraction["edges"] = [
            dict(edge) for edge in graph.get("links", []) if isinstance(edge, dict)
        ]
        enriched = self.enrich(extraction)
        result = dict(graph)
        result["nodes"] = enriched["nodes"]
        result["links"] = enriched["edges"]
        result["semantic_enrichment"] = enriched["semantic_enrichment"]
        return result

    def _inside_root(self, source_file: str) -> Path | None:
        path = (self.project_root / source_file).resolve()
        try:
            path.relative_to(self.project_root)
        except ValueError:
            return None
        return path

    def _fallback_command(
        self,
        source_path: Path,
        include_roots: tuple[Path, ...] = (),
    ) -> tuple[str, ...]:
        """Build a side-effect-free fallback command for one candidate TU."""

        language = "c" if source_path.suffix == ".c" else "c++"
        standard = "c11" if language == "c" else "c++17"
        return (
            self.executable, "-x", language, f"-std={standard}",
            *(f"-I{root}" for root in include_roots),
            "-fsyntax-only", "-ferror-limit=0", "-Xclang", "-ast-dump=json",
            str(source_path),
        )

    def _invocation(
        self,
        source_path: Path,
        header_files: tuple[str, ...],
    ) -> _Invocation:
        compile_entry = self._compile_command_for(source_path)
        if compile_entry is None:
            roots = self._inferred_include_roots(source_path, header_files)
            return _Invocation(self._fallback_command(source_path, roots), self.project_root, False)
        arguments, cwd = compile_entry
        command = (
            self.executable,
            *self._safe_compile_arguments(arguments, source_path, cwd),
            "-fsyntax-only",
            "-ferror-limit=0",
            "-Xclang",
            "-ast-dump=json",
            str(source_path),
        )
        return _Invocation(command, cwd, True)

    def _inferred_include_roots(
        self,
        source_path: Path,
        header_files: tuple[str, ...],
    ) -> tuple[Path, ...]:
        """Infer only roots where an include spelling has one admitted provider."""

        try:
            if source_path.stat().st_size > 4 * 1024 * 1024:
                return (self.project_root, source_path.parent)
            text = source_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return (self.project_root, source_path.parent)

        roots = {self.project_root, source_path.parent}
        for spelling in sorted(set(_INCLUDE_RE.findall(text))):
            include_path = PurePosixPath(spelling)
            if include_path.is_absolute() or ".." in include_path.parts or "\\" in spelling:
                continue
            providers: list[tuple[str, ...]] = []
            for header in header_files:
                parts = PurePosixPath(header).parts
                if len(parts) >= len(include_path.parts) and parts[-len(include_path.parts):] == include_path.parts:
                    providers.append(parts)
            if len(providers) != 1:
                continue
            prefix = providers[0][:-len(include_path.parts)]
            root = self.project_root.joinpath(*prefix).resolve()
            try:
                root.relative_to(self.project_root)
            except ValueError:
                continue
            if root.is_dir():
                roots.add(root)
        return tuple(sorted(roots, key=lambda path: path.as_posix()))

    def _compile_command_for(self, source_path: Path) -> tuple[list[str], Path] | None:
        """Read one exact TU command without executing the build-system command."""

        for relative in ("compile_commands.json", "build/compile_commands.json", "out/compile_commands.json"):
            database = self.project_root / relative
            if not database.is_file():
                continue
            try:
                if database.stat().st_size > 16 * 1024 * 1024:
                    continue
                payload = json.loads(database.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if not isinstance(payload, list):
                continue
            for entry in payload:
                if not isinstance(entry, dict):
                    continue
                raw_directory = Path(str(entry.get("directory") or self.project_root))
                # Relative database entries are portable build metadata. They
                # are relative to the database file, never Graphify's process
                # working directory, which may belong to another repository.
                directory = (
                    raw_directory
                    if raw_directory.is_absolute()
                    else database.parent / raw_directory
                ).resolve()
                try:
                    directory.relative_to(self.project_root)
                except ValueError:
                    continue
                listed = Path(str(entry.get("file") or ""))
                listed = listed if listed.is_absolute() else directory / listed
                try:
                    if listed.resolve() != source_path.resolve():
                        continue
                except OSError:
                    continue
                raw = entry.get("arguments")
                if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
                    return list(raw), directory
                command = entry.get("command")
                if isinstance(command, str):
                    try:
                        return _split_compile_command(command), directory
                    except ValueError:
                        continue
        return None

    @staticmethod
    def _safe_compile_arguments(arguments: list[str], source_path: Path, cwd: Path) -> tuple[str, ...]:
        """Return only explicitly admitted parse-affecting driver options."""

        # ``source_path`` and ``cwd`` remain in the signature for compatibility
        # with injected tests and callers; source inputs are always reconstructed
        # by ``_invocation`` rather than trusted from the compile database.
        del source_path, cwd
        return _ClangArgumentPolicy.filter(arguments)

    @staticmethod
    def _candidates(nodes: list[dict]) -> list[_Candidate]:
        candidates: list[_Candidate] = []
        for node in nodes:
            metadata = node.get("metadata")
            parked = metadata.get("unresolved_calls") if isinstance(metadata, dict) else None
            if not isinstance(parked, list):
                continue
            source_file = str(node.get("source_file") or "")
            for entry in parked:
                if not isinstance(entry, dict) or entry.get("lang") not in {"c", "cpp"}:
                    continue
                line = _line(entry.get("line"))
                callee = normalize_symbol_name(entry.get("callee"))
                receiver = str(entry.get("receiver_type") or "").strip()
                caller_id = str(node.get("id") or "")
                caller_name = normalize_symbol_name(node.get("label"), graph_label=True)
                if source_file and line and callee and receiver and caller_id and caller_name:
                    candidates.append(_Candidate(
                        caller_id, caller_name, callee, receiver, source_file, line,
                    ))
        return candidates

    @staticmethod
    def _target_index(
        nodes: list[dict], edges: list[dict],
    ) -> dict[tuple[str, str], list[tuple[str, str, int]]]:
        node_by_id = {str(node.get("id")): node for node in nodes if node.get("id")}
        index: dict[tuple[str, str], list[tuple[str, str, int]]] = defaultdict(list)
        for edge in edges:
            if edge.get("relation") not in {"method", "defines"}:
                continue
            owner = node_by_id.get(str(edge.get("source")))
            member = node_by_id.get(str(edge.get("target")))
            if not owner or not member or not owner.get("source_file") or not member.get("source_file"):
                continue
            member_line = _line(member.get("source_location"))
            if member_line is None:
                continue
            key = (
                normalize_symbol_name(owner.get("label"), graph_label=True),
                normalize_symbol_name(member.get("label"), graph_label=True),
            )
            index[key].append((str(member["id"]), str(member["source_file"]), member_line))
        return index

    def _read_ast(
        self, ast: dict, default_file: str,
    ) -> tuple[dict[str, _Declaration], list[_Call]]:
        declarations: dict[str, _Declaration] = {}
        pending_calls: list[tuple[str, dict, str, int]] = []

        def visit(
            node: object,
            owners: tuple[str, ...],
            caller: str | None,
            inherited_file: str,
            inherited_line: int,
        ) -> None:
            if not isinstance(node, dict):
                return
            kind = str(node.get("kind") or "")
            name = str(node.get("name") or "")
            source_file, line = self._node_location(node, inherited_file, inherited_line)
            next_owners = owners
            if kind in _OWNER_KINDS and name and not node.get("isImplicit"):
                next_owners = (*owners, name)
            next_caller = caller
            node_id = str(node.get("id") or "")
            if kind in _FUNCTION_KINDS and node_id and name:
                declarations[node_id] = _Declaration(name, owners, source_file, line)
                next_caller = node_id
            if kind in {"CallExpr", "CXXMemberCallExpr", "CXXOperatorCallExpr"} and caller:
                pending_calls.append((caller, node, source_file, line))
            for child in node.get("inner", []) or []:
                visit(child, next_owners, next_caller, source_file, line)

        visit(ast, (), None, default_file, 0)
        calls: list[_Call] = []
        for caller, call_node, source_file, line in pending_calls:
            member = self._referenced_member(call_node)
            if member is not None:
                calls.append(_Call(caller, member[0], member[1], source_file, line))
        return declarations, calls

    def _node_location(
        self,
        node: dict,
        inherited_file: str,
        inherited_line: int,
    ) -> tuple[str, int]:
        location = node.get("loc")
        if not isinstance(location, dict):
            node_range = node.get("range")
            location = node_range.get("begin") if isinstance(node_range, dict) else {}
        if not isinstance(location, dict):
            location = {}
        for nested in ("expansionLoc", "spellingLoc"):
            if isinstance(location.get(nested), dict):
                location = location[nested]
                break
        explicit_file = location.get("file")
        if explicit_file:
            # An explicit path carries provenance. If it escapes the project,
            # keep it unmatched instead of relabeling it as the parent file.
            source_file = self._relative_file(str(explicit_file)) or ""
        else:
            source_file = inherited_file
        # Clang's JSON AST elides a child's file/line when it is unchanged from
        # the enclosing declaration. Retaining both values is required for an
        # exact provenance match; treating an omitted line as zero loses valid
        # same-line declarations such as `struct X { void f(); };`.
        return source_file, int(location.get("line") or inherited_line)

    def _relative_file(self, raw_file: str) -> str | None:
        path = Path(raw_file)
        if not path.is_absolute():
            path = self.project_root / path
        try:
            return path.resolve().relative_to(self.project_root).as_posix()
        except (OSError, ValueError):
            return None

    @staticmethod
    def _referenced_member(node: dict) -> tuple[str, str] | None:
        children = node.get("inner", []) or []
        if not isinstance(children, list) or not children:
            return None
        # In Clang's call-expression AST, inner[0] is the callee expression;
        # later children are arguments and may contain unrelated member calls.
        stack: list[object] = [children[0]]
        while stack:
            item = stack.pop()
            if not isinstance(item, dict):
                continue
            decl_id = item.get("referencedMemberDecl")
            if decl_id and item.get("name"):
                return str(decl_id), normalize_symbol_name(item.get("name"))
            referenced = item.get("referencedDecl")
            if isinstance(referenced, dict) and referenced.get("id") and referenced.get("name"):
                return str(referenced["id"]), normalize_symbol_name(referenced["name"])
            stack.extend(item.get("inner", []) or [])
        return None

    @staticmethod
    def _confirmed_target(
        candidate: _Candidate,
        declarations: dict[str, _Declaration],
        calls: list[_Call],
        targets: dict[tuple[str, str], list[tuple[str, str, int]]],
    ) -> str | None:
        receiver = candidate.receiver_type.split("::")[-1]
        graph_targets = targets.get((receiver, candidate.callee), [])
        if len(graph_targets) != 1:
            return None
        target_id, target_file, target_line = graph_targets[0]
        matches = 0
        for call in calls:
            caller = declarations.get(call.caller_decl)
            target = declarations.get(call.target_decl)
            if caller is None or target is None:
                continue
            owner_matches = bool(target.owners) and target.owners[-1] == receiver
            if (
                call.source_file == candidate.source_file
                and call.line == candidate.line
                and call.callee == candidate.callee
                and caller.name == candidate.caller_name
                and target.name == candidate.callee
                and owner_matches
                and target.source_file == target_file
                and target.line == target_line
            ):
                matches += 1
        return target_id if matches == 1 else None

    @staticmethod
    def _result(extraction: dict, nodes: list[dict], edges: list[dict], report: dict) -> dict:
        result = dict(extraction)
        result["nodes"] = nodes
        result["edges"] = edges
        existing = extraction.get("semantic_enrichment")
        enrichment = dict(existing) if isinstance(existing, dict) else {}
        enrichment["clang"] = report
        result["semantic_enrichment"] = enrichment
        return result
