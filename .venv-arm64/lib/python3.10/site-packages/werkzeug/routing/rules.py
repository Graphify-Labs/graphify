from __future__ import annotations

import ast
import re
import typing as t
from dataclasses import dataclass
from string import Template
from types import CodeType
from urllib.parse import quote

from ..datastructures import iter_multi_items
from ..urls import _urlencode
from .converters import ValidationError

if t.TYPE_CHECKING:
    from .converters import BaseConverter
    from .map import Map


class Weighting(t.NamedTuple):
    number_static_weights: int
    static_weights: list[tuple[int, int]]
    number_argument_weights: int
    argument_weights: list[int]


@dataclass
class RulePart:
    """A part of a rule.

    Rules can be represented by parts as delimited by `/` with
    instances of this class representing those parts. The *content* is
    either the raw content if *static* or a regex string to match
    against. The *weight* can be used to order parts when matching.

    """

    content: str
    final: bool
    static: bool
    suffixed: bool
    weight: Weighting


_part_re = re.compile(
    r"""
    (?:
        (?P<slash>/)                                 # a slash
      |
        (?P<static>[^</]+)                           # static rule data
      |
        (?:
          <
            (?:
              (?P<converter>[a-zA-Z_][a-zA-Z0-9_]*)   # converter name
              (?:\((?P<arguments>.*?)\))?             # converter arguments
              :                                       # variable delimiter
            )?
            (?P<variable>[a-zA-Z_][a-zA-Z0-9_]*)      # variable name
           >
        )
    )
    """,
    re.VERBOSE,
)

_simple_rule_re = re.compile(r"<([^>]+)>")
_converter_args_re = re.compile(
    r"""
    \s*
    ((?P<name>\w+)\s*=\s*)?
    (?P<value>
        True|False|
        \d+.\d+|
        \d+.|
        \d+|
        [\w\d_.]+|
        [urUR]?(?P<stringval>"[^"]*?"|'[^']*')
    )\s*,
    """,
    re.VERBOSE,
)

_PYTHON_CONSTANTS = {"None": None, "True": True, "False": False}


def _find(value: str, target: str, pos: int) -> int:
    """Find the *target* in *value* after *pos*.

    Returns the *value* length if *target* isn't found.
    """
    try:
        return value.index(target, pos)
    except ValueError:
        return len(value)


def _pythonize(value: str) -> None | bool | int | float | str:
    if value in _PYTHON_CONSTANTS:
        return _PYTHON_CONSTANTS[value]
    for convert in int, float:
        try:
            return convert(value)
        except ValueError:
            pass
    if value[:1] == value[-1:] and value[0] in "\"'":
        value = value[1:-1]
    return str(value)


def parse_converter_args(argstr: str) -> tuple[tuple[t.Any, ...], dict[str, t.Any]]:
    argstr += ","
    args = []
    kwargs = {}
    position = 0

    for item in _converter_args_re.finditer(argstr):
        if item.start() != position:
            raise ValueError(
                f"Cannot parse converter argument '{argstr[position : item.start()]}'"
            )

        value = item.group("stringval")
        if value is None:
            value = item.group("value")
        value = _pythonize(value)
        if not item.group("name"):
            args.append(value)
        else:
            name = item.group("name")
            kwargs[name] = value
        position = item.end()

    return tuple(args), kwargs


class RuleFactory:
    """As soon as you have more complex URL setups it's a good idea to use rule
    factories to avoid repetitive tasks.  Some of them are builtin, others can
    be added by subclassing `RuleFactory` and overriding `get_rules`.
    """

    def get_rules(self, map: Map) -> t.Iterable[Rule]:
        """Subclasses of `RuleFactory` have to override this method and return
        an iterable of rules."""
        raise NotImplementedError()


