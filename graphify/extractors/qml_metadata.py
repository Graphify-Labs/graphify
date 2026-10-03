"""Bounded, source-only qmldir reader with independently owned metadata records."""

from __future__ import annotations

import re
import base64
from pathlib import Path

from graphify.qml_resolution_types import fact_edge, fact_node

MAX_METADATA_BYTES = 1_048_576
MAX_METADATA_RECORDS = 10_000
_VERSION = re.compile(r"^(\d{1,6})\.(\d{1,6})$")


def _version(value: str) -> tuple[int, int] | None:
    match = _VERSION.fullmatch(value)
    return (int(match[1]), int(match[2])) if match else None


def _identifier(value: str) -> bool:
    return all(part.isidentifier() for part in value.split("."))


def parse_qmldir(text: str, *, relative_file: str = "qmldir") -> dict:
    """Parse supported literal directives; unsupported coverage is never success."""
    file_node = fact_node(relative_file, "file", "qmldir", Path(relative_file).name, 1,
                          metadata_format="qmldir", span={
                              "start_byte": 0, "end_byte": len(text.encode("utf-8")),
                              "start_row": 0, "start_column": 0,
                              "end_row": text.count("\n"),
                              "end_column": len(text.rsplit("\n", 1)[-1].encode("utf-8"))})
    nodes, edges, failures = [file_node], [], []
    module_node = None
    occurrences: dict[tuple, int] = {}
    exports: set[tuple] = set()

    # Each record owns its data, avoiding the export-list cap in metadata rendering.
    def record(kind, key, label, line, **fields):
        count = occurrences.get((kind, key), 0)
        occurrences[kind, key] = count + 1
        node = fact_node(relative_file, kind, (key, count), label, line,
                         span=line_spans[line], **fields)
        nodes.append(node)
        parent = module_node or file_node
        edges.append(fact_edge(parent["id"], node["id"], "contains", node,
                               "qml_metadata_declaration"))
        return node

    def fail(line, reason):
        if len(failures) < 50:
            failures.append({"line": line, "code": "QML-META-001", "reason": reason})

    if len(text.encode("utf-8")) > MAX_METADATA_BYTES:
        fail(1, "metadata_size_limit")
        text = ""
    # UTF-8 byte offsets remain attached to each admitted directive.
    line_spans, offset = {}, 0
    source_lines = text.splitlines(keepends=True)
    for line, raw in enumerate(source_lines, 1):
        body = raw.rstrip("\r\n")
        end = offset + len(body.encode("utf-8"))
        line_spans[line] = {"start_byte": offset, "end_byte": end,
                            "start_row": line - 1, "end_row": line - 1,
                            "start_column": 0, "end_column": len(body.encode("utf-8"))}
        offset += len(raw.encode("utf-8"))
    meaningful = 0
    for line, raw in enumerate(text.splitlines(), 1):
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        meaningful += 1
        if meaningful > MAX_METADATA_RECORDS:
            fail(line, "metadata_record_limit")
            break
        tokens = value.split()
        if any(len(base64.b64encode(token.encode("utf-8"))) > 512 or
               any(ord(char) < 32 for char in token) for token in tokens):
            fail(line, "metadata_value_limit")
            continue
        head = tokens[0]
        if head == "module":
            if len(tokens) != 2 or not _identifier(tokens[1]) or module_node or meaningful != 1:
                fail(line, "invalid_module_declaration")
                continue
            module_node = record("module", tokens[1], tokens[1], line, uri=tokens[1],
                                 raw_name=tokens[1])
            continue
        if head in {"depends", "import"}:
            if len(tokens) not in {2, 3} or not _identifier(tokens[1]):
                fail(line, "invalid_module_dependency")
                continue
            version = _version(tokens[2]) if len(tokens) == 3 else None
            auto = len(tokens) == 3 and tokens[2] == "auto" and head == "import"
            if len(tokens) == 3 and not version and not auto:
                fail(line, "invalid_module_version")
                continue
            record("module_import" if head == "import" else "dependency", tuple(tokens),
                   tokens[1], line, uri=tokens[1], major=version[0] if version else None,
                   minor=version[1] if version else None, auto=auto)
            continue
        if head in {"plugin", "optional", "classname", "typeinfo", "prefer",
                    "designersupported"}:
            directive = "plugin" if tokens[:2] == ["optional", "plugin"] else head
            args = tokens[2:] if tokens[:2] == ["optional", "plugin"] else tokens[1:]
            valid = ((directive == "plugin" and len(args) in {1, 2}) or
                     (directive in {"classname", "typeinfo", "prefer"} and len(args) == 1) or
                     (directive == "designersupported" and not args))
            if not valid:
                fail(line, "unsupported_or_malformed_directive")
                continue
            record(directive, tuple(tokens), directive, line, value=args[0] if args else "",
                   optional=head == "optional", path=args[1] if len(args) > 1 else "")
            continue
        flag = head if head in {"singleton", "internal"} else ""
        entry = tokens[1:] if flag else tokens
        version = _version(entry[1]) if len(entry) == 3 else None
        valid = ((len(entry) == 2 and flag != "singleton") or
                 (len(entry) == 3 and version and flag != "internal"))
        if not valid or not entry[0].isidentifier() or not entry[-1].endswith((".qml", ".js", ".mjs")):
            fail(line, "unsupported_or_malformed_directive")
            continue
        export_key = (entry[0], version, flag == "internal")
        if export_key in exports:
            fail(line, "duplicate_export")
        exports.add(export_key)
        record("export", (entry[0], version, entry[-1], flag), entry[0], line,
               raw_name=entry[0], target_path=entry[-1],
               major=version[0] if version else None, minor=version[1] if version else None,
               internal=flag == "internal", singleton=flag == "singleton",
               export_kind="script" if entry[-1].endswith((".js", ".mjs")) else "type")
    result = {"nodes": nodes, "edges": edges, "diagnostics": []}
    if failures:
        result.update(error="QML-META-001: incomplete qmldir metadata; inspect diagnostics",
                      partial=True, parse_errors=failures)
        result["diagnostics"] = [{"code": item["code"], "severity": "error",
                                  "owner": "qmldir", "source_file": relative_file,
                                  "line": item["line"], "reason": item["reason"],
                                  "message": "Unsupported or malformed qmldir metadata",
                                  "recovery": "Correct the directive or use the documented literal subset."}
                                 for item in failures]
    return result


def extract_qmldir(path: Path, *, root: Path | None = None) -> dict:
    """Read one admitted file; do not follow any paths or plugins it declares."""
    path = Path(path)
    anchor = Path(root).resolve() if root is not None else path.resolve().parent
    relative = ""
    try:
        relative = path.resolve().relative_to(anchor).as_posix()
        if path.stat().st_size > MAX_METADATA_BYTES:
            return _read_failure(relative, "metadata_size_limit")
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError, ValueError):
        return _read_failure(relative, "metadata_unreadable_or_outside_root")
    return parse_qmldir(text, relative_file=relative)


def _read_failure(relative: str, reason: str) -> dict:
    return {"nodes": [], "edges": [], "error": "QML-META-002: metadata read rejected",
            "diagnostics": [{"code": "QML-META-002", "severity": "error", "owner": "qmldir",
                             "source_file": relative, "reason": reason,
                             "message": "Metadata unreadable, oversized or outside the scan root",
                             "recovery": "Use an accepted UTF-8 qmldir within the documented limits."}]}
