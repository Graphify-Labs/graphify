"""engine — moved verbatim from graphify/extract.py."""
from __future__ import annotations

import hashlib
import importlib
from graphify.extractors.base import _LANGUAGE_BUILTIN_GLOBALS, _file_stem, _make_id, _read_text
from graphify.ids import normalize_id
from graphify.extractors.models import LanguageConfig
from graphify.extractors.resolution import _resolve_js_import_target
from graphify.security import sanitize_metadata
from pathlib import Path


def _csharp_namespace_id(dotted_name: str) -> str:
    digest = hashlib.sha1(dotted_name.encode("utf-8")).hexdigest()[:16]
    return f"csharp_namespace:{digest}"

REFERENCE_CONTEXTS = frozenset({
    "field", "parameter_type", "return_type", "generic_arg", "attribute", "value", "type",
})

def _source_location(line: int | str | None) -> str | None:
    if line is None:
        return None
    if isinstance(line, str):
        return line if line.startswith("L") else f"L{line}"
    return f"L{line}"

def _semantic_reference_edge(
    source: str,
    target: str,
    context: str,
    source_file: str,
    line: int | str | None,
) -> dict:
    if context not in REFERENCE_CONTEXTS:
        raise ValueError(f"unknown reference context: {context}")
    return {
        "source": source,
        "target": target,
        "relation": "references",
        "context": context,
        "confidence": "EXTRACTED",
        "source_file": source_file,
        "source_location": _source_location(line),
        "weight": 1.0,
    }

_PYTHON_TYPE_CONTAINERS = frozenset({
    "list", "dict", "set", "tuple", "frozenset", "type",
    "List", "Dict", "Set", "Tuple", "FrozenSet", "Type",
    "Optional", "Union", "Sequence", "Iterable", "Mapping", "MutableMapping",
    "Iterator", "Callable", "Awaitable", "AsyncIterable", "AsyncIterator", "Coroutine",
    "Generator", "AsyncGenerator", "ContextManager", "AsyncContextManager",
    "Annotated", "ClassVar", "Final", "Literal", "Concatenate", "ParamSpec", "TypeVar",
    "None", "Ellipsis",
})

_PYTHON_ANNOTATION_NOISE = frozenset({
    # scalar builtins
    "str", "int", "float", "bool", "bytes", "bytearray", "complex", "object",
    "True", "False",
    # unittest.mock
    "MagicMock", "Mock", "AsyncMock", "NonCallableMock",
    "NonCallableMagicMock", "PropertyMock", "patch", "sentinel",
})

def _python_collect_type_refs(node, source: bytes, generic: bool, out: list[tuple[str, str]]) -> None:
    """Walk a Python type annotation; append (name, role) where role is 'type' or 'generic_arg'.

    Builtin/typing containers (list, dict, Optional, Union, …) are not emitted as refs themselves,
    but their nested type arguments still count as generic_arg.
    """
    if node is None:
        return
    t = node.type
    if t == "type":
        for c in node.children:
            if c.is_named:
                _python_collect_type_refs(c, source, generic, out)
        return
    if t == "identifier":
        name = _read_text(node, source)
        if name and name not in _PYTHON_TYPE_CONTAINERS and name not in _PYTHON_ANNOTATION_NOISE:
            out.append((name, "generic_arg" if generic else "type"))
        return
    if t == "attribute":
        tail = _read_text(node, source).rsplit(".", 1)[-1]
        if tail and tail not in _PYTHON_TYPE_CONTAINERS and tail not in _PYTHON_ANNOTATION_NOISE:
            out.append((tail, "generic_arg" if generic else "type"))
        return
    if t == "generic_type":
        for c in node.children:
            if c.type == "identifier":
                container = _read_text(c, source)
                if container and container not in _PYTHON_TYPE_CONTAINERS and container not in _PYTHON_ANNOTATION_NOISE:
                    out.append((container, "generic_arg" if generic else "type"))
            elif c.type == "type_parameter":
                for sub in c.children:
                    if sub.is_named:
                        _python_collect_type_refs(sub, source, True, out)
        return
    if t == "subscript":
        value = node.child_by_field_name("value")
        if value is not None:
            _python_collect_type_refs(value, source, generic, out)
        for c in node.children:
            if c is value or not c.is_named:
                continue
            _python_collect_type_refs(c, source, True, out)
        return
    if node.is_named:
        for c in node.children:
            if c.is_named:
                _python_collect_type_refs(c, source, generic, out)

def _csharp_pre_scan_interfaces(root_node, source: bytes) -> set[str]:
    """Return names declared as `interface` in this C# compilation unit."""
    out: set[str] = set()
    stack = [root_node]
    while stack:
        n = stack.pop()
        if n.type == "interface_declaration":
            name_node = n.child_by_field_name("name")
            if name_node is not None:
                text = _read_text(name_node, source)
                if text:
                    out.add(text)
        stack.extend(n.children)
    return out

def _csharp_classify_base(name: str, interface_names: set[str]) -> str:
    """`implements` if the base name is an interface (declared or by I-prefix convention), else `inherits`."""
    if name in interface_names:
        return "implements"
    if len(name) >= 2 and name[0] == "I" and name[1].isupper():
        return "implements"
    return "inherits"

_CSHARP_TYPE_PARAMETER_SCOPE_DECLARATIONS = frozenset({
    "class_declaration",
    "interface_declaration",
    "record_declaration",
    "struct_declaration",
    "method_declaration",
})

def _csharp_type_parameters_in_scope(node, source: bytes) -> frozenset[str]:
    """Return C# type-parameter names visible from ``node``."""
    names: set[str] = set()
    scope = node
    while scope is not None:
        if scope.type in _CSHARP_TYPE_PARAMETER_SCOPE_DECLARATIONS:
            for child in scope.children:
                if child.type != "type_parameter_list":
                    continue
                for param in child.children:
                    if param.type == "type_parameter":
                        name_node = next(
                            (sub for sub in param.children if sub.type == "identifier"),
                            None,
                        )
                        if name_node is not None:
                            name = _read_text(name_node, source)
                            if name:
                                names.add(name)
                    elif param.type == "identifier":
                        name = _read_text(param, source)
                        if name:
                            names.add(name)
        scope = scope.parent
    return frozenset(names)

def _csharp_collect_type_refs(
    node,
    source: bytes,
    generic: bool,
    out: list[tuple[str, str, bool, str]],
    skip: frozenset[str] | None = None,
) -> None:
    """Walk a C# type expression; append (name, role, qualified, qualifier) tuples."""
    if node is None:
        return
    if skip is None:
        skip = _csharp_type_parameters_in_scope(node, source)
    t = node.type
    if t == "predefined_type":
        return
    if t == "identifier":
        name = _read_text(node, source)
        if name and name not in skip:
            out.append((name, "generic_arg" if generic else "type", False, ""))
        return
    if t == "qualified_name":
        prefix, _, text = _read_text(node, source).rpartition(".")
        text = text.split("<", 1)[0]
        if text and text not in skip:
            out.append((text, "generic_arg" if generic else "type", True, prefix))
        return
    if t == "generic_name":
        name_child = node.child_by_field_name("name")
        if name_child is None:
            for sub in node.children:
                if sub.type == "identifier":
                    name_child = sub
                    break
        if name_child is not None:
            qualified = name_child.type == "qualified_name"
            prefix, _, name = _read_text(name_child, source).rpartition(".")
            if name and name not in skip:
                out.append((name, "generic_arg" if generic else "type", qualified, prefix if qualified else ""))
        for sub in node.children:
            if sub.type == "type_argument_list":
                for arg in sub.children:
                    if arg.is_named:
                        _csharp_collect_type_refs(arg, source, True, out, skip)
        return
    if t in ("nullable_type", "array_type", "pointer_type", "ref_type"):
        for c in node.children:
            if c.is_named:
                _csharp_collect_type_refs(c, source, generic, out, skip)
        return
    if node.is_named:
        for c in node.children:
            if c.is_named:
                _csharp_collect_type_refs(c, source, generic, out, skip)

def _csharp_attribute_names(method_node, source: bytes) -> list[tuple[str, bool, str]]:
    """Collect attribute names from a C# method/declaration's attribute_list children."""
    names: list[tuple[str, bool, str]] = []
    skip = _csharp_type_parameters_in_scope(method_node, source)
    for child in method_node.children:
        if child.type != "attribute_list":
            continue
        for attr in child.children:
            if attr.type != "attribute":
                continue
            name_node = attr.child_by_field_name("name")
            if name_node is None:
                for sub in attr.children:
                    if sub.type in ("identifier", "qualified_name"):
                        name_node = sub
                        break
            if name_node is not None:
                qualified = name_node.type == "qualified_name"
                prefix, _, text = _read_text(name_node, source).rpartition(".")
                if text and text not in skip:
                    names.append((text, qualified, prefix if qualified else ""))
    return names

_JAVA_TYPE_PARAMETER_SCOPE_DECLARATIONS = frozenset({
    "class_declaration",
    "interface_declaration",
    "record_declaration",
    "method_declaration",
    "constructor_declaration",
})

def _java_type_parameters_in_scope(node, source: bytes) -> frozenset[str]:
    """Return Java type-parameter names visible from ``node``."""
    names: set[str] = set()
    scope = node
    while scope is not None:
        if scope.type in _JAVA_TYPE_PARAMETER_SCOPE_DECLARATIONS:
            params = scope.child_by_field_name("type_parameters")
            if params is not None:
                for param in params.children:
                    if param.type != "type_parameter":
                        continue
                    name_node = next(
                        (child for child in param.children if child.type == "type_identifier"),
                        None,
                    )
                    if name_node is not None:
                        names.add(_read_text(name_node, source))
        scope = scope.parent
    return frozenset(names)

_JAVA_BUILTIN_TYPES = frozenset({
    # java.lang — core
    "Object", "String", "CharSequence", "StringBuilder", "StringBuffer",
    "Number", "Byte", "Short", "Integer", "Long", "Float", "Double",
    "Boolean", "Character", "Void", "Class", "Enum", "Record", "Math",
    "System", "Thread", "Runnable", "Comparable", "Iterable", "Cloneable",
    "AutoCloseable", "Appendable", "Readable", "Process", "ProcessBuilder",
    "Runtime", "Package", "ThreadLocal", "InheritableThreadLocal",
    # java.lang — throwables
    "Throwable", "Exception", "RuntimeException", "Error",
    "IllegalArgumentException", "IllegalStateException", "NullPointerException",
    "IndexOutOfBoundsException", "ArrayIndexOutOfBoundsException",
    "ClassCastException", "NumberFormatException", "ArithmeticException",
    "UnsupportedOperationException", "InterruptedException",
    "CloneNotSupportedException", "SecurityException", "StackOverflowError",
    "OutOfMemoryError", "AssertionError",
    # java.util — collections & core
    "Collection", "List", "ArrayList", "LinkedList", "Vector", "Stack",
    "Set", "HashSet", "LinkedHashSet", "TreeSet", "SortedSet", "NavigableSet",
    "EnumSet", "Map", "HashMap", "LinkedHashMap", "TreeMap", "SortedMap",
    "NavigableMap", "Hashtable", "EnumMap", "Properties", "Queue", "Deque",
    "ArrayDeque", "PriorityQueue", "Iterator", "ListIterator", "Comparator",
    "Optional", "OptionalInt", "OptionalLong", "OptionalDouble", "Collections",
    "Arrays", "Objects", "Date", "Calendar", "Random", "UUID", "Scanner",
    "StringJoiner", "StringTokenizer", "BitSet", "Spliterator", "Locale",
    "NoSuchElementException", "ConcurrentModificationException",
    # java.util.stream
    "Stream", "IntStream", "LongStream", "DoubleStream", "Collector",
    "Collectors",
    # java.util.function
    "Function", "BiFunction", "Consumer", "BiConsumer", "Supplier",
    "Predicate", "BiPredicate", "UnaryOperator", "BinaryOperator",
    "IntFunction", "ToIntFunction", "ToLongFunction", "ToDoubleFunction",
    # java.util.concurrent
    "Callable", "Future", "CompletableFuture", "CompletionStage", "Executor",
    "ExecutorService", "Executors", "ScheduledExecutorService", "TimeUnit",
    "ConcurrentHashMap", "ConcurrentMap", "CopyOnWriteArrayList",
    "BlockingQueue", "CountDownLatch", "Semaphore", "CyclicBarrier",
    "AtomicInteger", "AtomicLong", "AtomicBoolean", "AtomicReference",
    # java.time
    "Instant", "Duration", "Period", "LocalDate", "LocalTime", "LocalDateTime",
    "ZonedDateTime", "OffsetDateTime", "ZoneId", "ZoneOffset", "DayOfWeek",
    "Month", "Year", "Clock", "DateTimeFormatter",
    # java.io / java.nio.file
    "IOException", "UncheckedIOException", "FileNotFoundException", "File",
    "InputStream", "OutputStream", "Reader", "Writer", "BufferedReader",
    "BufferedWriter", "InputStreamReader", "OutputStreamWriter", "FileReader",
    "FileWriter", "PrintStream", "PrintWriter", "ByteArrayInputStream",
    "ByteArrayOutputStream", "Serializable", "Closeable", "Path", "Paths",
    "Files",
    # java.math
    "BigDecimal", "BigInteger",
})

def _java_collect_type_refs(
    node,
    source: bytes,
    generic: bool,
    out: list[tuple[str, str]],
    skip: frozenset[str] | None = None,
) -> None:
    """Walk a Java type expression; append (name, role) tuples."""
    if node is None:
        return
    if skip is None:
        skip = _java_type_parameters_in_scope(node, source)
    t = node.type
    if t in ("integral_type", "floating_point_type", "boolean_type", "void_type"):
        return
    if t == "type_identifier":
        name = _read_text(node, source)
        if name and name not in skip and name not in _JAVA_BUILTIN_TYPES:
            out.append((name, "generic_arg" if generic else "type"))
        return
    if t == "scoped_type_identifier":
        text = _read_text(node, source).rsplit(".", 1)[-1]
        if text and text not in _JAVA_BUILTIN_TYPES:
            out.append((text, "generic_arg" if generic else "type"))
        return
    if t == "generic_type":
        for c in node.children:
            if c.type in ("type_identifier", "scoped_type_identifier"):
                text = _read_text(c, source).rsplit(".", 1)[-1]
                if (
                    text
                    and text not in _JAVA_BUILTIN_TYPES
                    and (c.type == "scoped_type_identifier" or text not in skip)
                ):
                    out.append((text, "generic_arg" if generic else "type"))
                break
        for c in node.children:
            if c.type == "type_arguments":
                for arg in c.children:
                    if arg.is_named:
                        _java_collect_type_refs(arg, source, True, out, skip)
        return
    if t == "array_type":
        for c in node.children:
            if c.is_named:
                _java_collect_type_refs(c, source, generic, out, skip)
        return
    if node.is_named:
        for c in node.children:
            if c.is_named:
                _java_collect_type_refs(c, source, generic, out, skip)


def _java_receiver_type_name(type_node, source: bytes) -> str | None:
    """Return the concrete declared type usable for Java receiver resolution."""
    if type_node is None:
        return None
    t = type_node.type
    if t == "type_identifier":
        name = _read_text(type_node, source)
    elif t == "scoped_type_identifier":
        name = _read_text(type_node, source).rsplit(".", 1)[-1]
    elif t == "generic_type":
        base = next(
            (
                child
                for child in type_node.children
                if child.type in ("type_identifier", "scoped_type_identifier")
            ),
            None,
        )
        return _java_receiver_type_name(base, source)
    else:
        return None
    if (
        not name
        or name in _JAVA_BUILTIN_TYPES
        or name in _java_type_parameters_in_scope(type_node, source)
    ):
        return None
    return name


def _java_declarator_names(declaration_node, source: bytes) -> list[str]:
    names: list[str] = []
    for child in declaration_node.children:
        if child.type != "variable_declarator":
            continue
        name_node = child.child_by_field_name("name")
        if name_node is not None:
            name = _read_text(name_node, source)
            if name:
                names.append(name)
    return names


def _java_lambda_parameters(
    lambda_node,
    source: bytes,
) -> list[tuple[str, str | None]]:
    parameters = lambda_node.child_by_field_name("parameters")
    if parameters is None:
        return []
    if parameters.type == "identifier":
        return [(_read_text(parameters, source), None)]
    if parameters.type == "inferred_parameters":
        return [
            (_read_text(child, source), None)
            for child in parameters.children
            if child.type == "identifier"
        ]
    bindings: list[tuple[str, str | None]] = []
    for parameter in parameters.children:
        if parameter.type not in ("formal_parameter", "spread_parameter"):
            continue
        name_node = parameter.child_by_field_name("name")
        if name_node is not None:
            bindings.append((
                _read_text(name_node, source),
                _java_receiver_type_name(
                    parameter.child_by_field_name("type"), source
                ),
            ))
    return bindings


def _java_method_receiver_types(
    method_node,
    source: bytes,
    field_types: dict[str, str],
) -> dict[str, str]:
    """Build the receiver type table visible to one Java method.

    Current-class fields are the base scope, and parameters shadow them for the
    full method. Conflicting local declarations are omitted because raw call
    facts do not retain lexical scope.
    """
    method_types: dict[str, str] = {}
    ambiguous: set[str] = set()

    def bind(name: str, type_name: str | None) -> None:
        if not name or not type_name or name in ambiguous:
            return
        previous = method_types.get(name)
        if previous is not None and previous != type_name:
            method_types.pop(name, None)
            ambiguous.add(name)
        else:
            method_types[name] = type_name

    params = method_node.child_by_field_name("parameters")
    if params is not None:
        for param in params.children:
            if param.type not in ("formal_parameter", "spread_parameter"):
                continue
            type_name = _java_receiver_type_name(
                param.child_by_field_name("type"), source
            )
            name_node = param.child_by_field_name("name")
            if name_node is not None:
                bind(_read_text(name_node, source), type_name)

    body = method_node.child_by_field_name("body")
    stack = list(body.children) if body is not None else []
    while stack:
        node = stack.pop()
        if node.type in (
            "class_declaration",
            "class_body",
            "interface_declaration",
            "record_declaration",
            "enum_declaration",
            "annotation_type_declaration",
        ):
            continue
        if node.type == "lambda_expression":
            # Raw calls are method-scoped, so a lambda-local binding cannot be
            # distinguished from an enclosing binding with the same name.
            for name, type_name in _java_lambda_parameters(node, source):
                if type_name is None or field_types.get(name) not in (None, type_name):
                    method_types.pop(name, None)
                    ambiguous.add(name)
                else:
                    bind(name, type_name)
        if node.type == "local_variable_declaration":
            type_name = _java_receiver_type_name(
                node.child_by_field_name("type"), source
            )
            for name in _java_declarator_names(node, source):
                if field_types.get(name) not in (None, type_name):
                    method_types.pop(name, None)
                    ambiguous.add(name)
                else:
                    bind(name, type_name)
        stack.extend(node.children)

    table = dict(field_types)
    table.update(method_types)
    for name in ambiguous:
        table.pop(name, None)
    table.update({f"this.{name}": type_name for name, type_name in field_types.items()})
    return table


def _java_annotation_names(declaration_node, source: bytes) -> list[str]:
    """Collect annotation names from a Java declaration's `modifiers` child."""
    names: list[str] = []
    modifiers = None
    for child in declaration_node.children:
        if child.type == "modifiers":
            modifiers = child
            break
    if modifiers is None:
        return names
    for anno in modifiers.children:
        if anno.type not in ("marker_annotation", "annotation"):
            continue
        name_node = anno.child_by_field_name("name")
        if name_node is None:
            for sub in anno.children:
                if sub.type in ("identifier", "scoped_identifier", "type_identifier"):
                    name_node = sub
                    break
        if name_node is not None:
            text = _read_text(name_node, source).rsplit(".", 1)[-1]
            if text:
                names.append(text)
    return names

def _php_name_text(node, source: bytes) -> str | None:
    """Return the unqualified name text from a PHP `name`/`qualified_name` node."""
    if node is None:
        return None
    return _read_text(node, source).rsplit("\\", 1)[-1] or None

def _php_collect_type_refs(node, source: bytes, generic: bool, out: list[tuple[str, str]]) -> None:
    """Walk a PHP type expression; append (name, role) tuples."""
    if node is None:
        return
    t = node.type
    if t == "primitive_type":
        return
    if t == "named_type":
        for c in node.children:
            if c.type in ("name", "qualified_name"):
                text = _php_name_text(c, source)
                if text:
                    out.append((text, "generic_arg" if generic else "type"))
                return
        return
    if t in ("name", "qualified_name"):
        text = _php_name_text(node, source)
        if text:
            out.append((text, "generic_arg" if generic else "type"))
        return
    if t in ("nullable_type", "union_type", "intersection_type", "optional_type"):
        for c in node.children:
            if c.is_named:
                _php_collect_type_refs(c, source, generic, out)
        return
    if node.is_named:
        for c in node.children:
            if c.is_named:
                _php_collect_type_refs(c, source, generic, out)

def _php_method_return_type_node(method_node):
    """Return the named_type/primitive_type node sitting after formal_parameters."""
    saw_params = False
    for c in method_node.children:
        if c.type == "formal_parameters":
            saw_params = True
            continue
        if saw_params and c.is_named and c.type not in ("compound_statement",):
            if c.type in ("named_type", "primitive_type", "nullable_type",
                          "union_type", "intersection_type", "optional_type"):
                return c
    return None

