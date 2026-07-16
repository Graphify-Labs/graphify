"""
Parser for parsing a regular expression.
Take a string representing a regular expression and return the root node of its
parse tree.

usage::

    root_node = parse_regex('(hello|world)')

Remarks:
- The regex parser processes multiline, it ignores all whitespace and supports
  multiple named groups with the same name and #-style comments.

Limitations:
- Lookahead is not supported.
"""

from __future__ import annotations

import re

__all__ = [
    "Repeat",
    "Variable",
    "Regex",
    "Lookahead",
    "tokenize_regex",
    "parse_regex",
]


class Node:
    """
    Base class for all the grammar nodes.
    (You don't initialize this one.)
    """

    def __add__(self, other_node: Node) -> NodeSequence:
        return NodeSequence([self, other_node])

    def __or__(self, other_node: Node) -> AnyNode:
        return AnyNode([self, other_node])


class AnyNode(Node):
    """
    Union operation (OR operation) between several grammars. You don't
    initialize this yourself, but it's a result of a "Grammar1 | Grammar2"
    operation.
    """

    def __init__(self, children: list[Node]) -> None:
        self.children = children

    def __or__(self, other_node: Node) -> AnyNode:
        return AnyNode(self.children + [other_node])

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.children!r})"


class NodeSequence(Node):
    """
    Concatenation operation of several grammars. You don't initialize this
    yourself, but it's a result of a "Grammar1 + Grammar2" operation.
    """

    def __init__(self, children: list[Node]) -> None:
        self.children = children

    def __add__(self, other_node: Node) -> NodeSequence:
        return NodeSequence(self.children + [other_node])

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.children!r})"


class Regex(Node):
    """
    Regular expression.
    """

    def __init__(self, regex: str) -> None:
        re.compile(regex)  # Validate

        self.regex = regex

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(/{self.regex}/)"


class Lookahead(Node):
    """
    Lookahead expression.
    """

    def __init__(self, childnode: Node, negative: bool = False) -> None:
        self.childnode = childnode
        self.negative = negative

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.childnode!r})"


class Variable(Node):
    """
    Mark a variable in the regular grammar. This will be translated into a
    named group. Each variable can have his own completer, validator, etc..

    :param childnode: The grammar which is wrapped inside this variable.
    :param varname: String.
    """

    def __init__(self, childnode: Node, varname: str = "") -> None:
        self.childnode = childnode
        self.varname = varname

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(childnode={self.childnode!r}, varname={self.varname!r})"


class Repeat(Node):
    def __init__(
        self,
        childnode: Node,
        min_repeat: int = 0,
        max_repeat: int | None = None,
        greedy: bool = True,
    ) -> None:
        self.childnode = childnode
        self.min_repeat = min_repeat
        self.max_repeat = max_repeat
        self.greedy = greedy

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(childnode={self.childnode!r})"


def tokenize_regex(input: str) -> list[str]:
    """
    Takes a string, representing a regular expression as input, and tokenizes
    it.

    :param input: string, representing a regular expression.
    :returns: List of tokens.
    """
    # Regular expression for tokenizing other regular expressions.
    p = re.compile(
        r"""^(
        \(\?P\<[a-zA-Z0-9_-]+\>  | # Start of named group.
        \(\?#[^)]*\)             | # Comment
        \(\?=                    | # Start of lookahead assertion
        \(\?!                    | # Start of negative lookahead assertion
        \(\?<=                   | # If preceded by.
        \(\?<                    | # If not preceded by.
        \(?:                     | # Start of group. (non capturing.)
        \(                       | # Start of group.
        \(?[iLmsux]              | # Flags.
        \(?P=[a-zA-Z]+\)         | # Back reference to named group
        \)                       | # End of group.
        \{[^{}]*\}               | # Repetition
        \*\? | \+\? | \?\?\      | # Non greedy repetition.
        \* | \+ | \?             | # Repetition
        \#.*\n                   | # Comment
        \\. |

        # Character group.
        \[
            ( [^\]\\]  |  \\.)*
        \]                  |

        [^(){}]             |
        .
    )""",
        re.VERBOSE,
    )

    tokens = []

    while input:
        m = p.match(input)
        if m:
            token, input = input[: m.end()], input[m.end() :]
            if not token.isspace():
                tokens.append(token)
        else:
            raise Exception("Could not tokenize input regex.")

    return tokens


def parse_regex(regex_tokens: list[str]) -> Node:
    """
    Takes a list of tokens from the tokenizer, and returns a parse tree.
    """
    # We add a closing brace because that represents the final pop of the stack.
    tokens: list[str] = [")"] + regex_tokens[::-1]

    def wrap(lst: list[Node]) -> Node:
        """Turn list into sequence when it contains several items."""
        if len(lst) == 1:
            return lst[0]
        else:
            return NodeSequence(lst)

    def _parse() -> Node:
        or_list: list[list[Node]] = []
        result: list[Node] = []

        def wrapped_result() -> Node:
            if or_list == []:
                return wrap(result)
            else:
                or_list.append(result)
                return AnyNode([wrap(i) for i in or_list])

        while tokens:
            t = tokens.pop()

            if t.startswith("(?P<"):
                variable = Variable(_parse(), varname=t[4:-1])
                result.append(variable)

            elif t in ("*", "*?"):
                greedy = t == "*"
                result[-1] = Repeat(result[-1], greedy=greedy)

            elif t in ("+", "+?"):
                greedy = t == "+"
                result[-1] = Repeat(result[-1], min_repeat=1, greedy=greedy)

            elif t in ("?", "??"):
                if result == []:
                    raise Exception("Nothing to repeat." + repr(tokens))
                else:
                    greedy = t == "?"
                    result[-1] = Repeat(
                        result[-1], min_repeat=0, max_repeat=1, greedy=greedy
                    )

            elif t == "|":
                or_list.append(result)
                result = []

            elif t in ("(", "(?:"):
                result.append(_parse())

            elif t == "(?!":
                result.append(Lookahead(_parse(), negative=True))

            elif t == "(?=":
                result.append(Lookahead(_parse(), negative=False))

            elif t == ")":
                return wrapped_result()

            elif t.startswith("#"):
                pass

            elif t.startswith("{"):
                # TODO: implement!
                raise Exception(f"{t}-style repetition not yet supported")

            elif t.startswith("(?"):
                raise Exception(f"{t!r} not supported")

            elif t.isspace():
                pass
            else:
                result.append(Regex(t))

        raise Exception("Expecting ')' token")

    result = _parse()

    if len(tokens) != 0:
        raise Exception("Unmatched parentheses.")
    else:
        return result
