"""Final original-byte proof of an already-admitted QtTest include snapshot.

The caller owns reads and root admission. This checker inspects only supplied
bytes; neither an include literal nor a forged witness can open another file.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from graphify.extractors.cpp_include_guards import IncludeGuardIndex
from graphify.extractors.qt_cpp_test_context import QtTestContextError


def verify_include_witnesses(contexts, sources, *, root):
    """Require exact source/include/chain ownership before publishing source facts."""
    from graphify.extractors.qt_cpp_syntax import _parse_cpp, walk
    parsed = {}
    root = Path(root).resolve()

    def source_record(witness):
        try:
            path = (root / witness.source_file).resolve()
            key = str(path)
            path.relative_to(root)
            source = sources[key]
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            raise QtTestContextError("QtTest include witness is not an admitted source") from exc
        if hashlib.sha256(source).hexdigest() != witness.source_sha256:
            raise QtTestContextError("QtTest include witness source changed; retry the admitted snapshot")
        if key not in parsed:
            tree = _parse_cpp(source)
            list(walk(tree))
            parsed[key] = tree, IncludeGuardIndex(tree)
        tree, guards = parsed[key]
        start, end, start_row, end_row, start_column, end_column = witness.span
        node = tree.descendant_for_byte_range(start, end)
        if (node is None or node.type != "preproc_include" or node.start_byte != start or node.end_byte != end
                or (node.start_point.row, node.end_point.row, node.start_point.column, node.end_point.column)
                != (start_row, end_row, start_column, end_column)
                or node.parent is None or not (node.parent.type == "translation_unit" or guards.accepts(node.parent))):
            raise QtTestContextError("QtTest include witness does not match original source scope/span")
        item = node.child_by_field_name("path")
        literal = source[item.start_byte:item.end_byte] if item is not None else b""
        if len(literal) < 2 or literal[1:-1].decode() != witness.include_literal:
            raise QtTestContextError("QtTest include witness literal differs from original source")
        return key, literal[:1]

    for target, context in zip(contexts.paths, contexts.contexts):
        for activation in context.activations:
            expected = target
            for index, witness in enumerate(activation.witnesses):
                key, kind = source_record(witness)
                if key != expected or index == 0 and activation.after != witness.span[1]:
                    raise QtTestContextError("QtTest include witness has foreign source ordering")
                if index == len(activation.witnesses) - 1:
                    if kind != b"<" or witness.include_literal != activation.sdk_header:
                        raise QtTestContextError("QtTest include witness lacks its terminal SDK include")
                else:
                    if kind != b'"':
                        raise QtTestContextError("QtTest forward context requires a literal quoted input")
                    try:
                        if witness.build_root is not None:
                            proof = witness.build_root
                            if (proof.importer_file != witness.source_file or proof.include_span != witness.span
                                    or proof.include_literal != witness.include_literal
                                    or proof.importer_sha256 != witness.source_sha256
                                    or proof not in context.build_witnesses):
                                raise QtTestContextError("QtTest build include witness has foreign ownership")
                            expected = str((root / proof.header_file).resolve())
                        else:
                            expected = str((Path(key).parent / witness.include_literal).resolve())
                    except (OSError, RuntimeError, ValueError) as exc:
                        raise QtTestContextError("QtTest quoted include witness no longer resolves") from exc