# Kotlin stdlib scalar/collection/core types that appear constantly as type
# annotations but carry no useful semantic meaning as graph nodes (mirrors
# _JAVA_BUILTIN_TYPES / _PYTHON_ANNOTATION_NOISE / _GO_PREDECLARED_TYPES).
# Kotlin compiles to the JVM and freely references java.* types too, so this
# is combined with _JAVA_BUILTIN_TYPES at the call site rather than duplicated.
_KOTLIN_BUILTIN_TYPES = frozenset({
    # kotlin — scalars & core
    "Any", "Unit", "Nothing", "Boolean", "Byte", "Short", "Int", "Long",
    "Float", "Double", "Char", "String", "CharSequence", "Number",
    "Comparable", "Enum", "Annotation", "Pair", "Triple", "Lazy",
    "Function",
    # kotlin — throwables
    "Throwable", "Exception", "RuntimeException", "Error",
    "IllegalArgumentException", "IllegalStateException", "NullPointerException",
    "IndexOutOfBoundsException", "ClassCastException", "NumberFormatException",
    "ArithmeticException", "UnsupportedOperationException",
    "NoSuchElementException", "ConcurrentModificationException",
    "StackOverflowError", "OutOfMemoryError", "AssertionError",
    "InterruptedException",
    # kotlin.collections
    "Array", "List", "MutableList", "ArrayList", "Set", "MutableSet",
    "HashSet", "LinkedHashSet", "Map", "MutableMap", "HashMap",
    "LinkedHashMap", "Collection", "MutableCollection", "Iterable",
    "MutableIterable", "Iterator", "MutableIterator", "ListIterator",
    "MutableListIterator", "Sequence", "Comparator",
    # kotlin.text
    "Regex", "MatchResult", "StringBuilder",
})

def _kotlin_user_type_name(user_type_node, source: bytes) -> str | None:
    """Return the head identifier text from a Kotlin user_type node (without generics)."""
    if user_type_node is None:
        return None
    for c in user_type_node.children:
        if c.type == "type_identifier":
            text = _read_text(c, source)
            return text or None
        if c.type == "identifier":
            text = _read_text(c, source)
            return text or None
        if c.type == "simple_user_type":
            for sub in c.children:
                if sub.type in ("identifier", "type_identifier"):
                    text = _read_text(sub, source)
                    return text or None
    return None

def _kotlin_collect_type_refs(node, source: bytes, generic: bool, out: list[tuple[str, str]]) -> None:
    """Walk a Kotlin type expression; append (name, role) tuples."""
    if node is None:
        return
    t = node.type
    if t in ("integral_literal", "boolean_literal"):
        return
    if t == "user_type":
        for c in node.children:
            if c.type in ("identifier", "type_identifier"):
                text = _read_text(c, source)
                if text and text not in _KOTLIN_BUILTIN_TYPES and text not in _JAVA_BUILTIN_TYPES:
                    out.append((text, "generic_arg" if generic else "type"))
                break
            if c.type == "simple_user_type":
                for sub in c.children:
                    if sub.type in ("identifier", "type_identifier"):
                        text = _read_text(sub, source)
                        if text and text not in _KOTLIN_BUILTIN_TYPES and text not in _JAVA_BUILTIN_TYPES:
                            out.append((text, "generic_arg" if generic else "type"))
                        break
                break
        for c in node.children:
            if c.type == "type_arguments":
                for arg in c.children:
                    if arg.type == "type_projection":
                        for sub in arg.children:
                            if sub.is_named:
                                _kotlin_collect_type_refs(sub, source, True, out)
                    elif arg.is_named:
                        _kotlin_collect_type_refs(arg, source, True, out)
        return
    if t in ("identifier", "type_identifier"):
        text = _read_text(node, source)
        if text and text not in _KOTLIN_BUILTIN_TYPES and text not in _JAVA_BUILTIN_TYPES:
            out.append((text, "generic_arg" if generic else "type"))
        return
    if t in ("nullable_type", "parenthesized_type", "type_reference"):
        for c in node.children:
            if c.is_named:
                _kotlin_collect_type_refs(c, source, generic, out)
        return
    if node.is_named:
        for c in node.children:
            if c.is_named:
                _kotlin_collect_type_refs(c, source, generic, out)

def _kotlin_property_type_node(property_node):
    """Find the user_type node within a Kotlin property_declaration."""
    for c in property_node.children:
        if c.type == "variable_declaration":
            for sub in c.children:
                if sub.type in ("user_type", "nullable_type", "type_reference"):
                    return sub
        if c.type in ("user_type", "nullable_type", "type_reference"):
            return c
    return None

def _kotlin_function_return_type_node(func_node):
    """Find the return-type node of a Kotlin function_declaration (the type after `: ` post-params)."""
    saw_params = False
    saw_colon = False
    for c in func_node.children:
        if c.type == "function_value_parameters":
            saw_params = True
            continue
        if saw_params and c.type == ":":
            saw_colon = True
            continue
        if saw_colon:
            if c.is_named:
                return c
    return None

def _swift_declaration_keyword(node) -> str | None:
    """Return the leading kind token for a Swift class_declaration: class/struct/enum/extension/actor."""
    for c in node.children:
        if not c.is_named and c.type in ("class", "struct", "enum", "extension", "actor"):
            return c.type
    return None

def _swift_pre_scan(root_node, source: bytes) -> tuple[set[str], set[str]]:
    """Pre-scan a Swift compilation unit and return (protocol_names, class_like_names)."""
    protocols: set[str] = set()
    classes: set[str] = set()
    stack = [root_node]
    while stack:
        n = stack.pop()
        if n.type == "protocol_declaration":
            name_node = n.child_by_field_name("name")
            if name_node is None:
                for c in n.children:
                    if c.type == "type_identifier":
                        name_node = c
                        break
            if name_node is not None:
                text = _read_text(name_node, source)
                if text:
                    protocols.add(text)
        elif n.type == "class_declaration":
            kw = _swift_declaration_keyword(n)
            if kw in ("class", "struct", "enum", "actor"):
                name_node = n.child_by_field_name("name")
                if name_node is not None:
                    text = _read_text(name_node, source)
                    if text:
                        classes.add(text)
        stack.extend(n.children)
    return protocols, classes

def _swift_classify_base(name: str, kind: str | None, is_first: bool,
                          protocols: set[str], classes: set[str]) -> str:
    """Classify a Swift inheritance_specifier entry as `inherits` or `implements`."""
    if name in protocols:
        return "implements"
    if name in classes:
        return "inherits"
    # struct/enum/extension/actor cannot inherit a class — all conformances are protocols.
    if kind in ("struct", "enum", "extension", "actor"):
        return "implements"
    # `class`: first entry is conventionally the base class; subsequent are protocols.
    return "inherits" if is_first else "implements"

def _swift_user_type_name(user_type_node, source: bytes) -> str | None:
    """Return the head type_identifier text from a Swift user_type node (without generics)."""
    if user_type_node is None:
        return None
    for c in user_type_node.children:
        if c.type == "type_identifier":
            text = _read_text(c, source)
            return text or None
    return None

def _swift_collect_type_refs(node, source: bytes, generic: bool, out: list[tuple[str, str]]) -> None:
    """Walk a Swift type expression; append (name, role) tuples (role 'type' or 'generic_arg')."""
    if node is None:
        return
    t = node.type
    if t == "type_annotation":
        for c in node.children:
            if c.is_named:
                _swift_collect_type_refs(c, source, generic, out)
        return
    if t == "user_type":
        for c in node.children:
            if c.type == "type_identifier":
                text = _read_text(c, source)
                if text:
                    out.append((text, "generic_arg" if generic else "type"))
                break
        for c in node.children:
            if c.type == "type_arguments":
                for arg in c.children:
                    if arg.is_named:
                        _swift_collect_type_refs(arg, source, True, out)
        return
    if t == "type_identifier":
        text = _read_text(node, source)
        if text:
            out.append((text, "generic_arg" if generic else "type"))
        return
    if t in ("optional_type", "implicitly_unwrapped_optional_type", "array_type",
             "dictionary_type", "tuple_type"):
        for c in node.children:
            if c.is_named:
                _swift_collect_type_refs(c, source, generic, out)
        return
    if node.is_named:
        for c in node.children:
            if c.is_named:
                _swift_collect_type_refs(c, source, generic, out)

def _swift_property_type_node(property_node):
    """Return the type_annotation child of a Swift property_declaration, if any."""
    for c in property_node.children:
        if c.type == "type_annotation":
            return c
    return None

def _swift_property_name(property_node, source: bytes) -> str | None:
    """Return the bound name of a Swift property (``let x``/``var x = ...``)."""
    for c in property_node.children:
        if c.type == "pattern":
            for sc in c.children:
                if sc.type == "simple_identifier":
                    return _read_text(sc, source)
        if c.type == "simple_identifier":
            return _read_text(c, source)
    return None

def _swift_constructor_type(call_node, source: bytes) -> str | None:
    """If a Swift call expression is a constructor (``Foo()``), return the type name.

    Only upper-cased callees are treated as types so a free-function call like
    ``configure()`` in an initializer is not mistaken for a constructor.
    """
    first = call_node.children[0] if call_node.children else None
    if first is not None and first.type == "simple_identifier":
        text = _read_text(first, source)
        if text and text[:1].isupper():
            return text
    return None

def _swift_receiver_name(recv_node, source: bytes) -> str | None:
    """Return the depth-1 receiver name of a Swift member call (``recv.method()``).

    ``vm.update()`` -> ``vm``; ``Type.staticMethod()`` -> ``Type``;
    ``Singleton.shared.method()`` -> ``Singleton`` (head of the chain);
    ``self.svc.fetch()`` -> ``svc`` (the property the call is reached through).
    Returns None for anything deeper, so resolution stays depth-1.
    """
    if recv_node is None:
        return None
    if recv_node.type == "simple_identifier":
        return _read_text(recv_node, source)
    if recv_node.type == "navigation_expression":
        head = recv_node.children[0] if recv_node.children else None
        if head is not None and head.type == "simple_identifier":
            return _read_text(head, source)
        if head is not None and head.type == "self_expression":
            for child in recv_node.children:
                if child.type == "navigation_suffix":
                    for sc in child.children:
                        if sc.type == "simple_identifier":
                            return _read_text(sc, source)
    return None

_C_PRIMITIVE_TYPE_NODES = frozenset({
    "primitive_type", "sized_type_specifier", "auto", "placeholder_type_specifier",
})

def _c_collect_type_refs(node, source: bytes, generic: bool, out: list[tuple[str, str]]) -> None:
    """Walk a C type expression; append (name, role) tuples for user-defined types.
    Skips primitive types and qualifiers; recognises type_identifier."""
    if node is None or node.type in _C_PRIMITIVE_TYPE_NODES:
        return
    t = node.type
    if t == "type_identifier":
        text = _read_text(node, source)
        if text:
            out.append((text, "generic_arg" if generic else "type"))
        return
    if t in ("pointer_declarator", "reference_declarator", "array_declarator",
             "type_qualifier", "type_descriptor", "abstract_pointer_declarator",
             "abstract_reference_declarator", "abstract_array_declarator"):
        for c in node.children:
            if c.is_named:
                _c_collect_type_refs(c, source, generic, out)

def _cpp_collect_type_refs(node, source: bytes, generic: bool, out: list[tuple[str, str]]) -> None:
    """Walk a C++ type expression; append (name, role) tuples.
    Resolves qualified_identifier tails (std::string → string) and template_type
    base + arguments (std::vector<HttpClient> → vector + HttpClient as generic_arg)."""
    if node is None or node.type in _C_PRIMITIVE_TYPE_NODES:
        return
    t = node.type
    if t == "type_identifier":
        text = _read_text(node, source)
        if text:
            out.append((text, "generic_arg" if generic else "type"))
        return
    if t == "qualified_identifier":
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            _cpp_collect_type_refs(name_node, source, generic, out)
        return
    if t == "template_type":
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            text = _read_text(name_node, source)
            if text:
                out.append((text, "generic_arg" if generic else "type"))
        args_node = node.child_by_field_name("arguments")
        if args_node is not None:
            for c in args_node.children:
                if c.is_named:
                    _cpp_collect_type_refs(c, source, True, out)
        return
    if t in ("type_descriptor", "pointer_declarator", "reference_declarator",
             "array_declarator", "type_qualifier", "abstract_pointer_declarator",
             "abstract_reference_declarator", "abstract_array_declarator"):
        for c in node.children:
            if c.is_named:
                _cpp_collect_type_refs(c, source, generic, out)

def _scala_collect_type_refs(node, source: bytes, generic: bool, out: list[tuple[str, str]]) -> None:
    """Walk a Scala type expression; append (name, role) tuples.
    Handles type_identifier, generic_type (List[T]), and common type wrappers."""
    if node is None:
        return
    t = node.type
    if t == "type_identifier":
        text = _read_text(node, source)
        if text:
            out.append((text, "generic_arg" if generic else "type"))
        return
    if t == "generic_type":
        base = node.child_by_field_name("type")
        if base is None:
            for c in node.children:
                if c.type == "type_identifier":
                    base = c
                    break
        if base is not None and base.type == "type_identifier":
            text = _read_text(base, source)
            if text:
                out.append((text, "generic_arg" if generic else "type"))
        for c in node.children:
            if c.type == "type_arguments":
                for arg in c.children:
                    if arg.is_named:
                        _scala_collect_type_refs(arg, source, True, out)
        return
    if t in ("compound_type", "infix_type", "function_type", "tuple_type",
             "annotated_type", "projected_type"):
        for c in node.children:
            if c.is_named:
                _scala_collect_type_refs(c, source, generic, out)

def _python_collect_param_refs(params_node, source: bytes) -> list[tuple[str, str]]:
    """Collect type refs from each typed parameter under a `parameters` node."""
    out: list[tuple[str, str]] = []
    if params_node is None:
        return out
    for child in params_node.children:
        if child.type in ("typed_parameter", "typed_default_parameter"):
            type_node = child.child_by_field_name("type")
            _python_collect_type_refs(type_node, source, False, out)
    return out

def _python_param_names(params_node, source: bytes) -> set[str]:
    """Plain parameter identifiers declared on a Python `parameters` node.

    Covers positional/keyword params plus `*args` / `**kwargs` and typed or
    default forms — anything that binds a local name the function body can shadow
    a module-level definition with.
    """
    out: set[str] = set()
    if params_node is None:
        return out
    for child in params_node.children:
        if child.type == "identifier":
            out.add(_read_text(child, source))
        elif child.type in (
            "typed_parameter",
            "default_parameter",
            "typed_default_parameter",
            "list_splat_pattern",
            "dictionary_splat_pattern",
        ):
            # The bound name is the first identifier child (the rest is type/default).
            name_n = child.child_by_field_name("name")
            if name_n is None:
                name_n = next(
                    (c for c in child.children if c.type == "identifier"), None
                )
            if name_n is not None:
                out.add(_read_text(name_n, source))
    return out

def _python_collect_assignment_targets(node, source: bytes, out: set[str]) -> None:
    """Identifiers bound as `pattern` targets under a Python AST subtree.

    Recurses through `pattern_list` / `tuple_pattern` / `list_pattern` so tuple
    unpacking (`a, b = ...`, `for a, b in ...`) contributes every bound name.
    """
    if node is None:
        return
    if node.type == "identifier":
        out.add(_read_text(node, source))
        return
    if node.type in ("pattern_list", "tuple_pattern", "list_pattern"):
        for c in node.children:
            _python_collect_assignment_targets(c, source, out)

def _python_local_bound_names(func_def_node, source: bytes) -> set[str]:
    """Names bound LOCALLY inside a Python function: parameters plus assignment,
    `for`, `with ... as`, and comprehension targets.

    Used by the indirect-dispatch guard to reject a call-argument identifier that
    is a parameter or a local binding — it names a local value, not the module-
    level function/class that happens to share the name. Nested `function_definition`
    and `class_definition` subtrees are NOT descended into: their bindings belong
    to a different scope.
    """
    bound: set[str] = set()
    bound |= _python_param_names(func_def_node.child_by_field_name("parameters"), source)

    def walk(n) -> None:
        for child in n.children:
            t = child.type
            if t in ("function_definition", "class_definition", "lambda"):
                continue  # inner scope — its bindings are not this function's locals
            if t == "assignment":
                _python_collect_assignment_targets(
                    child.child_by_field_name("left"), source, bound
                )
            elif t in ("for_statement", "for_in_clause"):
                _python_collect_assignment_targets(
                    child.child_by_field_name("left"), source, bound
                )
            elif t == "with_statement":
                for item in child.children:
                    if item.type == "with_clause":
                        for wi in item.children:
                            if wi.type == "with_item":
                                alias = wi.child_by_field_name("alias")
                                _python_collect_assignment_targets(alias, source, bound)
            elif t == "named_expression":  # walrus :=
                _python_collect_assignment_targets(
                    child.child_by_field_name("name"), source, bound
                )
            walk(child)

    body = func_def_node.child_by_field_name("body")
    if body is not None:
        walk(body)
    return bound

def _python_module_bound_names(root, source: bytes) -> set[str]:
    """Names rebound by assignment at MODULE scope (top-level `x = ...`, `for`, walrus).

    The module-scope analogue of the per-function shadow set: a dispatch-table value
    whose name is reassigned to data at module level (`handler = build()`) names that
    value, not a same-named function, so it must not manufacture an indirect edge.
    Function and class bodies are not descended into — their bindings are local.
    """
    bound: set[str] = set()

    def walk(n) -> None:
        for child in n.children:
            t = child.type
            if t in ("function_definition", "class_definition", "lambda"):
                continue  # inner scope — not a module-level binding
            if t == "assignment":
                _python_collect_assignment_targets(
                    child.child_by_field_name("left"), source, bound
                )
            elif t in ("for_statement", "for_in_clause"):
                _python_collect_assignment_targets(
                    child.child_by_field_name("left"), source, bound
                )
            elif t == "named_expression":  # walrus :=
                _python_collect_assignment_targets(
                    child.child_by_field_name("name"), source, bound
                )
            walk(child)

    walk(root)
    return bound

_JS_SCOPE_BOUNDARY = frozenset({
    "function_declaration", "function_expression", "function", "arrow_function",
    "method_definition", "class_declaration", "class", "generator_function",
    "generator_function_declaration",
})

def _js_collect_pattern_idents(node, source: bytes, bound: set) -> None:
    """Collect binding identifier names from a JS/TS pattern (a parameter, or a
    declarator LHS). Recurses through destructuring (object/array patterns, rest)
    but never into the default-value side of `x = default` or a type annotation,
    so only names actually bound by the pattern are collected."""
    t = node.type
    if t in ("identifier", "shorthand_property_identifier_pattern"):
        bound.add(_read_text(node, source))
        return
    if t == "type_annotation":
        return  # `(h: Handler)` — Handler is a type, not a bound name
    if t == "assignment_pattern":  # `x = default` — only x is bound
        left = node.child_by_field_name("left")
        if left is not None:
            _js_collect_pattern_idents(left, source, bound)
        return
    if t == "pair_pattern":  # `{ a: localName }` — localName is bound
        val = node.child_by_field_name("value")
        if val is not None:
            _js_collect_pattern_idents(val, source, bound)
        return
    for c in node.children:
        if c.is_named:
            _js_collect_pattern_idents(c, source, bound)

def _js_local_bound_names(func_node, source: bytes) -> set[str]:
    """Names bound locally inside a JS/TS function: parameters plus `const`/`let`/
    `var` declarator targets. Mirrors `_python_local_bound_names`: an argument that
    is a parameter or local binding names a local value, not a same-named module
    function, so it must not manufacture an indirect_call edge. Nested function and
    class scopes are not descended into."""
    bound: set[str] = set()
    params = func_node.child_by_field_name("parameters")
    if params is not None:
        _js_collect_pattern_idents(params, source, bound)

    def walk(n) -> None:
        for c in n.children:
            if c.type in _JS_SCOPE_BOUNDARY:
                continue  # inner scope — its bindings are not this function's locals
            if c.type == "variable_declarator":
                name = c.child_by_field_name("name")
                if name is not None:
                    _js_collect_pattern_idents(name, source, bound)
            walk(c)

    body = func_node.child_by_field_name("body")
    if body is not None:
        walk(body)
    return bound

def _js_module_bound_names(root, source: bytes) -> set[str]:
    """Module-scope names rebound to NON-function data (`const X = {...}`, `let y = 5`).

    The JS/TS module-scope shadow set. Unlike the per-function set, a declarator
    whose value is itself a function (`const cb = () => {}`) is EXCLUDED: that name
    IS a callable we want dispatch tables to resolve to, not a data shadow.
    """
    bound: set[str] = set()

    def walk(n) -> None:
        for c in n.children:
            if c.type in _JS_SCOPE_BOUNDARY:
                continue
            if c.type == "variable_declarator":
                value = c.child_by_field_name("value")
                if value is None or value.type not in _JS_FUNCTION_VALUE_TYPES:
                    name = c.child_by_field_name("name")
                    if name is not None:
                        _js_collect_pattern_idents(name, source, bound)
            walk(c)

    walk(root)
    return bound

def _js_dispatch_value_idents(coll_node):
    """Yield identifier value-nodes of a JS/TS object/array literal that are
    function-reference candidates: object property VALUES and shorthand properties
    (`{ handler }`), and array elements. Keys and inline methods are not references."""
    if coll_node.type == "object":
        for c in coll_node.children:
            if c.type == "pair":
                val = c.child_by_field_name("value")
                if val is not None and val.type == "identifier":
                    yield val
            elif c.type == "shorthand_property_identifier":
                yield c
    else:  # array
        for el in coll_node.children:
            if el.type == "identifier":
                yield el

def _find_body(node, config: LanguageConfig):
    """Find the body node using config.body_field, falling back to child types."""
    b = node.child_by_field_name(config.body_field)
    if b:
        return b
    for child in node.children:
        if child.type in config.body_fallback_child_types:
            return child
    return None

