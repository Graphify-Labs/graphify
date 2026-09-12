"""Разбор интерфейса: стили (.css) и разметка (.html) + связь их с кодом.

Зачем. Штатный graphify строит граф по коду: функции и вызовы. Всё, что касается
вёрстки, для него не существует, поэтому вопрос «что сломается, если тронуть этот
класс» граф ответить не мог. Здесь добавлены три вещи:

  * из CSS достаются классы, идентификаторы и токены-переменные;
  * из HTML — те же классы и идентификаторы, встречающиеся в разметке;
  * из JS — обращения к ним из кода (querySelector, classList, closest и т. п.).

Узлы классов и идентификаторов у всех трёх разборщиков лежат в общем пространстве
имён, поэтому они склеиваются: один узел «.tp-canvas» связан и с правилом в стилях,
и с элементом в разметке, и с функцией, которая его трогает.

Сознательное упрощение: узел заводится на КЛАСС, а не на каждое правило. Правил в
крупном проекте десятки тысяч, граф из них превращается в кашу, а рассуждает человек
всё равно классами.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id  # noqa: F401

# Ограничители: интерфейсные файлы бывают огромными (styles.css на 400 КБ — обычное дело),
# но узлов из них должно выходить разумное количество, иначе граф теряет читаемость.
_MAX_BYTES = 4 * 1024 * 1024
_MAX_NODES_PER_FILE = 4000

_CLASS_RE = re.compile(r"\.(-?[_a-zA-Z][\w-]*)")
_ID_RE = re.compile(r"#(-?[_a-zA-Z][\w-]*)")
_VAR_DEF_RE = re.compile(r"(--[\w-]+)\s*:")
_VAR_USE_RE = re.compile(r"var\(\s*(--[\w-]+)")
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)


def _sel_node_id(kind: str, name: str) -> str:
    """Общее пространство имён для стилей, разметки и кода."""
    return _make_id("ui", kind, name)


def _sel_label(kind: str, name: str) -> str:
    return {"class": "." + name, "id": "#" + name, "var": name}[kind]


class _Collector:
    """Складывает узлы и рёбра, следит за потолком и не плодит повторов."""

    def __init__(self, path: Path):
        self.path = path
        self.str_path = str(path)
        self.nodes: list[dict] = []
        self.edges: list[dict] = []
        self._seen_nodes: set[str] = set()
        self._seen_edges: set[tuple] = set()

    def node(self, nid: str, label: str, line: int, file_type: str = "code",
             shared: bool = False) -> str | None:
        """shared=True — узел общий для стилей, разметки и кода.

        Такие узлы помечаются type="ui": graphify не добавляет им приставку по имени
        файла, поэтому «.tp-canvas» из styles.css, module.html и textproc.js — это
        один и тот же узел, а не три разных. Ровно ради этого всё и затевалось.
        """
        if not nid:
            return None
        if nid not in self._seen_nodes:
            if len(self._seen_nodes) >= _MAX_NODES_PER_FILE:
                return None
            self._seen_nodes.add(nid)
            n = {
                "id": nid, "label": label, "file_type": file_type,
                "source_file": self.str_path, "source_location": f"L{line}",
            }
            if shared:
                n["type"] = "ui"
            self.nodes.append(n)
        return nid

    def edge(self, src: str | None, tgt: str | None, relation: str, line: int,
             context: str | None = None) -> None:
        if not src or not tgt or src == tgt:
            return
        key = (src, tgt, relation)
        if key in self._seen_edges:
            return
        self._seen_edges.add(key)
        e = {
            "source": src, "target": tgt, "relation": relation,
            "confidence": "EXTRACTED", "source_file": self.str_path,
            "source_location": f"L{line}", "weight": 1.0,
        }
        if context:
            e["context"] = context
        self.edges.append(e)

    def result(self) -> dict:
        return {"nodes": self.nodes, "edges": self.edges}


def _read(path: Path) -> str | None:
    try:
        with path.open("rb") as f:
            raw = f.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES:
            return None
        return raw.decode("utf-8", errors="replace")
    except Exception:
        return None


# ---------------------------------------------------------------- стили


def _iter_css_rules(text: str):
    """Выдаёт (селектор, тело, номер строки) для правил верхнего уровня и внутри @-блоков.

    Свой проход вместо готового разборщика: зависимостей не добавляем, а нужны только
    селекторы и тела — с этим справляется счётчик скобок.
    """
    depth = 0
    buf: list[str] = []
    line = 1
    sel_line = 1
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\n":
            line += 1
        if ch == "{":
            selector = "".join(buf).strip()
            buf = []
            if selector.startswith("@"):
                # @media / @supports: внутрь заходим, само правило узлом не считаем
                depth += 1
                sel_line = line
                i += 1
                continue
            # тело правила
            body_start = i + 1
            body_depth = 1
            j = body_start
            body_line = line
            while j < n and body_depth:
                if text[j] == "{":
                    body_depth += 1
                elif text[j] == "}":
                    body_depth -= 1
                elif text[j] == "\n":
                    line += 1
                j += 1
            yield selector, text[body_start:j - 1], sel_line if sel_line > body_line else body_line
            i = j
            sel_line = line
            continue
        if ch == "}":
            depth = max(0, depth - 1)
            buf = []
            sel_line = line
            i += 1
            continue
        if ch == ";" and depth >= 0 and not buf:
            i += 1
            continue
        buf.append(ch)
        if len(buf) > 4000:  # защита от мусорного файла
            buf = []
        i += 1


def extract_css(path: Path) -> dict:
    """Классы, идентификаторы и токены из файла стилей."""
    text = _read(path)
    if text is None:
        return {"nodes": [], "edges": [], "error": "css file unreadable or too large"}
    text = _COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)

    c = _Collector(path)
    file_nid = c.node(_make_id(str(path)), path.name, 1)

    for selector, body, line in _iter_css_rules(text):
        if not selector or len(selector) > 600:
            continue
        targets: list[str] = []
        for name in set(_CLASS_RE.findall(selector)):
            nid = c.node(_sel_node_id("class", name), _sel_label("class", name), line, shared=True)
            c.edge(file_nid, nid, "styles", line, context="selector")
            if nid:
                targets.append(nid)
        for name in set(_ID_RE.findall(selector)):
            nid = c.node(_sel_node_id("id", name), _sel_label("id", name), line, shared=True)
            c.edge(file_nid, nid, "styles", line, context="selector")
            if nid:
                targets.append(nid)

        # Токены оформления: где заданы и кто ими пользуется.
        for var_name in set(_VAR_DEF_RE.findall(body)):
            vnid = c.node(_sel_node_id("var", var_name), _sel_label("var", var_name), line, shared=True)
            c.edge(file_nid, vnid, "defines_token", line)
        for var_name in set(_VAR_USE_RE.findall(body)):
            vnid = c.node(_sel_node_id("var", var_name), _sel_label("var", var_name), line, shared=True)
            for t in targets:
                c.edge(t, vnid, "uses_token", line)
            if not targets:
                c.edge(file_nid, vnid, "uses_token", line)

    return c.result()


# ---------------------------------------------------------------- разметка


class _MarkupParser(HTMLParser):
    def __init__(self, collector: _Collector, file_nid: str | None):
        super().__init__(convert_charrefs=True)
        self.c = collector
        self.file_nid = file_nid

    def handle_starttag(self, tag, attrs):
        line = self.getpos()[0]
        d = dict(attrs)
        el_id = (d.get("id") or "").strip()
        if el_id:
            nid = self.c.node(_sel_node_id("id", el_id), _sel_label("id", el_id), line, shared=True)
            self.c.edge(self.file_nid, nid, "markup", line, context=tag)
        classes = (d.get("class") or "").split()
        for name in classes[:12]:
            nid = self.c.node(_sel_node_id("class", name), _sel_label("class", name), line, shared=True)
            self.c.edge(self.file_nid, nid, "markup", line, context=tag)


def extract_html(path: Path) -> dict:
    """Идентификаторы и классы, встречающиеся в разметке."""
    text = _read(path)
    if text is None:
        return {"nodes": [], "edges": [], "error": "html file unreadable or too large"}
    c = _Collector(path)
    file_nid = c.node(_make_id(str(path)), path.name, 1)
    try:
        _MarkupParser(c, file_nid).feed(text)
    except Exception as e:  # разметка бывает сломанной — это не повод падать
        return {"nodes": c.nodes, "edges": c.edges, "error": str(e)}
    return c.result()


# ---------------------------------------------------------------- код → интерфейс

# Обращения к элементам из кода. Ловим и штатные способы, и принятые в проекте
# сокращения $ / $$ (обёртки над querySelector).
_JS_CALL_RE = re.compile(
    r"""(?P<fn>getElementById|querySelectorAll|querySelector|closest|matches|\$\$|\$)\s*\(\s*
        (?P<q>['"`])(?P<arg>[^'"`\n]{1,200})(?P=q)""",
    re.X,
)
_JS_CLASSLIST_RE = re.compile(
    r"""classList\s*\.\s*(?:add|remove|toggle|contains|replace)\s*\(\s*
        (?P<q>['"`])(?P<arg>[\w -]{1,120})(?P=q)""",
    re.X,
)


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _enclosing_symbol(nodes: list[dict], line: int) -> str | None:
    """Ближайшая функция выше по файлу — к ней и относим обращение.

    Точного разбора здесь нет намеренно: ради одной этой связи тащить AST заново
    дорого, а ошибка «прицепилось к соседней функции» не искажает картину — обе
    функции всё равно живут в одном файле и в одном сообществе.
    """
    best = None
    best_line = -1
    for n in nodes:
        loc = str(n.get("source_location") or "")
        if not loc.startswith("L"):
            continue
        try:
            nline = int(loc[1:].split("-")[0])
        except ValueError:
            continue
        if nline <= line and nline > best_line:
            best_line = nline
            best = n.get("id")
    return best


def selector_edges(path: Path, base_nodes: list[dict]) -> dict:
    """Рёбра «функция трогает этот класс/идентификатор» для файла кода."""
    text = _read(path)
    if text is None:
        return {"nodes": [], "edges": []}
    c = _Collector(path)
    file_nid = _make_id(str(path))

    def link(kind: str, name: str, line: int, how: str) -> None:
        nid = c.node(_sel_node_id(kind, name), _sel_label(kind, name), line, shared=True)
        src = _enclosing_symbol(base_nodes, line) or file_nid
        c.edge(src, nid, "touches_ui", line, context=how)

    for m in _JS_CALL_RE.finditer(text):
        arg = m.group("arg").strip()
        line = _line_of(text, m.start())
        fn = m.group("fn")
        if fn == "getElementById":
            if _ID_RE.fullmatch("#" + arg):
                link("id", arg, line, "getElementById")
            continue
        # селектор целиком: берём все классы и идентификаторы из него
        for name in set(_CLASS_RE.findall(arg)):
            link("class", name, line, fn)
        for name in set(_ID_RE.findall(arg)):
            link("id", name, line, fn)

    for m in _JS_CLASSLIST_RE.finditer(text):
        for name in m.group("arg").split():
            link("class", name, _line_of(text, m.start()), "classList")

    return c.result()
