from __future__ import annotations

from typing import TYPE_CHECKING

from prompt_toolkit.styles.pygments import pygments_token_to_classname

from .base import StyleAndTextTuples

if TYPE_CHECKING:
    from pygments.token import Token

__all__ = [
    "PygmentsTokens",
]


class PygmentsTokens:
    """
    Turn a pygments token list into a list of prompt_toolkit text fragments
    (``(style_str, text)`` tuples).
    """

    def __init__(self, token_list: list[tuple[Token, str]]) -> None:
        self.token_list = token_list

    def __pt_formatted_text__(self) -> StyleAndTextTuples:
        result: StyleAndTextTuples = []

        for token, text in self.token_list:
            result.append(("class:" + pygments_token_to_classname(token), text))

        return result