def _dynamic_import_js(node, source: bytes, caller_nid: str, str_path: str, edges: list,
                       seen_dyn_pairs: set) -> bool:
    """Detect dynamic import() calls in JS/TS and emit imports_from edges.

    Handles patterns like:
      await import('./foo.js')
      import('./foo.js').then(...)
      const m = await import(`./foo`)

    Returns True if the node was a dynamic import (caller should skip normal call handling).
    """
    # Dynamic import is a call_expression whose function child is the keyword "import".
    # tree-sitter-typescript parses `import('...')` as call_expression with first child
    # being an "import" token (type="import").
    func_node = node.child_by_field_name("function")
    if func_node is None:
        # Fallback: check first child directly (some TS versions)
        if node.children and _read_text(node.children[0], source) == "import":
            func_node = node.children[0]
        else:
            return False
    if _read_text(func_node, source) != "import":
        return False

    # Extract the module path from the arguments
    args = node.child_by_field_name("arguments")
    if args is None:
        return True  # It's an import() but no args — skip
    for arg in args.children:
        if arg.type == "template_string":
            # Skip dynamic template literals — path can't be statically resolved
            if any(c.type == "template_substitution" for c in arg.children):
                break
            raw = _read_text(arg, source).strip("`")
        elif arg.type == "string":
            raw = _read_text(arg, source).strip("'\" ")
        else:
            continue
        if not raw:
            break
        # Resolve path using the same logic as static imports.
        resolved = _resolve_js_import_target(raw, str_path)
        if resolved is None:
            break
        tgt_nid, resolved_path = resolved
        pair = (caller_nid, tgt_nid)
        if pair not in seen_dyn_pairs:
            seen_dyn_pairs.add(pair)
            edge = {
                "source": caller_nid,
                "target": tgt_nid,
                # A deferred `import(...)` is a real dependency, so keep it as an
                # `imports_from` edge (visible in the graph) but mark it `deferred`
                # so find_import_cycles does not treat it as a static import and
                # report a phantom file cycle (#1241).
                "relation": "imports_from",
                "context": "import",
                "deferred": True,
                "confidence": "EXTRACTED",
                "source_file": str_path,
                "source_location": f"L{node.start_point[0] + 1}",
                "weight": 1.0,
            }
            # Key the target salt by the resolved target file so a same-basename
            # cross-extension sibling isn't mis-salted onto the importer (#1814).
            if resolved_path is not None:
                edge["target_file"] = str(resolved_path)
            edges.append(edge)
        break
    return True

def _get_cpp_func_name(node, source: bytes) -> str | None:
    """Recursively unwrap declarator to find the innermost identifier (C++)."""
    if node.type == "identifier":
        return _read_text(node, source)
    if node.type in ("field_identifier", "destructor_name", "operator_name"):
        return _read_text(node, source)
    if node.type == "qualified_identifier":
        # An out-of-class DEFINITION (`void Foo::bar() {}`) carries a
        # qualified_identifier declarator. Retaining the `Foo::` qualifier makes
        # _make_id(stem, "Foo::bar") normalize to the same id as the in-class
        # member _make_id(class_nid, "bar"), so the decl in Foo.h and the def in
        # Foo.cpp resolve to ONE method node instead of two (#1547). The full
        # qualified text also handles nested scopes (`A::B::bar`). Free functions
        # never have a qualified_identifier here, so their bare-name ids are
        # unchanged; only qualified definitions shift onto their owning class.
        return _read_text(node, source)
    decl = node.child_by_field_name("declarator")
    if decl:
        return _get_cpp_func_name(decl, source)
    for child in node.children:
        if child.type == "identifier":
            return _read_text(child, source)
    return None

def _cpp_declarator_name(node, source: bytes) -> str | None:
    """Return the bare variable name from a C++ declaration declarator, unwrapping
    pointer/reference/init wrappers (``*f``, ``&r``, ``f = Foo()``). Returns None
    for anything that isn't a plain named local (arrays, function pointers,
    structured bindings) so the type table never records a guessed receiver."""
    t = node.type
    if t == "identifier":
        return _read_text(node, source)
    if t in ("pointer_declarator", "reference_declarator", "init_declarator"):
        inner = node.child_by_field_name("declarator")
        if inner is None:
            for c in node.children:
                if c.type in ("identifier", "pointer_declarator",
                              "reference_declarator"):
                    inner = c
                    break
        if inner is not None:
            return _cpp_declarator_name(inner, source)
    return None

def _cpp_local_var_types(body_node, source: bytes, table: dict[str, str]) -> None:
    """Collect ``var -> ClassName`` from local variable declarations in a C++
    function body, for receiver-type inference in the cross-file member-call pass
    (#1547). Handles ``Foo f;``, ``Foo* f;``, ``Foo *f = ...;``, ``Foo f = Foo();``.

    Only a class-like (``type_identifier``/``qualified_identifier``) type with a
    single named declarator is recorded — PRECISION over recall: a built-in type
    (``int x``), an ambiguous multi-declarator line, or an un-nameable declarator
    contributes nothing rather than a guess. A qualified type ``ns::Foo`` records
    its simple tail ``Foo`` so it keys to the type's definition node label.
    """
    stack = [body_node]
    while stack:
        n = stack.pop()
        if n.type in ("function_definition", "lambda_expression"):
            # Don't descend into a nested function/lambda: its locals are scoped
            # away and would pollute this body's table.
            if n is not body_node:
                continue
        if n.type == "declaration":
            type_node = n.child_by_field_name("type")
            if type_node is not None and type_node.type in (
                "type_identifier", "qualified_identifier"
            ):
                type_name = _read_text(type_node, source).split("::")[-1].strip()
                declarators = [
                    c for c in n.children
                    if c.type in ("identifier", "pointer_declarator",
                                  "reference_declarator", "init_declarator")
                ]
                # A single declarator only: `Foo a, b;` is ambiguous to attribute
                # to one receiver name cleanly, so skip multi-declarator lines.
                if type_name and type_name[:1].isupper() and len(declarators) == 1:
                    var = _cpp_declarator_name(declarators[0], source)
                    if var and var not in table:
                        table[var] = type_name
        for c in n.children:
            stack.append(c)

def _swift_local_var_types(body_node, source: bytes, table: dict[str, str]) -> None:
    """Collect ``var -> Type`` from local ``let``/``var`` bindings in a Swift
    function body, so a member call on the local (``x.method()``) resolves to Type
    in the cross-file member-call pass (#1604).

    Two initializer shapes are recorded, PRECISION over recall:
      - a constructor call ``let x = Type()`` (``_swift_constructor_type``);
      - a static-member access ``let x = Type.shared`` (a navigation_expression
        with an upper-cased head) — the singleton-cached-into-a-local idiom, one
        of the most common Swift call patterns and previously resolved to nothing.
    Nested function declarations are not descended into (their locals are scoped
    away); the first binding for a name wins, so a class property of the same name
    already in the table is not overwritten.
    """
    stack = [body_node]
    while stack:
        n = stack.pop()
        if n.type == "function_declaration" and n is not body_node:
            continue
        if n.type == "property_declaration":
            prop_type: str | None = None
            for child in n.children:
                if child.type == "call_expression":
                    prop_type = _swift_constructor_type(child, source)
                    break
                if child.type == "navigation_expression":
                    head = child.children[0] if child.children else None
                    if head is not None and head.type == "simple_identifier":
                        htext = _read_text(head, source)
                        if htext and htext[:1].isupper():
                            prop_type = htext
                    break
            name = _swift_property_name(n, source)
            if name and prop_type and name not in table:
                table[name] = prop_type
        for c in n.children:
            stack.append(c)

def _csharp_member_type_table(root, source: bytes) -> dict[str, str]:
    """Collect ``name -> TypeName`` for C# receiver typing (#1609): class fields,
    properties, method parameters, and local variable declarations.

    File-scoped, first-binding-wins (like the C++ table): a field declared once at
    class scope is visible to every method's `field.Method()`, and a param/local
    shadowing the same name is a conservative approximation graphify already accepts
    for receiver typing. Only a resolvable, non-`var` type name is recorded; `var`
    without a `new T()` initializer, and predefined/lower-cased primitives, are
    skipped (precision over recall — an untypable receiver is left for the resolver
    to drop rather than guess). `var v = new T()` is typed from the object-creation.
    """
    table: dict[str, str] = {}

    def _typed(type_node) -> str | None:
        info = _read_csharp_type_name(type_node, source)
        if not info:
            return None
        name = info[0]
        # A genuine C# class name is Pascal-cased; skip predefined primitives
        # (int/bool/string) which never own a resolvable method definition here.
        return name if name and name[:1].isupper() else None

    def _decl_names(var_decl):
        for c in var_decl.children:
            if c.type == "variable_declarator":
                nm = c.child_by_field_name("name") or next(
                    (g for g in c.children if g.type == "identifier"), None)
                if nm is not None:
                    yield _read_text(nm, source), c

    def _new_type(declarator) -> str | None:
        # `var v = new Server()` — recover the type from the object_creation_expression.
        for g in declarator.children:
            if g.type == "object_creation_expression":
                return _typed(g.child_by_field_name("type"))
        return None

    stack = [root]
    while stack:
        n = stack.pop()
        t = n.type
        if t in ("field_declaration", "local_declaration_statement"):
            vd = next((c for c in n.children if c.type == "variable_declaration"), None)
            if vd is not None:
                type_node = vd.child_by_field_name("type")
                declared = _typed(type_node)
                for name, decl in _decl_names(vd):
                    resolved = declared or _new_type(decl)
                    if name and resolved and name not in table:
                        table[name] = resolved
        elif t == "property_declaration":
            nm = n.child_by_field_name("name")
            resolved = _typed(n.child_by_field_name("type"))
            if nm is not None and resolved:
                pname = _read_text(nm, source)
                if pname not in table:
                    table[pname] = resolved
        elif t == "parameter":
            nm = n.child_by_field_name("name")
            resolved = _typed(n.child_by_field_name("type"))
            if nm is not None and resolved:
                pname = _read_text(nm, source)
                if pname not in table:
                    table[pname] = resolved
        for c in n.children:
            stack.append(c)
    return table

def _ts_receiver_type_table(root, source: bytes, table: dict[str, str]) -> None:
    """Add TS/JS receiver bindings to ``table`` (name -> TypeName), for member-call
    resolution beyond the constructor-injected `this.field` case (#1630):

      * local ``const/let/var x = new Foo()`` -> ``x: Foo`` (Pattern A);
      * a type-annotated parameter ``(svc: Svc)`` -> ``svc: Svc`` (Pattern B), so a
        call on the param — including inside a returned closure — resolves.

    File-scoped, first-binding-wins (merged into the constructor-injection table,
    which is populated first and therefore wins on a name clash). Only a bare
    ``type_identifier`` (a single class/interface name) is recorded — an array,
    union, generic, qualified, or predefined type is skipped (precision over
    recall, matching the receiver-typed resolvers for Swift/C#/C++)."""
    def _bare_type_ident(type_annotation):
        # type_annotation -> ": T"; accept only a single type_identifier child.
        idents = [c for c in type_annotation.children if c.type == "type_identifier"]
        others = [c for c in type_annotation.children
                  if c.is_named and c.type not in ("type_identifier",)]
        if len(idents) == 1 and not others:
            return _read_text(idents[0], source)
        return None

    stack = [root]
    while stack:
        n = stack.pop()
        t = n.type
        if t == "variable_declarator":
            name_n = n.child_by_field_name("name")
            value = n.child_by_field_name("value")
            if (name_n is not None and name_n.type == "identifier"
                    and value is not None and value.type == "new_expression"):
                ctor = value.child_by_field_name("constructor")
                if ctor is not None and ctor.type in ("identifier", "type_identifier"):
                    name = _read_text(name_n, source)
                    tname = _read_text(ctor, source)
                    if name and tname and name not in table:
                        table[name] = tname
        elif t == "required_parameter" or t == "optional_parameter":
            pat = n.child_by_field_name("pattern")
            ann = n.child_by_field_name("type")
            if pat is not None and pat.type == "identifier" and ann is not None:
                tname = _bare_type_ident(ann)
                name = _read_text(pat, source)
                if name and tname and name not in table:
                    table[name] = tname
        for c in n.children:
            stack.append(c)

def _find_require_call(value_node):
    """Return the call_expression node if `value_node` is a `require(...)` call
    or `require(...).x` member access. Otherwise None."""
    if value_node is None:
        return None
    if value_node.type == "call_expression":
        fn = value_node.child_by_field_name("function")
        if fn is not None and fn.type == "identifier":
            return value_node
    if value_node.type == "member_expression":
        obj = value_node.child_by_field_name("object")
        return _find_require_call(obj)
    return None

def _require_imports_js(node, source: bytes, file_nid: str, stem: str, edges: list, str_path: str) -> bool:
    """Detect CommonJS require imports inside lexical_declaration / variable_declaration.

    Handles three patterns:
      const { foo, bar } = require('./mod')   → file → mod (imports_from), file → foo, file → bar
      const mod         = require('./mod')   → file → mod (imports_from)
      const x           = require('./mod').y → file → mod (imports_from), file → y

    Returns True if any require import was found.
    """
    if node.type not in ("lexical_declaration", "variable_declaration"):
        return False
    found = False
    for child in node.children:
        if child.type != "variable_declarator":
            continue
        value = child.child_by_field_name("value")
        call = _find_require_call(value)
        if call is None:
            continue
        fn = call.child_by_field_name("function")
        if fn is None or _read_text(fn, source) != "require":
            continue
        args = call.child_by_field_name("arguments")
        if args is None:
            continue
        raw = None
        for arg in args.children:
            if arg.type == "string":
                raw = _read_text(arg, source).strip("'\"` ")
                break
        if not raw:
            continue
        resolved = _resolve_js_import_target(raw, str_path)
        if resolved is None:
            continue
        tgt_nid, resolved_path = resolved
        line = node.start_point[0] + 1
        edge = {
            "source": file_nid,
            "target": tgt_nid,
            "relation": "imports_from",
            "context": "import",
            "confidence": "EXTRACTED",
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        }
        # Key the target salt by the resolved target file so a same-basename
        # cross-extension sibling isn't mis-salted onto the importer (#1814).
        if resolved_path is not None:
            edge["target_file"] = str(resolved_path)
        edges.append(edge)
        found = True

        # Symbol-level edges for destructured / accessor binders.
        target_stem = _file_stem(resolved_path) if resolved_path is not None else None
        name_node = child.child_by_field_name("name")
        sym_names: list[str] = []
        if name_node is not None and name_node.type == "object_pattern":
            # `const { a, b: alias } = require('./m')` — emit edges for each property key
            for prop in name_node.children:
                if prop.type == "shorthand_property_identifier_pattern":
                    sym_names.append(_read_text(prop, source))
                elif prop.type == "pair_pattern":
                    key = prop.child_by_field_name("key")
                    if key is not None:
                        sym_names.append(_read_text(key, source))
        elif value is not None and value.type == "member_expression":
            # `const x = require('./m').y` — symbol is the property accessed
            prop = value.child_by_field_name("property")
            if prop is not None:
                sym_names.append(_read_text(prop, source))
        if target_stem is not None:
            for sym in sym_names:
                edges.append({
                    "source": file_nid,
                    "target": _make_id(target_stem, sym),
                    "relation": "imports",
                    "context": "import",
                    "confidence": "EXTRACTED",
                    "source_file": str_path,
                    "source_location": f"L{line}",
                    "weight": 1.0,
                })
    return found

_JS_FUNCTION_VALUE_TYPES = frozenset({"arrow_function", "function_expression", "function", "generator_function"})

def _js_member_assignment_target(left, source: bytes):
    """Classify the symbol an `assignment_expression` LHS defines when its RHS
    is a function. Returns (kind, owner_name, member_name) or None.

      this.foo = fn            → ("this",      None,  "foo")
      exports.foo = fn         → ("exports",   None,  "foo")
      module.exports.foo = fn  → ("exports",   None,  "foo")
      Foo.prototype.bar = fn   → ("prototype", "Foo", "bar")

    Any other shape (an arbitrary `obj.x = fn`) returns None and is skipped —
    capturing those would reintroduce the bare-named / phantom-god-node class
    of bug the module-level scope guard (#1077) exists to prevent.
    """
    if left is None or left.type != "member_expression":
        return None
    prop = left.child_by_field_name("property")
    if prop is None:
        return None
    member_name = _read_text(prop, source)
    if not member_name:
        return None
    obj = left.child_by_field_name("object")
    if obj is None:
        return None
    if obj.type == "this":
        return ("this", None, member_name)
    if obj.type == "identifier":
        if _read_text(obj, source) == "exports":
            return ("exports", None, member_name)
        return None
    if obj.type == "member_expression":
        # module.exports.X  or  Foo.prototype.X
        inner_obj = obj.child_by_field_name("object")
        inner_prop = obj.child_by_field_name("property")
        if inner_obj is None or inner_prop is None:
            return None
        inner_prop_name = _read_text(inner_prop, source)
        if inner_obj.type == "identifier":
            inner_obj_name = _read_text(inner_obj, source)
            if inner_obj_name == "module" and inner_prop_name == "exports":
                return ("exports", None, member_name)
            if inner_prop_name == "prototype":
                return ("prototype", inner_obj_name, member_name)
    return None

def _js_extra_walk(node, source: bytes, file_nid: str, stem: str, str_path: str,
                   nodes: list, edges: list, seen_ids: set, function_bodies: list,
                   parent_class_nid: str | None, add_node_fn, add_edge_fn,
                   callable_def_nids: set | None = None,
                   local_bound_names: dict | None = None) -> bool:
    """Handle lexical_declaration (arrow functions, CJS requires, module-level const literals) for JS/TS. Returns True if handled."""
    # CommonJS / prototype member assignments whose value is a function:
    #   exports.X = () => {}     → file-contained function  X()
    #   module.exports.X = fn    → file-contained function  X()
    #   Foo.prototype.bar = fn   → method bar() owned by Foo
    # (`this.X = fn` lives inside a function body, which is not recursed here;
    #  it is captured at the enclosing function — see the function branch.)
    if node.type == "expression_statement":
        assign = next((c for c in node.children
                       if c.type == "assignment_expression"), None)
        if assign is not None:
            value = assign.child_by_field_name("right")
            if value is not None and value.type in _JS_FUNCTION_VALUE_TYPES:
                target = _js_member_assignment_target(
                    assign.child_by_field_name("left"), source)
                if target is not None:
                    kind, owner_name, member_name = target
                    line = node.start_point[0] + 1
                    handled = False
                    if kind == "exports":
                        nid = _make_id(stem, member_name)
                        add_node_fn(nid, f"{member_name}()", line)
                        add_edge_fn(file_nid, nid, "contains", line)
                        handled = True
                    elif kind == "prototype":
                        owner_nid = _make_id(stem, owner_name)
                        nid = _make_id(owner_nid, member_name)
                        add_node_fn(nid, f".{member_name}()", line)
                        add_edge_fn(owner_nid, nid, "method", line)
                        handled = True
                    if handled:
                        if callable_def_nids is not None:
                            callable_def_nids.add(nid)  # CJS/prototype fn is callable
                        if local_bound_names is not None:
                            local_bound_names[nid] = _js_local_bound_names(value, source)
                        body = value.child_by_field_name("body")
                        if body:
                            function_bodies.append((nid, body))
                        return True

    # Class fields whose value is a function:
    #   class C { handler = () => {} }   → method handler() owned by C
    # Reaches here with parent_class_nid set because class bodies are recursed
    # with the class nid as parent.
    if parent_class_nid and node.type in ("field_definition", "public_field_definition"):
        prop = node.child_by_field_name("property") or node.child_by_field_name("name")
        value = node.child_by_field_name("value")
        if (prop is not None and value is not None
                and value.type in _JS_FUNCTION_VALUE_TYPES):
            field_name = _read_text(prop, source)
            if field_name:
                line = node.start_point[0] + 1
                nid = _make_id(parent_class_nid, field_name)
                add_node_fn(nid, f".{field_name}()", line)
                add_edge_fn(parent_class_nid, nid, "method", line)
                if callable_def_nids is not None:
                    callable_def_nids.add(nid)  # arrow class-field is callable
                if local_bound_names is not None:
                    local_bound_names[nid] = _js_local_bound_names(value, source)
                body = value.child_by_field_name("body")
                if body:
                    function_bodies.append((nid, body))
                return True

    if node.type in ("lexical_declaration", "variable_declaration"):
        # CJS require imports — emit edges, do not block other lexical_declaration handling
        require_found = _require_imports_js(node, source, file_nid, stem, edges, str_path)

        # Scope guard (#1077): only emit nodes for module-level declarations.
        # Without this, `const x = ...` inside an arrow callback (e.g. inside
        # `describe(() => { const set = new Set(...) })`) emits a bare-named
        # node, and the same name collides across unrelated files producing
        # phantom god-nodes. Bodies of arrow functions are walked separately
        # via function_bodies, so we never need to emit nodes for locals here.
        parent = node.parent
        is_module_level = parent is not None and (
            parent.type == "program"
            or (parent.type == "export_statement"
                and parent.parent is not None
                and parent.parent.type == "program")
        )

        # Arrow function declarations and module-level const literals (lexical_declaration only)
        arrow_found = False
        const_found = False
        if node.type == "lexical_declaration" and is_module_level:
            for child in node.children:
                if child.type == "variable_declarator":
                    value = child.child_by_field_name("value")
                    if value and value.type in _JS_FUNCTION_VALUE_TYPES:
                        # `const f = () => {}` and `const f = function(){}`
                        name_node = child.child_by_field_name("name")
                        if name_node:
                            func_name = _read_text(name_node, source)
                            line = child.start_point[0] + 1
                            # A name that normalizes to nothing (e.g. minified `$`)
                            # would collapse the id to the absolute file-stem and
                            # leak the scan path (#1899); skip it (no graph signal).
                            if not normalize_id(func_name):
                                continue
                            func_nid = _make_id(stem, func_name)
                            add_node_fn(func_nid, f"{func_name}()", line)
                            add_edge_fn(file_nid, func_nid, "contains", line)
                            if callable_def_nids is not None:
                                callable_def_nids.add(func_nid)  # `const f = () =>` is callable
                            if local_bound_names is not None:
                                local_bound_names[func_nid] = _js_local_bound_names(value, source)
                            body = value.child_by_field_name("body")
                            if body:
                                function_bodies.append((func_nid, body))
                            arrow_found = True
                    elif value and value.type in (
                        "object", "array", "as_expression", "call_expression", "new_expression",
                    ):
                        # Module-level const with literal/object/array/factory value
                        name_node = child.child_by_field_name("name")
                        if name_node:
                            const_name = _read_text(name_node, source)
                            line = child.start_point[0] + 1
                            const_nid = _make_id(stem, const_name)
                            add_node_fn(const_nid, const_name, line)
                            add_edge_fn(file_nid, const_nid, "contains", line)
                            const_found = True
        if arrow_found:
            return True
        if const_found:
            return True
        if require_found:
            return True
    return False

