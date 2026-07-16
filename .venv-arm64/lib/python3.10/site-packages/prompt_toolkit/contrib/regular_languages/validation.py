"""
Validator for a regular language.
"""

from __future__ import annotations

from prompt_toolkit.document import Document
from prompt_toolkit.validation import ValidationError, Validator

from .compiler import _CompiledGrammar

__all__ = [
    "GrammarValidator",
]


class GrammarValidator(Validator):
    """
    Validator which can be used for validation according to variables in
    the grammar. Each variable can have its own validator.

    :param compiled_grammar: `GrammarCompleter` instance.
    :param validators: `dict` mapping variable names of the grammar to the
                       `Validator` instances to be used for each variable.
    """

    def __init__(
        self, compiled_grammar: _CompiledGrammar, validators: dict[str, Validator]
    ) -> None:
        self.compiled_grammar = compiled_grammar
        self.validators = validators

    def validate(self, document: Document) -> None:
        # Parse input document.
        # We use `match`, not `match_prefix`, because for validation, we want
        # the actual, unambiguous interpretation of the input.
        m = self.compiled_grammar.match(document.text)

        if m:
            for v in m.variables():
                validator = self.validators.get(v.varname)

                if validator:
                    # Unescape text.
                    unwrapped_text = self.compiled_grammar.unescape(v.varname, v.value)

                    # Create a document, for the completions API (text/cursor_position)
                    inner_document = Document(unwrapped_text, len(unwrapped_text))

                    try:
                        validator.validate(inner_document)
                    except ValidationError as e:
                        raise ValidationError(
                            cursor_position=v.start + e.cursor_position,
                            message=e.message,
                        ) from e
        else:
            raise ValidationError(
                cursor_position=len(document.text), message="Invalid command"
            )
