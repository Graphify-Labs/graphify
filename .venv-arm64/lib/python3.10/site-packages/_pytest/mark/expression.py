r"""Evaluate match expressions, as used by `-k` and `-m`.

The grammar is:

expression: expr? EOF
expr:       and_expr ('or' and_expr)*
and_expr:   not_expr ('and' not_expr)*
not_expr:   'not' not_expr | '(' expr ')' | ident kwargs?

ident:      (\w|:|\+|-|\.|\[|\]|\\|/)+
kwargs:     ('(' name '=' value ( ', ' name '=' value )*  ')')
name:       a valid ident, but not a reserved keyword
value:      (unescaped) string literal | (-)?[0-9]+ | 'False' | 'True' | 'None'

The semantics are:

- Empty expression evaluates to False.
- ident evaluates to True or False according to a provided matcher function.
- ident with parentheses and keyword arguments evaluates to True or False according to a provided matcher function.
- or/and/not evaluate according to the usual boolean semantics.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from collections.abc import Mapping
from collections.abc import Sequence
import dataclasses
import enum
import keyword
import re
import types
from typing import Final
from typing import final
from typing import Literal
from typing import NoReturn
from typing import overload
from typing import Protocol


__all__ = [
    "Expression",
    "ExpressionMatcher",
]


FILE_NAME: Final = "<pytest match expression>"


class TokenType(enum.Enum):
    LPAREN = "left parenthesis"
    RPAREN = "right parenthesis"
    OR = "or"
    AND = "and"
    NOT = "not"
    IDENT = "identifier"
    EOF = "end of input"
    EQUAL = "="
    STRING = "string literal"
    COMMA = ","


@dataclasses.dataclass(frozen=True)
class Token:
    __slots__ = ("pos", "type", "value")
    type: TokenType
    value: str
    pos: int


class Scanner:
    __slots__ = ("current", "input", "tokens")

    def __init__(self, input: str) -> None:
        self.input = input
        self.tokens = self.lex(input)
        self.current = next(self.tokens)

    def lex(self, input: str) -> Iterator[Token]:
        pos = 0
        while pos < len(input):
            if input[pos] in (" ", "\t"):
                pos += 1
            elif input[pos] == "(":
                yield Token(TokenType.LPAREN, "(", pos)
                pos += 1
            elif input[pos] == ")":
                yield Token(TokenType.RPAREN, ")", pos)
                pos += 1
            elif input[pos] == "=":
                yield Token(TokenType.EQUAL, "=", pos)
                pos += 1
            elif input[pos] == ",":
                yield Token(TokenType.COMMA, ",", pos)
                pos += 1
            elif (quote_char := input[pos]) in ("'", '"'):
                end_quote_pos = input.find(quote_char, pos + 1)
                if end_quote_pos == -1:
                    raise SyntaxError(
                        f'closing quote "{quote_char}" is missing',
                        (FILE_NAME, 1, pos + 1, input),
                    )
                value = input[pos : end_quote_pos + 1]
                if (backslash_pos := value.find("\\")) != -1:
                    raise SyntaxError(
                        r'escaping with "\" not supported in marker expression',
                        (FILE_NAME, 1, pos + backslash_pos + 1, input),
                    )
                yield Token(TokenType.STRING, value, pos)
                pos += len(value)
            else:
                match = re.match(r"(:?\w|:|\+|-|\.|\[|\]|\\|/)+", input[pos:])
                if match:
                    value = match.group(0)
                    if value == "or":
                        yield Token(TokenType.OR, value, pos)
                    elif value == "and":
                        yield Token(TokenType.AND, value, pos)
                    elif value == "not":
                        yield Token(TokenType.NOT, value, pos)
                    else:
                        yield Token(TokenType.IDENT, value, pos)
                    pos += len(value)
                else:
                    raise SyntaxError(
                        f'unexpected character "{input[pos]}"',
                        (FILE_NAME, 1, pos + 1, input),
                    )
        yield Token(TokenType.EOF, "", pos)

    @overload
    def accept(self, type: TokenType, *, reject: Literal[True]) -> Token: ...

    @overload
    def accept(
        self, type: TokenType, *, reject: Literal[False] = False
    ) -> Token | None: ...

    def accept(self, type: TokenType, *, reject: bool = False) -> Token | None:
        if self.current.type is type:
            token = self.current
            if token.type is not TokenType.EOF:
                self.current = next(self.tokens)
            return token
        if reject:
            self.reject((type,))
        return None

    def reject(self, expected: Sequence[TokenType]) -> NoReturn:
        raise SyntaxError(
            "expected {}; got {}".format(
                " OR ".join(type.value for type in expected),
                self.current.type.value,
            ),
            (FILE_NAME, 1, self.current.pos + 1, self.input),
        )


# True, False and None are legal match expression identifiers,
# but illegal as Python identifiers. To fix this, this prefix
# is added to identifiers in the conversion to Python AST.
IDENT_PREFIX = "$"


def expression(s: Scanner) -> ast.Expression:
    if s.accept(TokenType.EOF):
        ret: ast.expr = ast.Constant(False)
    else:
        ret = expr(s)
        s.accept(TokenType.EOF, reject=True)
    return ast.fix_missing_locations(ast.Expression(ret))


def expr(s: Scanner) -> ast.expr:
    ret = and_expr(s)
    while s.accept(TokenType.OR):
        rhs = and_expr(s)
        ret = ast.BoolOp(ast.Or(), [ret, rhs])
    return ret


def and_expr(s: Scanner) -> ast.expr:
    ret = not_expr(s)
    while s.accept(TokenType.AND):
        rhs = not_expr(s)
        ret = ast.BoolOp(ast.And(), [ret, rhs])
    return ret


def not_expr(s: Scanner) -> ast.expr:
    if s.accept(TokenType.NOT):
        return ast.UnaryOp(ast.Not(), not_expr(s))
    if s.accept(TokenType.LPAREN):
        ret = expr(s)
        s.accept(TokenType.RPAREN, reject=True)
        return ret
    ident = s.accept(TokenType.IDENT)
    if ident:
        name = ast.Name(IDENT_PREFIX + ident.value, ast.Load())
        if s.accept(TokenType.LPAREN):
            ret = ast.Call(func=name, args=[], keywords=all_kwargs(s))
            s.accept(TokenType.RPAREN, reject=True)
        else:
            ret = name
        return ret

    s.reject((TokenType.NOT, TokenType.LPAREN, TokenType.IDENT))


BUILTIN_MATCHERS = {"True": True, "False": False, "None": None}


def single_kwarg(s: Scanner) -> ast.keyword:
    keyword_name = s.accept(TokenType.IDENT, reject=True)
    if not keyword_name.value.isidentifier():
        raise SyntaxError(
            f"not a valid python identifier {keyword_name.value}",
            (FILE_NAME, 1, keyword_name.pos + 1, s.input),
        )
    if keyword.iskeyword(keyword_name.value):
        raise SyntaxError(
            f"unexpected reserved python keyword `{keyword_name.value}`",
            (FILE_NAME, 1, keyword_name.pos + 1, s.input),
        )
    s.accept(TokenType.EQUAL, reject=True)

    if value_token := s.accept(TokenType.STRING):
        value: str | int | bool | None = value_token.value[1:-1]  # strip quotes
    else:
        value_token = s.accept(TokenType.IDENT, reject=True)
        if (number := value_token.value).isdigit() or (
            number.startswith("-") and number[1:].isdigit()
        ):
            value = int(number)
        elif value_token.value in BUILTIN_MATCHERS:
            value = BUILTIN_MATCHERS[value_token.value]
        else:
            raise SyntaxError(
                f'unexpected character/s "{value_token.value}"',
                (FILE_NAME, 1, value_token.pos + 1, s.input),
            )

    ret = ast.keyword(keyword_name.value, ast.Constant(value))
    return ret


def all_kwargs(s: Scanner) -> list[ast.keyword]:
    ret = [single_kwarg(s)]
    while s.accept(TokenType.COMMA):
        ret.append(single_kwarg(s))
    return ret


class ExpressionMatcher(Protocol):
    """A callable which, given an identifier and optional kwargs, should return
    whether it matches in an :class:`Expression` evaluation.

    Should be prepared to handle arbitrary strings as input.

    If no kwargs are provided, the expression of the form `foo`.
    If kwargs are provided, the expression is of the form `foo(1, b=True, "s")`.

    If the expression is not supported (e.g. don't want to accept the kwargs
    syntax variant), should raise :class:`~pytest.UsageError`.

    Example::

        def matcher(name: str, /, **kwargs: str | int | bool | None) -> bool:
            # Match `cat`.
            if name == "cat" and not kwargs:
                return True
            # Match `dog(barks=True)`.
            if name == "dog" and kwargs == {"barks": False}:
                return True
            return False
    """

    def __call__(self, name: str, /, **kwargs: str | int | bool | None) -> bool: ...


@dataclasses.dataclass
class MatcherNameAdapter:
    matcher: ExpressionMatcher
    name: str

    def __bool__(self) -> bool:
        return self.matcher(self.name)

    def __call__(self, **kwargs: str | int | bool | None) -> bool:
        return self.matcher(self.name, **kwargs)


class MatcherAdapter(Mapping[str, MatcherNameAdapter]):
    """Adapts a matcher function to a locals mapping as required by eval()."""

    def __init__(self, matcher: ExpressionMatcher) -> None:
        self.matcher = matcher

    def __getitem__(self, key: str) -> MatcherNameAdapter:
        return MatcherNameAdapter(matcher=self.matcher, name=key[len(IDENT_PREFIX) :])

    def __iter__(self) -> Iterator[str]:
        raise NotImplementedError()

    def __len__(self) -> int:
        raise NotImplementedError()


@final
class Expression:
    """A compiled match expression as used by -k and -m.

    The expression can be evaluated against different matchers.
    """

    __slots__ = ("_code", "input")

    def __init__(self, input: str, code: types.CodeType) -> None:
        #: The original input line, as a string.
        self.input: Final = input
        self._code: Final = code

    @classmethod
    def compile(cls, input: str) -> Expression:
        """Compile a match expression.

        :param input: The input expression - one line.

        :raises SyntaxError: If the expression is malformed.
        """
        astexpr = expression(Scanner(input))
        code = compile(
            astexpr,
            filename="<pytest match expression>",
            mode="eval",
        )
        return Expression(input, code)

    def evaluate(self, matcher: ExpressionMatcher) -> bool:
        """Evaluate the match expression.

        :param matcher:
            A callback which determines whether an identifier matches or not.
            See the :class:`ExpressionMatcher` protocol for details and example.

        :returns: Whether the expression matches or not.

        :raises UsageError:
            If the matcher doesn't support the expression. Cannot happen if the
            matcher supports all expressions.
        """
        return bool(eval(self._code, {"__builtins__": {}}, MatcherAdapter(matcher)))