def _ts_extra_walk(node, source: bytes, file_nid: str, stem: str, str_path: str,
                   nodes: list, edges: list, seen_ids: set, function_bodies: list,
                   parent_class_nid: str | None, add_node_fn, add_edge_fn,
                   walk_fn) -> bool:
    """Emit a container node for a TS `namespace`/`module` declaration.

    `namespace Foo {}` parses as `internal_module` (with `name`/`body` fields);
    `module Bar {}` and ambient `declare module "pkg" {}` parse as a named
    `module` node that exposes no fields, so its name and body are found
    positionally. Without this the container was never a node — its members were
    still reached by the default recurse but lost their namespace context. The
    members stay file-contained (parity with C#'s `_csharp_extra_walk`); the
    namespace becomes a sibling marker node so it is queryable. Returns True if
    handled.

    The guard requires `is_named` because the anonymous `module` keyword token
    shares the `module` type string and would otherwise match here.
    """
    if node.is_named and node.type in ("internal_module", "module"):
        name_node = node.child_by_field_name("name")
        if name_node is None:
            for child in node.children:
                if child.is_named and child.type in (
                        "identifier", "nested_identifier", "string"):
                    name_node = child
                    break
        body = node.child_by_field_name("body")
        if body is None:
            for child in node.children:
                if child.type == "statement_block":
                    body = child
                    break
        if name_node is not None:
            ns_name = _read_text(name_node, source)
            if name_node.type == "string":
                ns_name = ns_name.strip("'\"`")
            if ns_name:
                ns_nid = _make_id(stem, ns_name)
                line = node.start_point[0] + 1
                add_node_fn(ns_nid, ns_name, line)
                add_edge_fn(file_nid, ns_nid, "contains", line)
        if body is not None:
            for child in body.children:
                walk_fn(child, parent_class_nid)
        return True
    return False

def _csharp_namespace_name(node, source: bytes) -> str:
    name_node = node.child_by_field_name("name")
    if name_node is not None:
        return _read_text(name_node, source).strip()
    for child in node.children:
        if child.type in ("identifier", "qualified_name"):
            return _read_text(child, source).strip()
    return ""

def _csharp_extra_walk(node, source: bytes, file_nid: str, stem: str, str_path: str,
                       nodes: list, edges: list, seen_ids: set, function_bodies: list,
                       parent_class_nid: str | None, add_node_fn, add_edge_fn,
                       walk_fn, namespace_stack: list[str], scope_stack: list[str]) -> bool:
    """Handle namespace declarations for C#. Returns True if handled."""
    if node.type == "namespace_declaration":
        ns_name = _csharp_namespace_name(node, source)
        pushed = False
        if ns_name:
            namespace_stack.append(ns_name)
            scope_stack.append(f"s{node.start_byte}")
            pushed = True
            ns_label = ".".join(namespace_stack)
            ns_nid = _csharp_namespace_id(ns_label)
            line = node.start_point[0] + 1
            add_node_fn(ns_nid, ns_label, line, node_type="namespace", metadata={"kind": "csharp_namespace"})
            add_edge_fn(file_nid, ns_nid, "contains", line)
        body = node.child_by_field_name("body")
        if body:
            try:
                for child in body.children:
                    walk_fn(child, parent_class_nid)
            finally:
                if pushed:
                    namespace_stack.pop()
                    scope_stack.pop()
        elif pushed:
            namespace_stack.pop()
            scope_stack.pop()
        return True
    if node.type == "file_scoped_namespace_declaration":
        ns_name = _csharp_namespace_name(node, source)
        if ns_name:
            namespace_stack.append(ns_name)
            scope_stack.append(f"s{node.start_byte}")
            ns_label = ".".join(namespace_stack)
            ns_nid = _csharp_namespace_id(ns_label)
            line = node.start_point[0] + 1
            add_node_fn(ns_nid, ns_label, line, node_type="namespace", metadata={"kind": "csharp_namespace"})
            add_edge_fn(file_nid, ns_nid, "contains", line)
        return True
    return False

def _swift_extra_walk(node, source: bytes, file_nid: str, stem: str, str_path: str,
                      nodes: list, edges: list, seen_ids: set, function_bodies: list,
                      parent_class_nid: str | None, add_node_fn, add_edge_fn,
                      ensure_named_node_fn) -> bool:
    """Handle enum_entry for Swift. Returns True if handled."""
    if node.type == "enum_entry" and parent_class_nid:
        line = node.start_point[0] + 1
        for child in node.children:
            if child.type == "simple_identifier":
                case_name = _read_text(child, source)
                case_nid = _make_id(parent_class_nid, case_name)
                add_node_fn(case_nid, case_name, line)
                add_edge_fn(parent_class_nid, case_nid, "case_of", line)
        # Associated-value types nest as `enum_type_parameters -> user_type ->
        # type_identifier` (a sibling of the case-name simple_identifier). The
        # case-name loop above never descends into them, so `case started(Session)`
        # used to drop the Event -> Session reference entirely. Mirror the Swift
        # property/parameter emit style: collect the type refs and emit a
        # `references` edge from the ENUM node to each collected type.
        for child in node.children:
            if child.type != "enum_type_parameters":
                continue
            for grand in child.children:
                if not grand.is_named:
                    continue
                refs: list[tuple[str, str]] = []
                _swift_collect_type_refs(grand, source, False, refs)
                for ref_name, role in refs:
                    ctx = "generic_arg" if role == "generic_arg" else "type"
                    target_nid = ensure_named_node_fn(ref_name, line)
                    if target_nid != parent_class_nid:
                        add_edge_fn(parent_class_nid, target_nid, "references",
                                    line, context=ctx)
        return True
    return False

def _java_extra_walk(node, source: bytes, file_nid: str, stem: str, str_path: str,
                     nodes: list, edges: list, seen_ids: set, function_bodies: list,
                     parent_class_nid: str | None, add_node_fn, add_edge_fn,
                     walk_fn) -> bool:
    """Handle enum_constant for Java. Returns True if handled."""
    if node.type == "enum_constant" and parent_class_nid:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return True
        const_name = _read_text(name_node, source)
        line = node.start_point[0] + 1
        const_nid = _make_id(parent_class_nid, const_name)
        add_node_fn(const_nid, const_name, line)
        add_edge_fn(parent_class_nid, const_nid, "case_of", line)
        # Anonymous-body constants (`MONDAY { void greet(){} }`): descend so the
        # body's methods aren't dropped; const_nid attaches them to the constant.
        for child in node.children:
            if child.type == "class_body":
                for member in child.children:
                    walk_fn(member, parent_class_nid=const_nid)
        return True
    return False


def _kotlin_extra_walk(node, source: bytes, file_nid: str, stem: str, str_path: str,
                       nodes: list, edges: list, seen_ids: set, function_bodies: list,
                       parent_class_nid: str | None, add_node_fn, add_edge_fn,
                       walk_fn) -> bool:
    """Handle enum_entry for Kotlin. Returns True if handled (#1700 Kotlin half)."""
    if node.type == "enum_entry" and parent_class_nid:
        name_node = None
        for child in node.children:
            if child.type in ("simple_identifier", "identifier"):
                name_node = child
                break
        if name_node is None:
            return True
        const_name = _read_text(name_node, source)
        line = node.start_point[0] + 1
        const_nid = _make_id(parent_class_nid, const_name)
        add_node_fn(const_nid, const_name, line)
        add_edge_fn(parent_class_nid, const_nid, "case_of", line)
        for child in node.children:
            if child.type == "class_body":
                for member in child.children:
                    walk_fn(member, parent_class_nid=const_nid)
        return True
    return False


def _read_csharp_type_name(node, source: bytes) -> tuple[str, bool, str] | None:
    """Resolve a C# type name, whether it was qualified, and its qualifier prefix."""
    if node is None:
        return None
    if node.type in ("identifier", "predefined_type"):
        return (_read_text(node, source), False, "")
    if node.type == "qualified_name":
        prefix, _, tail = _read_text(node, source).rpartition(".")
        tail = tail.split("<", 1)[0]
        return (tail, True, prefix)
    if node.type == "generic_name":
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            qualified = name_node.type == "qualified_name"
            prefix, _, tail = _read_text(name_node, source).rpartition(".")
            return (tail, qualified, prefix if qualified else "")
    for child in node.children:
        if not child.is_named:
            continue
        result = _read_csharp_type_name(child, source)
        if result:
            return result
    return None

def _ruby_new_class_name(node, source: bytes) -> str | None:
    """Return ``ClassName`` if ``node`` is a ``ClassName.new(...)`` call, else None.

    Only a bare capitalized constant receiver counts (``Processor.new``);
    namespaced (``A::B.new``) and dynamic receivers are intentionally ignored so
    the binding stays unambiguous.
    """
    if node is None or node.type != "call":
        return None
    recv = node.child_by_field_name("receiver")
    meth = node.child_by_field_name("method")
    if recv is None or meth is None:
        return None
    if recv.type != "constant" or _read_text(meth, source) != "new":
        return None
    return _read_text(recv, source)

def _ruby_local_class_bindings(body_node, source: bytes) -> dict[str, str | None]:
    """Map ``local_var -> ClassName`` for ``var = ClassName.new`` within one Ruby
    method body, not descending into nested method definitions.

    100%-confidence contract: a variable assigned more than once, or to anything
    other than a single ``Constant.new``, maps to ``None`` (ambiguous) so callers
    never resolve it. Only the certain single-binding case carries a type.
    """
    bindings: dict[str, str | None] = {}
    boundary = {"method", "singleton_method"}

    def visit(n) -> None:
        for child in n.children:
            if child.type in boundary:
                continue  # nested method has its own scope
            if child.type == "assignment":
                left = child.child_by_field_name("left")
                right = child.child_by_field_name("right")
                if left is not None and left.type == "identifier":
                    var = _read_text(left, source)
                    cls = _ruby_new_class_name(right, source) if right is not None else None
                    if cls is None:
                        # assigned to something we can't type: poison if it was typed
                        if var in bindings:
                            bindings[var] = None
                    elif var in bindings:
                        if bindings[var] != cls:
                            bindings[var] = None  # reassigned to a different class
                    else:
                        bindings[var] = cls
            visit(child)

    visit(body_node)
    return bindings

def _ruby_const_last_name(node, source: bytes) -> str:
    """Last constant of a ``constant`` or ``scope_resolution`` (``A::B::C`` -> ``C``)."""
    if node is None:
        return ""
    if node.type == "constant":
        return _read_text(node, source)
    if node.type == "scope_resolution":
        consts = [c for c in node.children if c.type == "constant"]
        if consts:
            return _read_text(consts[-1], source)
    return ""

_RUBY_CLASS_FACTORIES = frozenset({("Struct", "new"), ("Class", "new"), ("Data", "define")})

def _ruby_extra_walk(node, source: bytes, file_nid: str, stem: str, str_path: str,
                     nodes: list, edges: list, seen_ids: set, function_bodies: list,
                     parent_class_nid: str | None, add_node, add_edge, walk,
                     callable_def_nids: set) -> bool:
    """Ruby: a constant assignment whose RHS is ``Struct.new(...)``,
    ``Class.new(Super)`` or ``Data.define(...)`` defines a class named after the
    constant (#1640). Synthesize the class node, attach block-defined methods via
    ``method`` (by recursing the block with the new node as parent), and emit an
    ``inherits`` edge for ``Class.new(Super)``. Returns True if handled.
    """
    if node.type != "assignment":
        return False
    left = node.child_by_field_name("left")
    right = node.child_by_field_name("right")
    if left is None or right is None or left.type != "constant" or right.type != "call":
        return False
    recv = right.child_by_field_name("receiver")
    meth = right.child_by_field_name("method")
    if recv is None or meth is None or recv.type != "constant":
        return False
    if (_read_text(recv, source), _read_text(meth, source)) not in _RUBY_CLASS_FACTORIES:
        return False

    const_name = _read_text(left, source)
    if not const_name:
        return False
    line = node.start_point[0] + 1
    class_nid = _make_id(stem, const_name)
    add_node(class_nid, const_name, line)
    callable_def_nids.add(class_nid)  # a class is callable (its constructor)
    # Mirror the generic class branch: containment always hangs off the file node.
    add_edge(file_nid, class_nid, "contains", line)

    # `Class.new(Super)` — the first positional constant argument is the superclass.
    if _read_text(recv, source) == "Class":
        args = next((c for c in right.children if c.type == "argument_list"), None)
        if args is not None:
            for arg in args.children:
                if arg.type in ("constant", "scope_resolution"):
                    base = _ruby_const_last_name(arg, source)
                    if base:
                        base_nid = _make_id(stem, base)
                        if base_nid not in seen_ids:
                            base_nid = _make_id(base)
                            if base_nid not in seen_ids:
                                # origin_file lets _disambiguate_colliding_node_ids
                                # tell this file's unresolved reference apart from
                                # another file's same-named one, instead of every
                                # file's stub collapsing onto one shared bare id
                                # (see ensure_named_node(), which sets the same
                                # field for this exact reason).
                                nodes.append({
                                    "id": base_nid, "label": base,
                                    "file_type": "code", "source_file": "",
                                    "source_location": "", "origin_file": str_path,
                                })
                                seen_ids.add(base_nid)
                        add_edge(class_nid, base_nid, "inherits", line)
                    break

    # Recurse the do/brace block so block-defined methods attach to the class.
    # The block wraps its statements in a `body_statement` (like a class body);
    # descend into it so the method handler sees parent_class_nid — otherwise the
    # default recurse resets the parent to None and the method hangs off the file
    # with a dot-less label.
    block = next((c for c in right.children if c.type in ("do_block", "block")), None)
    if block is not None:
        body = next((c for c in block.children if c.type == "body_statement"), block)
        for child in body.children:
            walk(child, parent_class_nid=class_nid)
    return True

