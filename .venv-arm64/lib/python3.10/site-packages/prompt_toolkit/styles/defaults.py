"""
The default styling.
"""

from __future__ import annotations

from prompt_toolkit.cache import memoized

from .base import ANSI_COLOR_NAMES, BaseStyle
from .named_colors import NAMED_COLORS
from .style import Style, merge_styles

__all__ = [
    "default_ui_style",
    "default_pygments_style",
]

#: Default styling. Mapping from classnames to their style definition.
PROMPT_TOOLKIT_STYLE = [
    # Highlighting of search matches in document.
    ("search", "bg:ansibrightyellow ansiblack"),
    ("search.current", ""),
    # Incremental search.
    ("incsearch", ""),
    ("incsearch.current", "reverse"),
    # Highlighting of select text in document.
    ("selected", "reverse"),
    ("cursor-column", "bg:#dddddd"),
    ("cursor-line", "underline"),
    ("color-column", "bg:#ccaacc"),
    # Highlighting of matching brackets.
    ("matching-bracket", ""),
    ("matching-bracket.other", "#000000 bg:#aacccc"),
    ("matching-bracket.cursor", "#ff8888 bg:#880000"),
    # Styling of other cursors, in case of block editing.
    ("multiple-cursors", "#000000 bg:#ccccaa"),
    # Line numbers.
    ("line-number", "#888888"),
    ("line-number.current", "bold"),
    ("tilde", "#8888ff"),
    # Default prompt.
    ("prompt", ""),
    ("prompt.arg", "noinherit"),
    ("prompt.arg.text", ""),
    ("prompt.search", "noinherit"),
    ("prompt.search.text", ""),
    # Search toolbar.
    ("search-toolbar", "bold"),
    ("search-toolbar.text", "nobold"),
    # System toolbar
    ("system-toolbar", "bold"),
    ("system-toolbar.text", "nobold"),
    # "arg" toolbar.
    ("arg-toolbar", "bold"),
    ("arg-toolbar.text", "nobold"),
    # Validation toolbar.
    ("validation-toolbar", "bg:#550000 #ffffff"),
    ("window-too-small", "bg:#550000 #ffffff"),
    # Completions toolbar.
    ("completion-toolbar", "bg:#bbbbbb #000000"),
    ("completion-toolbar.arrow", "bg:#bbbbbb #000000 bold"),
    ("completion-toolbar.completion", "bg:#bbbbbb #000000"),
    ("completion-toolbar.completion.current", "bg:#444444 #ffffff"),
    # Completions menu.
    ("completion-menu", "bg:#bbbbbb #000000"),
    ("completion-menu.completion", ""),
    # (Note: for the current completion, we use 'reverse' on top of fg/bg
    # colors. This is to have proper rendering with NO_COLOR=1).
    ("completion-menu.completion.current", "fg:#888888 bg:#ffffff reverse"),
    ("completion-menu.meta.completion", "bg:#999999 #000000"),
    ("completion-menu.meta.completion.current", "bg:#aaaaaa #000000"),
    ("completion-menu.multi-column-meta", "bg:#aaaaaa #000000"),
    # Fuzzy matches in completion menu (for FuzzyCompleter).
    ("completion-menu.completion fuzzymatch.outside", "fg:#444444"),
    ("completion-menu.completion fuzzymatch.inside", "bold"),
    ("completion-menu.completion fuzzymatch.inside.character", "underline"),
    ("completion-menu.completion.current fuzzymatch.outside", "fg:default"),
    ("completion-menu.completion.current fuzzymatch.inside", "nobold"),
    # Styling of readline-like completions.
    ("readline-like-completions", ""),
    ("readline-like-completions.completion", ""),
    ("readline-like-completions.completion fuzzymatch.outside", "#888888"),
    ("readline-like-completions.completion fuzzymatch.inside", ""),
    ("readline-like-completions.completion fuzzymatch.inside.character", "underline"),
    # Scrollbars.
    ("scrollbar.background", "bg:#aaaaaa"),
    ("scrollbar.button", "bg:#444444"),
    ("scrollbar.arrow", "noinherit bold"),
    # Start/end of scrollbars. Adding 'underline' here provides a nice little
    # detail to the progress bar, but it doesn't look good on all terminals.
    # ('scrollbar.start',                          'underline #ffffff'),
    # ('scrollbar.end',                            'underline #000000'),
    # Auto suggestion text.
    ("auto-suggestion", "#666666"),
    # Trailing whitespace and tabs.
    ("trailing-whitespace", "#999999"),
    ("tab", "#999999"),
    # When Control-C/D has been pressed. Grayed.
    ("aborting", "#888888 bg:default noreverse noitalic nounderline noblink"),
    ("exiting", "#888888 bg:default noreverse noitalic nounderline noblink"),
    # Entering a Vi digraph.
    ("digraph", "#4444ff"),
    # Control characters, like ^C, ^X.
    ("control-character", "ansiblue"),
    # Non-breaking space.
    ("nbsp", "underline ansiyellow"),
    # Default styling of HTML elements.
    ("i", "italic"),
    ("u", "underline"),
    ("s", "strike"),
    ("b", "bold"),
    ("em", "italic"),
    ("strong", "bold"),
    ("del", "strike"),
    ("hidden", "hidden"),
    # It should be possible to use the style names in HTML.
    # <reverse>...</reverse>  or <noreverse>...</noreverse>.
    ("italic", "italic"),
    ("underline", "underline"),
    ("strike", "strike"),
    ("bold", "bold"),
    ("reverse", "reverse"),
    ("noitalic", "noitalic"),
    ("nounderline", "nounderline"),
    ("nostrike", "nostrike"),
    ("nobold", "nobold"),
    ("noreverse", "noreverse"),
    # Prompt bottom toolbar
    ("bottom-toolbar", "reverse"),
]