class Subdomain(RuleFactory):
    """All URLs provided by this factory have the subdomain set to a
    specific domain. For example if you want to use the subdomain for
    the current language this can be a good setup::

        url_map = Map([
            Rule('/', endpoint='#select_language'),
            Subdomain('<string(length=2):lang_code>', [
                Rule('/', endpoint='index'),
                Rule('/about', endpoint='about'),
                Rule('/help', endpoint='help')
            ])
        ])

    All the rules except for the ``'#select_language'`` endpoint will now
    listen on a two letter long subdomain that holds the language code
    for the current request.
    """

    def __init__(self, subdomain: str, rules: t.Iterable[RuleFactory]) -> None:
        self.subdomain = subdomain
        self.rules = rules

    def get_rules(self, map: Map) -> t.Iterator[Rule]:
        for rulefactory in self.rules:
            for rule in rulefactory.get_rules(map):
                rule = rule.empty()
                rule.subdomain = self.subdomain
                yield rule


class Submount(RuleFactory):
    """Like `Subdomain` but prefixes the URL rule with a given string::

        url_map = Map([
            Rule('/', endpoint='index'),
            Submount('/blog', [
                Rule('/', endpoint='blog/index'),
                Rule('/entry/<entry_slug>', endpoint='blog/show')
            ])
        ])

    Now the rule ``'blog/show'`` matches ``/blog/entry/<entry_slug>``.
    """

    def __init__(self, path: str, rules: t.Iterable[RuleFactory]) -> None:
        self.path = path.rstrip("/")
        self.rules = rules

    def get_rules(self, map: Map) -> t.Iterator[Rule]:
        for rulefactory in self.rules:
            for rule in rulefactory.get_rules(map):
                rule = rule.empty()
                rule.rule = self.path + rule.rule
                yield rule


class EndpointPrefix(RuleFactory):
    """Prefixes all endpoints (which must be strings for this factory) with
    another string. This can be useful for sub applications::

        url_map = Map([
            Rule('/', endpoint='index'),
            EndpointPrefix('blog/', [Submount('/blog', [
                Rule('/', endpoint='index'),
                Rule('/entry/<entry_slug>', endpoint='show')
            ])])
        ])
    """

    def __init__(self, prefix: str, rules: t.Iterable[RuleFactory]) -> None:
        self.prefix = prefix
        self.rules = rules

    def get_rules(self, map: Map) -> t.Iterator[Rule]:
        for rulefactory in self.rules:
            for rule in rulefactory.get_rules(map):
                rule = rule.empty()
                rule.endpoint = self.prefix + rule.endpoint
                yield rule


class RuleTemplate:
    """Returns copies of the rules wrapped and expands string templates in
    the endpoint, rule, defaults or subdomain sections.

    Here a small example for such a rule template::

        from werkzeug.routing import Map, Rule, RuleTemplate

        resource = RuleTemplate([
            Rule('/$name/', endpoint='$name.list'),
            Rule('/$name/<int:id>', endpoint='$name.show')
        ])

        url_map = Map([resource(name='user'), resource(name='page')])

    When a rule template is called the keyword arguments are used to
    replace the placeholders in all the string parameters.
    """

    def __init__(self, rules: t.Iterable[Rule]) -> None:
        self.rules = list(rules)

    def __call__(self, *args: t.Any, **kwargs: t.Any) -> RuleTemplateFactory:
        return RuleTemplateFactory(self.rules, dict(*args, **kwargs))


class RuleTemplateFactory(RuleFactory):
    """A factory that fills in template variables into rules.  Used by
    `RuleTemplate` internally.

    :internal:
    """

    def __init__(
        self, rules: t.Iterable[RuleFactory], context: dict[str, t.Any]
    ) -> None:
        self.rules = rules
        self.context = context

    def get_rules(self, map: Map) -> t.Iterator[Rule]:
        for rulefactory in self.rules:
            for rule in rulefactory.get_rules(map):
                new_defaults = subdomain = None
                if rule.defaults:
                    new_defaults = {}
                    for key, value in rule.defaults.items():
                        if isinstance(value, str):
                            value = Template(value).substitute(self.context)
                        new_defaults[key] = value
                if rule.subdomain is not None:
                    subdomain = Template(rule.subdomain).substitute(self.context)
                new_endpoint = rule.endpoint
                if isinstance(new_endpoint, str):
                    new_endpoint = Template(new_endpoint).substitute(self.context)
                yield Rule(
                    Template(rule.rule).substitute(self.context),
                    new_defaults,
                    subdomain,
                    rule.methods,
                    rule.build_only,
                    new_endpoint,
                    rule.strict_slashes,
                )