def _extract_generic(
    path: Path, config: LanguageConfig, *, source_override: bytes | None = None
) -> dict:
    """Generic AST extractor driven by LanguageConfig.

    ``source_override`` parses the given bytes instead of reading ``path``, while
    still keying nodes/edges off ``path``. Lets container formats (e.g. Vue SFCs)
    mask the wrapper and parse just the embedded ``<script>``.
    """
    try:
        mod = importlib.import_module(config.ts_module)
        from tree_sitter import Language, Parser
        lang_fn = getattr(mod, config.ts_language_fn, None)
        if lang_fn is None:
            # Fallback for PHP: try "language_php" then "language"
            lang_fn = getattr(mod, "language", None)
        if lang_fn is None:
            return {"nodes": [], "edges": [], "error": f"No language function in {config.ts_module}"}
        language = Language(lang_fn())
    except ImportError:
        return {"nodes": [], "edges": [], "error": f"{config.ts_module} not installed"}
    except TypeError as e:
        # tree-sitter version mismatch: old Language() expects (lib_path),
        # new Language() expects (language_capsule, name). Surface a hint
        # so users see the upgrade path instead of a bare TypeError.
        hint = (
            f"tree-sitter version mismatch for {config.ts_module}: {e}. "
            "Try: pip install --upgrade tree-sitter tree-sitter-languages"
        )
        return {"nodes": [], "edges": [], "error": hint}
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    try:
        parser = Parser(language)
        source = path.read_bytes() if source_override is None else source_override
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    namespace_stack: list[str] = []
    scope_stack: list[str] = []
    function_bodies: list[tuple[str, object]] = []
    # nids of function / method / class definitions in this file. The indirect-
    # dispatch guard (Python) resolves a call-argument identifier to an edge only
    # when it names one of these callable defs — never an arbitrary same-named
    # node — so `process(config)` can't manufacture an edge to a non-callable.
    callable_def_nids: set[str] = set()
    # Python only: per-function set of locally-bound names (params + local
    # assignment / for / with-as / comprehension targets). The indirect-dispatch
    # guard skips any call-argument identifier in the enclosing function's set,
    # so a param/local that shadows a module function name yields no edge.
    local_bound_names: dict[str, set[str]] = {}
    pending_listen_edges: list[tuple[str, str, int]] = []
    # tree-sitter-swift parses both `class Foo` and `extension Foo` as
    # `class_declaration`. Same-file pairs collapse via seen_ids, but cross-file
    # extensions don't (file stem is part of the id), so they're collected here
    # for a corpus-level merge after every file has been parsed.
    swift_extensions: list[dict] = []
    # #1356: call expressions in property/field initializers (e.g.
    # `let vm = VM()`) live outside function bodies, so the call-walk never
    # reaches them. Collect (owner_nid, call_node) here and walk them too.
    initializer_nodes: list[tuple[str, object]] = []
    # Ruby include/extend/prepend mixins collected during the node walk (#1668),
    # merged into raw_calls after the call-walk populates it (raw_calls does not
    # exist yet while walk() runs). Resolved cross-file by the Ruby resolver.
    _ruby_mixin_calls: list[dict] = []
    # #1356: per-file map of local name -> declared type (properties + params),
    # threaded out as `swift_type_table` so member calls (`vm.update()`) can be
    # resolved to the receiver's real definition in _resolve_swift_member_calls.
    type_table: dict[str, str] = {}
    # Java receiver typing is method-scoped: current-class fields are shared,
    # while parameters and locals belong only to their declaring method.
    java_field_types: dict[str, dict[str, str]] = {}
    java_method_scopes: dict[int, tuple[object, str]] = {}

    csharp_interface_names: set[str] = set()
    if config.ts_module == "tree_sitter_c_sharp":
        csharp_interface_names = _csharp_pre_scan_interfaces(root, source)

    swift_protocol_names: set[str] = set()
    swift_class_names: set[str] = set()
    if config.ts_module == "tree_sitter_swift":
        swift_protocol_names, swift_class_names = _swift_pre_scan(root, source)

    def add_node(nid: str, label: str, line: int, *, node_type: str | None = None,
                 metadata: dict | None = None) -> None:
        if nid in seen_ids:
            return
        seen_ids.add(nid)
        merged = dict(metadata or {})
        if namespace_stack:
            merged.setdefault("namespace", ".".join(namespace_stack))
        if scope_stack and node_type != "namespace":
            merged.setdefault("scope_chain", list(scope_stack))
        node = {
            "id": nid,
            "label": label,
            "file_type": "code",
            "source_file": str_path,
            "source_location": f"L{line}",
        }
        if node_type:
            node["type"] = node_type
        if merged:
            node["metadata"] = sanitize_metadata(merged)
        nodes.append(node)

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0,
                 context: str | None = None,
                 metadata: dict | None = None) -> None:
        edge = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        }
        if context:
            edge["context"] = context
        if metadata:
            edge["metadata"] = sanitize_metadata(metadata)
        edges.append(edge)

    def ensure_named_node(name: str, line: int) -> str:
        nid = _make_id(stem, ".".join(namespace_stack), name)
        if nid in seen_ids:
            return nid
        nid = _make_id(name)
        if nid not in seen_ids:
            # The name isn't defined in this file, so this is a cross-file reference
            # (e.g. a `Thing` type annotation imported from another module). Emit a
            # SOURCELESS stub — like the inheritance-base path below — so the
            # corpus-level rewire can collapse it onto the real definition. A sourced
            # stub here makes _disambiguate_colliding_node_ids bake the referencing
            # file's path (with extension) into the id and blocks the rewire, which is
            # the phantom-duplicate-node bug (#1402).
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": name,
                "file_type": "code",
                "source_file": "",
                "source_location": "",
                "origin_file": str_path,
            })
        return nid

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def walk(node, parent_class_nid: str | None = None) -> None:
        t = node.type

        # Import types
        if t in config.import_types:
            if config.import_handler:
                imported_modules = config.import_handler(node, source, file_nid, stem, edges, str_path, scope_stack)
                # Module-level import handlers (Swift) name a module, not a file
                # path, so there is no pre-existing node to anchor the edge to.
                # They return (id, label) pairs for which we materialize a
                # `type=module` node; otherwise build_from_json prunes every such
                # import edge as a dangling/external reference. The same module
                # imported from N files shares one id (file_type=code keeps
                # build.py validation happy; `type=module` exempts it from
                # id-disambiguation) so it collapses to one shared node (#1327).
                if imported_modules:
                    line = node.start_point[0] + 1
                    for mod_nid, mod_label in imported_modules:
                        if mod_nid not in seen_ids:
                            seen_ids.add(mod_nid)
                            nodes.append({
                                "id": mod_nid,
                                "label": mod_label,
                                "file_type": "code",
                                "type": "module",
                                "source_file": str_path,
                                "source_location": f"L{line}",
                            })
            # For export_statement: only return (skip children) if it's a re-export
            # (has a `from` source). Otherwise fall through to walk children which may
            # contain function_declaration, class_declaration, etc.
            if t == "export_statement":
                has_source = any(c.type == "string" for c in node.children)
                if not has_source:
                    for child in node.children:
                        walk(child, parent_class_nid)
            return

        # Class types
        if t in config.class_types:
            # Resolve class name
            name_node = node.child_by_field_name(config.name_field)
            if name_node is None:
                for child in node.children:
                    if child.type in config.name_fallback_child_types:
                        name_node = child
                        break
            if not name_node:
                return
            class_name = _read_text(name_node, source)
            class_nid = _make_id(stem, ".".join(namespace_stack), class_name)
            line = node.start_point[0] + 1
            metadata = None
            if config.ts_module == "tree_sitter_c_sharp" and parent_class_nid:
                metadata = {"is_nested_type": True}
            add_node(class_nid, class_name, line, metadata=metadata)
            callable_def_nids.add(class_nid)  # a class is callable (constructor)
            # A nested class/object/trait is contained by its ENCLOSING type, not
            # the file (#2040). parent_class_nid is threaded down the walk for
            # every language and is always a real class-like node (never a
            # namespace — namespace handlers pass it through unchanged), so it is
            # a valid edge source. The `!= class_nid` guard avoids a self-loop
            # when same-name nesting (`class Foo: class Foo`) collides ids, since
            # class ids omit the enclosing type name. Top-level types (parent
            # None) still source from the file, keeping the containment tree
            # connected: file -> Outer -> Inner.
            if parent_class_nid and parent_class_nid != class_nid:
                add_edge(parent_class_nid, class_nid, "contains", line)
            else:
                add_edge(file_nid, class_nid, "contains", line)

            # TS/JS decorators on the class and its members (@Component, @Injectable,
            # @Input, @Inject, @Entity, …). Decorators live only in class subtrees.
            if config.ts_module in ("tree_sitter_javascript", "tree_sitter_typescript"):
                _ts_emit_decorator_edges(node, class_nid, stem, source,
                                         ensure_named_node, add_edge)

            if config.ts_module == "tree_sitter_swift" and any(
                c.type == "extension" for c in node.children
            ):
                swift_extensions.append({"nid": class_nid, "label": class_name})

            # Python-specific: inheritance
            if config.ts_module == "tree_sitter_python":
                args = node.child_by_field_name("superclasses")
                if args:
                    for arg in args.children:
                        if arg.type == "identifier":
                            base = _read_text(arg, source)
                            base_nid = ensure_named_node(base, line)
                            add_edge(class_nid, base_nid, "inherits", line)

            # Swift-specific: conformance / inheritance
            if config.ts_module == "tree_sitter_swift":
                swift_kind = _swift_declaration_keyword(node) if t == "class_declaration" else "protocol"
                seen_swift_base = False
                for child in node.children:
                    if child.type != "inheritance_specifier":
                        continue
                    base_name: str | None = None
                    user_type_node = None
                    for sub in child.children:
                        if sub.type == "user_type":
                            user_type_node = sub
                            base_name = _swift_user_type_name(sub, source)
                            break
                        if sub.type == "type_identifier":
                            base_name = _read_text(sub, source) or None
                            break
                    if not base_name:
                        continue
                    base_nid = _make_id(stem, base_name)
                    if base_nid not in seen_ids:
                        base_nid = _make_id(base_name)
                        if base_nid not in seen_ids:
                            nodes.append({
                                "id": base_nid,
                                "label": base_name,
                                "file_type": "code",
                                "source_file": "",
                                "source_location": "",
                            })
                            seen_ids.add(base_nid)
                    if t == "protocol_declaration":
                        relation = "inherits"
                    else:
                        relation = _swift_classify_base(
                            base_name, swift_kind, not seen_swift_base,
                            swift_protocol_names, swift_class_names,
                        )
                    seen_swift_base = True
                    add_edge(class_nid, base_nid, relation, line)
                    if user_type_node is not None:
                        for arg_child in user_type_node.children:
                            if arg_child.type != "type_arguments":
                                continue
                            for arg in arg_child.children:
                                if not arg.is_named:
                                    continue
                                refs: list[tuple[str, str]] = []
                                _swift_collect_type_refs(arg, source, True, refs)
                                for ref_name, _role in refs:
                                    target = ensure_named_node(ref_name, line)
                                    add_edge(class_nid, target, "references", line,
                                             context="generic_arg")

            # PHP-specific: extends → inherits, implements → implements, use → mixes_in
            if config.ts_module == "tree_sitter_php":
                def _php_emit_base(base_name: str, rel: str, at_line: int) -> None:
                    if not base_name:
                        return
                    base_nid = _make_id(stem, base_name)
                    if base_nid not in seen_ids:
                        base_nid = _make_id(base_name)
                        if base_nid not in seen_ids:
                            nodes.append({
                                "id": base_nid,
                                "label": base_name,
                                "file_type": "code",
                                "source_file": "",
                                "source_location": "",
                            })
                            seen_ids.add(base_nid)
                    add_edge(class_nid, base_nid, rel, at_line)

                for child in node.children:
                    if child.type == "base_clause":
                        for sub in child.children:
                            if sub.type in ("name", "qualified_name"):
                                _php_emit_base(_php_name_text(sub, source) or "",
                                                "inherits", child.start_point[0] + 1)
                    elif child.type == "class_interface_clause":
                        for sub in child.children:
                            if sub.type in ("name", "qualified_name"):
                                _php_emit_base(_php_name_text(sub, source) or "",
                                                "implements", child.start_point[0] + 1)
                body = node.child_by_field_name("body")
                if body is None:
                    for c in node.children:
                        if c.type == "declaration_list":
                            body = c
                            break
                if body is not None:
                    for member in body.children:
                        if member.type != "use_declaration":
                            continue
                        for sub in member.children:
                            if sub.type in ("name", "qualified_name"):
                                _php_emit_base(_php_name_text(sub, source) or "",
                                                "mixes_in", member.start_point[0] + 1)

            # Kotlin-specific: delegation_specifiers → inherits (constructor_invocation) / implements (user_type)
            if config.ts_module == "tree_sitter_kotlin":
                for child in node.children:
                    if child.type != "delegation_specifiers":
                        continue
                    for spec in child.children:
                        if spec.type != "delegation_specifier":
                            continue
                        relation = "implements"
                        user_type_node = None
                        for sub in spec.children:
                            if sub.type == "constructor_invocation":
                                relation = "inherits"
                                for inner in sub.children:
                                    if inner.type == "user_type":
                                        user_type_node = inner
                                        break
                                break
                            if sub.type == "user_type":
                                user_type_node = sub
                                break
                            # `class Foo : Bar by baz` wraps the delegated
                            # interface `Bar` in an `explicit_delegation`
                            # node; grab its first `user_type` descendant so
                            # the implements edge (and generic-arg recovery)
                            # still fire.
                            if sub.type == "explicit_delegation":
                                for inner in sub.children:
                                    if inner.type == "user_type":
                                        user_type_node = inner
                                        break
                                break
                        if user_type_node is None:
                            continue
                        base = _kotlin_user_type_name(user_type_node, source)
                        if not base:
                            continue
                        base_nid = ensure_named_node(base, line)
                        add_edge(class_nid, base_nid, relation, line)
                        for arg_child in user_type_node.children:
                            if arg_child.type != "type_arguments":
                                continue
                            for arg in arg_child.children:
                                if arg.type == "type_projection":
                                    for inner in arg.children:
                                        if not inner.is_named:
                                            continue
                                        refs: list[tuple[str, str]] = []
                                        _kotlin_collect_type_refs(inner, source, True, refs)
                                        for ref_name, _role in refs:
                                            target = ensure_named_node(ref_name, line)
                                            add_edge(class_nid, target, "references", line,
                                                     context="generic_arg")

            # Ruby: `class Dog < Animal` puts the base class in the `superclass`
            # field (a `<` token followed by a constant or scope_resolution).
            # There was no Ruby branch, so every Ruby inherits edge was dropped.
            if config.ts_module == "tree_sitter_ruby":
                sup = node.child_by_field_name("superclass")
                if sup is not None:
                    base = ""
                    for sub in sup.children:
                        if sub.type == "constant":
                            base = _read_text(sub, source)
                            break
                        if sub.type == "scope_resolution":
                            consts = [c for c in sub.children if c.type == "constant"]
                            if consts:
                                base = _read_text(consts[-1], source)
                            break
                    if base:
                        base_nid = ensure_named_node(base, line)
                        add_edge(class_nid, base_nid, "inherits", line)

                # `include`/`extend`/`prepend <Const>` in the class/module body ->
                # a `mixes_in` edge to the module (#1668). The module usually lives
                # in another file, so defer resolution to the cross-file Ruby
                # resolver (reusing the #1634 candidate logic and the #1640 module
                # nodes as targets). Only bare/namespaced constant arguments count;
                # `extend self`, `include some_var`, etc. are skipped.
                _rb_body = _find_body(node, config)
                if _rb_body is not None:
                    for _stmt in _rb_body.children:
                        if _stmt.type != "call" or _stmt.child_by_field_name("receiver") is not None:
                            continue
                        _m = _stmt.child_by_field_name("method")
                        if _m is None or _read_text(_m, source) not in ("include", "extend", "prepend"):
                            continue
                        _args = _stmt.child_by_field_name("arguments")
                        if _args is None:
                            continue
                        for _arg in _args.children:
                            if _arg.type not in ("constant", "scope_resolution"):
                                continue
                            _mod = _ruby_const_last_name(_arg, source)
                            if _mod:
                                _ruby_mixin_calls.append({
                                    "caller_nid": class_nid,
                                    "callee": _mod,
                                    "is_mixin": True,
                                    "source_file": str_path,
                                    "source_location": f"L{_stmt.start_point[0] + 1}",
                                })

            # C#-specific: inheritance / interface implementation via base_list
            if config.ts_module == "tree_sitter_c_sharp":
                csharp_type_params = _csharp_type_parameters_in_scope(node, source)
                for child in node.children:
                    if child.type != "base_list":
                        continue
                    for sub in child.children:
                        if sub.type not in ("identifier", "generic_name", "qualified_name"):
                            continue
                        base_info = _read_csharp_type_name(sub, source)
                        if base_info is None:
                            continue
                        base, qualified, qualifier = base_info
                        if not base or base in csharp_type_params:
                            continue
                        base_nid = _make_id(stem, ".".join(namespace_stack), base)
                        if base_nid not in seen_ids:
                            base_nid = _make_id(base)
                            if base_nid not in seen_ids:
                                nodes.append({
                                    "id": base_nid,
                                    "label": base,
                                    "file_type": "code",
                                    "source_file": "",
                                    "source_location": "",
                                })
                                seen_ids.add(base_nid)
                        relation = _csharp_classify_base(base, csharp_interface_names)
                        metadata = {"ref_token": base}
                        if qualified:
                            metadata["qualified"] = True
                        if qualifier:
                            metadata["ref_qualifier"] = qualifier
                        add_edge(class_nid, base_nid, relation, line, metadata=metadata)
                        if sub.type == "generic_name":
                            for tal in sub.children:
                                if tal.type != "type_argument_list":
                                    continue
                                for arg in tal.children:
                                    if not arg.is_named:
                                        continue
                                    refs: list[tuple[str, str, bool, str]] = []
                                    _csharp_collect_type_refs(
                                        arg, source, True, refs, csharp_type_params
                                    )
                                    for ref_name, _role, ref_qualified, ref_qualifier in refs:
                                        target = ensure_named_node(ref_name, line)
                                        metadata = {"ref_token": ref_name}
                                        if ref_qualified:
                                            metadata["qualified"] = True
                                        if ref_qualifier:
                                            metadata["ref_qualifier"] = ref_qualifier
                                        add_edge(class_nid, target, "references", line,
                                                 context="generic_arg", metadata=metadata)

            # Java-specific: extends (superclass) / implements (interfaces) / interface-extends
            if config.ts_module in ("tree_sitter_java", "tree_sitter_groovy"):
                def _emit_java_parent(base_name: str, rel: str, at_line: int) -> None:
                    if not base_name:
                        return
                    base_nid = _make_id(stem, base_name)
                    if base_nid not in seen_ids:
                        base_nid = _make_id(base_name)
                        if base_nid not in seen_ids:
                            nodes.append({
                                "id": base_nid,
                                "label": base_name,
                                "file_type": "code",
                                "source_file": "",
                                "source_location": "",
                            })
                            seen_ids.add(base_nid)
                    add_edge(class_nid, base_nid, rel, at_line)

                def _emit_java_parent_type(type_node, rel: str, at_line: int) -> None:
                    refs: list[tuple[str, str]] = []
                    _java_collect_type_refs(type_node, source, False, refs)
                    parent_emitted = False
                    for ref_name, role in refs:
                        if role == "type" and not parent_emitted:
                            _emit_java_parent(ref_name, rel, at_line)
                            parent_emitted = True
                        elif role == "generic_arg":
                            target_nid = ensure_named_node(ref_name, at_line)
                            if target_nid != class_nid:
                                add_edge(class_nid, target_nid, "references", at_line,
                                         context="generic_arg")

                sup = node.child_by_field_name("superclass")
                if sup is not None:
                    for sub in sup.children:
                        if sub.is_named:
                            _emit_java_parent_type(sub, "inherits", line)
                            break

                ifs = node.child_by_field_name("interfaces")
                if ifs is not None:
                    for sub in ifs.children:
                        if sub.type == "type_list":
                            for tid in sub.children:
                                if tid.is_named:
                                    _emit_java_parent_type(tid, "implements", line)

                if t == "interface_declaration":
                    for child in node.children:
                        if child.type == "extends_interfaces":
                            for sub in child.children:
                                if sub.type == "type_list":
                                    for tid in sub.children:
                                        if tid.is_named:
                                            _emit_java_parent_type(tid, "inherits", line)

                for anno_name in _java_annotation_names(node, source):
                    target_nid = ensure_named_node(anno_name, line)
                    if target_nid != class_nid:
                        add_edge(class_nid, target_nid, "references", line,
                                 context="attribute")

                if t == "record_declaration":
                    components = node.child_by_field_name("parameters")
                    if components is not None:
                        for component in components.children:
                            if component.type == "formal_parameter":
                                type_node = component.child_by_field_name("type")
                            elif component.type == "spread_parameter":
                                type_node = next(
                                    (
                                        child
                                        for child in component.children
                                        if child.is_named
                                        and child.type not in ("modifiers", "variable_declarator")
                                    ),
                                    None,
                                )
                            else:
                                continue
                            refs: list[tuple[str, str]] = []
                            _java_collect_type_refs(type_node, source, False, refs)
                            component_line = component.start_point[0] + 1
                            for ref_name, role in refs:
                                ctx = "generic_arg" if role == "generic_arg" else "field"
                                target_nid = ensure_named_node(ref_name, component_line)
                                if target_nid != class_nid:
                                    add_edge(class_nid, target_nid, "references",
                                             component_line, context=ctx)

            # Scala: extends_clause carries `extends Base with Trait1 with Trait2`.
            # The first base after `extends` is `inherits`; each subsequent
            # type after `with` is `mixes_in`. Also walk class_parameters for
            # constructor-as-field type references.
            if config.ts_module == "tree_sitter_scala":
                extend = node.child_by_field_name("extend")
                if extend is None:
                    for c in node.children:
                        if c.type == "extends_clause":
                            extend = c
                            break
                if extend is not None:
                    bases: list[tuple[str, int]] = []
                    for c in extend.children:
                        if c.type == "type_identifier":
                            bases.append((_read_text(c, source), c.start_point[0] + 1))
                        elif c.type == "generic_type":
                            base = c.child_by_field_name("type")
                            if base is None:
                                for sc in c.children:
                                    if sc.type == "type_identifier":
                                        base = sc
                                        break
                            if base is not None:
                                bases.append((_read_text(base, source), c.start_point[0] + 1))
                    for idx, (base_name, base_line) in enumerate(bases):
                        rel = "inherits" if idx == 0 else "mixes_in"
                        base_nid = ensure_named_node(base_name, base_line)
                        if base_nid != class_nid:
                            add_edge(class_nid, base_nid, rel, base_line)
                for c in node.children:
                    if c.type != "class_parameters":
                        continue
                    for cp in c.children:
                        if cp.type != "class_parameter":
                            continue
                        ptype = cp.child_by_field_name("type")
                        if ptype is None:
                            continue
                        cp_line = cp.start_point[0] + 1
                        refs: list[tuple[str, str]] = []
                        _scala_collect_type_refs(ptype, source, False, refs)
                        for ref_name, role in refs:
                            ctx = "generic_arg" if role == "generic_arg" else "field"
                            target_nid = ensure_named_node(ref_name, cp_line)
                            if target_nid != class_nid:
                                add_edge(class_nid, target_nid, "references",
                                         cp_line, context=ctx)

            # C++-specific: inheritance via base_class_clause (class and struct).
            # tree-sitter-cpp shape:
            #   class_specifier / struct_specifier
            #     base_class_clause
            #       access_specifier? ("public"/"protected"/"private")  -- skip
            #       "virtual"?                                          -- skip
            #       type_identifier                                     -- "Base"
            #       qualified_identifier                                -- "ns::Base"
            #       template_type                                       -- "Vec<int>"
            # Multiple bases are siblings separated by ',' tokens.
            if config.ts_module == "tree_sitter_cpp":
                for child in node.children:
                    if child.type != "base_class_clause":
                        continue
                    for sub in child.children:
                        base = ""
                        template_args_node = None
                        if sub.type == "type_identifier":
                            base = _read_text(sub, source)
                        elif sub.type == "qualified_identifier":
                            # Use the unqualified tail so "std::vector" matches
                            # a "vector" node id if one exists in the graph;
                            # fall back to the full qualified text otherwise.
                            tail = sub.child_by_field_name("name")
                            base = _read_text(tail, source) if tail else _read_text(sub, source)
                        elif sub.type == "template_type":
                            tname = sub.child_by_field_name("name")
                            base = _read_text(tname, source) if tname else _read_text(sub, source)
                            # The base's template_argument_list carries generic
                            # type arguments (class Car : public Base<Dep>). The
                            # Java handler (_emit_java_parent_type) emits these as
                            # generic_arg references; C++ dropped them because we
                            # only emitted the `inherits` edge on the base name.
                            template_args_node = sub.child_by_field_name("arguments")
                        else:
                            continue
                        if not base:
                            continue
                        base_nid = ensure_named_node(base, line)
                        add_edge(class_nid, base_nid, "inherits", line)
                        # Emit a generic_arg reference for each type argument on the
                        # base (Base<Dep> -> Car references Dep). _cpp_collect_type_refs
                        # handles nested/qualified args (Base<std::vector<Dep>>) too.
                        if template_args_node is not None:
                            arg_refs: list[tuple[str, str]] = []
                            for arg in template_args_node.children:
                                if arg.is_named:
                                    _cpp_collect_type_refs(arg, source, True, arg_refs)
                            for ref_name, _role in arg_refs:
                                target_nid = ensure_named_node(ref_name, line)
                                if target_nid != class_nid:
                                    add_edge(class_nid, target_nid, "references",
                                             line, context="generic_arg")

            # Find body and recurse
            body = _find_body(node, config)
            if body:
                for child in body.children:
                    walk(child, parent_class_nid=class_nid)
            return

        # Event listener property arrays: $listen = [Event::class => [Listener::class]]
        if (t == "property_declaration"
                and parent_class_nid
                and config.event_listener_properties):
            handled_event_listener = False
            for element in node.children:
                if element.type != "property_element":
                    continue
                prop_name: str | None = None
                array_node = None
                for c in element.children:
                    if c.type == "variable_name":
                        for sc in c.children:
                            if sc.type == "name":
                                prop_name = _read_text(sc, source)
                                break
                    elif c.type == "array_creation_expression":
                        array_node = c
                if (prop_name is None
                        or prop_name not in config.event_listener_properties
                        or array_node is None):
                    continue
                handled_event_listener = True
                for entry in array_node.children:
                    if entry.type != "array_element_initializer":
                        continue
                    event_cls: str | None = None
                    listener_arr = None
                    for sub in entry.children:
                        if sub.type == "class_constant_access_expression" and event_cls is None:
                            for sc in sub.children:
                                if sc.is_named and sc.type in ("name", "qualified_name"):
                                    event_cls = _read_text(sc, source)
                                    break
                        elif sub.type == "array_creation_expression":
                            listener_arr = sub
                    if not event_cls or listener_arr is None:
                        continue
                    for listener_entry in listener_arr.children:
                        if listener_entry.type != "array_element_initializer":
                            continue
                        for item in listener_entry.children:
                            if item.type != "class_constant_access_expression":
                                continue
                            for sc in item.children:
                                if sc.is_named and sc.type in ("name", "qualified_name"):
                                    listener_cls = _read_text(sc, source)
                                    line_no = item.start_point[0] + 1
                                    pending_listen_edges.append((event_cls, listener_cls, line_no))
                                    break
                            break
            if handled_event_listener:
                return

        if (config.ts_module == "tree_sitter_c_sharp"
                and t == "field_declaration"
                and parent_class_nid):
            type_node = node.child_by_field_name("type")
            if type_node is None:
                for child in node.children:
                    if child.type == "variable_declaration":
                        type_node = child.child_by_field_name("type")
                        if type_node is not None:
                            break
            type_info = _read_csharp_type_name(type_node, source)
            if type_info:
                type_name, qualified, qualifier = type_info
                csharp_type_params = _csharp_type_parameters_in_scope(
                    type_node if type_node is not None else node, source
                )
                if not type_name or type_name in csharp_type_params:
                    return
                line = node.start_point[0] + 1
                metadata = {"ref_token": type_name}
                if qualified:
                    metadata["qualified"] = True
                if qualifier:
                    metadata["ref_qualifier"] = qualifier
                add_edge(parent_class_nid, ensure_named_node(type_name, line),
                         "references", line, context="field", metadata=metadata)
            return

        if (config.ts_module == "tree_sitter_c_sharp"
                and t == "property_declaration"
                and parent_class_nid):
            # C# auto-properties (`public Widget Main { get; set; }`) are the
            # idiomatic way to declare state, yet only field_declaration was
            # handled — so property types produced no references edge. Unlike a
            # field, a property exposes its type on the node directly (no
            # variable_declaration wrapper), so read it straight off the `type`
            # field. Use _csharp_collect_type_refs (like the Java/PHP/Kotlin
            # siblings) so `List<Widget>` yields both the List field ref and the
            # Widget generic_arg ref.
            type_node = node.child_by_field_name("type")
            if type_node is not None:
                line = node.start_point[0] + 1
                refs: list[tuple[str, str, bool, str]] = []
                _csharp_collect_type_refs(type_node, source, False, refs)
                for ref_name, role, qualified, qualifier in refs:
                    ctx = "generic_arg" if role == "generic_arg" else "field"
                    target_nid = ensure_named_node(ref_name, line)
                    if target_nid != parent_class_nid:
                        metadata = {"ref_token": ref_name}
                        if qualified:
                            metadata["qualified"] = True
                        if qualifier:
                            metadata["ref_qualifier"] = qualifier
                        add_edge(parent_class_nid, target_nid, "references",
                                 line, context=ctx, metadata=metadata)
            return

        if (config.ts_module == "tree_sitter_java"
                and t == "field_declaration"
                and parent_class_nid):
            type_node = node.child_by_field_name("type")
            if type_node is not None:
                receiver_type = _java_receiver_type_name(type_node, source)
                if receiver_type:
                    fields = java_field_types.setdefault(parent_class_nid, {})
                    for field_name in _java_declarator_names(node, source):
                        fields[field_name] = receiver_type
                line = node.start_point[0] + 1
                refs: list[tuple[str, str]] = []
                _java_collect_type_refs(type_node, source, False, refs)
                for ref_name, role in refs:
                    ctx = "generic_arg" if role == "generic_arg" else "field"
                    target_nid = ensure_named_node(ref_name, line)
                    if target_nid != parent_class_nid:
                        add_edge(parent_class_nid, target_nid, "references",
                                 line, context=ctx)
            return

        if (config.ts_module == "tree_sitter_php"
                and t == "property_declaration"
                and parent_class_nid):
            for c in node.children:
                if c.type not in ("named_type", "primitive_type", "nullable_type",
                                   "union_type", "intersection_type", "optional_type"):
                    continue
                line = node.start_point[0] + 1
                refs: list[tuple[str, str]] = []
                _php_collect_type_refs(c, source, False, refs)
                for ref_name, role in refs:
                    ctx = "generic_arg" if role == "generic_arg" else "field"
                    target_nid = ensure_named_node(ref_name, line)
                    if target_nid != parent_class_nid:
                        add_edge(parent_class_nid, target_nid, "references", line, context=ctx)
                break
            return

        if (config.ts_module == "tree_sitter_kotlin"
                and t == "property_declaration"
                and parent_class_nid):
            type_node = _kotlin_property_type_node(node)
            if type_node is not None:
                line = node.start_point[0] + 1
                refs: list[tuple[str, str]] = []
                _kotlin_collect_type_refs(type_node, source, False, refs)
                for ref_name, role in refs:
                    ctx = "generic_arg" if role == "generic_arg" else "field"
                    target_nid = ensure_named_node(ref_name, line)
                    if target_nid != parent_class_nid:
                        add_edge(parent_class_nid, target_nid, "references", line, context=ctx)
            return

        if (config.ts_module == "tree_sitter_swift"
                and t == "property_declaration"
                and parent_class_nid):
            line = node.start_point[0] + 1
            prop_type: str | None = None
            type_anno = _swift_property_type_node(node)
            if type_anno is not None:
                refs: list[tuple[str, str]] = []
                _swift_collect_type_refs(type_anno, source, False, refs)
                for ref_name, role in refs:
                    ctx = "generic_arg" if role == "generic_arg" else "field"
                    target_nid = ensure_named_node(ref_name, line)
                    if target_nid != parent_class_nid:
                        add_edge(parent_class_nid, target_nid, "references", line, context=ctx)
                    if prop_type is None and role == "type":
                        prop_type = ref_name
            # #1356 Stage 1: walk the initializer so a constructor call
            # (`let vm = VM()`) produces a calls edge. #1356 Stage 2a: when the
            # property has no type annotation, infer its type from the
            # constructor so `vm.update()` later resolves to VM.
            for child in node.children:
                if child.type in config.call_types:
                    initializer_nodes.append((parent_class_nid, child))
                    if prop_type is None:
                        ctor = _swift_constructor_type(child, source)
                        if ctor is not None:
                            prop_type = ctor
                # #1604 Stage 2b: `let x = Type.shared` (or any `Type.staticProp`)
                # binds x to Type via a static-member access, which is a
                # navigation_expression, not a constructor call. Infer x's type from
                # the uppercase head so later `x.method()` calls resolve to Type. This
                # is the singleton idiom (`Type.shared`) cached into a local var and
                # called on a subsequent line — extremely common in Swift.
                elif child.type == "navigation_expression" and prop_type is None:
                    head = child.children[0] if child.children else None
                    if head is not None and head.type == "simple_identifier":
                        htext = _read_text(head, source)
                        if htext and htext[:1].isupper():
                            prop_type = htext
            prop_name = _swift_property_name(node, source)
            if prop_name and prop_type:
                type_table[prop_name] = prop_type
            return

        if (config.ts_module == "tree_sitter_scala"
                and t in ("val_definition", "var_definition")
                and parent_class_nid):
            type_node = node.child_by_field_name("type")
            if type_node is not None:
                line = node.start_point[0] + 1
                refs: list[tuple[str, str]] = []
                _scala_collect_type_refs(type_node, source, False, refs)
                for ref_name, role in refs:
                    ctx = "generic_arg" if role == "generic_arg" else "field"
                    target_nid = ensure_named_node(ref_name, line)
                    if target_nid != parent_class_nid:
                        add_edge(parent_class_nid, target_nid, "references",
                                 line, context=ctx)
            # fall through so any call expressions in the initializer get walked

        if (config.ts_module == "tree_sitter_cpp"
                and t == "field_declaration"
                and parent_class_nid):
            # Skip method prototypes (field_declaration with a function_declarator
            # is a member-function declaration, not a data member).
            decls = list(node.children_by_field_name("declarator"))
            is_method = any(
                d.type == "function_declarator"
                or (d.type in ("pointer_declarator", "reference_declarator")
                    and any(c.type == "function_declarator" for c in d.children))
                for d in decls
            )
            if not is_method:
                type_node = node.child_by_field_name("type")
                if type_node is not None:
                    line = node.start_point[0] + 1
                    refs: list[tuple[str, str]] = []
                    _cpp_collect_type_refs(type_node, source, False, refs)
                    for ref_name, role in refs:
                        ctx = "generic_arg" if role == "generic_arg" else "field"
                        target_nid = ensure_named_node(ref_name, line)
                        if target_nid != parent_class_nid:
                            add_edge(parent_class_nid, target_nid, "references",
                                     line, context=ctx)
            # Emit a node for each data member. Use children_by_field_name so we
            # only visit declarator children, not the type node (which would give
            # us the type name, not the field name). Handles int x, y; via
            # multiple declarator fields and static const int MAX = 100; via the
            # init_declarator → field_identifier recursion in _get_cpp_func_name.
            for decl in decls:
                name = _get_cpp_func_name(decl, source)
                if name:
                    line = decl.start_point[0] + 1
                    field_nid = _make_id(parent_class_nid, name)
                    add_node(field_nid, name, line)
                    add_edge(parent_class_nid, field_nid, "defines", line, context="field")
            return

        # Function types
        if t in config.function_types:
            # Swift deinit/subscript have no name field — resolve before generic fallback
            if t == "deinit_declaration":
                func_name: str | None = "deinit"
            elif t == "subscript_declaration":
                func_name = "subscript"
            elif config.resolve_function_name_fn is not None:
                # C/C++ style: use declarator
                declarator = node.child_by_field_name("declarator")
                func_name = None
                if declarator:
                    func_name = config.resolve_function_name_fn(declarator, source)
            else:
                name_node = node.child_by_field_name(config.name_field)
                if name_node is None:
                    for child in node.children:
                        if child.type in config.name_fallback_child_types:
                            name_node = child
                            break
                func_name = _read_text(name_node, source) if name_node else None

            if not func_name:
                return
            # A name that normalizes to nothing collapses `_make_id(prefix, name)`
            # onto the (absolute-path-derived) prefix, leaking the scan path and
            # colliding with the file/class node (#1899). No graph signal; skip.
            if not normalize_id(func_name):
                return

            line = node.start_point[0] + 1
            if parent_class_nid:
                func_nid = _make_id(parent_class_nid, func_name)
                add_node(func_nid, f".{func_name}()", line)
                add_edge(parent_class_nid, func_nid, "method", line)
            else:
                func_nid = _make_id(stem, func_name)
                add_node(func_nid, f"{func_name}()", line)
                add_edge(file_nid, func_nid, "contains", line)
            callable_def_nids.add(func_nid)  # function / method def is callable
            if config.ts_module == "tree_sitter_python":
                local_bound_names[func_nid] = _python_local_bound_names(node, source)
            elif config.ts_module in ("tree_sitter_javascript", "tree_sitter_typescript"):
                local_bound_names[func_nid] = _js_local_bound_names(node, source)

            if config.ts_module == "tree_sitter_python":
                params_node = node.child_by_field_name("parameters")
                for ref_name, role in _python_collect_param_refs(params_node, source):
                    ctx = "generic_arg" if role == "generic_arg" else "parameter_type"
                    target_nid = ensure_named_node(ref_name, line)
                    if target_nid != func_nid:
                        edges.append(
                            _semantic_reference_edge(func_nid, target_nid, ctx, str_path, line)
                        )
                return_type_node = node.child_by_field_name("return_type")
                if return_type_node is not None:
                    return_refs: list[tuple[str, str]] = []
                    _python_collect_type_refs(return_type_node, source, False, return_refs)
                    for ref_name, role in return_refs:
                        ctx = "generic_arg" if role == "generic_arg" else "return_type"
                        target_nid = ensure_named_node(ref_name, line)
                        if target_nid != func_nid:
                            edges.append(
                                _semantic_reference_edge(func_nid, target_nid, ctx, str_path, line)
                            )

            if config.ts_module == "tree_sitter_c_sharp":
                csharp_type_params = _csharp_type_parameters_in_scope(node, source)
                params_node = node.child_by_field_name("parameters")
                if params_node is not None:
                    for p in params_node.children:
                        if p.type != "parameter":
                            continue
                        type_node = p.child_by_field_name("type")
                        refs: list[tuple[str, str, bool, str]] = []
                        _csharp_collect_type_refs(
                            type_node, source, False, refs, csharp_type_params
                        )
                        for ref_name, role, qualified, qualifier in refs:
                            ctx = "generic_arg" if role == "generic_arg" else "parameter_type"
                            target_nid = ensure_named_node(ref_name, line)
                            if target_nid != func_nid:
                                metadata = {"ref_token": ref_name}
                                if qualified:
                                    metadata["qualified"] = True
                                if qualifier:
                                    metadata["ref_qualifier"] = qualifier
                                add_edge(func_nid, target_nid, "references", line,
                                         context=ctx, metadata=metadata)
                return_node = node.child_by_field_name("returns")
                if return_node is not None:
                    refs: list[tuple[str, str, bool, str]] = []
                    _csharp_collect_type_refs(
                        return_node, source, False, refs, csharp_type_params
                    )
                    for ref_name, role, qualified, qualifier in refs:
                        ctx = "generic_arg" if role == "generic_arg" else "return_type"
                        target_nid = ensure_named_node(ref_name, line)
                        if target_nid != func_nid:
                            metadata = {"ref_token": ref_name}
                            if qualified:
                                metadata["qualified"] = True
                            if qualifier:
                                metadata["ref_qualifier"] = qualifier
                            add_edge(func_nid, target_nid, "references", line,
                                     context=ctx, metadata=metadata)
                for attr_name, qualified, qualifier in _csharp_attribute_names(node, source):
                    target_nid = ensure_named_node(attr_name, line)
                    if target_nid != func_nid:
                        metadata = {"ref_token": attr_name}
                        if qualified:
                            metadata["qualified"] = True
                        if qualifier:
                            metadata["ref_qualifier"] = qualifier
                        add_edge(func_nid, target_nid, "references", line,
                                 context="attribute", metadata=metadata)

            if config.ts_module == "tree_sitter_java":
                params_node = node.child_by_field_name("parameters")
                if params_node is not None:
                    for p in params_node.children:
                        if p.type != "formal_parameter":
                            continue
                        type_node = p.child_by_field_name("type")
                        refs = []
                        _java_collect_type_refs(type_node, source, False, refs)
                        for ref_name, role in refs:
                            ctx = "generic_arg" if role == "generic_arg" else "parameter_type"
                            target_nid = ensure_named_node(ref_name, line)
                            if target_nid != func_nid:
                                add_edge(func_nid, target_nid, "references", line, context=ctx)
                return_node = node.child_by_field_name("type")
                if return_node is not None:
                    refs = []
                    _java_collect_type_refs(return_node, source, False, refs)
                    for ref_name, role in refs:
                        ctx = "generic_arg" if role == "generic_arg" else "return_type"
                        target_nid = ensure_named_node(ref_name, line)
                        if target_nid != func_nid:
                            add_edge(func_nid, target_nid, "references", line, context=ctx)
                for anno_name in _java_annotation_names(node, source):
                    target_nid = ensure_named_node(anno_name, line)
                    if target_nid != func_nid:
                        add_edge(func_nid, target_nid, "references", line, context="attribute")

            if config.ts_module == "tree_sitter_php":
                params_container = None
                for c in node.children:
                    if c.type == "formal_parameters":
                        params_container = c
                        break
                if params_container is not None:
                    for p in params_container.children:
                        # PHP 8 constructor property promotion (`__construct(private
                        # Repo $repo)`) parses the promoted param as
                        # property_promotion_parameter, not simple_parameter. Its
                        # type sits in the same direct named child shape, so accept
                        # both here; a promoted param is additionally a class field.
                        if p.type not in ("simple_parameter", "property_promotion_parameter"):
                            continue
                        is_promoted = p.type == "property_promotion_parameter"
                        type_node = None
                        for sub in p.children:
                            if sub.type in ("named_type", "primitive_type", "nullable_type",
                                             "union_type", "intersection_type", "optional_type"):
                                type_node = sub
                                break
                        refs: list[tuple[str, str]] = []
                        _php_collect_type_refs(type_node, source, False, refs)
                        for ref_name, role in refs:
                            ctx = "generic_arg" if role == "generic_arg" else "parameter_type"
                            target_nid = ensure_named_node(ref_name, line)
                            if target_nid != func_nid:
                                add_edge(func_nid, target_nid, "references", line, context=ctx)
                            # A promoted param declares a real class field; mirror
                            # the property_declaration field-context edge so the
                            # type is discoverable as a class field too.
                            if is_promoted and parent_class_nid and target_nid != parent_class_nid:
                                fctx = "generic_arg" if role == "generic_arg" else "field"
                                add_edge(parent_class_nid, target_nid, "references",
                                         line, context=fctx)
                return_node = _php_method_return_type_node(node)
                if return_node is not None:
                    refs = []
                    _php_collect_type_refs(return_node, source, False, refs)
                    for ref_name, role in refs:
                        ctx = "generic_arg" if role == "generic_arg" else "return_type"
                        target_nid = ensure_named_node(ref_name, line)
                        if target_nid != func_nid:
                            add_edge(func_nid, target_nid, "references", line, context=ctx)

            if config.ts_module == "tree_sitter_kotlin":
                params_container = None
                for c in node.children:
                    if c.type == "function_value_parameters":
                        params_container = c
                        break
                if params_container is not None:
                    for p in params_container.children:
                        if p.type != "parameter":
                            continue
                        param_type_node = None
                        for sub in p.children:
                            if sub.type in ("user_type", "nullable_type", "type_reference"):
                                param_type_node = sub
                                break
                        refs: list[tuple[str, str]] = []
                        _kotlin_collect_type_refs(param_type_node, source, False, refs)
                        for ref_name, role in refs:
                            ctx = "generic_arg" if role == "generic_arg" else "parameter_type"
                            target_nid = ensure_named_node(ref_name, line)
                            if target_nid != func_nid:
                                add_edge(func_nid, target_nid, "references", line, context=ctx)
                return_type_node = _kotlin_function_return_type_node(node)
                if return_type_node is not None:
                    refs = []
                    _kotlin_collect_type_refs(return_type_node, source, False, refs)
                    for ref_name, role in refs:
                        ctx = "generic_arg" if role == "generic_arg" else "return_type"
                        target_nid = ensure_named_node(ref_name, line)
                        if target_nid != func_nid:
                            add_edge(func_nid, target_nid, "references", line, context=ctx)

            if config.ts_module == "tree_sitter_swift":
                for p in node.children:
                    if p.type != "parameter":
                        continue
                    type_node = p.child_by_field_name("type")
                    refs: list[tuple[str, str]] = []
                    _swift_collect_type_refs(type_node, source, False, refs)
                    param_type: str | None = None
                    for ref_name, role in refs:
                        ctx = "generic_arg" if role == "generic_arg" else "parameter_type"
                        target_nid = ensure_named_node(ref_name, line)
                        if target_nid != func_nid:
                            add_edge(func_nid, target_nid, "references", line, context=ctx)
                        if param_type is None and role == "type":
                            param_type = ref_name
                    # #1356 Stage 2a: record param name -> type (flat per-file
                    # table; later params with the same name win, which is fine
                    # for the depth-1 member-call resolution we do).
                    if param_type:
                        name_node = p.child_by_field_name("name")
                        pname = _read_text(name_node, source) if name_node else None
                        if pname:
                            type_table[pname] = param_type
                return_node = node.child_by_field_name("return_type")
                if return_node is not None:
                    refs = []
                    _swift_collect_type_refs(return_node, source, False, refs)
                    for ref_name, role in refs:
                        ctx = "generic_arg" if role == "generic_arg" else "return_type"
                        target_nid = ensure_named_node(ref_name, line)
                        if target_nid != func_nid:
                            add_edge(func_nid, target_nid, "references", line, context=ctx)

            if (config.ts_module in ("tree_sitter_javascript", "tree_sitter_typescript")
                    and func_name == "constructor"):
                params_node = node.child_by_field_name("parameters")
                if params_node is not None:
                    for p in params_node.children:
                        if p.type != "required_parameter":
                            continue
                        has_modifier = any(
                            c.type in ("accessibility_modifier", "readonly")
                            for c in p.children
                        )
                        if not has_modifier:
                            continue
                        name_n = p.child_by_field_name("pattern")
                        type_n = p.child_by_field_name("type")
                        if name_n is None or type_n is None:
                            continue
                        pname = _read_text(name_n, source)
                        for tc in type_n.children:
                            if tc.type == "type_identifier":
                                ptype = _read_text(tc, source)
                                if pname and ptype:
                                    type_table[pname] = ptype
                                break

            if config.ts_module in ("tree_sitter_c", "tree_sitter_cpp"):
                collect = (_cpp_collect_type_refs if config.ts_module == "tree_sitter_cpp"
                           else _c_collect_type_refs)
                return_node = node.child_by_field_name("type")
                if return_node is not None:
                    refs: list[tuple[str, str]] = []
                    collect(return_node, source, False, refs)
                    for ref_name, role in refs:
                        ctx = "generic_arg" if role == "generic_arg" else "return_type"
                        target_nid = ensure_named_node(ref_name, line)
                        if target_nid != func_nid:
                            add_edge(func_nid, target_nid, "references", line, context=ctx)
                # function_declarator may be wrapped in pointer/reference declarators
                decl = node.child_by_field_name("declarator")
                while decl is not None and decl.type in (
                        "pointer_declarator", "reference_declarator"):
                    decl = decl.child_by_field_name("declarator")
                if decl is not None and decl.type == "function_declarator":
                    params_node = decl.child_by_field_name("parameters")
                    if params_node is not None:
                        for p in params_node.children:
                            if p.type != "parameter_declaration":
                                continue
                            ptype = p.child_by_field_name("type")
                            if ptype is None:
                                continue
                            refs = []
                            collect(ptype, source, False, refs)
                            for ref_name, role in refs:
                                ctx = "generic_arg" if role == "generic_arg" else "parameter_type"
                                target_nid = ensure_named_node(ref_name, line)
                                if target_nid != func_nid:
                                    add_edge(func_nid, target_nid, "references",
                                             line, context=ctx)

            if config.ts_module == "tree_sitter_scala":
                params_node = None
                for c in node.children:
                    if c.type == "parameters":
                        params_node = c
                        break
                if params_node is not None:
                    for p in params_node.children:
                        if p.type != "parameter":
                            continue
                        ptype = p.child_by_field_name("type")
                        if ptype is None:
                            continue
                        refs: list[tuple[str, str]] = []
                        _scala_collect_type_refs(ptype, source, False, refs)
                        for ref_name, role in refs:
                            ctx = "generic_arg" if role == "generic_arg" else "parameter_type"
                            target_nid = ensure_named_node(ref_name, line)
                            if target_nid != func_nid:
                                add_edge(func_nid, target_nid, "references",
                                         line, context=ctx)
                return_node = node.child_by_field_name("return_type")
                if return_node is not None:
                    refs = []
                    _scala_collect_type_refs(return_node, source, False, refs)
                    for ref_name, role in refs:
                        ctx = "generic_arg" if role == "generic_arg" else "return_type"
                        target_nid = ensure_named_node(ref_name, line)
                        if target_nid != func_nid:
                            add_edge(func_nid, target_nid, "references",
                                     line, context=ctx)

            body = _find_body(node, config)
            # JS/TS: capture `this.X = () => {}` / `this.X = function(){}`
            # assigned directly in this function/constructor body. They live
            # inside the body (otherwise only walked for calls), so without this
            # they are never emitted — the dominant miss on constructor-style
            # ("function Foo(){ this.bar = () => {} }") and many CommonJS repos.
            # Owner is the enclosing class when present (a constructor's methods
            # belong to the class), else the function itself.
            if body is not None and config.ts_module in (
                "tree_sitter_javascript", "tree_sitter_typescript"
            ):
                this_owner_nid = parent_class_nid if parent_class_nid else func_nid
                for stmt in body.children:
                    if stmt.type != "expression_statement":
                        continue
                    assign = next((c for c in stmt.children
                                   if c.type == "assignment_expression"), None)
                    if assign is None:
                        continue
                    val = assign.child_by_field_name("right")
                    if val is None or val.type not in _JS_FUNCTION_VALUE_TYPES:
                        continue
                    tgt = _js_member_assignment_target(
                        assign.child_by_field_name("left"), source)
                    if tgt is None or tgt[0] != "this":
                        continue
                    m_name = tgt[2]
                    m_line = stmt.start_point[0] + 1
                    m_nid = _make_id(this_owner_nid, m_name)
                    add_node(m_nid, f".{m_name}()", m_line)
                    add_edge(this_owner_nid, m_nid, "method", m_line)
                    m_body = val.child_by_field_name("body")
                    if m_body:
                        function_bodies.append((m_nid, m_body))
            if body:
                if config.ts_module == "tree_sitter_java" and parent_class_nid:
                    java_method_scopes[id(body)] = (node, parent_class_nid)
                function_bodies.append((func_nid, body))
            return

        # JS/TS arrow functions and C# namespaces — language-specific extra handling
        if config.ts_module in ("tree_sitter_javascript", "tree_sitter_typescript"):
            if _js_extra_walk(node, source, file_nid, stem, str_path,
                              nodes, edges, seen_ids, function_bodies,
                              parent_class_nid, add_node, add_edge,
                              callable_def_nids, local_bound_names):
                return

        # TS namespace / module containers (internal_module, module)
        if config.ts_module == "tree_sitter_typescript":
            if _ts_extra_walk(node, source, file_nid, stem, str_path,
                              nodes, edges, seen_ids, function_bodies,
                              parent_class_nid, add_node, add_edge, walk):
                return

        if config.ts_module == "tree_sitter_c_sharp":
            if _csharp_extra_walk(node, source, file_nid, stem, str_path,
                                   nodes, edges, seen_ids, function_bodies,
                                   parent_class_nid, add_node, add_edge, walk,
                                   namespace_stack, scope_stack):
                return

        if config.ts_module == "tree_sitter_swift":
            if _swift_extra_walk(node, source, file_nid, stem, str_path,
                                  nodes, edges, seen_ids, function_bodies,
                                  parent_class_nid, add_node, add_edge,
                                  ensure_named_node):
                return

        if config.ts_module == "tree_sitter_java":
            if _java_extra_walk(node, source, file_nid, stem, str_path,
                                nodes, edges, seen_ids, function_bodies,
                                parent_class_nid, add_node, add_edge, walk):
                return

        if config.ts_module == "tree_sitter_kotlin":
            if _kotlin_extra_walk(node, source, file_nid, stem, str_path,
                                  nodes, edges, seen_ids, function_bodies,
                                  parent_class_nid, add_node, add_edge, walk):
                return

        if config.ts_module == "tree_sitter_ruby":
            if _ruby_extra_walk(node, source, file_nid, stem, str_path,
                                nodes, edges, seen_ids, function_bodies,
                                parent_class_nid, add_node, add_edge, walk,
                                callable_def_nids):
                return

        # Python's `@property` / `@staticmethod` / `@classmethod` wrap the
        # inner function_definition in a `decorated_definition` node. The
        # default recurse below clears parent_class_nid, which would cause the
        # inner method to be emitted with a class-unqualified node id (e.g.
        # `file_baz` instead of `file_bar_baz`). That diverges from the
        # class-qualified id the rationale walker uses for the same method's
        # docstring, leaving the rationale edge dangling and the docstring
        # node orphaned (#1050). Treat decorated_definition as a transparent
        # wrapper so parent_class_nid propagates to the real function node.
        if t == "decorated_definition":
            for child in node.children:
                walk(child, parent_class_nid=parent_class_nid)
            return

        # Default: recurse
        for child in node.children:
            walk(child, parent_class_nid=None)

    walk(root)

    # ── Call-graph pass ───────────────────────────────────────────────────────
    label_to_nid: dict[str, str] = {}     # case-sensitive (Ruby, C#, Java, Kotlin, etc.)
    label_to_nid_ci: dict[str, str] = {}  # case-insensitive (PHP functions/classes)
    # nid -> source_file, so the indirect-dispatch guard can tell a genuine local
    # non-callable (reject) from an import-resolved foreign symbol whose definition
    # lives in another file (defer to the cross-file resolver). JS/TS named imports
    # surface the imported symbol's REAL node into this file's label map.
    nid_to_sf: dict[str, str] = {}
    for n in nodes:
        nid_to_sf[n["id"]] = str(n.get("source_file") or "")
        if n.get("type") == "namespace":
            continue
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        label_to_nid[normalised] = n["id"]
        label_to_nid_ci[normalised.lower()] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()
    seen_indirect_pairs: set[tuple[str, str]] = set()  # Python indirect_call dedup
    seen_dyn_import_pairs: set[tuple[str, str]] = set()
    seen_static_ref_pairs: set[tuple[str, str, str]] = set()
    seen_helper_ref_pairs: set[tuple[str, str, str]] = set()
    seen_bind_pairs: set[tuple[str, str, str]] = set()
    raw_calls: list[dict] = []  # unresolved calls for cross-file resolution in extract()
    # Ruby: per-method `var -> ClassName` table from `var = Const.new` bindings,
    # populated before walk_calls runs. Lets member-call raw_calls carry a
    # receiver_type so the cross-file pass resolves `var.method` by type (#ruby).
    ruby_var_types: dict[str, dict[str, str | None]] = {}
    java_receiver_types = {
        body_id: _java_method_receiver_types(
            method_node,
            source,
            java_field_types.get(class_nid, {}),
        )
        for body_id, (method_node, class_nid) in java_method_scopes.items()
    }

    def _emit_indirect_by_name(ident_name: str, loc_node, scope_nid: str,
                               context: str) -> None:
        """Resolve a name that is referenced AS A VALUE to a real callable def and emit
        one INFERRED ``indirect_call`` edge — deferring an unknown / foreign name to the
        cross-file resolver, which applies the single-definition god-node guard and the
        GLOBAL callable-target check. The name is already extracted; scope filtering is
        the CALLER's job: an identifier reference must reject param/local shadows (a bare
        name IS a binding — see ``_emit_indirect_ref``), whereas a ``getattr(obj, "x")``
        string names an ATTRIBUTE and is never shadowed by a local, so that path passes
        the name straight through. ``loc_node`` supplies the source line.
        """
        ref_nid = label_to_nid.get(ident_name)
        # Defer to the cross-file resolver when the name is not defined in this file
        # (`from .h import fn`), or resolves to an import-surfaced FOREIGN symbol whose
        # definition (and callability) lives in another file (JS/TS named imports map
        # the real node into this file's label map). The cross-file pass applies the
        # single-definition god-node guard plus the GLOBAL callable-target check, so a
        # foreign non-callable (an imported data const) still produces no edge.
        if ref_nid is None or (
            ref_nid not in callable_def_nids and nid_to_sf.get(ref_nid, "") != str_path
        ):
            raw_calls.append({
                "caller_nid": scope_nid,
                "callee": ident_name,
                "is_member_call": False,
                "indirect": True,
                "context": context,
                "source_file": str_path,
                "source_location": f"L{loc_node.start_point[0] + 1}",
            })
            return
        if ref_nid == scope_nid or ref_nid not in callable_def_nids:
            return  # self-ref, or a same-named LOCAL non-callable data node — no edge
        if (scope_nid, ref_nid) in seen_call_pairs:
            return  # already a direct call to this target
        if (scope_nid, ref_nid) in seen_indirect_pairs:
            return
        seen_indirect_pairs.add((scope_nid, ref_nid))
        edges.append({
            "source": scope_nid,
            "target": ref_nid,
            "relation": "indirect_call",
            "context": context,
            "confidence": "INFERRED",
            "source_file": str_path,
            "source_location": f"L{loc_node.start_point[0] + 1}",
            "weight": 1.0,
        })

    def _emit_indirect_ref(ident, scope_nid: str, enclosing_locals, context: str) -> None:
        """A function referenced BY NAME — passed as a call argument, or listed as a
        value in a dispatch table — is an indirect dependency of ``scope_nid``. Emit
        it as a distinct INFERRED ``indirect_call`` (kept out of the precise ``calls``
        relation) only when the name resolves to a real callable and is NOT shadowed
        by a parameter / local binding. A callback defined in another file is deferred
        to the cross-file resolver via an ``indirect`` raw_call carrying its context.
        Language-agnostic; shared by the call-argument and dispatch-table capture
        paths for Python and JS/TS (#1565, #1566).
        """
        if ident is None or ident.type not in ("identifier", "shorthand_property_identifier"):
            return
        ident_name = _read_text(ident, source)
        # shadowing: a param / local binding names a local value, not the module fn
        if ident_name in enclosing_locals or ident_name in ("self", "cls"):
            return
        _emit_indirect_by_name(ident_name, ident, scope_nid, context)

    def _python_dispatch_value_idents(coll_node):
        """Yield the identifier value-nodes of a dict/list/set/tuple literal that are
        function-reference candidates: dict VALUES (never keys), and the elements of a
        list/set/tuple. Nested collections are reached by the caller's own recursion."""
        if coll_node.type == "dictionary":
            for pair in coll_node.children:
                if pair.type == "pair":
                    val = pair.child_by_field_name("value")
                    if val is not None and val.type == "identifier":
                        yield val
        else:  # list / set / tuple
            for el in coll_node.children:
                if el.type == "identifier":
                    yield el

    def _python_ref_value_idents(value_node):
        """Identifiers on the VALUE side of an assignment RHS or a return: a bare name
        (`cb = handler`, `return handler`) or the elements of a bare unpack
        (`a, b = f, g`). A collection LITERAL on the RHS (`cb = [f]`, `cb = (f, g)`) is a
        dispatch table reached by the normal recursion, so it is not handled here."""
        if value_node is None:
            return
        if value_node.type == "identifier":
            yield value_node
        elif value_node.type == "expression_list":
            for ch in value_node.children:
                if ch.type == "identifier":
                    yield ch

    def _getattr_ref_name(call_node):
        """If ``call_node`` is a builtin ``getattr(obj, "name"[, default])`` whose name
        argument is a PLAIN string literal, return ``(name, string_node)``: the string
        names an attribute looked up by that exact name, so it resolves to a callable
        def of the same label. A dynamic name — a variable, an f-string, a concatenation,
        any expression — is not statically resolvable and yields ``None`` (no edge is
        manufactured), as do the 1-arg form and ``obj.getattr(...)`` (a method, not the
        builtin). Unlike an identifier, a string is an attribute name and is never
        shadowed by a param/local, so callers resolve it without the shadow guard.
        """
        fn = call_node.child_by_field_name("function")
        if fn is None or fn.type != "identifier" or _read_text(fn, source) != "getattr":
            return None
        args = call_node.child_by_field_name("arguments")
        if args is None:
            return None
        positional = [c for c in args.children
                      if c.is_named and c.type not in ("keyword_argument", "comment")]
        if len(positional) < 2:
            return None
        name_node = positional[1]
        if name_node.type != "string" or any(
            ch.type == "interpolation" for ch in name_node.children
        ):
            return None  # variable, f-string, concatenation, or expression — dynamic
        content = next(
            (ch for ch in name_node.children if ch.type == "string_content"), None)
        if content is None:
            return None  # empty string "" — no attribute name
        return _read_text(content, source), name_node

    def _php_class_const_scope(n) -> str | None:
        scope = n.child_by_field_name("scope")
        if scope is None:
            for c in n.children:
                if c.is_named and c.type in ("name", "qualified_name", "identifier"):
                    scope = c
                    break
        if scope is None:
            return None
        return _read_text(scope, source)

    _tracked_body_ids: set[int] = set()
    _JS_CLOSURE_TYPES = ("arrow_function", "function_expression")

    def walk_calls(
        node,
        caller_nid: str,
        java_types: dict[str, str] | None = None,
    ) -> None:
        if node.type in config.function_boundary_types:
            # JS/TS: an inline/returned closure not separately tracked in
            # function_bodies would otherwise drop its calls at this boundary.
            # Descend into it with the enclosing caller so `return () =>
            # svc.doThing()` links to the caller (#1630). Tracked closures
            # (const-assigned arrows) are walked with their own nid — skip to
            # avoid double-counting.
            if (config.ts_module in ("tree_sitter_javascript", "tree_sitter_typescript")
                    and node.type in _JS_CLOSURE_TYPES):
                body = node.child_by_field_name("body")
                if body is not None and id(body) not in _tracked_body_ids:
                    for child in node.children:
                        walk_calls(child, caller_nid, java_types)
            return

        if node.type in config.call_types:
            # JS/TS dynamic imports: await import('./foo.js')
            if config.ts_module in ("tree_sitter_javascript", "tree_sitter_typescript"):
                if _dynamic_import_js(node, source, caller_nid, str_path,
                                      edges, seen_dyn_import_pairs):
                    # Still recurse into children (import().then(...) may have calls)
                    for child in node.children:
                        walk_calls(child, caller_nid, java_types)
                    return

            callee_name: str | None = None
            is_member_call: bool = False
            is_this_field_call: bool = False
            swift_receiver: str | None = None
            member_receiver: str | None = None

            # Special handling per language
            if config.ts_module == "tree_sitter_swift":
                # Swift: first child may be simple_identifier or navigation_expression
                first = node.children[0] if node.children else None
                if first:
                    if first.type == "simple_identifier":
                        callee_name = _read_text(first, source)
                    elif first.type == "navigation_expression":
                        is_member_call = True
                        for child in first.children:
                            if child.type == "navigation_suffix":
                                for sc in child.children:
                                    if sc.type == "simple_identifier":
                                        callee_name = _read_text(sc, source)
                        # #1356: capture the receiver so the cross-file pass can
                        # resolve it through the file's type table.
                        recv_node = first.children[0] if first.children else None
                        swift_receiver = _swift_receiver_name(recv_node, source)
            elif config.ts_module == "tree_sitter_kotlin":
                # Kotlin: first child may be simple_identifier/identifier or
                # navigation_expression. PyPI's `tree_sitter_kotlin` produces
                # `identifier` for plain identifier nodes; older grammar
                # versions (including the JVM `io.github.bonede:tree-sitter-kotlin`
                # binding) produce `simple_identifier`. Accept both.
                first = node.children[0] if node.children else None
                if first:
                    if first.type in ("simple_identifier", "identifier"):
                        callee_name = _read_text(first, source)
                    elif first.type == "navigation_expression":
                        is_member_call = True
                        for child in reversed(first.children):
                            if child.type in ("simple_identifier", "identifier"):
                                callee_name = _read_text(child, source)
                                break
            elif config.ts_module == "tree_sitter_scala":
                # Scala: first child
                first = node.children[0] if node.children else None
                if first:
                    if first.type == "identifier":
                        callee_name = _read_text(first, source)
                    elif first.type == "field_expression":
                        is_member_call = True
                        field = first.child_by_field_name("field")
                        if field:
                            callee_name = _read_text(field, source)
                        else:
                            for child in reversed(first.children):
                                if child.type == "identifier":
                                    callee_name = _read_text(child, source)
                                    break
            elif config.ts_module == "tree_sitter_c_sharp" and node.type == "invocation_expression":
                # C#: the invoked function is the `function` field. A member call
                # `recv.Method(...)` is a member_access_expression (receiver in its
                # `expression` field, method in `name`). Capture a simple-identifier
                # or `this` receiver + set is_member_call so the receiver-typed
                # resolver (_resolve_csharp_member_calls) can bind it to the
                # receiver's declared type. Without this the bare method name matched
                # any same-named method in the corpus, silently mis-resolving
                # `_server.Save()` to an unrelated `Cache.Save()` (#1609).
                fn_node = node.child_by_field_name("function")
                if fn_node is not None and fn_node.type == "member_access_expression":
                    mname = fn_node.child_by_field_name("name")
                    recv = fn_node.child_by_field_name("expression")
                    if mname is not None:
                        callee_name = _read_text(mname, source)
                        is_member_call = True
                        if recv is not None and recv.type == "identifier":
                            member_receiver = _read_text(recv, source)
                        elif recv is not None and recv.type == "this_expression":
                            member_receiver = "this"
                elif fn_node is not None and fn_node.type == "identifier":
                    callee_name = _read_text(fn_node, source)
                else:
                    # Fallback: original name-field / first-named-child scan.
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        callee_name = _read_text(name_node, source)
                    else:
                        for child in node.children:
                            if child.is_named:
                                raw = _read_text(child, source)
                                if "." in raw:
                                    callee_name = raw.split(".")[-1]
                                    is_member_call = True
                                    parts = raw.split(".")
                                    if len(parts) == 2 and parts[0]:
                                        member_receiver = parts[0]
                                else:
                                    callee_name = raw
                                break
            elif config.ts_module == "tree_sitter_php":
                # PHP: distinguish call expression subtypes
                if node.type == "function_call_expression":
                    func_node = node.child_by_field_name("function")
                    if func_node:
                        callee_name = _read_text(func_node, source)
                elif node.type == "scoped_call_expression":
                    # Static method call: Helper::format() → callee = "Helper"
                    scope_node = node.child_by_field_name("scope")
                    if scope_node:
                        callee_name = _read_text(scope_node, source)
                else:
                    # member_call_expression: $obj->method()
                    is_member_call = True
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        callee_name = _read_text(name_node, source)
            elif config.ts_module == "tree_sitter_cpp":
                # C++: function field, then field_expression/qualified_identifier
                func_node = node.child_by_field_name(config.call_function_field) if config.call_function_field else None
                if func_node:
                    if func_node.type == "identifier":
                        callee_name = _read_text(func_node, source)
                    elif func_node.type == "field_expression":
                        # `f.bar()` / `f->bar()` / `this->bar()`: receiver is the
                        # `argument` (object) field, callee is the `field` (#1547).
                        # Capture a simple-identifier (or `this`) receiver so the
                        # cross-file pass can resolve it through the file's type
                        # table; chained receivers (`a.b.method()`) are left to bail.
                        is_member_call = True
                        name = func_node.child_by_field_name("field")
                        if name:
                            callee_name = _read_text(name, source)
                        obj = func_node.child_by_field_name("argument")
                        if obj is not None and obj.type == "identifier":
                            member_receiver = _read_text(obj, source)
                        elif obj is not None and obj.type == "this":
                            member_receiver = "this"
                    elif func_node.type == "qualified_identifier":
                        # `Foo::bar()`: the scope (`Foo`) is the receiver type named
                        # explicitly in source (EXTRACTED), the name is the callee.
                        is_member_call = True
                        name = func_node.child_by_field_name("name")
                        if name:
                            callee_name = _read_text(name, source)
                        scope = func_node.child_by_field_name("scope")
                        if scope is not None:
                            member_receiver = _read_text(scope, source)
            elif config.ts_module == "tree_sitter_java":
                if node.type == "object_creation_expression":
                    # `new Foo(...)` — the constructed type is in the `type` field,
                    # not `name`, so the generic path misses it (#1373).
                    type_node = node.child_by_field_name("type")
                    if type_node is not None:
                        raw = _read_text(type_node, source).split("<", 1)[0].strip()
                        if raw:
                            callee_name = raw.rsplit(".", 1)[-1]
                elif node.type == "method_invocation":
                    name_node = node.child_by_field_name("name")
                    if name_node is not None:
                        callee_name = _read_text(name_node, source)
                    receiver = node.child_by_field_name("object")
                    if receiver is not None:
                        is_member_call = True
                        if receiver.type == "identifier":
                            member_receiver = _read_text(receiver, source)
                        elif receiver.type == "this":
                            member_receiver = "this"
                        elif receiver.type == "field_access":
                            owner = receiver.child_by_field_name("object")
                            field = receiver.child_by_field_name("field")
                            if owner is not None and owner.type == "this" and field is not None:
                                member_receiver = f"this.{_read_text(field, source)}"
                                is_this_field_call = True
            elif config.ts_module == "tree_sitter_ruby":
                # Ruby's `call` node carries `receiver` and `method` as direct
                # fields (no intermediate accessor node), so the generic accessor
                # model doesn't apply. Read them directly and capture a simple
                # receiver (`p` in `p.run`, `Processor` in `Processor.new`) so the
                # cross-file pass can resolve member calls by the receiver's type.
                meth = node.child_by_field_name("method")
                if meth is not None:
                    callee_name = _read_text(meth, source)
                recv = node.child_by_field_name("receiver")
                if recv is not None:
                    is_member_call = True
                    if recv.type in ("identifier", "constant"):
                        member_receiver = _read_text(recv, source)
                    elif recv.type == "scope_resolution":
                        # Namespaced receiver `Billing::Processor.call` — capture the
                        # last constant so cross-file resolution can bind it by the
                        # bare class name (the god-node guard bails if ambiguous).
                        member_receiver = _ruby_const_last_name(recv, source) or None
            else:
                # Generic: get callee from call_function_field
                func_node = node.child_by_field_name(config.call_function_field) if config.call_function_field else None
                if func_node:
                    if func_node.type == "identifier":
                        callee_name = _read_text(func_node, source)
                    elif func_node.type in config.call_accessor_node_types:
                        is_member_call = True
                        if config.call_accessor_field:
                            attr = func_node.child_by_field_name(config.call_accessor_field)
                            if attr:
                                callee_name = _read_text(attr, source)
                        if config.call_accessor_object_field:
                            # Capture a simple-identifier receiver (e.g. `ClassName`
                            # in `ClassName.method()`) so cross-file member-call
                            # resolution can resolve qualified class-method calls
                            # (#1446). Chained receivers (`a.b.method()`) are skipped
                            # UNLESS the chain is `this.field.method()` (#1316).
                            obj = func_node.child_by_field_name(config.call_accessor_object_field)
                            if obj is not None and obj.type == "identifier":
                                member_receiver = _read_text(obj, source)
                            elif (obj is not None
                                  and obj.type in config.call_accessor_node_types
                                  and config.call_accessor_object_field):
                                inner_obj = obj.child_by_field_name(config.call_accessor_object_field)
                                if inner_obj is not None and inner_obj.type == "this":
                                    inner_prop = obj.child_by_field_name(config.call_accessor_field)
                                    if inner_prop is not None:
                                        member_receiver = _read_text(inner_prop, source)
                                        is_this_field_call = True
                    else:
                        # Try reading the node directly (e.g. Java name field is the callee)
                        callee_name = _read_text(func_node, source)

            if callee_name and callee_name not in _LANGUAGE_BUILTIN_GLOBALS:
                # A capitalized-receiver member call (`ClassName.method()`) must defer
                # to receiver-based cross-file resolution: the bare method name can
                # collide with an in-file node — even the calling method itself, when a
                # viewset action delegates to a same-named service action — which would
                # match `tgt_nid == caller_nid` and silently drop the call (#1446). The
                # captured receiver is resolved later in _resolve_python_member_calls.
                # C#: ANY member call with a captured receiver defers to the
                # receiver-typed resolver — a bare method-name match ignores the
                # receiver's declared type and mis-binds to an unrelated same-named
                # method (#1609). The receiver may be lowercase (`_server.Save()`),
                # so this is broader than the capitalized/this-field Python rule.
                _csharp_defer = (
                    config.ts_module == "tree_sitter_c_sharp"
                    and is_member_call and member_receiver
                )
                _java_defer = (
                    config.ts_module == "tree_sitter_java" and is_member_call
                )
                if _java_defer or (
                    is_member_call
                    and member_receiver
                    and (
                        member_receiver[:1].isupper()
                        or is_this_field_call
                        or _csharp_defer
                    )
                ):
                    tgt_nid = None
                else:
                    tgt_nid = label_to_nid.get(callee_name)
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        line = node.start_point[0] + 1
                        edges.append({
                            "source": caller_nid,
                            "target": tgt_nid,
                            "relation": "calls",
                            "context": "call",
                            "confidence": "EXTRACTED",
                            "source_file": str_path,
                            "source_location": f"L{line}",
                            "weight": 1.0,
                        })
                elif callee_name and not tgt_nid:
                    # Callee not in this file — save for cross-file resolution in extract()
                    rc_entry = {
                        "caller_nid": caller_nid,
                        "callee": callee_name,
                        "is_member_call": is_member_call,
                        "source_file": str_path,
                        "source_location": f"L{node.start_point[0] + 1}",
                        "receiver": swift_receiver or member_receiver,
                    }
                    # Ruby: attach the receiver's inferred type from the method's
                    # local `var = Const.new` bindings, when unambiguously known.
                    if member_receiver and config.ts_module == "tree_sitter_ruby":
                        rc_entry["receiver_type"] = ruby_var_types.get(
                            caller_nid, {}
                        ).get(member_receiver)
                    # Tag the C++ raw_call's language so the cross-file C++ resolver
                    # claims it unambiguously: a `.h` file routes to extract_cpp or
                    # extract_objc by content, and both resolvers see `.h` in their
                    # suffix sets, so a source_file suffix alone can't separate them.
                    if config.ts_module == "tree_sitter_cpp":
                        rc_entry["lang"] = "cpp"
                    # C#: tag the raw_call so _resolve_csharp_member_calls claims it
                    # and types the receiver against the file's field/param/local
                    # type table (#1609).
                    if config.ts_module == "tree_sitter_c_sharp":
                        rc_entry["lang"] = "csharp"
                    if config.ts_module == "tree_sitter_java":
                        rc_entry["lang"] = "java"
                        receiver_type = (java_types or {}).get(member_receiver or "")
                        if receiver_type:
                            rc_entry["receiver_type"] = receiver_type
                    raw_calls.append(rc_entry)

            # Indirect dispatch: a function passed BY NAME as a call argument
            # (executor.submit(fn), Thread(target=fn), map(fn, xs)) is a real dependency
            # the callee-only scan above can't see. Emit it as a distinct `indirect_call`
            # relation so strict `calls` queries stay precise while affected/blast-radius
            # picks up the edge. Python only for now; dispatch via dict literals, getattr
            # or decorators lives in other AST nodes and is left to a follow-up.
            #
            # Emission is general across call targets (no submit/map/Thread allow-list):
            # the value is catching a callback passed to ANY function. Two guards keep
            # it sound — without them an identifier merely matching a node label produced
            # false edges for the idiomatic shadow case and for plain data variables:
            #   1. SHADOWING — skip an argument that is a parameter or local binding of
            #      the enclosing function; it names a local value, not the module fn.
            #   2. CALLABLE TARGET — resolve only to a function / method / class def, so
            #      `process(config)` can't point at a same-named non-callable node.
            if config.ts_module == "tree_sitter_python":
                args_node = node.child_by_field_name("arguments")
                if args_node is not None:
                    enclosing_locals = local_bound_names.get(caller_nid, frozenset())
                    for arg in args_node.children:
                        if arg.type == "identifier":
                            _emit_indirect_ref(arg, caller_nid, enclosing_locals, "argument")
                        elif arg.type == "keyword_argument":
                            _emit_indirect_ref(
                                arg.child_by_field_name("value"),
                                caller_nid, enclosing_locals, "argument")
                # Reflective dispatch: getattr(obj, "handler") names a callable by
                # string literal (#1566 slice 3). The string is an ATTRIBUTE name, not
                # an identifier binding, so it is never shadowed by a param/local — it
                # resolves straight to the callable, bypassing the identifier shadow
                # guard. A dynamic name (getattr(obj, name)) is unresolvable → no edge.
                getattr_ref = _getattr_ref_name(node)
                if getattr_ref is not None:
                    ref_name, loc = getattr_ref
                    _emit_indirect_by_name(ref_name, loc, caller_nid, "getattr")
            elif config.ts_module in ("tree_sitter_javascript", "tree_sitter_typescript"):
                # JS/TS: a callback passed by name (`arr.map(fn)`, `setTimeout(fn)`,
                # `el.addEventListener("x", fn)`). Positional identifier args only —
                # inline arrows/function expressions are direct definitions, not a
                # by-name reference. No keyword args in JS (named args are objects,
                # handled by the collection pass).
                args_node = node.child_by_field_name("arguments")
                if args_node is not None:
                    enclosing_locals = local_bound_names.get(caller_nid, frozenset())
                    for arg in args_node.children:
                        if arg.type == "identifier":
                            _emit_indirect_ref(arg, caller_nid, enclosing_locals, "argument")

            # Helper function calls: config('foo.bar') → uses_config edge to "foo"
            if (callee_name and callee_name in config.helper_fn_names):
                args_node = node.child_by_field_name("arguments")
                first_key: str | None = None
                if args_node:
                    for arg in args_node.children:
                        if arg.type != "argument":
                            continue
                        for inner in arg.children:
                            if inner.type == "string":
                                for sc in inner.children:
                                    if sc.type == "string_content":
                                        first_key = _read_text(sc, source)
                                        break
                                break
                        if first_key:
                            break
                if first_key:
                    segment = first_key.split(".")[0]
                    tgt_nid = (label_to_nid_ci.get(segment.lower())
                               or label_to_nid_ci.get(f"{segment}.php".lower()))
                    if tgt_nid and tgt_nid != caller_nid:
                        relation = f"uses_{callee_name}"
                        pair3 = (caller_nid, tgt_nid, relation)
                        if pair3 not in seen_helper_ref_pairs:
                            seen_helper_ref_pairs.add(pair3)
                            line = node.start_point[0] + 1
                            edges.append({
                                "source": caller_nid,
                                "target": tgt_nid,
                                "relation": relation,
                                "confidence": "EXTRACTED",
                                "confidence_score": 1.0,
                                "source_file": str_path,
                                "source_location": f"L{line}",
                                "weight": 1.0,
                            })

            # Service container bindings: $this->app->bind(Foo::class, Bar::class)
            if (node.type == "member_call_expression"
                    and callee_name
                    and callee_name in config.container_bind_methods):
                args_node = node.child_by_field_name("arguments")
                class_args: list[str] = []
                if args_node:
                    for arg in args_node.children:
                        if arg.type != "argument":
                            continue
                        for inner in arg.children:
                            if inner.type == "class_constant_access_expression":
                                cls = _php_class_const_scope(inner)
                                if cls:
                                    class_args.append(cls)
                                break
                        if len(class_args) >= 2:
                            break
                if len(class_args) == 2:
                    contract_name, impl_name = class_args
                    contract_nid = label_to_nid_ci.get(contract_name.lower())
                    impl_nid = label_to_nid_ci.get(impl_name.lower())
                    if contract_nid and impl_nid and contract_nid != impl_nid:
                        pair3 = (contract_nid, impl_nid, "bound_to")
                        if pair3 not in seen_bind_pairs:
                            seen_bind_pairs.add(pair3)
                            line = node.start_point[0] + 1
                            edges.append({
                                "source": contract_nid,
                                "target": impl_nid,
                                "relation": "bound_to",
                                "confidence": "EXTRACTED",
                                "confidence_score": 1.0,
                                "source_file": str_path,
                                "source_location": f"L{line}",
                                "weight": 1.0,
                            })

        # Static property access: Foo::$bar → uses_static_prop edge
        if node.type in config.static_prop_types:
            scope_node = node.child_by_field_name("scope")
            if scope_node is None:
                for child in node.children:
                    if child.is_named and child.type in ("name", "qualified_name", "identifier"):
                        scope_node = child
                        break
            if scope_node is not None:
                class_name = _read_text(scope_node, source)
                tgt_nid = label_to_nid_ci.get(class_name.lower())
                if tgt_nid and tgt_nid != caller_nid:
                    pair3 = (caller_nid, tgt_nid, "uses_static_prop")
                    if pair3 not in seen_static_ref_pairs:
                        seen_static_ref_pairs.add(pair3)
                        line = node.start_point[0] + 1
                        edges.append({
                            "source": caller_nid,
                            "target": tgt_nid,
                            "relation": "uses_static_prop",
                            "confidence": "EXTRACTED",
                            "confidence_score": 1.0,
                            "source_file": str_path,
                            "source_location": f"L{line}",
                            "weight": 1.0,
                        })

        # PHP class constant access: Foo::BAR → references_constant edge
        if config.ts_module == "tree_sitter_php" and node.type == "class_constant_access_expression":
            class_name = _php_class_const_scope(node)
            if class_name:
                tgt_nid = label_to_nid_ci.get(class_name.lower())
                if tgt_nid and tgt_nid != caller_nid:
                    pair3 = (caller_nid, tgt_nid, "references_constant")
                    if pair3 not in seen_static_ref_pairs:
                        seen_static_ref_pairs.add(pair3)
                        line = node.start_point[0] + 1
                        edges.append({
                            "source": caller_nid,
                            "target": tgt_nid,
                            "relation": "references_constant",
                            "confidence": "EXTRACTED",
                            "confidence_score": 1.0,
                            "source_file": str_path,
                            "source_location": f"L{line}",
                            "weight": 1.0,
                        })

        # Dispatch tables (#1566): a function listed as a value in a dict/list/set/
        # tuple literal inside this body is an indirect dependency of the enclosing
        # function. Reuses the shared resolve-and-emit guard (callable-target-only,
        # not shadowed by a param/local, cross-file deferral).
        if config.ts_module == "tree_sitter_python" and node.type in (
            "dictionary", "list", "set", "tuple"
        ):
            enclosing_locals = local_bound_names.get(caller_nid, frozenset())
            for ident in _python_dispatch_value_idents(node):
                _emit_indirect_ref(ident, caller_nid, enclosing_locals, "collection")
        elif config.ts_module in ("tree_sitter_javascript", "tree_sitter_typescript") \
                and node.type in ("object", "array"):
            enclosing_locals = local_bound_names.get(caller_nid, frozenset())
            for ident in _js_dispatch_value_idents(node):
                _emit_indirect_ref(ident, caller_nid, enclosing_locals, "collection")

        # Assignment / return references (#1566 slice 2): a function bound to a name
        # (cb = handler) or returned from a factory (return handler) is an indirect
        # dependency of the enclosing function. The VALUE side only -- the assignment
        # TARGET is a new local binding, not a reference -- so the shared shadow guard
        # still holds (a param/local named on the RHS is the local, not the module fn).
        if config.ts_module == "tree_sitter_python" and node.type == "assignment":
            enclosing_locals = local_bound_names.get(caller_nid, frozenset())
            for ident in _python_ref_value_idents(node.child_by_field_name("right")):
                _emit_indirect_ref(ident, caller_nid, enclosing_locals, "assignment")
        elif config.ts_module == "tree_sitter_python" and node.type == "return_statement":
            enclosing_locals = local_bound_names.get(caller_nid, frozenset())
            value = next((c for c in node.children if c.is_named), None)
            for ident in _python_ref_value_idents(value):
                _emit_indirect_ref(ident, caller_nid, enclosing_locals, "return")

        for child in node.children:
            walk_calls(child, caller_nid, java_types)

    if config.ts_module == "tree_sitter_ruby":
        for caller_nid, body_node in function_bodies:
            ruby_var_types[caller_nid] = _ruby_local_class_bindings(body_node, source)

    # C++: build the per-file `var -> ClassName` table from local declarations in
    # every function body so the cross-file member-call pass can type a receiver
    # (#1547). File-scoped (not per-body): a later body's `Foo f;` doesn't clobber
    # an earlier binding (`var not in table`), keeping resolution conservative.
    if config.ts_module == "tree_sitter_cpp":
        for _caller_nid, body_node in function_bodies:
            _cpp_local_var_types(body_node, source, type_table)

    # Swift: type local `let x = Type()` / `let x = Type.shared` bindings inside
    # method bodies so `x.method()` on a later line resolves — class-level
    # properties are typed in the walk, but method-body locals were not (#1604).
    if config.ts_module == "tree_sitter_swift":
        for _caller_nid, body_node in function_bodies:
            _swift_local_var_types(body_node, source, type_table)

    # JS/TS: bodies already walked with their own caller_nid (const-assigned
    # arrows, methods). An INLINE/returned arrow or function-expression that is
    # NOT separately tracked (e.g. `return () => svc.doThing()`) is otherwise
    # skipped at the arrow boundary in walk_calls, losing its calls — so let
    # walk_calls descend into such untracked closures with the enclosing caller
    # (#1630 Pattern B). Guarding on the tracked set prevents double-walking.
    _tracked_body_ids.update(id(b) for _, b in function_bodies)

    for caller_nid, body_node in function_bodies:
        walk_calls(
            body_node,
            caller_nid,
            java_receiver_types.get(id(body_node)),
        )

    # #1356: walk property/field initializers (collected above). walk_calls
    # self-guards against re-entering function bodies and dedups via
    # seen_call_pairs, so a closure inside an initializer is not double-walked.
    for owner_nid, init_node in initializer_nodes:
        walk_calls(init_node, owner_nid)

    # ── Event listener pass ───────────────────────────────────────────────────
    seen_listen_pairs: set[tuple[str, str]] = set()
    for event_name, listener_name, line in pending_listen_edges:
        event_nid = label_to_nid_ci.get(event_name.lower())
        listener_nid = label_to_nid_ci.get(listener_name.lower())
        if not event_nid or not listener_nid or event_nid == listener_nid:
            continue
        pair2 = (event_nid, listener_nid)
        if pair2 in seen_listen_pairs:
            continue
        seen_listen_pairs.add(pair2)
        edges.append({
            "source": event_nid,
            "target": listener_nid,
            "relation": "listened_by",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        })

    # ── Module-level dispatch tables (#1566) ──────────────────────────────────
    # A function listed as a value in a TOP-LEVEL dict/list/set/tuple literal (a
    # route / handler registry) is an indirect dependency of the file. Attributed
    # to the file node. Function and class bodies are walked above, so this scan
    # stops at their boundaries — it must not re-attribute a method's local table
    # to the file, and class-attribute tables are a later refinement.
    if config.ts_module == "tree_sitter_python":
        module_bound = _python_module_bound_names(root, source)

        def _scan_module_dispatch(n) -> None:
            if n.type in ("function_definition", "class_definition"):
                return
            if n.type in ("dictionary", "list", "set", "tuple"):
                for ident in _python_dispatch_value_idents(n):
                    _emit_indirect_ref(ident, file_nid, module_bound, "collection")
            elif n.type == "assignment":
                # Module-level alias / re-export: CALLBACK = handler
                for ident in _python_ref_value_idents(n.child_by_field_name("right")):
                    _emit_indirect_ref(ident, file_nid, module_bound, "assignment")
            elif n.type == "call":
                # Module-level reflective dispatch: HANDLER = getattr(mod, "handler")
                # (#1566 slice 3). Attributed to the file node, like a module table.
                getattr_ref = _getattr_ref_name(n)
                if getattr_ref is not None:
                    ref_name, loc = getattr_ref
                    _emit_indirect_by_name(ref_name, loc, file_nid, "getattr")
            for c in n.children:
                _scan_module_dispatch(c)

        _scan_module_dispatch(root)
    elif config.ts_module in ("tree_sitter_javascript", "tree_sitter_typescript"):
        js_module_bound = _js_module_bound_names(root, source)

        def _scan_js_module_dispatch(n) -> None:
            if n.type in _JS_SCOPE_BOUNDARY:
                return  # function / class bodies are walked separately
            if n.type in ("object", "array"):
                for ident in _js_dispatch_value_idents(n):
                    _emit_indirect_ref(ident, file_nid, js_module_bound, "collection")
            elif n.type in ("call_expression", "new_expression"):
                # Module-level callback registration is idiomatic in JS — Express
                # routes (`app.get("/", handler)`), event wiring (`emitter.on("e",
                # handler)`), `setTimeout(fn)`. Capture identifier args as indirect
                # refs of the file (inline arrows are direct defs, not by-name refs).
                margs = n.child_by_field_name("arguments")
                if margs is not None:
                    for marg in margs.children:
                        if marg.type == "identifier":
                            _emit_indirect_ref(marg, file_nid, js_module_bound, "argument")
            for c in n.children:
                _scan_js_module_dispatch(c)

        _scan_js_module_dispatch(root)

    # ── Clean edges ───────────────────────────────────────────────────────────
    valid_ids = seen_ids
    clean_edges = []
    for edge in edges:
        src, tgt = edge["source"], edge["target"]
        if src in valid_ids and (tgt in valid_ids or edge["relation"] in ("imports", "imports_from", "re_exports")):
            clean_edges.append(edge)

    # Ruby mixins were collected during the node walk (before raw_calls existed);
    # fold them in so the cross-file resolver sees them (#1668).
    if _ruby_mixin_calls:
        raw_calls.extend(_ruby_mixin_calls)
    result = {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}
    if callable_def_nids:
        # Mark function / method / class defs with a `_callable` attribute so the
        # cross-file indirect_call pass can resolve a by-name callback only to a real
        # callable (never a same-named data symbol). A marker rides on the node dict
        # and survives the id-remap / disambiguation passes in extract(); a pre-remap
        # id set would go stale and silently drop every cross-file indirect edge when
        # ids are relativized (#1566 regression). Stripped before output, like origin_file.
        for n in nodes:
            if n["id"] in callable_def_nids:
                n["_callable"] = True
    if swift_extensions:
        result["swift_extensions"] = swift_extensions
    # TS/JS: augment the constructor-injection type table with local `new`
    # bindings and type-annotated parameters, so `const s = new Svc(); s.m()` and
    # a call on a typed param (incl. inside a closure) resolve (#1630). The
    # constructor-injection entries are populated during the walk above and win on
    # a name clash (first-binding-wins in the helper).
    if config.ts_module in ("tree_sitter_javascript", "tree_sitter_typescript"):
        _ts_receiver_type_table(root, source, type_table)
    if type_table:
        if config.ts_module == "tree_sitter_swift":
            result["swift_type_table"] = {"path": str_path, "table": type_table}
        elif config.ts_module in ("tree_sitter_javascript", "tree_sitter_typescript"):
            result["ts_type_table"] = {"path": str_path, "table": type_table}
        elif config.ts_module == "tree_sitter_cpp":
            result["cpp_type_table"] = {"path": str_path, "table": type_table}
    # C#: a file-wide receiver type table (field/property/param/local -> Type) for
    # _resolve_csharp_member_calls (#1609). Built from the whole tree, not just
    # function bodies, so class-level fields/properties are in scope for every method.
    if config.ts_module == "tree_sitter_c_sharp":
        cs_table = _csharp_member_type_table(root, source)
        if cs_table:
            result["csharp_type_table"] = {"path": str_path, "table": cs_table}
    return result

