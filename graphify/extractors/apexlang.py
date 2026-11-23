"""Oracle APEX 26.1+ APEXlang (.apx) extractor."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import sys
import threading
import unicodedata

from graphify.extractors.base import _read_source_text


ARCHITECTURAL_TYPES = {
    "app": "app",
    "page": "page",
    "region": "region",
    "process": "process",
    "dynamicAction": "dynamic_action",
    "list": "list",
    "lov": "lov",
    "authentication": "authentication",
    "authorization": "authorization",
    "appProcess": "app_process",
    "buildOption": "build_option",
}

DISPLAY_TYPES = {
    "app": "App",
    "page": "Page",
    "region": "Region",
    "process": "Process",
    "dynamic_action": "Dynamic Action",
    "list": "List",
    "lov": "LOV",
    "authentication": "Authentication",
    "authorization": "Authorization",
    "app_process": "Application Process",
    "build_option": "Build Option",
}

# Graphify's node type for anchors shared by many files. Nodes of this type are
# exempt from cross-file id salting and merge by id.
SHARED_ANCHOR_TYPE = "module"
DECLARATION_RE = re.compile(
    r'^\s*([A-Za-z][A-Za-z0-9-]*)'
    r'(?:\s+("(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|[^\s(){}"\'][^\s(){}]*))?\s*\(\s*$'
)
NAME_RE = re.compile(r'^\s*name\s*:\s*(.*?)\s*$')
CLOSE_COMPONENT_RE = re.compile(r'^\s*\)\s*$')
PROPERTY_RE = re.compile(r'^\s*([A-Za-z][A-Za-z0-9]*)\s*:\s*(.*?)\s*$')
REFERENCE_RE = re.compile(r'^\s*([A-Za-z][A-Za-z0-9]*)\s*:\s*@([^\s\]}]+)')
PAGE_TARGET_RE = re.compile(r'\bpage\s*:\s*(\d+)\b', re.IGNORECASE)
APEX_URL_PAGE_RE = re.compile(r'f\?p=([^:\s]*):(\d+):', re.IGNORECASE)
APPLICATION_PROPERTY_RE = re.compile(r'^\s*application\s*:\s*(\d+)\s*$', re.IGNORECASE)
SQL_NAME_PART = r'(?:"[^"]+"|#[A-Za-z0-9_]+#|[A-Za-z][A-Za-z0-9_$#]*)'
SQL_IDENTIFIER = rf'{SQL_NAME_PART}(?:\s*\.\s*{SQL_NAME_PART})*'
SUBSTITUTION_PART_RE = re.compile(r'#[^#]*#')
FROM_START_RE = re.compile(r'\b(?:FROM|JOIN)\b\s+', re.IGNORECASE)
FROM_STOP_RE = re.compile(
    r'\b(?:WHERE|GROUP|ORDER|HAVING|CONNECT|START|UNION|INTERSECT|MINUS|MODEL'
    r'|FETCH|OFFSET|FOR|JOIN|INNER|LEFT|RIGHT|FULL|CROSS|NATURAL|ON|USING|SET'
    r'|RETURNING|INTO|VALUES|SELECT|WITH|AS)\b',
    re.IGNORECASE,
)
FROM_ITEM_RE = re.compile(rf'^\s*({SQL_IDENTIFIER})')
FROM_KEYWORDS = {"table", "lateral", "xmltable", "json_table", "only", "the"}
CTE_RE = re.compile(
    rf'\b({SQL_IDENTIFIER})\s*(?:\([^()]*\))?\s+AS\s*'
    rf'(?:NOT\s+MATERIALIZED\s+|MATERIALIZED\s+)?\(\s*(?:WITH|SELECT)\b',
    re.IGNORECASE,
)
WRITE_RE = re.compile(
    rf'\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|MERGE\s+INTO)\s+({SQL_IDENTIFIER})',
    re.IGNORECASE,
)
PAREN_CALL_RE = re.compile(
    rf'(?<![\w$#".:])({SQL_IDENTIFIER}\s*\.\s*(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_$#]*))\s*\(',
    re.IGNORECASE,
)
STATEMENT_CALL_RE = re.compile(
    rf'^\s*({SQL_IDENTIFIER}\s*\.\s*(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_$#]*))\s*;',
    re.IGNORECASE | re.MULTILINE,
)

COMPONENT_REFERENCE_PROPERTIES = {
    "listofvalues": "lov",
    "namedlov": "lov",
    "lov": "lov",
    "buildoption": "build_option",
    "authentication": "authentication",
    "authenticationscheme": "authentication",
    "list": "list",
}

IGNORED_SQL_OBJECTS = {
    "dual",
}

SQL_PROPERTY_NAMES = {
    "sqlquery",
    "plsqlcode",
    "plsqlexpression",
    "plsqlfunctionbody",
    "functionbody",
    "whereclause",
}
TABLE_PROPERTY_NAMES = {"tablename"}
FUNCTION_PROPERTY_NAMES = {"authfunctionname"}
QUALIFIED_MEMBER_RE = re.compile(
    r"(?<![\w$#.:])([A-Za-z_][\w$#]*)\s*\.\s*([A-Za-z_][\w$#]*)"
)


class ApexlangParseError(ValueError):
    """Raised when an APEXlang file is structurally incomplete."""


@dataclass
class Frame:
    kind: str
    identifier: str
    line: int
    node_id: str | None
    architectural_owner: str | None


def make_id(*parts: object) -> str:
    """Return a stable Graphify-compatible identifier."""
    raw = unicodedata.normalize("NFC", "_".join(str(part) for part in parts if str(part)))
    raw = unicodedata.normalize("NFC", raw.casefold())
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", raw)
    normalized = re.sub(r"_+", "_", normalized).strip("_").lower()
    if not raw.isascii():
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        return f"{normalized}_u{digest}"
    return normalized


class DatabaseMirror:
    """Resolve references to objects mirrored under ``database/<SCHEMA>/``."""

    TABLE_FOLDERS = ("tables", "views")
    INDEXED_FOLDERS = (*TABLE_FOLDERS, "packages", "synonyms")
    SYNONYM_TARGET_RE = re.compile(
        r'\bFOR\s+(?:"?([A-Za-z0-9_$#]+)"?\s*\.\s*)?"?([A-Za-z0-9_$#]+)"?\s*;',
        re.IGNORECASE,
    )
    _INDEX_CACHE: dict[str, tuple[tuple[tuple[str, int, int, int], ...], dict[str, dict[str, dict]]]] = {}
    _INDEX_LOCK = threading.Lock()

    def __init__(self, root: Path | None = None, schema: str | None = None) -> None:
        self.root = root
        self.schema = schema

    @classmethod
    def clear_cache(cls) -> None:
        with cls._INDEX_LOCK:
            cls._INDEX_CACHE.clear()

    @classmethod
    def _mirror_stamp(cls, root: Path) -> tuple[tuple[str, int, int, int], ...]:
        """Fingerprint mirrored .sql files so newly added, edited, or deleted objects invalidate the cache."""
        entries: list[tuple[str, int, int, int]] = []
        try:
            schema_dirs = sorted(path for path in (root / "database").iterdir() if path.is_dir())
        except OSError:
            return ()
        for schema_dir in schema_dirs:
            for folder in cls.INDEXED_FOLDERS:
                for file in cls._sql_files(schema_dir / folder):
                    try:
                        st = file.stat()
                    except OSError:
                        continue
                    entries.append(
                        (file.relative_to(root).as_posix(), st.st_ino, st.st_mtime_ns, st.st_size)
                    )
        return tuple(entries)

    @classmethod
    def for_application_file(cls, source: Path) -> DatabaseMirror:
        """Locate the mirror from ``<root>/apps/<schema>/<app id>/...``."""
        parts = source.parts
        for index in range(len(parts) - 3, -1, -1):
            if parts[index] == "apps" and parts[index + 2].isdigit():
                return cls(Path(*parts[:index]) if index else Path(), parts[index + 1])
        return cls()

    @staticmethod
    def _sql_files(directory: Path) -> list[Path]:
        try:
            return sorted(directory.glob("*.sql"))
        except OSError:
            return []

    @classmethod
    def _scan_root(cls, root: Path) -> dict[str, dict[str, dict]]:
        """Index tables, packages and synonyms of every mirrored schema."""
        index: dict[str, dict[str, dict]] = {}
        try:
            schema_dirs = sorted(path for path in (root / "database").iterdir() if path.is_dir())
        except OSError:
            return index
        for schema_dir in schema_dirs:
            entry: dict[str, dict] = {"tables": {}, "packages": {}, "synonyms": {}}
            for folder in cls.TABLE_FOLDERS:
                for file in cls._sql_files(schema_dir / folder):
                    file_id = make_id(file.relative_to(root).with_suffix("").as_posix())
                    entry["tables"].setdefault(
                        file.stem.upper(), make_id(file_id, schema_dir.name, file.stem)
                    )
            for file in cls._sql_files(schema_dir / "packages"):
                name = file.stem.upper()
                for suffix in ("_SPEC", "_BODY"):
                    if name.endswith(suffix):
                        name = name[: -len(suffix)]
                        break
                file_id = make_id(file.relative_to(root).with_suffix("").as_posix())
                if file.stem.upper().endswith("_SPEC") or name not in entry["packages"]:
                    entry["packages"][name] = file_id
            for file in cls._sql_files(schema_dir / "synonyms"):
                try:
                    text = file.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                match = cls.SYNONYM_TARGET_RE.search(text)
                if match:
                    target_schema = (match.group(1) or schema_dir.name).upper()
                    entry["synonyms"][file.stem.upper()] = (target_schema, match.group(2).upper())
            index[schema_dir.name.upper()] = entry
        return index

    def _index(self) -> dict[str, dict[str, dict]]:
        if self.root is None:
            return {}
        key = str(self.root.resolve())
        stamp = self._mirror_stamp(self.root)
        with self._INDEX_LOCK:
            cached = self._INDEX_CACHE.get(key)
            if cached is None or cached[0] != stamp:
                cached = (stamp, self._scan_root(self.root))
                self._INDEX_CACHE[key] = cached
            return cached[1]

    def _resolve(self, schema: str, name: str, kind: str) -> str | None:
        index = self._index()
        entry = index.get(schema.upper())
        if entry is None:
            return None
        found = entry[kind].get(name)
        if found:
            return found
        target = entry["synonyms"].get(name)
        if target is None:
            return None
        target_entry = index.get(target[0])
        return target_entry[kind].get(target[1]) if target_entry else None

    def table(self, label: str) -> str | None:
        parts = label.upper().split(".")
        if len(parts) == 1:
            schema, name = (self.schema or ""), parts[0]
        elif len(parts) == 2:
            schema, name = parts
        else:
            return None
        return self._resolve(schema, name, "tables")

    def package(self, label: str) -> str | None:
        parts = label.upper().split(".")
        if len(parts) == 3:
            schema, name = parts[0], parts[1]
        elif len(parts) == 2:
            schema, name = (self.schema or ""), parts[0]
        else:
            return None
        return self._resolve(schema, name, "packages")


def _clean_identifier(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


def _application_id(path: Path, text: str) -> str:
    parts = path.parts
    for index, part in enumerate(parts):
        if part == "apps" and index + 2 < len(parts) and parts[index + 2].isdigit():
            return parts[index + 2]
    match = re.search(r"(?m)^\s*app\s+(\d+)\s*\(\s*$", text)
    return match.group(1) if match else "unknown"


def _source_location(line: int) -> str:
    return f"L{line}"


def _node(
    node_id: str,
    label: str,
    source_path: str,
    line: int | None,
    **metadata: object,
) -> dict:
    result = {
        "id": node_id,
        "label": label,
        "file_type": "code",
        "source_file": source_path,
        "source_location": _source_location(line) if line is not None else None,
    }
    if metadata:
        result["metadata"] = metadata
    return result


def _edge(source: str, target: str, relation: str, source_path: str, line: int) -> dict:
    return {
        "source": source,
        "target": target,
        "relation": relation,
        "confidence": "EXTRACTED",
        "source_file": source_path,
        "source_location": _source_location(line),
        "weight": 1.0,
    }


def _label(kind: str, identifier: str, name: str | None = None) -> str:
    display = DISPLAY_TYPES[kind]
    if kind in {"app", "page"}:
        return f"{display} {identifier}" + (f": {name}" if name else "")
    return f"{display}: {name or identifier}"


def _nearest_page(frames: list[Frame]) -> str | None:
    for frame in reversed(frames):
        if frame.kind == "page" and frame.node_id:
            return frame.node_id
    return None


def _nearest_owner(frames: list[Frame], fallback: str) -> str:
    for frame in reversed(frames):
        if frame.architectural_owner:
            return frame.architectural_owner
    return fallback


def _navigation_application(segment: str | None, current_app_id: str) -> str | None:
    if segment is None:
        return current_app_id
    segment = segment.strip()
    if not segment or segment.startswith("&"):
        return current_app_id
    if segment.isdigit():
        return segment
    return None


def _strip_sql_comments_and_literals(text: str) -> str:
    masked = list(text)
    pattern = re.compile(r"--[^\n]*|/\*.*?\*/|'(?:''|[^'])*'", re.DOTALL)
    for match in pattern.finditer(text):
        masked[match.start():match.end()] = [
            "\n" if char == "\n" else " " for char in match.group(0)
        ]
    return "".join(masked)


def _reference_label(value: str) -> str:
    parts = []
    for part in re.split(r"\s*\.\s*", value.strip()):
        if len(part) >= 2 and part[0] == part[-1] == '"':
            part = part[1:-1]
        parts.append(part)
    while len(parts) > 1 and SUBSTITUTION_PART_RE.fullmatch(parts[0]):
        parts.pop(0)
    return ".".join(part.upper() for part in parts)


def _is_ignored_object(name: str) -> bool:
    return name.rsplit(".", 1)[-1].casefold() in IGNORED_SQL_OBJECTS


def _blank_out(pattern: str, text: str) -> str:
    return re.sub(
        pattern,
        lambda match: "".join("\n" if char == "\n" else " " for char in match.group(0)),
        text,
        flags=re.IGNORECASE,
    )


def _from_clause_starts(text: str):
    index = 0
    in_quoted_identifier = False
    while index < len(text):
        char = text[index]
        if char == '"':
            if in_quoted_identifier and index + 1 < len(text) and text[index + 1] == '"':
                index += 2
                continue
            in_quoted_identifier = not in_quoted_identifier
        elif not in_quoted_identifier:
            match = FROM_START_RE.match(text, index)
            if match:
                yield match.end()
                index = match.end()
                continue
        index += 1


def _from_items(text: str):
    for start in _from_clause_starts(text):
        index = item_start = start
        depth = 0
        while index < len(text):
            char = text[index]
            if char == '(':
                depth += 1
            elif char == ')':
                if depth == 0:
                    break
                depth -= 1
            elif char == ',' and depth == 0:
                yield text[item_start:index]
                item_start = index + 1
            elif depth == 0 and (char.isalpha() or char == '_'):
                if FROM_STOP_RE.match(text, index):
                    if index > item_start:
                        yield text[item_start:index]
                    item_start = None
                    break
                index += re.match(r'[A-Za-z0-9_$#]*', text[index:]).end()
                continue
            index += 1
        if item_start is not None:
            yield text[item_start:index]


def _qualified_members(text: str) -> set[str]:
    clean = _strip_sql_comments_and_literals(text)
    return {
        f"{match.group(1)}.{match.group(2)}".upper()
        for match in QUALIFIED_MEMBER_RE.finditer(clean)
    }


def _sql_dependencies(text: str) -> tuple[set[str], set[str], set[str]]:
    clean = _strip_sql_comments_and_literals(text)
    reads_clean = _blank_out(r'\bDELETE\s+FROM\b', clean)
    reads_clean = _blank_out(r'\bEXTRACT\s*\([^()]*\)', reads_clean)
    writes_clean = _blank_out(r'\bFOR\s+UPDATE\b', clean)
    cte_names = {
        _reference_label(match.group(1)).casefold()
        for match in CTE_RE.finditer(reads_clean)
    }
    reads = set()
    for item in _from_items(reads_clean):
        item_match = FROM_ITEM_RE.match(item)
        if not item_match:
            continue
        if item_match.group(1).casefold() in FROM_KEYWORDS:
            continue
        label = _reference_label(item_match.group(1))
        if label.casefold() not in cte_names:
            reads.add(label)
    writes = {_reference_label(match.group(1)) for match in WRITE_RE.finditer(writes_clean)}
    calls = {
        _reference_label(match.group(1))
        for pattern in (PAREN_CALL_RE, STATEMENT_CALL_RE)
        for match in pattern.finditer(clean)
    }
    reads = {name for name in reads if not _is_ignored_object(name)}
    writes = {name for name in writes if not _is_ignored_object(name)}
    write_keys = {name.casefold() for name in writes}
    calls = {
        name
        for name in calls
        if name.casefold() not in write_keys
        and not name.casefold().startswith(("apex_", "sys.", "dbms_"))
    }
    return reads, writes, calls


def _strip_comments(line: str, in_block_comment: bool) -> tuple[str, bool]:
    output: list[str] = []
    index = 0
    quote: str | None = None
    is_mime_value = bool(re.match(r"^\s*(?:fileTypes|comments)\s*:", line))
    while index < len(line):
        char = line[index]
        if in_block_comment:
            end = line.find("*/", index)
            if end < 0:
                return "".join(output), True
            in_block_comment = False
            index = end + 2
            continue
        if quote is not None:
            output.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {'"', "'"}:
            quote = char
            output.append(char)
            index += 1
            continue
        if line.startswith("/*", index):
            if (
                is_mime_value
                and re.search(r"(?:^|[\s:,])[A-Za-z0-9*.+-]+$", line[:index])
                and re.match(r"\s*(?:,|$|/\*|//)", line[index + 2:])
            ):
                output.append("/")
                index += 1
                continue
            in_block_comment = True
            index += 2
            continue
        if line.startswith("//", index) and not (index and line[index - 1] == ":"):
            break
        output.append(char)
        index += 1
    return "".join(output), in_block_comment


def parse_apexlang(text: str, path: Path) -> dict[str, object]:
    """Parse architectural APEXlang declarations from *text*."""
    source_path = str(path)
    app_id = _application_id(path, text)
    app_node_id = make_id("apex", "app", app_id)
    file_node_id = make_id(source_path)
    nodes: list[dict] = [_node(file_node_id, path.name, source_path, None)]
    node_by_id = {file_node_id: nodes[0]}
    edges: list[dict] = []
    edge_keys: set[tuple[str, str, str, str, str]] = set()
    frames: list[Frame] = []
    declared_ids: dict[str, int] = {}
    in_fence = False
    in_block_comment = False
    pending_property: str | None = None
    pending_application: str | None = None
    fence_owner: str | None = None
    fence_start = 0
    fence_lines: list[str] = []
    fence_is_database_code = False

    def is_synthetic(node: dict) -> bool:
        return bool(node.get("metadata", {}).get("synthetic_reference"))

    def add_node(node: dict) -> None:
        if is_synthetic(node):
            node["type"] = SHARED_ANCHOR_TYPE
        existing = node_by_id.get(node["id"])
        if existing is None:
            node_by_id[node["id"]] = node
            nodes.append(node)
            return
        if is_synthetic(existing) and not is_synthetic(node):
            existing.clear()
            existing.update(node)

    mirror = DatabaseMirror.for_application_file(path)

    def mirrored_members(sql_text: str) -> set[str]:
        return {name for name in _qualified_members(sql_text) if mirror.package(name)}

    def add_reference_node(label: str, relation: str) -> str:
        mirrored = mirror.package(label) if relation == "calls" else mirror.table(label)
        if mirrored:
            return mirrored
        node_id = make_id(label)
        if node_id not in node_by_id:
            node = _node(node_id, label, "", None, origin_file=source_path)
            node["source_location"] = ""
            node["type"] = SHARED_ANCHOR_TYPE
            node_by_id[node_id] = node
            nodes.append(node)
        return node_id

    def unique_declaration_id(base: str) -> str:
        seen = declared_ids.get(base, 0) + 1
        declared_ids[base] = seen
        return base if seen == 1 else f"{base}_{seen}"

    def add_edge(source: str, target: str, relation: str, line: int) -> None:
        candidate = _edge(source, target, relation, source_path, line)
        key = (
            source,
            target,
            relation,
            candidate["source_file"],
            candidate["source_location"],
        )
        if key not in edge_keys:
            edge_keys.add(key)
            edges.append(candidate)

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if in_fence:
            fence_count = raw_line.count("```")
            if fence_count % 2:
                block = "\n".join(fence_lines)
                if fence_owner and fence_is_database_code:
                    reads, writes, calls = _sql_dependencies(block)
                    calls |= mirrored_members(block)
                    for target in sorted(reads, key=str.casefold):
                        add_edge(fence_owner, add_reference_node(target, "reads_from"), "reads_from", fence_start)
                    for target in sorted(writes, key=str.casefold):
                        add_edge(fence_owner, add_reference_node(target, "writes_to"), "writes_to", fence_start)
                    for target in sorted(calls, key=str.casefold):
                        add_edge(fence_owner, add_reference_node(target, "calls"), "calls", fence_start)
                in_fence = False
                fence_owner = None
                fence_lines = []
                fence_is_database_code = False
                pending_property = None
                pending_application = None
            else:
                fence_lines.append(raw_line)
            continue

        line, in_block_comment = _strip_comments(raw_line, in_block_comment)
        fence_count = line.count("```")
        if fence_count % 2:
            prefix = line.split("```", 1)[0]
            property_match = PROPERTY_RE.match(prefix)
            if property_match:
                pending_property = property_match.group(1)
            language = line.split("```", 1)[1].strip().casefold()
            in_fence = True
            fence_owner = _nearest_owner(frames, app_node_id)
            fence_start = line_number + 1
            fence_lines = []
            fence_is_database_code = (
                language in {"sql", "plsql"}
                or (pending_property or "").casefold() in SQL_PROPERTY_NAMES
            )
            continue

        if not line.strip():
            continue

        declaration = DECLARATION_RE.match(line)
        if declaration:
            token = declaration.group(1)
            identifier = _clean_identifier(declaration.group(2), token)
            kind = ARCHITECTURAL_TYPES.get(token)
            node_id: str | None = None
            owner = _nearest_owner(frames, app_node_id)

            if kind == "app":
                if identifier.isdigit():
                    app_id = identifier
                    app_node_id = make_id("apex", "app", app_id)
                node_id = app_node_id
                add_node(
                    _node(node_id, _label(kind, app_id), source_path, line_number,
                          component_type=kind, application_id=app_id)
                )
                add_edge(file_node_id, node_id, "contains", line_number)
                owner = node_id
            elif kind == "page":
                node_id = make_id("apex", "app", app_id, "page", identifier)
                add_node(
                    _node(node_id, _label(kind, identifier), source_path, line_number,
                          component_type=kind, application_id=app_id, page_id=identifier)
                )
                add_edge(file_node_id, node_id, "contains", line_number)
                add_edge(app_node_id, node_id, "contains", line_number)
                owner = node_id
            elif kind:
                if kind in {"region", "process", "dynamic_action"}:
                    parent_id = _nearest_page(frames) or app_node_id
                else:
                    parent_id = app_node_id
                node_id = unique_declaration_id(make_id(parent_id, kind, identifier))
                add_node(
                    _node(node_id, _label(kind, identifier), source_path, line_number,
                          component_type=kind, application_id=app_id,
                          component_identifier=identifier)
                )
                add_edge(parent_id, node_id, "contains", line_number)
                owner = node_id

            pending_application = None
            frames.append(
                Frame(
                    kind=kind or token,
                    identifier=identifier,
                    line=line_number,
                    node_id=node_id,
                    architectural_owner=node_id or owner,
                )
            )
            continue

        if CLOSE_COMPONENT_RE.match(line):
            if not frames:
                raise ApexlangParseError(f"unexpected component close at {source_path}:L{line_number}")
            frames.pop()
            pending_property = None
            pending_application = None
            continue

        name_match = NAME_RE.match(line)
        if name_match and frames:
            name = _clean_identifier(name_match.group(1), frames[-1].identifier)
            frame = frames[-1]
            if frame.node_id and frame.node_id in node_by_id:
                node_by_id[frame.node_id]["label"] = _label(frame.kind, frame.identifier, name)

        owner = _nearest_owner(frames, app_node_id)
        reference_match = REFERENCE_RE.match(line)
        if reference_match:
            property_name = reference_match.group(1).casefold()
            raw_reference = reference_match.group(2)
            reference = _clean_identifier(raw_reference, raw_reference)
            is_template_reference = reference.startswith("/")
            reference = reference.lstrip("/")
            if property_name in COMPONENT_REFERENCE_PROPERTIES and not is_template_reference:
                target_kind = COMPONENT_REFERENCE_PROPERTIES[property_name]
                target = make_id(app_node_id, target_kind, reference)
                add_node(
                    _node(
                        target,
                        _label(target_kind, reference),
                        source_path,
                        line_number,
                        component_type=target_kind,
                        application_id=app_id,
                        synthetic_reference=True,
                    )
                )
                add_edge(owner, target, "references_component", line_number)

        application_match = APPLICATION_PROPERTY_RE.match(line)
        if application_match:
            pending_application = application_match.group(1)

        for page_match in PAGE_TARGET_RE.finditer(line):
            target_app = _navigation_application(pending_application, app_id)
            if target_app is None:
                continue
            target = make_id("apex", "app", target_app, "page", page_match.group(1))
            if target != owner:
                add_edge(owner, target, "navigates_to", line_number)
        for page_match in APEX_URL_PAGE_RE.finditer(line):
            target_app = _navigation_application(page_match.group(1), app_id)
            if target_app is None:
                continue
            target = make_id("apex", "app", target_app, "page", page_match.group(2))
            if target != owner:
                add_edge(owner, target, "navigates_to", line_number)

        property_match = PROPERTY_RE.match(line)
        if property_match:
            pending_property = property_match.group(1)
            property_name = pending_property.casefold()
            property_value = property_match.group(2).strip()
            if property_name == "authorizationscheme" and property_value:
                reference = _clean_identifier(property_value.lstrip("@"), property_value)
                target = make_id(app_node_id, "authorization", reference)
                add_node(
                    _node(
                        target,
                        _label("authorization", reference),
                        source_path,
                        line_number,
                        component_type="authorization",
                        application_id=app_id,
                        synthetic_reference=True,
                    )
                )
                add_edge(owner, target, "secured_by", line_number)
            if property_name in TABLE_PROPERTY_NAMES and property_value:
                table = _reference_label(_clean_identifier(property_value, property_value))
                if table and not _is_ignored_object(table):
                    add_edge(owner, add_reference_node(table, "reads_from"), "reads_from", line_number)
            if property_name in FUNCTION_PROPERTY_NAMES and property_value:
                function = _reference_label(_clean_identifier(property_value, property_value))
                if "." in function and not _is_ignored_object(function):
                    add_edge(owner, add_reference_node(function, "calls"), "calls", line_number)
            if property_name in SQL_PROPERTY_NAMES and property_value:
                reads, writes, calls = _sql_dependencies(property_value)
                calls |= mirrored_members(property_value)
                for target in sorted(reads, key=str.casefold):
                    add_edge(owner, add_reference_node(target, "reads_from"), "reads_from", line_number)
                for target in sorted(writes, key=str.casefold):
                    add_edge(owner, add_reference_node(target, "writes_to"), "writes_to", line_number)
                for target in sorted(calls, key=str.casefold):
                    add_edge(owner, add_reference_node(target, "calls"), "calls", line_number)

    if in_fence:
        raise ApexlangParseError(f"unclosed multiline fence in {source_path}")
    if frames:
        opened = frames[-1]
        raise ApexlangParseError(
            f"unclosed component '{opened.kind} {opened.identifier}' "
            f"from {source_path}:L{opened.line}"
        )

    return {"nodes": nodes, "edges": edges}


def extract_apexlang(path: Path) -> dict[str, object]:
    """Extract architectural components and database/package dependencies from Oracle APEX .apx files."""
    try:
        text = _read_source_text(path)
        return parse_apexlang(text, path)
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
        display_error = " ".join(error.splitlines())
        display_path = " ".join(str(path).splitlines())
        print(
            f"Warning: APEXlang extraction failed for {display_path}: "
            f"{type(exc).__name__}: {display_error}",
            file=sys.stderr,
        )
        return {"nodes": [], "edges": [], "error": error}