_ASTT = t.TypeVar("_ASTT", bound=ast.AST)


def _prefix_names(src: str, expected_type: type[_ASTT]) -> _ASTT:
    """ast parse and prefix names with `.` to avoid collision with user vars"""
    tree: ast.AST = ast.parse(src).body[0]
    if isinstance(tree, ast.Expr):
        tree = tree.value
    if not isinstance(tree, expected_type):
        raise TypeError(
            f"AST node is of type {type(tree).__name__}, not {expected_type.__name__}"
        )
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            node.id = f".{node.id}"
    return tree


_CALL_CONVERTER_CODE_FMT = "self._converters[{elem!r}].to_url()"
_IF_KWARGS_URL_ENCODE_CODE = """\
if kwargs:
    params = self._encode_query_vars(kwargs)
    q = "?" if params else ""
else:
    q = params = ""
"""
_IF_KWARGS_URL_ENCODE_AST = _prefix_names(_IF_KWARGS_URL_ENCODE_CODE, ast.If)
_URL_ENCODE_AST_NAMES = (
    _prefix_names("q", ast.Name),
    _prefix_names("params", ast.Name),
)


class Rule(RuleFactory):
    """A Rule represents one URL pattern.  There are some options for `Rule`
    that change the way it behaves and are passed to the `Rule` constructor.
    Note that besides the rule-string all arguments *must* be keyword arguments
    in order to not break the application on Werkzeug upgrades.

    `string`
        Rule strings basically are just normal URL paths with placeholders in
        the format ``<converter(arguments):name>`` where the converter and the
        arguments are optional.  If no converter is defined the `default`
        converter is used which means `string` in the normal configuration.

        URL rules that end with a slash are branch URLs, others are leaves.
        If you have `strict_slashes` enabled (which is the default), all
        branch URLs that are matched without a trailing slash will trigger a
        redirect to the same URL with the missing slash appended.

        The converters are defined on the `Map`.

    `endpoint`
        The endpoint for this rule. This can be anything. A reference to a
        function, a string, a number etc.  The preferred way is using a string
        because the endpoint is used for URL generation.

    `defaults`
        An optional dict with defaults for other rules with the same endpoint.
        This is a bit tricky but useful if you want to have unique URLs::

            url_map = Map([
                Rule('/all/', defaults={'page': 1}, endpoint='all_entries'),
                Rule('/all/page/<int:page>', endpoint='all_entries')
            ])

        If a user now visits ``http://example.com/all/page/1`` they will be
        redirected to ``http://example.com/all/``.  If `redirect_defaults` is
        disabled on the `Map` instance this will only affect the URL
        generation.

    `subdomain`
        The subdomain rule string for this rule. If not specified the rule
        only matches for the `default_subdomain` of the map.  If the map is
        not bound to a subdomain this feature is disabled.

        Can be useful if you want to have user profiles on different subdomains
        and all subdomains are forwarded to your application::

            url_map = Map([
                Rule('/', subdomain='<username>', endpoint='user/homepage'),
                Rule('/stats', subdomain='<username>', endpoint='user/stats')
            ])

    `methods`
        A sequence of http methods this rule applies to.  If not specified, all
        methods are allowed. For example this can be useful if you want different
        endpoints for `POST` and `GET`.  If methods are defined and the path
        matches but the method matched against is not in this list or in the
        list of another rule for that path the error raised is of the type
        `MethodNotAllowed` rather than `NotFound`.  If `GET` is present in the
        list of methods and `HEAD` is not, `HEAD` is added automatically.

    `strict_slashes`
        Override the `Map` setting for `strict_slashes` only for this rule. If
        not specified the `Map` setting is used.

    `merge_slashes`
        Override :attr:`Map.merge_slashes` for this rule.

    `build_only`
        Set this to True and the rule will never match but will create a URL
        that can be build. This is useful if you have resources on a subdomain
        or folder that are not handled by the WSGI application (like static data)

    `redirect_to`
        If given this must be either a string or callable.  In case of a
        callable it's called with the url adapter that triggered the match and
        the values of the URL as keyword arguments and has to return the target
        for the redirect, otherwise it has to be a string with placeholders in
        rule syntax::

            def foo_with_slug(adapter, id):
                # ask the database for the slug for the old id.  this of
                # course has nothing to do with werkzeug.
                return f'foo/{Foo.get_slug_for_id(id)}'

            url_map = Map([
                Rule('/foo/<slug>', endpoint='foo'),
                Rule('/some/old/url/<slug>', redirect_to='foo/<slug>'),
                Rule('/other/old/url/<int:id>', redirect_to=foo_with_slug)
            ])

        When the rule is matched the routing system will raise a
        `RequestRedirect` exception with the target for the redirect.

        Keep in mind that the URL will be joined against the URL root of the
        script so don't use a leading slash on the target URL unless you
        really mean root of that domain.

    `alias`
        If enabled this rule serves as an alias for another rule with the same
        endpoint and arguments.

    `host`
        If provided and the URL map has host matching enabled this can be
        used to provide a match rule for the whole host.  This also means
        that the subdomain feature is disabled.

    `websocket`
        If ``True``, this rule is only matches for WebSocket (``ws://``,
        ``wss://``) requests. By default, rules will only match for HTTP
        requests.

    .. versionchanged:: 2.1
        Percent-encoded newlines (``%0a``), which are decoded by WSGI
        servers, are considered when routing instead of terminating the
        match early.

    .. versionadded:: 1.0
        Added ``websocket``.

    .. versionadded:: 1.0
        Added ``merge_slashes``.

    .. versionadded:: 0.7
        Added ``alias`` and ``host``.

    .. versionchanged:: 0.6.1
       ``HEAD`` is added to ``methods`` if ``GET`` is present.
    """

    def __init__(
        self,
        string: str,
        defaults: t.Mapping[str, t.Any] | None = None,
        subdomain: str | None = None,
        methods: t.Iterable[str] | None = None,
        build_only: bool = False,
        endpoint: t.Any | None = None,
        strict_slashes: bool | None = None,
        merge_slashes: bool | None = None,
        redirect_to: str | t.Callable[..., str] | None = None,
        alias: bool = False,
        host: str | None = None,
        websocket: bool = False,
    ) -> None:
        if not string.startswith("/"):
            raise ValueError(f"URL rule '{string}' must start with a slash.")

        self.rule = string
        self.is_leaf = not string.endswith("/")
        self.is_branch = string.endswith("/")

        self.map: Map = None  # type: ignore
        self.strict_slashes = strict_slashes
        self.merge_slashes = merge_slashes
        self.subdomain = subdomain
        self.host = host
        self.defaults = defaults
        self.build_only = build_only
        self.alias = alias
        self.websocket = websocket

        if methods is not None:
            if isinstance(methods, str):
                raise TypeError("'methods' should be a list of strings.")

            methods = {x.upper() for x in methods}

            if "HEAD" not in methods and "GET" in methods:
                methods.add("HEAD")

            if websocket and methods - {"GET", "HEAD", "OPTIONS"}:
                raise ValueError(
                    "WebSocket rules can only use 'GET', 'HEAD', and 'OPTIONS' methods."
                )

        self.methods = methods
        self.endpoint: t.Any = endpoint
        self.redirect_to = redirect_to

        if defaults:
            self.arguments = set(map(str, defaults))
        else:
            self.arguments = set()

        self._converters: dict[str, BaseConverter] = {}
        self._trace: list[tuple[bool, str]] = []
        self._parts: list[RulePart] = []

    def empty(self) -> Rule:
        """
        Return an unbound copy of this rule.

        This can be useful if want to reuse an already bound URL for another
        map.  See ``get_empty_kwargs`` to override what keyword arguments are
        provided to the new copy.
        """
        return type(self)(self.rule, **self.get_empty_kwargs())

    def get_empty_kwargs(self) -> t.Mapping[str, t.Any]:
        """
        Provides kwargs for instantiating empty copy with empty()

        Use this method to provide custom keyword arguments to the subclass of
        ``Rule`` when calling ``some_rule.empty()``.  Helpful when the subclass
        has custom keyword arguments that are needed at instantiation.

        Must return a ``dict`` that will be provided as kwargs to the new
        instance of ``Rule``, following the initial ``self.rule`` value which
        is always provided as the first, required positional argument.
        """
        defaults = None
        if self.defaults:
            defaults = dict(self.defaults)
        return dict(
            defaults=defaults,
            subdomain=self.subdomain,
            methods=self.methods,
            build_only=self.build_only,
            endpoint=self.endpoint,
            strict_slashes=self.strict_slashes,
            redirect_to=self.redirect_to,
            alias=self.alias,
            host=self.host,
        )

    def get_rules(self, map: Map) -> t.Iterator[Rule]:
        yield self

    def refresh(self) -> None:
        """Rebinds and refreshes the URL.  Call this if you modified the
        rule in place.

        :internal:
        """
        self.bind(self.map, rebind=True)

    def bind(self, map: Map, rebind: bool = False) -> None:
        """Bind the url to a map and create a regular expression based on
        the information from the rule itself and the defaults from the map.

        :internal:
        """
        if self.map is not None and not rebind:
            raise RuntimeError(f"url rule {self!r} already bound to map {self.map!r}")
        self.map = map
        if self.strict_slashes is None:
            self.strict_slashes = map.strict_slashes
        if self.merge_slashes is None:
            self.merge_slashes = map.merge_slashes
        if self.subdomain is None:
            self.subdomain = map.default_subdomain
        self.compile()

    def get_converter(
        self,
        variable_name: str,
        converter_name: str,
        args: tuple[t.Any, ...],
        kwargs: t.Mapping[str, t.Any],
    ) -> BaseConverter:
        """Looks up the converter for the given parameter.

        .. versionadded:: 0.9
        """
        if converter_name not in self.map.converters:
            raise LookupError(f"the converter {converter_name!r} does not exist")
        return self.map.converters[converter_name](self.map, *args, **kwargs)

    def _encode_query_vars(self, query_vars: t.Mapping[str, t.Any]) -> str:
        items: t.Iterable[tuple[str, str]] = iter_multi_items(query_vars)

        if self.map.sort_parameters:
            items = sorted(items, key=self.map.sort_key)

        return _urlencode(items)

    def _parse_rule(self, rule: str) -> t.Iterable[RulePart]:
        content = ""
        static = True
        argument_weights = []
        static_weights: list[tuple[int, int]] = []
        final = False
        convertor_number = 0

        pos = 0
        while pos < len(rule):
            match = _part_re.match(rule, pos)
            if match is None:
                raise ValueError(f"malformed url rule: {rule!r}")

            data = match.groupdict()
            if data["static"] is not None:
                static_weights.append((len(static_weights), -len(data["static"])))
                self._trace.append((False, data["static"]))
                content += data["static"] if static else re.escape(data["static"])

            if data["variable"] is not None:
                if static:
                    # Switching content to represent regex, hence the need to escape
                    content = re.escape(content)
                static = False
                c_args, c_kwargs = parse_converter_args(data["arguments"] or "")
                convobj = self.get_converter(
                    data["variable"], data["converter"] or "default", c_args, c_kwargs
                )
                self._converters[data["variable"]] = convobj
                self.arguments.add(data["variable"])
                if not convobj.part_isolating:
                    final = True
                content += f"(?P<__werkzeug_{convertor_number}>{convobj.regex})"
                convertor_number += 1
                argument_weights.append(convobj.weight)
                self._trace.append((True, data["variable"]))

            if data["slash"] is not None:
                self._trace.append((False, "/"))
                if final:
                    content += "/"
                else:
                    if not static:
                        content += r"\Z"
                    weight = Weighting(
                        -len(static_weights),
                        static_weights,
                        -len(argument_weights),
                        argument_weights,
                    )
                    yield RulePart(
                        content=content,
                        final=final,
                        static=static,
                        suffixed=False,
                        weight=weight,
                    )
                    content = ""
                    static = True
                    argument_weights = []
                    static_weights = []
                    final = False
                    convertor_number = 0

            pos = match.end()

        suffixed = False
        if final and content[-1] == "/":
            # If a converter is part_isolating=False (matches slashes) and ends with a
            # slash, augment the regex to support slash redirects.
            suffixed = True
            content = content[:-1] + "(?<!/)(/?)"
        if not static:
            content += r"\Z"
        weight = Weighting(
            -len(static_weights),
            static_weights,
            -len(argument_weights),
            argument_weights,
        )
        yield RulePart(
            content=content,
            final=final,
            static=static,
            suffixed=suffixed,
            weight=weight,
        )
        if suffixed:
            yield RulePart(
                content="", final=False, static=True, suffixed=False, weight=weight
            )

    def compile(self) -> None:
        """Compiles the regular expression and stores it."""
        assert self.map is not None, "rule not bound"

        if self.map.host_matching:
            domain_rule = self.host or ""
        else:
            domain_rule = self.subdomain or ""
        self._parts = []
        self._trace = []
        self._converters = {}
        if domain_rule == "":
            self._parts = [
                RulePart(
                    content="",
                    final=False,
                    static=True,
                    suffixed=False,
                    weight=Weighting(0, [], 0, []),
                )
            ]
        else:
            self._parts.extend(self._parse_rule(domain_rule))
        self._trace.append((False, "|"))
        rule = self.rule
        if self.merge_slashes:
            rule = re.sub("/{2,}", "/", self.rule)
        self._parts.extend(self._parse_rule(rule))

        self._build: t.Callable[..., tuple[str, str]]
        self._build = self._compile_builder(False).__get__(self, None)
        self._build_unknown: t.Callable[..., tuple[str, str]]
        self._build_unknown = self._compile_builder(True).__get__(self, None)

    @staticmethod
    def _get_func_code(code: CodeType, name: str) -> t.Callable[..., tuple[str, str]]:
        globs: dict[str, t.Any] = {}
        locs: dict[str, t.Any] = {}
        exec(code, globs, locs)
        return locs[name]  # type: ignore

    def _compile_builder(
        self, append_unknown: bool = True
    ) -> t.Callable[..., tuple[str, str]]:
        defaults = self.defaults or {}
        dom_ops: list[tuple[bool, str]] = []
        url_ops: list[tuple[bool, str]] = []

        opl = dom_ops
        for is_dynamic, data in self._trace:
            if data == "|" and opl is dom_ops:
                opl = url_ops
                continue
            # this seems like a silly case to ever come up but:
            # if a default is given for a value that appears in the rule,
            # resolve it to a constant ahead of time
            if is_dynamic and data in defaults:
                data = self._converters[data].to_url(defaults[data])
                opl.append((False, data))
            elif not is_dynamic:
                # safe = https://url.spec.whatwg.org/#url-path-segment-string
                opl.append((False, quote(data, safe="!$&'()*+,/:;=@")))
            else:
                opl.append((True, data))

        def _convert(elem: str) -> ast.Call:
            ret = _prefix_names(_CALL_CONVERTER_CODE_FMT.format(elem=elem), ast.Call)
            ret.args = [ast.Name(elem, ast.Load())]
            return ret

        def _parts(ops: list[tuple[bool, str]]) -> list[ast.expr]:
            parts: list[ast.expr] = [
                _convert(elem) if is_dynamic else ast.Constant(elem)
                for is_dynamic, elem in ops
            ]
            parts = parts or [ast.Constant("")]
            # constant fold
            ret = [parts[0]]
            for p in parts[1:]:
                if isinstance(p, ast.Constant) and isinstance(ret[-1], ast.Constant):
                    ret[-1] = ast.Constant(ret[-1].value + p.value)  # type: ignore[operator]
                else:
                    ret.append(p)
            return ret

        dom_parts = _parts(dom_ops)
        url_parts = _parts(url_ops)
        body: list[ast.stmt]
        if not append_unknown:
            body = []
        else:
            body = [_IF_KWARGS_URL_ENCODE_AST]
            url_parts.extend(_URL_ENCODE_AST_NAMES)

        def _join(parts: list[ast.expr]) -> ast.expr:
            if len(parts) == 1:  # shortcut
                return parts[0]
            return ast.JoinedStr(parts)

        body.append(
            ast.Return(ast.Tuple([_join(dom_parts), _join(url_parts)], ast.Load()))
        )

        pargs = [
            elem
            for is_dynamic, elem in dom_ops + url_ops
            if is_dynamic and elem not in defaults
        ]
        kargs = [str(k) for k in defaults]

        func_ast = _prefix_names("def _(): pass", ast.FunctionDef)
        func_ast.name = f"<builder:{self.rule!r}>"
        func_ast.args.args.append(ast.arg(".self", None))
        for arg in pargs + kargs:
            func_ast.args.args.append(ast.arg(arg, None))
        func_ast.args.kwarg = ast.arg(".kwargs", None)
        for _ in kargs:
            func_ast.args.defaults.append(ast.Constant(""))
        func_ast.body = body

        # Use `ast.parse` instead of `ast.Module` for better portability, since the
        # signature of `ast.Module` can change.
        module = ast.parse("")
        module.body = [func_ast]

        # mark everything as on line 1, offset 0
        # less error-prone than `ast.fix_missing_locations`
        # bad line numbers cause an assert to fail in debug builds
        for node in ast.walk(module):
            if "lineno" in node._attributes:
                node.lineno = 1  # type: ignore[attr-defined]
            if "end_lineno" in node._attributes:
                node.end_lineno = node.lineno  # type: ignore[attr-defined]
            if "col_offset" in node._attributes:
                node.col_offset = 0  # type: ignore[attr-defined]
            if "end_col_offset" in node._attributes:
                node.end_col_offset = node.col_offset  # type: ignore[attr-defined]

        code = compile(module, "<werkzeug routing>", "exec")
        return self._get_func_code(code, func_ast.name)

    def build(
        self, values: t.Mapping[str, t.Any], append_unknown: bool = True
    ) -> tuple[str, str] | None:
        """Assembles the relative url for that rule and the subdomain.
        If building doesn't work for some reasons `None` is returned.

        :internal:
        """
        try:
            if append_unknown:
                return self._build_unknown(**values)
            else:
                return self._build(**values)
        except ValidationError:
            return None

    def provides_defaults_for(self, rule: Rule) -> bool:
        """Check if this rule has defaults for a given rule.

        :internal:
        """
        return bool(
            not self.build_only
            and self.defaults
            and self.endpoint == rule.endpoint
            and self != rule
            and self.arguments == rule.arguments
        )

    def suitable_for(
        self, values: t.Mapping[str, t.Any], method: str | None = None
    ) -> bool:
        """Check if the dict of values has enough data for url generation.

        :internal:
        """
        # if a method was given explicitly and that method is not supported
        # by this rule, this rule is not suitable.
        if (
            method is not None
            and self.methods is not None
            and method not in self.methods
        ):
            return False

        defaults = self.defaults or ()

        # all arguments required must be either in the defaults dict or
        # the value dictionary otherwise it's not suitable
        for key in self.arguments:
            if key not in defaults and key not in values:
                return False

        # in case defaults are given we ensure that either the value was
        # skipped or the value is the same as the default value.
        if defaults:
            for key, value in defaults.items():
                if key in values and value != values[key]:
                    return False

        return True

    def build_compare_key(self) -> tuple[int, int, int]:
        """The build compare key for sorting.

        :internal:
        """
        return (1 if self.alias else 0, -len(self.arguments), -len(self.defaults or ()))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, type(self)) and self._trace == other._trace

    __hash__ = None  # type: ignore

    def __str__(self) -> str:
        return self.rule

    def __repr__(self) -> str:
        if self.map is None:
            return f"<{type(self).__name__} (unbound)>"
        parts = []
        for is_dynamic, data in self._trace:
            if is_dynamic:
                parts.append(f"<{data}>")
            else:
                parts.append(data)
        parts_str = "".join(parts).lstrip("|")
        methods = f" ({', '.join(self.methods)})" if self.methods is not None else ""
        return f"<{type(self).__name__} {parts_str!r}{methods} -> {self.endpoint}>"