def _ts_decorator_name(deco_node, source: bytes) -> str | None:
    """Return the head symbol of a TS `decorator` node.

    `@Injectable` -> the identifier; `@Component({...})` / `@Input()` -> the
    `function` of the call_expression; `@ng.Component()` / `@core.Injectable` ->
    the `property` of the member_expression (the imported symbol, not the
    namespace alias).
    """
    for child in deco_node.children:
        if not child.is_named:
            continue
        target = child
        if target.type == "call_expression":
            target = target.child_by_field_name("function") or target
        if target.type == "member_expression":
            prop = target.child_by_field_name("property")
            return _read_text(prop, source) if prop else None
        if target.type == "identifier":
            return _read_text(target, source)
        return None
    return None

def _ts_method_name(method_node, source: bytes) -> str | None:
    """Name of a `method_definition`, matching the id the function-types branch
    builds (`_make_id(class_nid, name)`)."""
    name_node = method_node.child_by_field_name("name")
    return _read_text(name_node, source) if name_node else None

def _ts_descendant_decorators(node) -> list:
    """Collect `decorator` nodes under `node` (e.g. parameter decorators inside a
    method's formal_parameters, or a field's own decorator), without crossing into
    a nested class or a nested method, which own their own decorators."""
    out: list = []

    def rec(n, top: bool) -> None:
        for child in n.children:
            ct = child.type
            if ct == "decorator":
                out.append(child)
            elif ct in ("class_declaration", "abstract_class_declaration"):
                continue
            elif ct == "method_definition" and not top:
                continue
            else:
                rec(child, False)

    rec(node, True)
    return out