# Style that will turn for instance the class 'red' into 'red'.
COLORS_STYLE = [(name, "fg:" + name) for name in ANSI_COLOR_NAMES] + [
    (name.lower(), "fg:" + name) for name in NAMED_COLORS
]


WIDGETS_STYLE = [
    # Dialog windows.
    ("dialog", "bg:#4444ff"),
    ("dialog.body", "bg:#ffffff #000000"),
    ("dialog.body text-area", "bg:#cccccc"),
    ("dialog.body text-area last-line", "underline"),
    ("dialog frame.label", "#ff0000 bold"),
    # Scrollbars in dialogs.
    ("dialog.body scrollbar.background", ""),
    ("dialog.body scrollbar.button", "bg:#000000"),
    ("dialog.body scrollbar.arrow", ""),
    ("dialog.body scrollbar.start", "nounderline"),
    ("dialog.body scrollbar.end", "nounderline"),
    # Buttons.
    ("button", ""),
    ("button.arrow", "bold"),
    ("button.focused", "bg:#aa0000 #ffffff"),
    # Menu bars.
    ("menu-bar", "bg:#aaaaaa #000000"),
    ("menu-bar.selected-item", "bg:#ffffff #000000"),
    ("menu", "bg:#888888 #ffffff"),
    ("menu.border", "#aaaaaa"),
    ("menu.border shadow", "#444444"),
    # Shadows.
    ("dialog shadow", "bg:#000088"),
    ("dialog.body shadow", "bg:#aaaaaa"),
    ("progress-bar", "bg:#000088"),
    ("progress-bar.used", "bg:#ff0000"),
]


# The default Pygments style, include this by default in case a Pygments lexer
# is used.
PYGMENTS_DEFAULT_STYLE = {
    "pygments.whitespace": "#bbbbbb",
    "pygments.comment": "italic #408080",
    "pygments.comment.preproc": "noitalic #bc7a00",
    "pygments.keyword": "bold #008000",
    "pygments.keyword.pseudo": "nobold",
    "pygments.keyword.type": "nobold #b00040",
    "pygments.operator": "#666666",
    "pygments.operator.word": "bold #aa22ff",
    "pygments.name.builtin": "#008000",
    "pygments.name.function": "#0000ff",
    "pygments.name.class": "bold #0000ff",
    "pygments.name.namespace": "bold #0000ff",
    "pygments.name.exception": "bold #d2413a",
    "pygments.name.variable": "#19177c",
    "pygments.name.constant": "#880000",
    "pygments.name.label": "#a0a000",
    "pygments.name.entity": "bold #999999",
    "pygments.name.attribute": "#7d9029",
    "pygments.name.tag": "bold #008000",
    "pygments.name.decorator": "#aa22ff",
    # Note: In Pygments, Token.String is an alias for Token.Literal.String,
    #       and Token.Number as an alias for Token.Literal.Number.
    "pygments.literal.string": "#ba2121",
    "pygments.literal.string.doc": "italic",
    "pygments.literal.string.interpol": "bold #bb6688",
    "pygments.literal.string.escape": "bold #bb6622",
    "pygments.literal.string.regex": "#bb6688",
    "pygments.literal.string.symbol": "#19177c",
    "pygments.literal.string.other": "#008000",
    "pygments.literal.number": "#666666",
    "pygments.generic.heading": "bold #000080",
    "pygments.generic.subheading": "bold #800080",
    "pygments.generic.deleted": "#a00000",
    "pygments.generic.inserted": "#00a000",
    "pygments.generic.error": "#ff0000",
    "pygments.generic.emph": "italic",
    "pygments.generic.strong": "bold",
    "pygments.generic.prompt": "bold #000080",
    "pygments.generic.output": "#888",
    "pygments.generic.traceback": "#04d",
    "pygments.error": "border:#ff0000",
}


@memoized()
def default_ui_style() -> BaseStyle:
    """
    Create a default `Style` object.
    """
    return merge_styles(
        [
            Style(PROMPT_TOOLKIT_STYLE),
            Style(COLORS_STYLE),
            Style(WIDGETS_STYLE),
        ]
    )


@memoized()
def default_pygments_style() -> Style:
    """
    Create a `Style` object that contains the default Pygments style.
    """
    return Style.from_dict(PYGMENTS_DEFAULT_STYLE)