def _ts_emit_decorator_edges(class_node, class_nid: str, stem: str, source: bytes,
                             ensure_named_node, add_edge) -> None:
    """Emit `references` edges (context="decorator") from a class and its members
    to the symbols of the TS decorators applied to them.

    Decorators only occur on classes, class members, and parameters, so a single
    pass over the class declaration covers them. Members that are graph nodes
    (methods, incl. the constructor) own their decorators and their parameter
    decorators; members that are not nodes (fields, parameters) attribute to the
    enclosing class. Targets go through `ensure_named_node`, so a decorator
    imported from another module (the common case — `@Component` from
    `@angular/core`) becomes a sourceless stub the corpus rewire collapses onto
    the real definition.
    """
    def emit(deco_node, owner_nid: str) -> None:
        name = _ts_decorator_name(deco_node, source)
        if not name:
            return
        line = deco_node.start_point[0] + 1
        target = ensure_named_node(name, line)
        if target != owner_nid:
            add_edge(owner_nid, target, "references", line, context="decorator")

    # Class-level decorators: direct children of the class node (`@Deco class C`),
    # plus — when exported (`@Deco export class C`) — the decorators that sit on
    # the wrapping export_statement, before the class.
    for child in class_node.children:
        if child.type == "decorator":
            emit(child, class_nid)
    parent = class_node.parent
    if parent is not None and parent.type == "export_statement":
        for child in parent.children:
            if child.type == "decorator":
                emit(child, class_nid)
            elif child.type in ("class_declaration", "abstract_class_declaration"):
                break

    # Member decorators inside the class body.
    body = next((c for c in class_node.children if c.type == "class_body"), None)
    if body is None:
        return
    for member in body.children:
        mt = member.type
        if mt == "decorator":
            # A method decorator is a sibling preceding the method; skip past any
            # stacked decorators to find it.
            owner = class_nid
            sib = member.next_named_sibling
            while sib is not None and sib.type == "decorator":
                sib = sib.next_named_sibling
            if sib is not None and sib.type == "method_definition":
                mname = _ts_method_name(sib, source)
                if mname:
                    owner = _make_id(class_nid, mname)
            emit(member, owner)
        elif mt == "method_definition":
            mname = _ts_method_name(member, source)
            m_nid = _make_id(class_nid, mname) if mname else class_nid
            for deco in _ts_descendant_decorators(member):
                emit(deco, m_nid)
        else:
            # Fields / accessors: the member is not a node, so attribute its
            # decorators (e.g. `@Input()`, `@Column()`) to the class.
            for deco in _ts_descendant_decorators(member):
                emit(deco, class_nid)
