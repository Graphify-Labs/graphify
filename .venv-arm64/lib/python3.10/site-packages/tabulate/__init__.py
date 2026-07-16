"""Pretty-print tabular data."""

from importlib.metadata import (
    version as _version,
    PackageNotFoundError as _PackageNotFoundError,
)

try:
    __version__ = _version("tabulate")
except _PackageNotFoundError:
    __version__ = "unknown"

import warnings
from collections import namedtuple
from collections.abc import Iterable, Sized
from html import escape as htmlescape
from itertools import chain, zip_longest as izip_longest
from functools import reduce, partial
import io
import re
import math
import textwrap
import dataclasses
import sys

try:
    import wcwidth  # optional wide-character (CJK) support
except ImportError:
    wcwidth = None


def _is_file(f):
    return isinstance(f, io.IOBase)


__all__ = ["tabulate", "tabulate_formats", "simple_separated_format"]
try:
    from .version import version as __version__  # noqa: F401
except ImportError:
    pass  # running __init__.py as a script, AppVeyor pytests


# minimum extra space in headers
MIN_PADDING = 2

# Whether or not to preserve leading/trailing whitespace in data.
PRESERVE_WHITESPACE = False

# TextWrapper breaks words longer than 'width'.
_BREAK_LONG_WORDS = True
# TextWrapper is breaking hyphenated words.
_BREAK_ON_HYPHENS = True


_DEFAULT_FLOATFMT = "g"
_DEFAULT_INTFMT = ""
_DEFAULT_MISSINGVAL = ""
# default align will be overwritten by "left", "center" or "decimal"
# depending on the formatter
_DEFAULT_ALIGN = "default"


# if True, enable wide-character (CJK) support
WIDE_CHARS_MODE = wcwidth is not None

# Constant that can be used as part of passed rows to generate a separating line
# It is purposely an unprintable character, very unlikely to be used in a table
SEPARATING_LINE = "\001"

Line = namedtuple("Line", ["begin", "hline", "sep", "end"])


DataRow = namedtuple("DataRow", ["begin", "sep", "end"])


# A table structure is supposed to be:
#
#     --- lineabove ---------
#         headerrow
#     --- linebelowheader ---
#         datarow
#     --- linebetweenrows ---
#     ... (more datarows) ...
#     --- linebetweenrows ---
#         last datarow
#     --- linebelow ---------
#
# TableFormat's line* elements can be
#
#   - either None, if the element is not used,
#   - or a Line tuple,
#   - or a function: [col_widths], [col_alignments] -> string.
#
# TableFormat's *row elements can be
#
#   - either None, if the element is not used,
#   - or a DataRow tuple,
#   - or a function: [cell_values], [col_widths], [col_alignments] -> string.
#
# padding (an integer) is the amount of white space around data values.
#
# with_header_hide:
#
#   - either None, to display all table elements unconditionally,
#   - or a list of elements not to be displayed if the table has column headers.
#
TableFormat = namedtuple(
    "TableFormat",
    [
        "lineabove",
        "linebelowheader",
        "linebetweenrows",
        "linebelow",
        "headerrow",
        "datarow",
        "padding",
        "with_header_hide",
    ],
)


def _is_separating_line_value(value):
    return type(value) is str and value.strip() == SEPARATING_LINE


def _is_separating_line(row):
    row_type = type(row)
    is_sl = (row_type == list or row_type == str) and (
        (len(row) >= 1 and _is_separating_line_value(row[0]))
        or (len(row) >= 2 and _is_separating_line_value(row[1]))
    )

    return is_sl


def _pipe_segment_with_colons(align, colwidth):
    """Return a segment of a horizontal line with optional colons which
    indicate column's alignment (as in `pipe` output format)."""
    w = colwidth
    if align in ["right", "decimal"]:
        return ("-" * (w - 1)) + ":"
    elif align == "center":
        return ":" + ("-" * (w - 2)) + ":"
    elif align == "left":
        return ":" + ("-" * (w - 1))
    else:
        return "-" * w


def _pipe_line_with_colons(colwidths, colaligns):
    """Return a horizontal line with optional colons to indicate column's
    alignment (as in `pipe` output format)."""
    if not colaligns:  # e.g. printing an empty data frame (github issue #15)
        colaligns = [""] * len(colwidths)
    segments = "|".join(
        _pipe_segment_with_colons(a, w) for a, w in zip(colaligns, colwidths)
    )
    return f"|{segments}|"


def _grid_segment_with_colons(colwidth, align):
    """Return a segment of a horizontal line with optional colons which indicate
    column's alignment in a grid table."""
    width = colwidth
    if align == "right":
        return ("=" * (width - 1)) + ":"
    elif align == "center":
        return ":" + ("=" * (width - 2)) + ":"
    elif align == "left":
        return ":" + ("=" * (width - 1))
    else:
        return "=" * width


def _grid_line_with_colons(colwidths, colaligns):
    """Return a horizontal line with optional colons to indicate column's alignment
    in a grid table."""
    if not colaligns:
        colaligns = [""] * len(colwidths)
    segments = "+".join(
        _grid_segment_with_colons(w, a) for a, w in zip(colaligns, colwidths)
    )
    return f"+{segments}+"


def _mediawiki_row_with_attrs(separator, cell_values, colwidths, colaligns):
    alignment = {
        "left": "",
        "right": 'style="text-align: right;"| ',
        "center": 'style="text-align: center;"| ',
        "decimal": 'style="text-align: right;"| ',
    }
    # hard-coded padding _around_ align attribute and value together
    # rather than padding parameter which affects only the value
    values_with_attrs = [
        " " + alignment.get(a, "") + c + " " for c, a in zip(cell_values, colaligns)
    ]
    colsep = separator * 2
    return (separator + colsep.join(values_with_attrs)).rstrip()


def _textile_row_with_attrs(cell_values, colwidths, colaligns):
    cell_values[0] += " "
    alignment = {"left": "<.", "right": ">.", "center": "=.", "decimal": ">."}
    values = "|".join(alignment.get(a, "") + v for a, v in zip(colaligns, cell_values))
    return f"|{values}|"


def _html_begin_table_without_header(colwidths_ignore, colaligns_ignore):
    # this table header will be suppressed if there is a header row
    return "<table>\n<tbody>"


def _html_row_with_attrs(celltag, unsafe, cell_values, colwidths, colaligns):
    alignment = {
        "left": "",
        "right": ' style="text-align: right;"',
        "center": ' style="text-align: center;"',
        "decimal": ' style="text-align: right;"',
    }
    if unsafe:
        values_with_attrs = [
            "<{0}{1}>{2}</{0}>".format(celltag, alignment.get(a, ""), c)
            for c, a in zip(cell_values, colaligns)
        ]
    else:
        values_with_attrs = [
            "<{0}{1}>{2}</{0}>".format(celltag, alignment.get(a, ""), htmlescape(c))
            for c, a in zip(cell_values, colaligns)
        ]
    rowhtml = "<tr>{}</tr>".format("".join(values_with_attrs).rstrip())
    if celltag == "th":  # it's a header row, create a new table header
        rowhtml = f"<table>\n<thead>\n{rowhtml}\n</thead>\n<tbody>"
    return rowhtml


def _moin_row_with_attrs(celltag, cell_values, colwidths, colaligns, header=""):
    alignment = {
        "left": "",
        "right": '<style="text-align: right;">',
        "center": '<style="text-align: center;">',
        "decimal": '<style="text-align: right;">',
    }
    values_with_attrs = [
        "{}{} {} ".format(celltag, alignment.get(a, ""), header + c + header)
        for c, a in zip(cell_values, colaligns)
    ]
    return "".join(values_with_attrs) + "||"


def _latex_line_begin_tabular(colwidths, colaligns, booktabs=False, longtable=False):
    alignment = {"left": "l", "right": "r", "center": "c", "decimal": "r"}
    tabular_columns_fmt = "".join([alignment.get(a, "l") for a in colaligns])
    return "\n".join(
        [
            ("\\begin{tabular}{" if not longtable else "\\begin{longtable}{")
            + tabular_columns_fmt
            + "}",
            "\\toprule" if booktabs else "\\hline",
        ]
    )


def _asciidoc_row(is_header, *args):
    """handle header and data rows for asciidoc format"""

    def make_header_line(is_header, colwidths, colaligns):
        # generate the column specifiers

        alignment = {"left": "<", "right": ">", "center": "^", "decimal": ">"}
        # use the column widths generated by tabulate for the asciidoc column width specifiers
        asciidoc_alignments = zip(
            colwidths, [alignment[colalign] for colalign in colaligns]
        )
        asciidoc_column_specifiers = [
            f"{align}{width:d}" for width, align in asciidoc_alignments
        ]
        header_list = ['cols="' + (",".join(asciidoc_column_specifiers)) + '"']

        # generate the list of options (currently only "header")
        options_list = []

        if is_header:
            options_list.append("header")

        if options_list:
            options_list = ",".join(options_list)
            header_list.append(f'options="{options_list}"')

        # generate the list of entries in the table header field

        return "[{}]\n|====".format(",".join(header_list))

    if len(args) == 2:
        # two arguments are passed if called in the context of aboveline
        # print the table header with column widths and optional header tag
        return make_header_line(False, *args)

    elif len(args) == 3:
        # three arguments are passed if called in the context of dataline or headerline
        # print the table line and make the aboveline if it is a header

        cell_values, colwidths, colaligns = args
        data_line = "|" + "|".join(cell_values)

        if is_header:
            return make_header_line(True, colwidths, colaligns) + "\n" + data_line
        else:
            return data_line

    else:
        raise ValueError(
            "_asciidoc_row() requires two (colwidths, colaligns) "
            + "or three (cell_values, colwidths, colaligns) arguments) "
        )


LATEX_ESCAPE_RULES = {
    r"&": r"\&",
    r"%": r"\%",
    r"$": r"\$",
    r"#": r"\#",
    r"_": r"\_",
    r"^": r"\^{}",
    r"{": r"\{",
    r"}": r"\}",
    r"~": r"\textasciitilde{}",
    "\\": r"\textbackslash{}",
    r"<": r"\ensuremath{<}",
    r">": r"\ensuremath{>}",
}


def _latex_row(cell_values, colwidths, colaligns, escrules=LATEX_ESCAPE_RULES):
    def escape_char(c):
        return escrules.get(c, c)

    escaped_values = ["".join(map(escape_char, cell)) for cell in cell_values]
    rowfmt = DataRow("", "&", "\\\\")
    return _build_simple_row(escaped_values, rowfmt)


def _rst_escape_first_column(rows, headers):
    def escape_empty(val):
        if isinstance(val, (str, bytes)) and not val.strip():
            return ".."
        else:
            return val

    new_headers = list(headers)
    new_rows = []
    if headers:
        new_headers[0] = escape_empty(headers[0])
    for row in rows:
        new_row = list(row)
        if new_row:
            new_row[0] = escape_empty(row[0])
        new_rows.append(new_row)
    return new_rows, new_headers


_table_formats = {
    "simple": TableFormat(
        lineabove=Line("", "-", "  ", ""),
        linebelowheader=Line("", "-", "  ", ""),
        linebetweenrows=None,
        linebelow=Line("", "-", "  ", ""),
        headerrow=DataRow("", "  ", ""),
        datarow=DataRow("", "  ", ""),
        padding=0,
        with_header_hide=["lineabove", "linebelow"],
    ),
    "plain": TableFormat(
        lineabove=None,
        linebelowheader=None,
        linebetweenrows=None,
        linebelow=None,
        headerrow=DataRow("", "  ", ""),
        datarow=DataRow("", "  ", ""),
        padding=0,
        with_header_hide=None,
    ),
    "grid": TableFormat(
        lineabove=Line("+", "-", "+", "+"),
        linebelowheader=Line("+", "=", "+", "+"),
        linebetweenrows=Line("+", "-", "+", "+"),
        linebelow=Line("+", "-", "+", "+"),
        headerrow=DataRow("|", "|", "|"),
        datarow=DataRow("|", "|", "|"),
        padding=1,
        with_header_hide=None,
    ),
    "simple_grid": TableFormat(
        lineabove=Line("┌", "─", "┬", "┐"),
        linebelowheader=Line("├", "─", "┼", "┤"),
        linebetweenrows=Line("├", "─", "┼", "┤"),
        linebelow=Line("└", "─", "┴", "┘"),
        headerrow=DataRow("│", "│", "│"),
        datarow=DataRow("│", "│", "│"),
        padding=1,
        with_header_hide=None,
    ),
    "rounded_grid": TableFormat(
        lineabove=Line("╭", "─", "┬", "╮"),
        linebelowheader=Line("├", "─", "┼", "┤"),
        linebetweenrows=Line("├", "─", "┼", "┤"),
        linebelow=Line("╰", "─", "┴", "╯"),
        headerrow=DataRow("│", "│", "│"),
        datarow=DataRow("│", "│", "│"),
        padding=1,
        with_header_hide=None,
    ),
    "heavy_grid": TableFormat(
        lineabove=Line("┏", "━", "┳", "┓"),
        linebelowheader=Line("┣", "━", "╋", "┫"),
        linebetweenrows=Line("┣", "━", "╋", "┫"),
        linebelow=Line("┗", "━", "┻", "┛"),
        headerrow=DataRow("┃", "┃", "┃"),
        datarow=DataRow("┃", "┃", "┃"),
        padding=1,
        with_header_hide=None,
    ),
    "mixed_grid": TableFormat(
        lineabove=Line("┍", "━", "┯", "┑"),
        linebelowheader=Line("┝", "━", "┿", "┥"),
        linebetweenrows=Line("├", "─", "┼", "┤"),
        linebelow=Line("┕", "━", "┷", "┙"),
        headerrow=DataRow("│", "│", "│"),
        datarow=DataRow("│", "│", "│"),
        padding=1,
        with_header_hide=None,
    ),
    "double_grid": TableFormat(
        lineabove=Line("╔", "═", "╦", "╗"),
        linebelowheader=Line("╠", "═", "╬", "╣"),
        linebetweenrows=Line("╠", "═", "╬", "╣"),
        linebelow=Line("╚", "═", "╩", "╝"),
        headerrow=DataRow("║", "║", "║"),
        datarow=DataRow("║", "║", "║"),
        padding=1,
        with_header_hide=None,
    ),
    "fancy_grid": TableFormat(
        lineabove=Line("╒", "═", "╤", "╕"),
        linebelowheader=Line("╞", "═", "╪", "╡"),
        linebetweenrows=Line("├", "─", "┼", "┤"),
        linebelow=Line("╘", "═", "╧", "╛"),
        headerrow=DataRow("│", "│", "│"),
        datarow=DataRow("│", "│", "│"),
        padding=1,
        with_header_hide=None,
    ),
    "colon_grid": TableFormat(
        lineabove=Line("+", "-", "+", "+"),
        linebelowheader=_grid_line_with_colons,
        linebetweenrows=Line("+", "-", "+", "+"),
        linebelow=Line("+", "-", "+", "+"),
        headerrow=DataRow("|", "|", "|"),
        datarow=DataRow("|", "|", "|"),
        padding=1,
        with_header_hide=None,
    ),
    "outline": TableFormat(
        lineabove=Line("+", "-", "+", "+"),
        linebelowheader=Line("+", "=", "+", "+"),
        linebetweenrows=None,
        linebelow=Line("+", "-", "+", "+"),
        headerrow=DataRow("|", "|", "|"),
        datarow=DataRow("|", "|", "|"),
        padding=1,
        with_header_hide=None,
    ),
    "simple_outline": TableFormat(
        lineabove=Line("┌", "─", "┬", "┐"),
        linebelowheader=Line("├", "─", "┼", "┤"),
        linebetweenrows=None,
        linebelow=Line("└", "─", "┴", "┘"),
        headerrow=DataRow("│", "│", "│"),
        datarow=DataRow("│", "│", "│"),
        padding=1,
        with_header_hide=None,
    ),
    "rounded_outline": TableFormat(
        lineabove=Line("╭", "─", "┬", "╮"),
        linebelowheader=Line("├", "─", "┼", "┤"),
        linebetweenrows=None,
        linebelow=Line("╰", "─", "┴", "╯"),
        headerrow=DataRow("│", "│", "│"),
        datarow=DataRow("│", "│", "│"),
        padding=1,
        with_header_hide=None,
    ),
    "heavy_outline": TableFormat(
        lineabove=Line("┏", "━", "┳", "┓"),
        linebelowheader=Line("┣", "━", "╋", "┫"),
        linebetweenrows=None,
        linebelow=Line("┗", "━", "┻", "┛"),
        headerrow=DataRow("┃", "┃", "┃"),
        datarow=DataRow("┃", "┃", "┃"),
        padding=1,
        with_header_hide=None,
    ),
    "mixed_outline": TableFormat(
        lineabove=Line("┍", "━", "┯", "┑"),
        linebelowheader=Line("┝", "━", "┿", "┥"),
        linebetweenrows=None,
        linebelow=Line("┕", "━", "┷", "┙"),
        headerrow=DataRow("│", "│", "│"),
        datarow=DataRow("│", "│", "│"),
        padding=1,
        with_header_hide=None,
    ),
    "double_outline": TableFormat(
        lineabove=Line("╔", "═", "╦", "╗"),
        linebelowheader=Line("╠", "═", "╬", "╣"),
        linebetweenrows=None,
        linebelow=Line("╚", "═", "╩", "╝"),
        headerrow=DataRow("║", "║", "║"),
        datarow=DataRow("║", "║", "║"),
        padding=1,
        with_header_hide=None,
    ),
    "fancy_outline": TableFormat(
        lineabove=Line("╒", "═", "╤", "╕"),
        linebelowheader=Line("╞", "═", "╪", "╡"),
        linebetweenrows=None,
        linebelow=Line("╘", "═", "╧", "╛"),
        headerrow=DataRow("│", "│", "│"),
        datarow=DataRow("│", "│", "│"),
        padding=1,
        with_header_hide=None,
    ),
    "github": TableFormat(
        lineabove=Line("|", "-", "|", "|"),
        linebelowheader=Line("|", "-", "|", "|"),
        linebetweenrows=None,
        linebelow=None,
        headerrow=DataRow("|", "|", "|"),
        datarow=DataRow("|", "|", "|"),
        padding=1,
        with_header_hide=["lineabove"],
    ),
    "pipe": TableFormat(
        lineabove=_pipe_line_with_colons,
        linebelowheader=_pipe_line_with_colons,
        linebetweenrows=None,
        linebelow=None,
        headerrow=DataRow("|", "|", "|"),
        datarow=DataRow("|", "|", "|"),
        padding=1,
        with_header_hide=["lineabove"],
    ),
    "orgtbl": TableFormat(
        lineabove=None,
        linebelowheader=Line("|", "-", "+", "|"),
        linebetweenrows=None,
        linebelow=None,
        headerrow=DataRow("|", "|", "|"),
        datarow=DataRow("|", "|", "|"),
        padding=1,
        with_header_hide=None,
    ),
    "jira": TableFormat(
        lineabove=None,
        linebelowheader=None,
        linebetweenrows=None,
        linebelow=None,
        headerrow=DataRow("||", "||", "||"),
        datarow=DataRow("|", "|", "|"),
        padding=1,
        with_header_hide=None,
    ),
    "presto": TableFormat(
        lineabove=None,
        linebelowheader=Line("", "-", "+", ""),
        linebetweenrows=None,
        linebelow=None,
        headerrow=DataRow("", "|", ""),
        datarow=DataRow("", "|", ""),
        padding=1,
        with_header_hide=None,
    ),
    "pretty": TableFormat(
        lineabove=Line("+", "-", "+", "+"),
        linebelowheader=Line("+", "-", "+", "+"),
        linebetweenrows=None,
        linebelow=Line("+", "-", "+", "+"),
        headerrow=DataRow("|", "|", "|"),
        datarow=DataRow("|", "|", "|"),
        padding=1,
        with_header_hide=None,
    ),
    "psql": TableFormat(
        lineabove=Line("+", "-", "+", "+"),
        linebelowheader=Line("|", "-", "+", "|"),
        linebetweenrows=None,
        linebelow=Line("+", "-", "+", "+"),
        headerrow=DataRow("|", "|", "|"),
        datarow=DataRow("|", "|", "|"),
        padding=1,
        with_header_hide=None,
    ),
    "rst": TableFormat(
        lineabove=Line("", "=", "  ", ""),
        linebelowheader=Line("", "=", "  ", ""),
        linebetweenrows=None,
        linebelow=Line("", "=", "  ", ""),
        headerrow=DataRow("", "  ", ""),
        datarow=DataRow("", "  ", ""),
        padding=0,
        with_header_hide=None,
    ),
    "mediawiki": TableFormat(
        lineabove=Line(
            '{| class="wikitable" style="text-align: left;"',
            "",
            "",
            "\n|+ <!-- caption -->\n|-",
        ),
        linebelowheader=Line("|-", "", "", ""),
        linebetweenrows=Line("|-", "", "", ""),
        linebelow=Line("|}", "", "", ""),
        headerrow=partial(_mediawiki_row_with_attrs, "!"),
        datarow=partial(_mediawiki_row_with_attrs, "|"),
        padding=0,
        with_header_hide=None,
    ),
    "moinmoin": TableFormat(
        lineabove=None,
        linebelowheader=None,
        linebetweenrows=None,
        linebelow=None,
        headerrow=partial(_moin_row_with_attrs, "||", header="'''"),
        datarow=partial(_moin_row_with_attrs, "||"),
        padding=1,
        with_header_hide=None,
    ),
    "youtrack": TableFormat(
        lineabove=None,
        linebelowheader=None,
        linebetweenrows=None,
        linebelow=None,
        headerrow=DataRow("|| ", " || ", " || "),
        datarow=DataRow("| ", " | ", " |"),
        padding=1,
        with_header_hide=None,
    ),
    "html": TableFormat(
        lineabove=_html_begin_table_without_header,
        linebelowheader="",
        linebetweenrows=None,
        linebelow=Line("</tbody>\n</table>", "", "", ""),
        headerrow=partial(_html_row_with_attrs, "th", False),
        datarow=partial(_html_row_with_attrs, "td", False),
        padding=0,
        with_header_hide=["lineabove"],
    ),
    "unsafehtml": TableFormat(
        lineabove=_html_begin_table_without_header,
        linebelowheader="",
        linebetweenrows=None,
        linebelow=Line("</tbody>\n</table>", "", "", ""),
        headerrow=partial(_html_row_with_attrs, "th", True),
        datarow=partial(_html_row_with_attrs, "td", True),
        padding=0,
        with_header_hide=["lineabove"],
    ),
    "latex": TableFormat(
        lineabove=_latex_line_begin_tabular,
        linebelowheader=Line("\\hline", "", "", ""),
        linebetweenrows=None,
        linebelow=Line("\\hline\n\\end{tabular}", "", "", ""),
        headerrow=_latex_row,
        datarow=_latex_row,
        padding=1,
        with_header_hide=None,
    ),
    "latex_raw": TableFormat(
        lineabove=_latex_line_begin_tabular,
        linebelowheader=Line("\\hline", "", "", ""),
        linebetweenrows=None,
        linebelow=Line("\\hline\n\\end{tabular}", "", "", ""),
        headerrow=partial(_latex_row, escrules={}),
        datarow=partial(_latex_row, escrules={}),
        padding=1,
        with_header_hide=None,
    ),
    "latex_booktabs": TableFormat(
        lineabove=partial(_latex_line_begin_tabular, booktabs=True),
        linebelowheader=Line("\\midrule", "", "", ""),
        linebetweenrows=None,
        linebelow=Line("\\bottomrule\n\\end{tabular}", "", "", ""),
        headerrow=_latex_row,
        datarow=_latex_row,
        padding=1,
        with_header_hide=None,
    ),
    "latex_longtable": TableFormat(
        lineabove=partial(_latex_line_begin_tabular, longtable=True),
        linebelowheader=Line("\\hline\n\\endhead", "", "", ""),
        linebetweenrows=None,
        linebelow=Line("\\hline\n\\end{longtable}", "", "", ""),
        headerrow=_latex_row,
        datarow=_latex_row,
        padding=1,
        with_header_hide=None,
    ),
    "tsv": TableFormat(
        lineabove=None,
        linebelowheader=None,
        linebetweenrows=None,
        linebelow=None,
        headerrow=DataRow("", "\t", ""),
        datarow=DataRow("", "\t", ""),
        padding=0,
        with_header_hide=None,
    ),
    "textile": TableFormat(
        lineabove=None,
        linebelowheader=None,
        linebetweenrows=None,
        linebelow=None,
        headerrow=DataRow("|_. ", "|_.", "|"),
        datarow=_textile_row_with_attrs,
        padding=1,
        with_header_hide=None,
    ),
    "asciidoc": TableFormat(
        lineabove=partial(_asciidoc_row, False),
        linebelowheader=None,
        linebetweenrows=None,
        linebelow=Line("|====", "", "", ""),
        headerrow=partial(_asciidoc_row, True),
        datarow=partial(_asciidoc_row, False),
        padding=1,
        with_header_hide=["lineabove"],
    ),
}


tabulate_formats = sorted(_table_formats.keys())

# The table formats for which multiline cells will be folded into subsequent
# table rows. The key is the original format specified at the API. The value is
# the format that will be used to represent the original format.
multiline_formats = {
    "plain": "plain",
    "simple": "simple",
    "grid": "grid",
    "simple_grid": "simple_grid",
    "rounded_grid": "rounded_grid",
    "heavy_grid": "heavy_grid",
    "mixed_grid": "mixed_grid",
    "double_grid": "double_grid",
    "fancy_grid": "fancy_grid",
    "colon_grid": "colon_grid",
    "pipe": "pipe",
    "orgtbl": "orgtbl",
    "jira": "jira",
    "presto": "presto",
    "pretty": "pretty",
    "psql": "psql",
    "rst": "rst",
    "github": "github",
    "outline": "outline",
    "simple_outline": "simple_outline",
    "rounded_outline": "rounded_outline",
    "heavy_outline": "heavy_outline",
    "mixed_outline": "mixed_outline",
    "double_outline": "double_outline",
    "fancy_outline": "fancy_outline",
}

# TODO: Add multiline support for the remaining table formats:
#       - mediawiki: Replace \n with <br>
#       - moinmoin: TBD
#       - youtrack: TBD
#       - html: Replace \n with <br>
#       - latex*: Use "makecell" package: In header, replace X\nY with
#         \thead{X\\Y} and in data row, replace X\nY with \makecell{X\\Y}
#       - tsv: TBD
#       - textile: Replace \n with <br/> (must be well-formed XML)

_multiline_codes = re.compile(r"\r|\n|\r\n")
_multiline_codes_bytes = re.compile(b"\r|\n|\r\n")

# Handle ANSI escape sequences for both control sequence introducer (CSI) and
# operating system command (OSC). Both of these begin with 0x1b (or octal 033),
# which will be shown below as ESC.
#
# CSI ANSI escape codes have the following format, defined in section 5.4 of ECMA-48:
#
# CSI: ESC followed by the '[' character (0x5b)
# Parameter Bytes: 0..n bytes in the range 0x30-0x3f
# Intermediate Bytes: 0..n bytes in the range 0x20-0x2f
# Final Byte: a single byte in the range 0x40-0x7e
#
# Also include the terminal hyperlink sequences as described here:
# https://gist.github.com/egmontkob/eb114294efbcd5adb1944c9f3cb5feda
#
# OSC 8 ; params ; uri ST display_text OSC 8 ;; ST
#
# Example: \x1b]8;;https://example.com\x5ctext to show\x1b]8;;\x5c
#
# Where:
# OSC: ESC followed by the ']' character (0x5d)
# params: 0..n optional key value pairs separated by ':' (e.g. foo=bar:baz=qux:abc=123)
# URI: the actual URI with protocol scheme (e.g. https://, file://, ftp://)
# ST: ESC followed by the '\' character (0x5c)
_esc = r"\x1b"
_csi = rf"{_esc}\["
_osc = rf"{_esc}\]"
_st = rf"{_esc}\\"

_ansi_escape_pat = rf"""
    (
        # terminal colors, etc
        {_csi}        # CSI
        [\x30-\x3f]*  # parameter bytes
        [\x20-\x2f]*  # intermediate bytes
        [\x40-\x7e]   # final byte
    |
        # terminal hyperlinks
        {_osc}8;        # OSC opening
        (\w+=\w+:?)*    # key=value params list (submatch 2)
        ;               # delimiter
        ([^{_esc}]+)    # URI - anything but ESC (submatch 3)
        {_st}           # ST
        ([^{_esc}]+)    # link text - anything but ESC (submatch 4)
        {_osc}8;;{_st}  # "closing" OSC sequence
    )
"""
_ansi_codes = re.compile(_ansi_escape_pat, re.VERBOSE)
_ansi_codes_bytes = re.compile(_ansi_escape_pat.encode("utf8"), re.VERBOSE)
_ansi_color_reset_code = "\033[0m"

_float_with_thousands_separators = re.compile(
    r"^(([+-]?[0-9]{1,3})(?:,([0-9]{3}))*)?(?(1)\.[0-9]*|\.[0-9]+)?$"
)


def simple_separated_format(separator):
    """Construct a simple TableFormat with columns separated by a separator.

    >>> tsv = simple_separated_format("\\t") ; \
        tabulate([["foo", 1], ["spam", 23]], tablefmt=tsv) == 'foo \\t 1\\nspam\\t23'
    True

    """
    return TableFormat(
        None,
        None,
        None,
        None,
        headerrow=DataRow("", separator, ""),
        datarow=DataRow("", separator, ""),
        padding=0,
        with_header_hide=None,
    )


def _isnumber_with_thousands_separator(string):
    """
    >>> _isnumber_with_thousands_separator(".")
    False
    >>> _isnumber_with_thousands_separator("1")
    True
    >>> _isnumber_with_thousands_separator("1.")
    True
    >>> _isnumber_with_thousands_separator(".1")
    True
    >>> _isnumber_with_thousands_separator("1000")
    False
    >>> _isnumber_with_thousands_separator("1,000")
    True
    >>> _isnumber_with_thousands_separator("1,0000")
    False
    >>> _isnumber_with_thousands_separator("1,000.1234")
    True
    >>> _isnumber_with_thousands_separator(b"1,000.1234")
    True
    >>> _isnumber_with_thousands_separator("+1,000.1234")
    True
    >>> _isnumber_with_thousands_separator("-1,000.1234")
    True
    """
    try:
        string = string.decode()
    except (UnicodeDecodeError, AttributeError):
        pass

    return bool(re.match(_float_with_thousands_separators, string))


def _isconvertible(conv, string):
    try:
        conv(string)
        return True
    except (ValueError, TypeError):
        return False


def _isnumber(string):
    """Detects if something *could* be considered a numeric value, vs. just a string.

    This promotes types convertible to both int and float to be considered
    a float.  Note that, iff *all* values appear to be some form of numeric
    value such as eg. "1e2", they would be considered numbers!

    The exception is things that appear to be numbers but overflow to
    +/-inf, eg. "1e23456"; we'll have to exclude them explicitly.

    >>> _isnumber(123)
    True
    >>> _isnumber(123.45)
    True
    >>> _isnumber("123.45")
    True
    >>> _isnumber("123")
    True
    >>> _isnumber("spam")
    False
    >>> _isnumber("123e45")
    True
    >>> _isnumber("123e45678")  # evaluates equal to 'inf', but ... isn't
    False
    >>> _isnumber("inf")
    True
    >>> from fractions import Fraction
    >>> _isnumber(Fraction(1,3))
    True

    """
    return (
        # fast path
        type(string) in (float, int)
        # covers 'NaN', +/- 'inf', and eg. '1e2', as well as any type
        # convertible to int/float.
        or (
            _isconvertible(float, string)
            and (
                # some other type convertible to float
                not isinstance(string, (str, bytes))
                # or, a numeric string eg. "1e1...", "NaN", ..., but isn't
                # just an over/underflow
                or (
                    not (math.isinf(float(string)) or math.isnan(float(string)))
                    or string.lower() in ["inf", "-inf", "nan"]
                )
            )
        )
    )


def _isint(string, inttype=int):
    """
    >>> _isint("123")
    True
    >>> _isint("123.45")
    False
    """
    return (
        type(string) is inttype
        or (
            (hasattr(string, "is_integer") or hasattr(string, "__array__"))
            and str(type(string)).startswith("<class 'numpy.int")
        )  # numpy.int64 and similar
        or (
            isinstance(string, (bytes, str)) and _isconvertible(inttype, string)
        )  # integer as string
    )


def _isbool(string):
    """
    >>> _isbool(True)
    True
    >>> _isbool("False")
    True
    >>> _isbool(1)
    False
    """
    return type(string) is bool or (
        isinstance(string, (bytes, str)) and string in ("True", "False")
    )


def _type(string, has_invisible=True, numparse=True):
    """The least generic type (type(None), int, float, str, unicode).

    Treats empty string as missing for the purposes of type deduction, so as to not influence
    the type of an otherwise complete column; does *not* result in missingval replacement!

    >>> _type(None) is type(None)
    True
    >>> _type("") is type(None)
    True
    >>> _type("foo") is type("")
    True
    >>> _type("1") is type(1)
    True
    >>> _type('\x1b[31m42\x1b[0m') is type(42)
    True
    >>> _type('\x1b[31m42\x1b[0m') is type(42)
    True

    """

    if has_invisible and isinstance(string, (str, bytes)):
        string = _strip_ansi(string)

    if string is None or (isinstance(string, (bytes, str)) and not string):
        return type(None)
    elif hasattr(string, "isoformat"):  # datetime.datetime, date, and time
        return str
    elif _isbool(string):
        return bool
    elif numparse and (
        _isint(string)
        or (
            isinstance(string, str)
            and _isnumber_with_thousands_separator(string)
            and "." not in string
        )
    ):
        return int
    elif numparse and (
        _isnumber(string)
        or (isinstance(string, str) and _isnumber_with_thousands_separator(string))
    ):
        return float
    elif isinstance(string, bytes):
        return bytes
    else:
        return str


def _afterpoint(string):
    """Symbols after a decimal point, -1 if the string lacks the decimal point.

    >>> _afterpoint("123.45")
    2
    >>> _afterpoint("1001")
    -1
    >>> _afterpoint("eggs")
    -1
    >>> _afterpoint("123e45")
    2
    >>> _afterpoint("123,456.78")
    2

    """
    if _isnumber(string) or _isnumber_with_thousands_separator(string):
        if _isint(string):
            return -1
        else:
            pos = string.rfind(".")
            pos = string.lower().rfind("e") if pos < 0 else pos
            if pos >= 0:
                return len(string) - pos - 1
            else:
                return -1  # no point
    else:
        return -1  # not a number


def _padleft(width, s):
    """Flush right.

    >>> _padleft(6, '\u044f\u0439\u0446\u0430') == '  \u044f\u0439\u0446\u0430'
    True

    """
    fmt = "{0:>%ds}" % width
    return fmt.format(s)


def _padright(width, s):
    """Flush left.

    >>> _padright(6, '\u044f\u0439\u0446\u0430') == '\u044f\u0439\u0446\u0430  '
    True

    """
    fmt = "{0:<%ds}" % width
    return fmt.format(s)


def _padboth(width, s):
    """Center string.

    >>> _padboth(6, '\u044f\u0439\u0446\u0430') == ' \u044f\u0439\u0446\u0430 '
    True

    """
    fmt = "{0:^%ds}" % width
    return fmt.format(s)


def _padnone(ignore_width, s):
    return s


def _strip_ansi(s):
    r"""Remove ANSI escape sequences, both CSI (color codes, etc) and OSC hyperlinks.

    CSI sequences are simply removed from the output, while OSC hyperlinks are replaced
    with the link text. Note: it may be desirable to show the URI instead but this is not
    supported.

    >>> repr(_strip_ansi('\x1B]8;;https://example.com\x1B\\This is a link\x1B]8;;\x1B\\'))
    "'This is a link'"

    >>> repr(_strip_ansi('\x1b[31mred\x1b[0m text'))
    "'red text'"

    """
    if isinstance(s, str):
        return _ansi_codes.sub(r"\4", s)
    else:  # a bytestring
        return _ansi_codes_bytes.sub(r"\4", s)


def _visible_width(s):
    """Visible width of a printed string. ANSI color codes are removed.

    >>> _visible_width('\x1b[31mhello\x1b[0m'), _visible_width("world")
    (5, 5)

    """
    # optional wide-character support
    if wcwidth is not None and WIDE_CHARS_MODE:
        len_fn = wcwidth.wcswidth
    else:
        len_fn = len
    if isinstance(s, (str, bytes)):
        return len_fn(_strip_ansi(s))
    else:
        return len_fn(str(s))


def _is_multiline(s):
    if isinstance(s, str):
        return bool(re.search(_multiline_codes, s))
    else:  # a bytestring
        return bool(re.search(_multiline_codes_bytes, s))


def _multiline_width(multiline_s, line_width_fn=len):
    """Visible width of a potentially multiline content."""
    return max(map(line_width_fn, re.split("[\r\n]", multiline_s)))


def _choose_width_fn(has_invisible, enable_widechars, is_multiline):
    """Return a function to calculate visible cell width."""
    if has_invisible:
        line_width_fn = _visible_width
    elif enable_widechars:  # optional wide-character support if available
        line_width_fn = wcwidth.wcswidth
    else:
        line_width_fn = len
    if is_multiline:
        width_fn = lambda s: _multiline_width(s, line_width_fn)  # noqa: E731
    else:
        width_fn = line_width_fn
    return width_fn


def _align_column_choose_padfn(strings, alignment, has_invisible, preserve_whitespace):
    if alignment == "right":
        if not preserve_whitespace:
            strings = [s.strip() for s in strings]
        padfn = _padleft
    elif alignment == "center":
        if not preserve_whitespace:
            strings = [s.strip() for s in strings]
        padfn = _padboth
    elif alignment == "decimal":
        if has_invisible:
            decimals = [_afterpoint(_strip_ansi(s)) for s in strings]
        else:
            decimals = [_afterpoint(s) for s in strings]
        maxdecimals = max(decimals)
        strings = [s + (maxdecimals - decs) * " " for s, decs in zip(strings, decimals)]
        padfn = _padleft
    elif not alignment:
        padfn = _padnone
    else:
        if not preserve_whitespace:
            strings = [s.strip() for s in strings]
        padfn = _padright
    return strings, padfn


def _align_column_choose_width_fn(has_invisible, enable_widechars, is_multiline):
    if has_invisible:
        line_width_fn = _visible_width
    elif enable_widechars:  # optional wide-character support if available
        line_width_fn = wcwidth.wcswidth
    else:
        line_width_fn = len
    if is_multiline:
        width_fn = lambda s: _align_column_multiline_width(  # noqa: E731
            s, line_width_fn
        )
    else:
        width_fn = line_width_fn
    return width_fn


def _align_column_multiline_width(multiline_s, line_width_fn=len):
    """Visible width of a potentially multiline content."""
    return list(map(line_width_fn, re.split("[\r\n]", multiline_s)))


def _flat_list(nested_list):
    ret = []
    for item in nested_list:
        if isinstance(item, list):
            ret.extend(item)
        else:
            ret.append(item)
    return ret


def _align_column(
    strings,
    alignment,
    minwidth=0,
    has_invisible=True,
    enable_widechars=False,
    is_multiline=False,
    preserve_whitespace=False,
):
    """[string] -> [padded_string]"""
    strings, padfn = _align_column_choose_padfn(
        strings, alignment, has_invisible, preserve_whitespace
    )
    width_fn = _align_column_choose_width_fn(
        has_invisible, enable_widechars, is_multiline
    )

    s_widths = list(map(width_fn, strings))
    maxwidth = max(max(_flat_list(s_widths)), minwidth)
    # TODO: refactor column alignment in single-line and multiline modes
    if is_multiline:
        if not enable_widechars and not has_invisible:
            padded_strings = [
                "\n".join([padfn(maxwidth, s) for s in ms.splitlines()])
                for ms in strings
            ]
        else:
            # enable wide-character width corrections
            s_lens = [[len(s) for s in re.split("[\r\n]", ms)] for ms in strings]
            visible_widths = [
                [maxwidth - (w - l) for w, l in zip(mw, ml)]
                for mw, ml in zip(s_widths, s_lens)
            ]
            # wcswidth and _visible_width don't count invisible characters;
            # padfn doesn't need to apply another correction
            padded_strings = [
                "\n".join([padfn(w, s) for s, w in zip((ms.splitlines() or ms), mw)])
                for ms, mw in zip(strings, visible_widths)
            ]
    else:  # single-line cell values
        if not enable_widechars and not has_invisible:
            padded_strings = [padfn(maxwidth, s) for s in strings]
        else:
            # enable wide-character width corrections
            s_lens = list(map(len, strings))
            visible_widths = [maxwidth - (w - l) for w, l in zip(s_widths, s_lens)]
            # wcswidth and _visible_width don't count invisible characters;
            # padfn doesn't need to apply another correction
            padded_strings = [padfn(w, s) for s, w in zip(strings, visible_widths)]
    return padded_strings


def _more_generic(type1, type2):
    types = {
        type(None): 0,
        bool: 1,
        int: 2,
        float: 3,
        bytes: 4,
        str: 5,
    }
    invtypes = {
        5: str,
        4: bytes,
        3: float,
        2: int,
        1: bool,
        0: type(None),
    }
    moregeneric = max(types.get(type1, 5), types.get(type2, 5))
    return invtypes[moregeneric]


def _column_type(strings, has_invisible=True, numparse=True):
    """The least generic type all column values are convertible to.

    >>> _column_type([True, False]) is bool
    True
    >>> _column_type(["1", "2"]) is int
    True
    >>> _column_type(["1", "2.3"]) is float
    True
    >>> _column_type(["1", "2.3", "four"]) is str
    True
    >>> _column_type(["four", '\u043f\u044f\u0442\u044c']) is str
    True
    >>> _column_type([None, "brux"]) is str
    True
    >>> _column_type([1, 2, None]) is int
    True
    >>> import datetime as dt
    >>> _column_type([dt.datetime(1991,2,19), dt.time(17,35)]) is str
    True

    """
    types = [_type(s, has_invisible, numparse) for s in strings]
    return reduce(_more_generic, types, bool)


def _format(val, valtype, floatfmt, intfmt, missingval="", has_invisible=True):
    """Format a value according to its deduced type.  Empty values are deemed valid for any type.

    Unicode is supported:

    >>> hrow = ['\u0431\u0443\u043a\u0432\u0430', '\u0446\u0438\u0444\u0440\u0430'] ; \
        tbl = [['\u0430\u0437', 2], ['\u0431\u0443\u043a\u0438', 4]] ; \
        good_result = '\\u0431\\u0443\\u043a\\u0432\\u0430      \\u0446\\u0438\\u0444\\u0440\\u0430\\n-------  -------\\n\\u0430\\u0437             2\\n\\u0431\\u0443\\u043a\\u0438           4' ; \
        tabulate(tbl, headers=hrow) == good_result
    True

    """  # noqa: E501
    if val is None:
        return missingval
    if isinstance(val, (bytes, str)) and not val:
        return ""

    if valtype is str:
        return f"{val}"
    elif valtype is int:
        if isinstance(val, str):
            val_striped = val.encode("unicode_escape").decode("utf-8")
            colored = re.search(
                r"(\\[xX]+[0-9a-fA-F]+\[\d+[mM]+)([0-9.]+)(\\.*)$", val_striped
            )
            if colored:
                total_groups = len(colored.groups())
                if total_groups == 3:
                    digits = colored.group(2)
                    if digits.isdigit():
                        val_new = (
                            colored.group(1)
                            + format(int(digits), intfmt)
                            + colored.group(3)
                        )
                        val = val_new.encode("utf-8").decode("unicode_escape")
            intfmt = ""
        return format(val, intfmt)
    elif valtype is bytes:
        try:
            return str(val, "ascii")
        except (TypeError, UnicodeDecodeError):
            return str(val)
    elif valtype is float:
        is_a_colored_number = has_invisible and isinstance(val, (str, bytes))
        if is_a_colored_number:
            raw_val = _strip_ansi(val)
            try:
                formatted_val = format(float(raw_val), floatfmt)
            except (ValueError, TypeError):
                return f"{val}"
            return val.replace(raw_val, formatted_val)
        else:
            if isinstance(val, str) and "," in val:
                val = val.replace(",", "")  # handle thousands-separators
            try:
                return format(float(val), floatfmt)
            except (ValueError, TypeError):
                return f"{val}"
    else:
        return f"{val}"


def _align_header(
    header, alignment, width, visible_width, is_multiline=False, width_fn=None
):
    "Pad string header to width chars given known visible_width of the header."
    if is_multiline:
        header_lines = re.split(_multiline_codes, header)
        padded_lines = [
            _align_header(h, alignment, width, width_fn(h)) for h in header_lines
        ]
        return "\n".join(padded_lines)
    # else: not multiline
    ninvisible = len(header) - visible_width
    width += ninvisible
    if alignment == "left":
        return _padright(width, header)
    elif alignment == "center":
        return _padboth(width, header)
    elif not alignment:
        return f"{header}"
    else:
        return _padleft(width, header)


def _remove_separating_lines(rows):
    if isinstance(rows, list):
        separating_lines = []
        sans_rows = []
        for index, row in enumerate(rows):
            if _is_separating_line(row):
                separating_lines.append(index)
            else:
                sans_rows.append(row)
        return sans_rows, separating_lines
    else:
        return rows, None


def _reinsert_separating_lines(rows, separating_lines):
    if separating_lines:
        for index in separating_lines:
            rows.insert(index, SEPARATING_LINE)


def _prepend_row_index(rows, index):
    """Add a left-most index column."""
    if index is None or index is False:
        return rows
    if isinstance(index, Sized) and len(index) != len(rows):
        raise ValueError(
            "index must be as long as the number of data rows: "
            + f"len(index)={len(index)} len(rows)={len(rows)}"
        )
    sans_rows, separating_lines = _remove_separating_lines(rows)
    new_rows = []
    index_iter = iter(index)
    for row in sans_rows:
        index_v = next(index_iter)
        new_rows.append([index_v] + list(row))
    rows = new_rows
    _reinsert_separating_lines(rows, separating_lines)
    return rows


def _bool(val):
    "A wrapper around standard bool() which doesn't throw on NumPy arrays"
    try:
        return bool(val)
    except ValueError:  # val is likely to be a numpy array with many elements
        return False


def _normalize_tabular_data(tabular_data, headers, showindex="default"):
    """Transform a supported data type to a list of lists, and a list of headers,
    with headers padding.

    Supported tabular data types:

    * list-of-lists or another iterable of iterables

    * list of named tuples (usually used with headers="keys")

    * list of dicts (usually used with headers="keys")

    * list of OrderedDicts (usually used with headers="keys")

    * list of dataclasses (usually used with headers="keys")

    * 2D NumPy arrays

    * NumPy record arrays (usually used with headers="keys")

    * dict of iterables (usually used with headers="keys")

    * pandas.DataFrame (usually used with headers="keys")

    The first row can be used as headers if headers="firstrow",
    column indices can be used as headers if headers="keys".

    If showindex="default", show row indices of the pandas.DataFrame.
    If showindex="always", show row indices for all types of data.
    If showindex="never", don't show row indices for all types of data.
    If showindex is an iterable, show its values as row indices.

    """

    try:
        bool(headers)
    except ValueError:  # numpy.ndarray, pandas.core.index.Index, ...
        headers = list(headers)

    err_msg = (
        "\n\nTo build a table python-tabulate requires two-dimensional data "
        "like a list of lists or similar."
        "\nDid you forget a pair of extra [] or ',' in ()?"
    )
    index = None
    if hasattr(tabular_data, "keys") and hasattr(tabular_data, "values"):
        # dict-like and pandas.DataFrame?
        if callable(tabular_data.values):
            # likely a conventional dict
            keys = tabular_data.keys()
            try:
                rows = list(
                    izip_longest(*tabular_data.values())
                )  # columns have to be transposed
            except TypeError:  # not iterable
                raise TypeError(err_msg)

        elif hasattr(tabular_data, "index"):
            # values is a property, has .index => it's likely a pandas.DataFrame (pandas 0.11.0)
            keys = list(tabular_data)
            if (
                showindex in ["default", "always", True]
                and tabular_data.index.name is not None
            ):
                if isinstance(tabular_data.index.name, list):
                    keys[:0] = tabular_data.index.name
                else:
                    keys[:0] = [tabular_data.index.name]
            vals = tabular_data.values  # values matrix doesn't need to be transposed
            # for DataFrames add an index per default
            index = list(tabular_data.index)
            rows = [list(row) for row in vals]
        else:
            raise ValueError("tabular data doesn't appear to be a dict or a DataFrame")

        if headers == "keys":
            headers = list(map(str, keys))  # headers should be strings

    else:  # it's a usual iterable of iterables, or a NumPy array, or an iterable of dataclasses
        try:
            rows = list(tabular_data)
        except TypeError:  # not iterable
            raise TypeError(err_msg)

        if headers == "keys" and not rows:
            # an empty table (issue #81)
            headers = []
        elif (
            headers == "keys"
            and hasattr(tabular_data, "dtype")
            and tabular_data.dtype.names
        ):
            # numpy record array
            headers = tabular_data.dtype.names
        elif (
            headers == "keys"
            and len(rows) > 0
            and isinstance(rows[0], tuple)
            and hasattr(rows[0], "_fields")
        ):
            # namedtuple
            headers = list(map(str, rows[0]._fields))
        elif len(rows) > 0 and hasattr(rows[0], "keys") and hasattr(rows[0], "values"):
            # dict-like object
            uniq_keys = set()  # implements hashed lookup
            keys = []  # storage for set
            if headers == "firstrow":
                firstdict = rows[0] if len(rows) > 0 else {}
                keys.extend(firstdict.keys())
                uniq_keys.update(keys)
                rows = rows[1:]
            for row in rows:
                for k in row.keys():
                    # Save unique items in input order
                    if k not in uniq_keys:
                        keys.append(k)
                        uniq_keys.add(k)
            if headers == "keys":
                headers = keys
            elif isinstance(headers, dict):
                # a dict of headers for a list of dicts
                headers = [headers.get(k, k) for k in keys]
                headers = list(map(str, headers))
            elif headers == "firstrow":
                if len(rows) > 0:
                    headers = [firstdict.get(k, k) for k in keys]
                    headers = list(map(str, headers))
                else:
                    headers = []
            elif headers:
                raise ValueError(
                    "headers for a list of dicts is not a dict or a keyword"
                )
            rows = [[row.get(k) for k in keys] for row in rows]

        elif (
            headers == "keys"
            and hasattr(tabular_data, "description")
            and hasattr(tabular_data, "fetchone")
            and hasattr(tabular_data, "rowcount")
        ):
            # Python Database API cursor object (PEP 0249)
            # print tabulate(cursor, headers='keys')
            headers = [column[0] for column in tabular_data.description]

        elif (
            dataclasses is not None
            and len(rows) > 0
            and dataclasses.is_dataclass(rows[0])
        ):
            # Python's dataclass
            field_names = [field.name for field in dataclasses.fields(rows[0])]
            if headers == "keys":
                headers = field_names
            rows = [
                (
                    [getattr(row, f) for f in field_names]
                    if not _is_separating_line(row)
                    else row
                )
                for row in rows
            ]

        elif headers == "keys" and len(rows) > 0:
            # keys are column indices
            headers = list(map(str, range(len(rows[0]))))

    # take headers from the first row if necessary
    if headers == "firstrow" and len(rows) > 0:
        if index is not None:
            headers = [index[0]] + list(rows[0])
            index = index[1:]
        else:
            headers = rows[0]
        headers = list(map(str, headers))  # headers should be strings
        rows = rows[1:]
    elif headers == "firstrow":
        headers = []

    headers = list(map(str, headers))
    #    rows = list(map(list, rows))
    rows = list(map(lambda r: r if _is_separating_line(r) else list(r), rows))

    # add or remove an index column
    showindex_is_a_str = type(showindex) in [str, bytes]
    if showindex == "default" and index is not None:
        rows = _prepend_row_index(rows, index)
    elif isinstance(showindex, Sized) and not showindex_is_a_str:
        rows = _prepend_row_index(rows, list(showindex))
    elif isinstance(showindex, Iterable) and not showindex_is_a_str:
        rows = _prepend_row_index(rows, showindex)
    elif showindex == "always" or (_bool(showindex) and not showindex_is_a_str):
        if index is None:
            index = list(range(len(rows)))
        rows = _prepend_row_index(rows, index)
    elif showindex == "never" or (not _bool(showindex) and not showindex_is_a_str):
        pass

    # pad with empty headers for initial columns if necessary
    headers_pad = 0
    if headers and len(rows) > 0:
        headers_pad = max(0, len(rows[0]) - len(headers))
        headers = [""] * headers_pad + headers

    return rows, headers, headers_pad


def _wrap_text_to_colwidths(
    list_of_lists,
    colwidths,
    numparses=True,
    missingval=_DEFAULT_MISSINGVAL,
    break_long_words=_BREAK_LONG_WORDS,
    break_on_hyphens=_BREAK_ON_HYPHENS,
):
    if len(list_of_lists):
        num_cols = len(list_of_lists[0])
    else:
        num_cols = 0
    numparses = _expand_iterable(numparses, num_cols, True)

    result = []

    for row in list_of_lists:
        new_row = []
        for cell, width, numparse in zip(row, colwidths, numparses):
            if _isnumber(cell) and numparse:
                new_row.append(cell)
                continue

            if width is not None:
                wrapper = _CustomTextWrap(
                    width=width,
                    break_long_words=break_long_words,
                    break_on_hyphens=break_on_hyphens,
                )
                # Cast based on our internal type handling. Any future custom
                # formatting of types (such as datetimes) may need to be more
                # explicit than just `str` of the object. Also doesn't work for
                # custom floatfmt/intfmt, nor with any missing/blank cells.
                casted_cell = (
                    missingval
                    if cell is None
                    else (
                        str(cell)
                        if cell == "" or _isnumber(cell)
                        else str(_type(cell, numparse)(cell))
                    )
                )
                wrapped = [
                    "\n".join(wrapper.wrap(line))
                    for line in casted_cell.splitlines()
                    if line.strip() != ""
                ]
                new_row.append("\n".join(wrapped))
            else:
                new_row.append(cell)
        result.append(new_row)

    return result


def _to_str(s, encoding="utf8", errors="ignore"):
    """
    A type safe wrapper for converting a bytestring to str. This is essentially just
    a wrapper around .decode() intended for use with things like map(), but with some
    specific behavior:

    1. if the given parameter is not a bytestring, it is returned unmodified
    2. decode() is called for the given parameter and assumes utf8 encoding, but the
       default error behavior is changed from 'strict' to 'ignore'

    >>> repr(_to_str(b'foo'))
    "'foo'"

    >>> repr(_to_str('foo'))
    "'foo'"

    >>> repr(_to_str(42))
    "'42'"

    """
    if isinstance(s, bytes):
        return s.decode(encoding=encoding, errors=errors)
    return str(s)


def tabulate(
    tabular_data,
    headers=(),
    tablefmt="simple",
    floatfmt=_DEFAULT_FLOATFMT,
    intfmt=_DEFAULT_INTFMT,
    numalign=_DEFAULT_ALIGN,
    stralign=_DEFAULT_ALIGN,
    missingval=_DEFAULT_MISSINGVAL,
    showindex="default",
    disable_numparse=False,
    colglobalalign=None,
    colalign=None,
    preserve_whitespace=False,
    maxcolwidths=None,
    headersglobalalign=None,
    headersalign=None,
    rowalign=None,
    maxheadercolwidths=None,
    break_long_words=_BREAK_LONG_WORDS,
    break_on_hyphens=_BREAK_ON_HYPHENS,
):
    """Format a fixed width table for pretty printing.

    >>> print(tabulate([[1, 2.34], [-56, "8.999"], ["2", "10001"]]))
    ---  ---------
      1      2.34
    -56      8.999
      2  10001
    ---  ---------

    The first required argument (`tabular_data`) can be a
    list-of-lists (or another iterable of iterables), a list of named
    tuples, a dictionary of iterables, an iterable of dictionaries,
    an iterable of dataclasses, a two-dimensional NumPy array,
    NumPy record array, or a Pandas' dataframe.


    Table headers
    -------------

    To print nice column headers, supply the second argument (`headers`):

      - `headers` can be an explicit list of column headers
      - if `headers="firstrow"`, then the first row of data is used
      - if `headers="keys"`, then dictionary keys or column indices are used

    Otherwise a headerless table is produced.

    If the number of headers is less than the number of columns, they
    are supposed to be names of the last columns. This is consistent
    with the plain-text format of R and Pandas' dataframes.

    >>> print(tabulate([["sex","age"],["Alice","F",24],["Bob","M",19]],
    ...       headers="firstrow"))
           sex      age
    -----  -----  -----
    Alice  F         24
    Bob    M         19

    By default, pandas.DataFrame data have an additional column called
    row index. To add a similar column to all other types of data,
    use `showindex="always"` or `showindex=True`. To suppress row indices
    for all types of data, pass `showindex="never" or `showindex=False`.
    To add a custom row index column, pass `showindex=some_iterable`.

    >>> print(tabulate([["F",24],["M",19]], showindex="always"))
    -  -  --
    0  F  24
    1  M  19
    -  -  --


    Column and Headers alignment
    ----------------------------

    `tabulate` tries to detect column types automatically, and aligns
    the values properly. By default it aligns decimal points of the
    numbers (or flushes integer numbers to the right), and flushes
    everything else to the left. Possible column alignments
    (`numalign`, `stralign`) are: "right", "center", "left", "decimal"
    (only for `numalign`), and None (to disable alignment).

    `colglobalalign` allows for global alignment of columns, before any
        specific override from `colalign`. Possible values are: None
        (defaults according to coltype), "right", "center", "decimal",
        "left".
    `colalign` allows for column-wise override starting from left-most
        column. Possible values are: "global" (no override), "right",
        "center", "decimal", "left".
    `headersglobalalign` allows for global headers alignment, before any
        specific override from `headersalign`. Possible values are: None
        (follow columns alignment), "right", "center", "left".
    `headersalign` allows for header-wise override starting from left-most
        given header. Possible values are: "global" (no override), "same"
        (follow column alignment), "right", "center", "left".

    Note on intended behaviour: If there is no `tabular_data`, any column
        alignment argument is ignored. Hence, in this case, header
        alignment cannot be inferred from column alignment.

    Table formats
    -------------

    `intfmt` is a format specification used for columns which
    contain numeric data without a decimal point. This can also be
    a list or tuple of format strings, one per column.

    `floatfmt` is a format specification used for columns which
    contain numeric data with a decimal point. This can also be
    a list or tuple of format strings, one per column.

    `None` values are replaced with a `missingval` string (like
    `floatfmt`, this can also be a list of values for different
    columns):

    >>> print(tabulate([["spam", 1, None],
    ...                 ["eggs", 42, 3.14],
    ...                 ["other", None, 2.7]], missingval="?"))
    -----  --  ----
    spam    1  ?
    eggs   42  3.14
    other   ?  2.7
    -----  --  ----

    Various plain-text table formats (`tablefmt`) are supported:
    'plain', 'simple', 'grid', 'pipe', 'orgtbl', 'rst', 'mediawiki',
    'latex', 'latex_raw', 'latex_booktabs', 'latex_longtable' and tsv.
    Variable `tabulate_formats`contains the list of currently supported formats.

    "plain" format doesn't use any pseudographics to draw tables,
    it separates columns with a double space:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                 ["strings", "numbers"], "plain"))
    strings      numbers
    spam         41.9999
    eggs        451

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]], tablefmt="plain"))
    spam   41.9999
    eggs  451

    "simple" format is like Pandoc simple_tables:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                 ["strings", "numbers"], "simple"))
    strings      numbers
    ---------  ---------
    spam         41.9999
    eggs        451

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]], tablefmt="simple"))
    ----  --------
    spam   41.9999
    eggs  451
    ----  --------

    "grid" is similar to tables produced by Emacs table.el package or
    Pandoc grid_tables:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                ["strings", "numbers"], "grid"))
    +-----------+-----------+
    | strings   |   numbers |
    +===========+===========+
    | spam      |   41.9999 |
    +-----------+-----------+
    | eggs      |  451      |
    +-----------+-----------+

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]], tablefmt="grid"))
    +------+----------+
    | spam |  41.9999 |
    +------+----------+
    | eggs | 451      |
    +------+----------+

    "simple_grid" draws a grid using single-line box-drawing
    characters:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                ["strings", "numbers"], "simple_grid"))
    ┌───────────┬───────────┐
    │ strings   │   numbers │
    ├───────────┼───────────┤
    │ spam      │   41.9999 │
    ├───────────┼───────────┤
    │ eggs      │  451      │
    └───────────┴───────────┘

    "rounded_grid" draws a grid using single-line box-drawing
    characters with rounded corners:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                ["strings", "numbers"], "rounded_grid"))
    ╭───────────┬───────────╮
    │ strings   │   numbers │
    ├───────────┼───────────┤
    │ spam      │   41.9999 │
    ├───────────┼───────────┤
    │ eggs      │  451      │
    ╰───────────┴───────────╯

    "heavy_grid" draws a grid using bold (thick) single-line box-drawing
    characters:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                ["strings", "numbers"], "heavy_grid"))
    ┏━━━━━━━━━━━┳━━━━━━━━━━━┓
    ┃ strings   ┃   numbers ┃
    ┣━━━━━━━━━━━╋━━━━━━━━━━━┫
    ┃ spam      ┃   41.9999 ┃
    ┣━━━━━━━━━━━╋━━━━━━━━━━━┫
    ┃ eggs      ┃  451      ┃
    ┗━━━━━━━━━━━┻━━━━━━━━━━━┛

    "mixed_grid" draws a grid using a mix of light (thin) and heavy (thick) lines
    box-drawing characters:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                ["strings", "numbers"], "mixed_grid"))
    ┍━━━━━━━━━━━┯━━━━━━━━━━━┑
    │ strings   │   numbers │
    ┝━━━━━━━━━━━┿━━━━━━━━━━━┥
    │ spam      │   41.9999 │
    ├───────────┼───────────┤
    │ eggs      │  451      │
    ┕━━━━━━━━━━━┷━━━━━━━━━━━┙

    "double_grid" draws a grid using double-line box-drawing
    characters:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                ["strings", "numbers"], "double_grid"))
    ╔═══════════╦═══════════╗
    ║ strings   ║   numbers ║
    ╠═══════════╬═══════════╣
    ║ spam      ║   41.9999 ║
    ╠═══════════╬═══════════╣
    ║ eggs      ║  451      ║
    ╚═══════════╩═══════════╝

    "fancy_grid" draws a grid using a mix of single and
    double-line box-drawing characters:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                ["strings", "numbers"], "fancy_grid"))
    ╒═══════════╤═══════════╕
    │ strings   │   numbers │
    ╞═══════════╪═══════════╡
    │ spam      │   41.9999 │
    ├───────────┼───────────┤
    │ eggs      │  451      │
    ╘═══════════╧═══════════╛

    "colon_grid" is similar to "grid" but uses colons only to define
    columnwise content alignment, without whitespace padding,
    similar to the alignment specification of Pandoc `grid_tables`:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                ["strings", "numbers"], "colon_grid"))
    +-----------+-----------+
    | strings   | numbers   |
    +:==========+:==========+
    | spam      | 41.9999   |
    +-----------+-----------+
    | eggs      | 451       |
    +-----------+-----------+

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                ["strings", "numbers"], "colon_grid",
    ...                colalign=["right", "left"]))
    +-----------+-----------+
    | strings   | numbers   |
    +==========:+:==========+
    | spam      | 41.9999   |
    +-----------+-----------+
    | eggs      | 451       |
    +-----------+-----------+

    "outline" is the same as the "grid" format but doesn't draw lines between rows:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                ["strings", "numbers"], "outline"))
    +-----------+-----------+
    | strings   |   numbers |
    +===========+===========+
    | spam      |   41.9999 |
    | eggs      |  451      |
    +-----------+-----------+

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]], tablefmt="outline"))
    +------+----------+
    | spam |  41.9999 |
    | eggs | 451      |
    +------+----------+

    "simple_outline" is the same as the "simple_grid" format but doesn't draw lines between rows:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                ["strings", "numbers"], "simple_outline"))
    ┌───────────┬───────────┐
    │ strings   │   numbers │
    ├───────────┼───────────┤
    │ spam      │   41.9999 │
    │ eggs      │  451      │
    └───────────┴───────────┘

    "rounded_outline" is the same as the "rounded_grid" format but doesn't draw lines between rows:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                ["strings", "numbers"], "rounded_outline"))
    ╭───────────┬───────────╮
    │ strings   │   numbers │
    ├───────────┼───────────┤
    │ spam      │   41.9999 │
    │ eggs      │  451      │
    ╰───────────┴───────────╯

    "heavy_outline" is the same as the "heavy_grid" format but doesn't draw lines between rows:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                ["strings", "numbers"], "heavy_outline"))
    ┏━━━━━━━━━━━┳━━━━━━━━━━━┓
    ┃ strings   ┃   numbers ┃
    ┣━━━━━━━━━━━╋━━━━━━━━━━━┫
    ┃ spam      ┃   41.9999 ┃
    ┃ eggs      ┃  451      ┃
    ┗━━━━━━━━━━━┻━━━━━━━━━━━┛

    "mixed_outline" is the same as the "mixed_grid" format but doesn't draw lines between rows:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                ["strings", "numbers"], "mixed_outline"))
    ┍━━━━━━━━━━━┯━━━━━━━━━━━┑
    │ strings   │   numbers │
    ┝━━━━━━━━━━━┿━━━━━━━━━━━┥
    │ spam      │   41.9999 │
    │ eggs      │  451      │
    ┕━━━━━━━━━━━┷━━━━━━━━━━━┙

    "double_outline" is the same as the "double_grid" format but doesn't draw lines between rows:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                ["strings", "numbers"], "double_outline"))
    ╔═══════════╦═══════════╗
    ║ strings   ║   numbers ║
    ╠═══════════╬═══════════╣
    ║ spam      ║   41.9999 ║
    ║ eggs      ║  451      ║
    ╚═══════════╩═══════════╝

    "fancy_outline" is the same as the "fancy_grid" format but doesn't draw lines between rows:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                ["strings", "numbers"], "fancy_outline"))
    ╒═══════════╤═══════════╕
    │ strings   │   numbers │
    ╞═══════════╪═══════════╡
    │ spam      │   41.9999 │
    │ eggs      │  451      │
    ╘═══════════╧═══════════╛

    "pipe" is like tables in PHP Markdown Extra extension or Pandoc
    pipe_tables:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                ["strings", "numbers"], "pipe"))
    | strings   |   numbers |
    |:----------|----------:|
    | spam      |   41.9999 |
    | eggs      |  451      |

    "presto" is like tables produce by the Presto CLI:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                ["strings", "numbers"], "presto"))
     strings   |   numbers
    -----------+-----------
     spam      |   41.9999
     eggs      |  451

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]], tablefmt="pipe"))
    |:-----|---------:|
    | spam |  41.9999 |
    | eggs | 451      |

    "orgtbl" is like tables in Emacs org-mode and orgtbl-mode. They
    are slightly different from "pipe" format by not using colons to
    define column alignment, and using a "+" sign to indicate line
    intersections:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                ["strings", "numbers"], "orgtbl"))
    | strings   |   numbers |
    |-----------+-----------|
    | spam      |   41.9999 |
    | eggs      |  451      |


    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]], tablefmt="orgtbl"))
    | spam |  41.9999 |
    | eggs | 451      |

    "rst" is like a simple table format from reStructuredText; please
    note that reStructuredText accepts also "grid" tables:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]],
    ...                ["strings", "numbers"], "rst"))
    =========  =========
    strings      numbers
    =========  =========
    spam         41.9999
    eggs        451
    =========  =========

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]], tablefmt="rst"))
    ====  ========
    spam   41.9999
    eggs  451
    ====  ========

    "mediawiki" produces a table markup used in Wikipedia and on other
    MediaWiki-based sites:

    >>> print(tabulate([["strings", "numbers"], ["spam", 41.9999], ["eggs", "451.0"]],
    ...                headers="firstrow", tablefmt="mediawiki"))
    {| class="wikitable" style="text-align: left;"
    |+ <!-- caption -->
    |-
    ! strings   !! style="text-align: right;"|   numbers
    |-
    | spam      || style="text-align: right;"|   41.9999
    |-
    | eggs      || style="text-align: right;"|  451
    |}

    "html" produces HTML markup as an html.escape'd str
    with a ._repr_html_ method so that Jupyter Lab and Notebook display the HTML
    and a .str property so that the raw HTML remains accessible
    the unsafehtml table format can be used if an unescaped HTML format is required:

    >>> print(tabulate([["strings", "numbers"], ["spam", 41.9999], ["eggs", "451.0"]],
    ...                headers="firstrow", tablefmt="html"))
    <table>
    <thead>
    <tr><th>strings  </th><th style="text-align: right;">  numbers</th></tr>
    </thead>
    <tbody>
    <tr><td>spam     </td><td style="text-align: right;">  41.9999</td></tr>
    <tr><td>eggs     </td><td style="text-align: right;"> 451     </td></tr>
    </tbody>
    </table>

    "latex" produces a tabular environment of LaTeX document markup:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]], tablefmt="latex"))
    \\begin{tabular}{lr}
    \\hline
     spam &  41.9999 \\\\
     eggs & 451      \\\\
    \\hline
    \\end{tabular}

    "latex_raw" is similar to "latex", but doesn't escape special characters,
    such as backslash and underscore, so LaTeX commands may embedded into
    cells' values:

    >>> print(tabulate([["spam$_9$", 41.9999], ["\\\\emph{eggs}", "451.0"]], tablefmt="latex_raw"))
    \\begin{tabular}{lr}
    \\hline
     spam$_9$    &  41.9999 \\\\
     \\emph{eggs} & 451      \\\\
    \\hline
    \\end{tabular}

    "latex_booktabs" produces a tabular environment of LaTeX document markup
    using the booktabs.sty package:

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]], tablefmt="latex_booktabs"))
    \\begin{tabular}{lr}
    \\toprule
     spam &  41.9999 \\\\
     eggs & 451      \\\\
    \\bottomrule
    \\end{tabular}

    "latex_longtable" produces a tabular environment that can stretch along
    multiple pages, using the longtable package for LaTeX.

    >>> print(tabulate([["spam", 41.9999], ["eggs", "451.0"]], tablefmt="latex_longtable"))
    \\begin{longtable}{lr}
    \\hline
     spam &  41.9999 \\\\
     eggs & 451      \\\\
    \\hline
    \\end{longtable}


    Number parsing
    --------------
    By default, anything which can be parsed as a number is a number.
    This ensures numbers represented as strings are aligned properly.
    This can lead to weird results for particular strings such as
    specific git SHAs e.g. "42992e1" will be parsed into the number
    429920 and aligned as such.

    To completely disable number parsing (and alignment), use
    `disable_numparse=True`. For more fine grained control, a list column
    indices is used to disable number parsing only on those columns
    e.g. `disable_numparse=[0, 2]` would disable number parsing only on the
    first and third columns.

    Column Widths and Auto Line Wrapping
    ------------------------------------
    Tabulate will, by default, set the width of each column to the length of the
    longest element in that column. However, in situations where fields are expected
    to reasonably be too long to look good as a single line, tabulate can help automate
    word wrapping long fields for you. Use the parameter `maxcolwidths` to provide a
    list of maximal column widths:

    >>> print(tabulate( \
          [('1', 'John Smith', \
            'This is a rather long description that might look better if it is wrapped a bit')], \
          headers=("Issue Id", "Author", "Description"), \
          maxcolwidths=[None, None, 30], \
          tablefmt="grid"  \
        ))
    +------------+------------+-------------------------------+
    |   Issue Id | Author     | Description                   |
    +============+============+===============================+
    |          1 | John Smith | This is a rather long         |
    |            |            | description that might look   |
    |            |            | better if it is wrapped a bit |
    +------------+------------+-------------------------------+

    Header column width can be specified in a similar way using `maxheadercolwidths`.

    """

    if tabular_data is None:
        tabular_data = []

    list_of_lists, headers, headers_pad = _normalize_tabular_data(
        tabular_data, headers, showindex=showindex
    )
    list_of_lists, separating_lines = _remove_separating_lines(list_of_lists)

    if maxcolwidths is not None:
        if type(maxcolwidths) is tuple:  # Check if tuple, convert to list if so
            maxcolwidths = list(maxcolwidths)
        if len(list_of_lists):
            num_cols = len(list_of_lists[0])
        else:
            num_cols = 0
        if isinstance(maxcolwidths, int):  # Expand scalar for all columns
            maxcolwidths = _expand_iterable(maxcolwidths, num_cols, maxcolwidths)
        else:  # Ignore col width for any 'trailing' columns
            maxcolwidths = _expand_iterable(maxcolwidths, num_cols, None)

        numparses = _expand_numparse(disable_numparse, num_cols)
        list_of_lists = _wrap_text_to_colwidths(
            list_of_lists,
            maxcolwidths,
            numparses=numparses,
            missingval=missingval,
            break_long_words=break_long_words,
            break_on_hyphens=break_on_hyphens,
        )

    if maxheadercolwidths is not None:
        num_cols = len(list_of_lists[0]) if list_of_lists else len(headers)
        if isinstance(maxheadercolwidths, int):  # Expand scalar for all columns
            maxheadercolwidths = _expand_iterable(
                maxheadercolwidths, num_cols, maxheadercolwidths
            )
        else:  # Ignore col width for any 'trailing' columns
            maxheadercolwidths = _expand_iterable(maxheadercolwidths, num_cols, None)

        numparses = _expand_numparse(disable_numparse, num_cols)
        headers = _wrap_text_to_colwidths(
            [headers],
            maxheadercolwidths,
            numparses=numparses,
            missingval=missingval,
            break_long_words=break_long_words,
            break_on_hyphens=break_on_hyphens,
        )[0]

    # empty values in the first column of RST tables should be escaped (issue #82)
    # "" should be escaped as "\\ " or ".."
    if tablefmt == "rst":
        list_of_lists, headers = _rst_escape_first_column(list_of_lists, headers)

    # PrettyTable formatting does not use any extra padding.
    # Numbers are not parsed and are treated the same as strings for alignment.
    # Check if pretty is the format being used and override the defaults so it
    # does not impact other formats.
    min_padding = MIN_PADDING
    if tablefmt == "pretty":
        min_padding = 0
        disable_numparse = True
        numalign = "center" if numalign == _DEFAULT_ALIGN else numalign
        stralign = "center" if stralign == _DEFAULT_ALIGN else stralign
    else:
        numalign = "decimal" if numalign == _DEFAULT_ALIGN else numalign
        stralign = "left" if stralign == _DEFAULT_ALIGN else stralign

    # 'colon_grid' uses colons in the line beneath the header to represent a column's
    # alignment instead of literally aligning the text differently. Hence,
    # left alignment of the data in the text output is enforced.
    if tablefmt == "colon_grid":
        colglobalalign = "left"
        headersglobalalign = "left"

    # optimization: look for ANSI control codes once,
    # enable smart width functions only if a control code is found
    #
    # convert the headers and rows into a single, tab-delimited string ensuring
    # that any bytestrings are decoded safely (i.e. errors ignored)
    plain_text = "\t".join(
        chain(
            # headers
            map(_to_str, headers),
            # rows: chain the rows together into a single iterable after mapping
            # the bytestring conversino to each cell value
            chain.from_iterable(map(_to_str, row) for row in list_of_lists),
        )
    )

    has_invisible = _ansi_codes.search(plain_text) is not None

    enable_widechars = wcwidth is not None and WIDE_CHARS_MODE
    if (
        not isinstance(tablefmt, TableFormat)
        and tablefmt in multiline_formats
        and _is_multiline(plain_text)
    ):
        tablefmt = multiline_formats.get(tablefmt, tablefmt)
        is_multiline = True
    else:
        is_multiline = False
    width_fn = _choose_width_fn(has_invisible, enable_widechars, is_multiline)

    # format rows and columns, convert numeric values to strings
    cols = list(izip_longest(*list_of_lists))
    numparses = _expand_numparse(disable_numparse, len(cols))
    coltypes = [_column_type(col, numparse=np) for col, np in zip(cols, numparses)]
    if isinstance(floatfmt, str):  # old version
        float_formats = len(cols) * [
            floatfmt
        ]  # just duplicate the string to use in each column
    else:  # if floatfmt is list, tuple etc we have one per column
        float_formats = list(floatfmt)
        if len(float_formats) < len(cols):
            float_formats.extend((len(cols) - len(float_formats)) * [_DEFAULT_FLOATFMT])
    if isinstance(intfmt, str):  # old version
        int_formats = len(cols) * [
            intfmt
        ]  # just duplicate the string to use in each column
    else:  # if intfmt is list, tuple etc we have one per column
        int_formats = list(intfmt)
        if len(int_formats) < len(cols):
            int_formats.extend((len(cols) - len(int_formats)) * [_DEFAULT_INTFMT])
    if isinstance(missingval, str):
        missing_vals = len(cols) * [missingval]
    else:
        missing_vals = list(missingval)
        if len(missing_vals) < len(cols):
            missing_vals.extend((len(cols) - len(missing_vals)) * [_DEFAULT_MISSINGVAL])
    cols = [
        [_format(v, ct, fl_fmt, int_fmt, miss_v, has_invisible) for v in c]
        for c, ct, fl_fmt, int_fmt, miss_v in zip(
            cols, coltypes, float_formats, int_formats, missing_vals
        )
    ]

    # align columns
    # first set global alignment
    if colglobalalign is not None:  # if global alignment provided
        aligns = [colglobalalign] * len(cols)
    else:  # default
        aligns = [numalign if ct in [int, float] else stralign for ct in coltypes]
    # then specific alignments
    if colalign is not None:
        assert isinstance(colalign, Iterable)
        if isinstance(colalign, str):
            warnings.warn(
                f"As a string, `colalign` is interpreted as {[c for c in colalign]}. "
                f'Did you mean `colglobalalign = "{colalign}"` or `colalign = ("{colalign}",)`?',
                stacklevel=2,
            )
        for idx, align in enumerate(colalign):
            if not idx < len(aligns):
                break
            elif align != "global":
                aligns[idx] = align
    minwidths = (
        [width_fn(h) + min_padding for h in headers] if headers else [0] * len(cols)
    )
    aligns_copy = aligns.copy()
    # Reset alignments in copy of alignments list to "left" for 'colon_grid' format,
    # which enforces left alignment in the text output of the data.
    if tablefmt == "colon_grid":
        aligns_copy = ["left"] * len(cols)
    cols = [
        _align_column(
            c,
            a,
            minw,
            has_invisible,
            enable_widechars,
            is_multiline,
            preserve_whitespace,
        )
        for c, a, minw in zip(cols, aligns_copy, minwidths)
    ]

    aligns_headers = None
    if headers:
        # align headers and add headers
        t_cols = cols or [[""]] * len(headers)
        # first set global alignment
        if headersglobalalign is not None:  # if global alignment provided
            aligns_headers = [headersglobalalign] * len(t_cols)
        else:  # default
            aligns_headers = aligns or [stralign] * len(headers)
        # then specific header alignments
        if headersalign is not None:
            assert isinstance(headersalign, Iterable)
            if isinstance(headersalign, str):
                warnings.warn(
                    f"As a string, `headersalign` is interpreted as {[c for c in headersalign]}. "
                    f'Did you mean `headersglobalalign = "{headersalign}"` '
                    f'or `headersalign = ("{headersalign}",)`?',
                    stacklevel=2,
                )
            for idx, align in enumerate(headersalign):
                hidx = headers_pad + idx
                if not hidx < len(aligns_headers):
                    break
                elif align == "same" and hidx < len(aligns):  # same as column align
                    aligns_headers[hidx] = aligns[hidx]
                elif align != "global":
                    aligns_headers[hidx] = align
        minwidths = [
            max(minw, max(width_fn(cl) for cl in c))
            for minw, c in zip(minwidths, t_cols)
        ]
        headers = [
            _align_header(h, a, minw, width_fn(h), is_multiline, width_fn)
            for h, a, minw in zip(headers, aligns_headers, minwidths)
        ]
        rows = list(zip(*cols))
    else:
        minwidths = [max(width_fn(cl) for cl in c) for c in cols]
        rows = list(zip(*cols))

    if not isinstance(tablefmt, TableFormat):
        tablefmt = _table_formats.get(tablefmt, _table_formats["simple"])

    ra_default = rowalign if isinstance(rowalign, str) else None
    rowaligns = _expand_iterable(rowalign, len(rows), ra_default)
    _reinsert_separating_lines(rows, separating_lines)

    return _format_table(
        tablefmt,
        headers,
        aligns_headers,
        rows,
        minwidths,
        aligns,
        is_multiline,
        rowaligns=rowaligns,
    )


def _expand_numparse(disable_numparse, column_count):
    """
    Return a list of bools of length `column_count` which indicates whether
    number parsing should be used on each column.
    If `disable_numparse` is a list of indices, each of those indices are False,
    and everything else is True.
    If `disable_numparse` is a bool, then the returned list is all the same.
    """
    if isinstance(disable_numparse, Iterable):
        numparses = [True] * column_count
        for index in disable_numparse:
            numparses[index] = False
        return numparses
    else:
        return [not disable_numparse] * column_count


def _expand_iterable(original, num_desired, default):
    """
    Expands the `original` argument to return a return a list of
    length `num_desired`. If `original` is shorter than `num_desired`, it will
    be padded with the value in `default`.
    If `original` is not a list to begin with (i.e. scalar value) a list of
    length `num_desired` completely populated with `default will be returned
    """
    if isinstance(original, Iterable) and not isinstance(original, str):
        return original + [default] * (num_desired - len(original))
    else:
        return [default] * num_desired


def _pad_row(cells, padding):
    if cells:
        if cells == SEPARATING_LINE:
            return SEPARATING_LINE
        pad = " " * padding
        padded_cells = [pad + cell + pad for cell in cells]
        return padded_cells
    else:
        return cells


def _build_simple_row(padded_cells, rowfmt):
    "Format row according to DataRow format without padding."
    begin, sep, end = rowfmt
    return (begin + sep.join(padded_cells) + end).rstrip()


def _build_row(padded_cells, colwidths, colaligns, rowfmt):
    "Return a string which represents a row of data cells."
    if not rowfmt:
        return None
    if callable(rowfmt):
        return rowfmt(padded_cells, colwidths, colaligns)
    else:
        return _build_simple_row(padded_cells, rowfmt)


def _append_basic_row(lines, padded_cells, colwidths, colaligns, rowfmt, rowalign=None):
    # NOTE: rowalign is ignored and exists for api compatibility with _append_multiline_row
    lines.append(_build_row(padded_cells, colwidths, colaligns, rowfmt))
    return lines


def _align_cell_veritically(text_lines, num_lines, column_width, row_alignment):
    delta_lines = num_lines - len(text_lines)
    blank = [" " * column_width]
    if row_alignment == "bottom":
        return blank * delta_lines + text_lines
    elif row_alignment == "center":
        top_delta = delta_lines // 2
        bottom_delta = delta_lines - top_delta
        return top_delta * blank + text_lines + bottom_delta * blank
    else:
        return text_lines + blank * delta_lines


def _append_multiline_row(
    lines, padded_multiline_cells, padded_widths, colaligns, rowfmt, pad, rowalign=None
):
    colwidths = [w - 2 * pad for w in padded_widths]
    cells_lines = [c.splitlines() for c in padded_multiline_cells]
    nlines = max(map(len, cells_lines))  # number of lines in the row
    # vertically pad cells where some lines are missing
    # cells_lines = [
    #     (cl + [" " * w] * (nlines - len(cl))) for cl, w in zip(cells_lines, colwidths)
    # ]

    cells_lines = [
        _align_cell_veritically(cl, nlines, w, rowalign)
        for cl, w in zip(cells_lines, colwidths)
    ]
    lines_cells = [[cl[i] for cl in cells_lines] for i in range(nlines)]
    for ln in lines_cells:
        padded_ln = _pad_row(ln, pad)
        _append_basic_row(lines, padded_ln, colwidths, colaligns, rowfmt)
    return lines


def _build_line(colwidths, colaligns, linefmt):
    "Return a string which represents a horizontal line."
    if not linefmt:
        return None
    if callable(linefmt):
        return linefmt(colwidths, colaligns)
    else:
        begin, fill, sep, end = linefmt
        cells = [fill * w for w in colwidths]
        return _build_simple_row(cells, (begin, sep, end))


def _append_line(lines, colwidths, colaligns, linefmt):
    lines.append(_build_line(colwidths, colaligns, linefmt))
    return lines


class JupyterHTMLStr(str):
    """Wrap the string with a _repr_html_ method so that Jupyter
    displays the HTML table"""

    def _repr_html_(self):
        return self

    @property
    def str(self):
        """add a .str property so that the raw string is still accessible"""
        return self


def _format_table(
    fmt, headers, headersaligns, rows, colwidths, colaligns, is_multiline, rowaligns
):
    """Produce a plain-text representation of the table."""
    lines = []
    hidden = fmt.with_header_hide if (headers and fmt.with_header_hide) else []
    pad = fmt.padding
    headerrow = fmt.headerrow

    padded_widths = [(w + 2 * pad) for w in colwidths]
    if is_multiline:
        pad_row = (
            lambda row, _: row
        )  # noqa: E731 # do it later, in _append_multiline_row
        append_row = partial(_append_multiline_row, pad=pad)
    else:
        pad_row = _pad_row
        append_row = _append_basic_row

    padded_headers = pad_row(headers, pad)

    if fmt.lineabove and "lineabove" not in hidden:
        _append_line(lines, padded_widths, colaligns, fmt.lineabove)

    if padded_headers:
        append_row(lines, padded_headers, padded_widths, headersaligns, headerrow)
        if fmt.linebelowheader and "linebelowheader" not in hidden:
            _append_line(lines, padded_widths, colaligns, fmt.linebelowheader)

    if rows and fmt.linebetweenrows and "linebetweenrows" not in hidden:
        # initial rows with a line below
        for row, ralign in zip(rows[:-1], rowaligns):
            if row != SEPARATING_LINE:
                append_row(
                    lines,
                    pad_row(row, pad),
                    padded_widths,
                    colaligns,
                    fmt.datarow,
                    rowalign=ralign,
                )
            _append_line(lines, padded_widths, colaligns, fmt.linebetweenrows)
        # the last row without a line below
        append_row(
            lines,
            pad_row(rows[-1], pad),
            padded_widths,
            colaligns,
            fmt.datarow,
            rowalign=rowaligns[-1],
        )
    else:
        separating_line = (
            fmt.linebetweenrows
            or fmt.linebelowheader
            or fmt.linebelow
            or fmt.lineabove
            or Line("", "", "", "")
        )
        for row in rows:
            # test to see if either the 1st column or the 2nd column (account for showindex) has
            # the SEPARATING_LINE flag
            if _is_separating_line(row):
                _append_line(lines, padded_widths, colaligns, separating_line)
            else:
                append_row(
                    lines, pad_row(row, pad), padded_widths, colaligns, fmt.datarow
                )

    if fmt.linebelow and "linebelow" not in hidden:
        _append_line(lines, padded_widths, colaligns, fmt.linebelow)

    if headers or rows:
        output = "\n".join(lines)
        if fmt.lineabove == _html_begin_table_without_header:
            return JupyterHTMLStr(output)
        else:
            return output
    else:  # a completely empty table
        return ""


class _CustomTextWrap(textwrap.TextWrapper):
    """A custom implementation of CPython's textwrap.TextWrapper. This supports
    both wide characters (Korea, Japanese, Chinese)  - including mixed string.
    For the most part, the `_handle_long_word` and `_wrap_chunks` functions were
    copy pasted out of the CPython baseline, and updated with our custom length
    and line appending logic.
    """

    def __init__(self, *args, **kwargs):
        self._active_codes = []
        self.max_lines = None  # For python2 compatibility
        textwrap.TextWrapper.__init__(self, *args, **kwargs)

    @staticmethod
    def _len(item):
        """Custom len that gets console column width for wide
        and non-wide characters as well as ignores color codes"""
        stripped = _strip_ansi(item)
        if wcwidth:
            return wcwidth.wcswidth(stripped)
        else:
            return len(stripped)

    def _update_lines(self, lines, new_line):
        """Adds a new line to the list of lines the text is being wrapped into
        This function will also track any ANSI color codes in this string as well
        as add any colors from previous lines order to preserve the same formatting
        as a single unwrapped string.
        """
        code_matches = [x for x in _ansi_codes.finditer(new_line)]
        color_codes = [
            code.string[code.span()[0] : code.span()[1]] for code in code_matches
        ]

        # Add color codes from earlier in the unwrapped line, and then track any new ones we add.
        new_line = "".join(self._active_codes) + new_line

        for code in color_codes:
            if code != _ansi_color_reset_code:
                self._active_codes.append(code)
            else:  # A single reset code resets everything
                self._active_codes = []

        # Always ensure each line is color terminated if any colors are
        # still active, otherwise colors will bleed into other cells on the console
        if len(self._active_codes) > 0:
            new_line = new_line + _ansi_color_reset_code

        lines.append(new_line)

    def _handle_long_word(self, reversed_chunks, cur_line, cur_len, width):
        """_handle_long_word(chunks : [string],
                             cur_line : [string],
                             cur_len : int, width : int)
        Handle a chunk of text (most likely a word, not whitespace) that
        is too long to fit in any line.
        """
        # Figure out when indent is larger than the specified width, and make
        # sure at least one character is stripped off on every pass
        if width < 1:
            space_left = 1
        else:
            space_left = width - cur_len

        # If we're allowed to break long words, then do so: put as much
        # of the next chunk onto the current line as will fit.
        if self.break_long_words and space_left > 0:
            # Tabulate Custom: Build the string up piece-by-piece in order to
            # take each charcter's width into account
            chunk = reversed_chunks[-1]
            i = 1
            # Only count printable characters, so strip_ansi first, index later.
            stripped_chunk = _strip_ansi(chunk)
            while (
                i <= len(stripped_chunk) and self._len(stripped_chunk[:i]) <= space_left
            ):
                i = i + 1
            # Consider escape codes when breaking words up
            total_escape_len = 0
            last_group = 0
            if _ansi_codes.search(chunk) is not None:
                for group, _, _, _ in _ansi_codes.findall(chunk):
                    escape_len = len(group)
                    if (
                        group
                        in chunk[last_group : i + total_escape_len + escape_len - 1]
                    ):
                        total_escape_len += escape_len
                        found = _ansi_codes.search(chunk[last_group:])
                        last_group += found.end()
            cur_line.append(chunk[: i + total_escape_len - 1])
            reversed_chunks[-1] = chunk[i + total_escape_len - 1 :]

        # Otherwise, we have to preserve the long word intact.  Only add
        # it to the current line if there's nothing already there --
        # that minimizes how much we violate the width constraint.
        elif not cur_line:
            cur_line.append(reversed_chunks.pop())

        # If we're not allowed to break long words, and there's already
        # text on the current line, do nothing.  Next time through the
        # main loop of _wrap_chunks(), we'll wind up here again, but
        # cur_len will be zero, so the next line will be entirely
        # devoted to the long word that we can't handle right now.

    def _wrap_chunks(self, chunks):
        """_wrap_chunks(chunks : [string]) -> [string]
        Wrap a sequence of text chunks and return a list of lines of
        length 'self.width' or less.  (If 'break_long_words' is false,
        some lines may be longer than this.)  Chunks correspond roughly
        to words and the whitespace between them: each chunk is
        indivisible (modulo 'break_long_words'), but a line break can
        come between any two chunks.  Chunks should not have internal
        whitespace; ie. a chunk is either all whitespace or a "word".
        Whitespace chunks will be removed from the beginning and end of
        lines, but apart from that whitespace is preserved.
        """
        lines = []
        if self.width <= 0:
            raise ValueError("invalid width %r (must be > 0)" % self.width)
        if self.max_lines is not None:
            if self.max_lines > 1:
                indent = self.subsequent_indent
            else:
                indent = self.initial_indent
            if self._len(indent) + self._len(self.placeholder.lstrip()) > self.width:
                raise ValueError("placeholder too large for max width")

        # Arrange in reverse order so items can be efficiently popped
        # from a stack of chucks.
        chunks.reverse()

        while chunks:

            # Start the list of chunks that will make up the current line.
            # cur_len is just the length of all the chunks in cur_line.
            cur_line = []
            cur_len = 0

            # Figure out which static string will prefix this line.
            if lines:
                indent = self.subsequent_indent
            else:
                indent = self.initial_indent

            # Maximum width for this line.
            width = self.width - self._len(indent)

            # First chunk on line is whitespace -- drop it, unless this
            # is the very beginning of the text (ie. no lines started yet).
            if self.drop_whitespace and chunks[-1].strip() == "" and lines:
                del chunks[-1]

            while chunks:
                chunk_len = self._len(chunks[-1])

                # Can at least squeeze this chunk onto the current line.
                if cur_len + chunk_len <= width:
                    cur_line.append(chunks.pop())
                    cur_len += chunk_len

                # Nope, this line is full.
                else:
                    break

            # The current line is full, and the next chunk is too big to
            # fit on *any* line (not just this one).
            if chunks and self._len(chunks[-1]) > width:
                self._handle_long_word(chunks, cur_line, cur_len, width)
                cur_len = sum(map(self._len, cur_line))

            # If the last chunk on this line is all whitespace, drop it.
            if self.drop_whitespace and cur_line and cur_line[-1].strip() == "":
                cur_len -= self._len(cur_line[-1])
                del cur_line[-1]

            if cur_line:
                if (
                    self.max_lines is None
                    or len(lines) + 1 < self.max_lines
                    or (
                        not chunks
                        or self.drop_whitespace
                        and len(chunks) == 1
                        and not chunks[0].strip()
                    )
                    and cur_len <= width
                ):
                    # Convert current line back to a string and store it in
                    # list of all lines (return value).
                    self._update_lines(lines, indent + "".join(cur_line))
                else:
                    while cur_line:
                        if (
                            cur_line[-1].strip()
                            and cur_len + self._len(self.placeholder) <= width
                        ):
                            cur_line.append(self.placeholder)
                            self._update_lines(lines, indent + "".join(cur_line))
                            break
                        cur_len -= self._len(cur_line[-1])
                        del cur_line[-1]
                    else:
                        if lines:
                            prev_line = lines[-1].rstrip()
                            if (
                                self._len(prev_line) + self._len(self.placeholder)
                                <= self.width
                            ):
                                lines[-1] = prev_line + self.placeholder
                                break
                        self._update_lines(lines, indent + self.placeholder.lstrip())
                    break

        return lines


def _main():
    """\
    Usage: tabulate [options] [FILE ...]

    Pretty-print tabular data.
    See also https://github.com/astanin/python-tabulate

    FILE                      a filename of the file with tabular data;
                              if "-" or missing, read data from stdin.

    Options:

    -h, --help                show this message
    -1, --header              use the first row of data as a table header
    -o FILE, --output FILE    print table to FILE (default: stdout)
    -s REGEXP, --sep REGEXP   use a custom column separator (default: whitespace)
    -F FPFMT, --float FPFMT   floating point number format (default: g)
    -I INTFMT, --int INTFMT   integer point number format (default: "")
    -f FMT, --format FMT      set output table format; supported formats:
                              plain, simple, grid, fancy_grid, pipe, orgtbl,
                              rst, mediawiki, html, latex, latex_raw,
                              latex_booktabs, latex_longtable, tsv
                              (default: simple)
    """
    import getopt

    usage = textwrap.dedent(_main.__doc__)
    try:
        opts, args = getopt.getopt(
            sys.argv[1:],
            "h1o:s:F:I:f:",
            [
                "help",
                "header",
                "output=",
                "sep=",
                "float=",
                "int=",
                "colalign=",
                "format=",
            ],
        )
    except getopt.GetoptError as e:
        print(e)
        print(usage)
        sys.exit(2)
    headers = []
    floatfmt = _DEFAULT_FLOATFMT
    intfmt = _DEFAULT_INTFMT
    colalign = None
    tablefmt = "simple"
    sep = r"\s+"
    outfile = "-"
    for opt, value in opts:
        if opt in ["-1", "--header"]:
            headers = "firstrow"
        elif opt in ["-o", "--output"]:
            outfile = value
        elif opt in ["-F", "--float"]:
            floatfmt = value
        elif opt in ["-I", "--int"]:
            intfmt = value
        elif opt in ["-C", "--colalign"]:
            colalign = value.split()
        elif opt in ["-f", "--format"]:
            if value not in tabulate_formats:
                print("%s is not a supported table format" % value)
                print(usage)
                sys.exit(3)
            tablefmt = value
        elif opt in ["-s", "--sep"]:
            sep = value
        elif opt in ["-h", "--help"]:
            print(usage)
            sys.exit(0)
    files = [sys.stdin] if not args else args
    with sys.stdout if outfile == "-" else open(outfile, "w") as out:
        for f in files:
            if f == "-":
                f = sys.stdin
            if _is_file(f):
                _pprint_file(
                    f,
                    headers=headers,
                    tablefmt=tablefmt,
                    sep=sep,
                    floatfmt=floatfmt,
                    intfmt=intfmt,
                    file=out,
                    colalign=colalign,
                )
            else:
                with open(f) as fobj:
                    _pprint_file(
                        fobj,
                        headers=headers,
                        tablefmt=tablefmt,
                        sep=sep,
                        floatfmt=floatfmt,
                        intfmt=intfmt,
                        file=out,
                        colalign=colalign,
                    )


def _pprint_file(fobject, headers, tablefmt, sep, floatfmt, intfmt, file, colalign):
    rows = fobject.readlines()
    table = [re.split(sep, r.rstrip()) for r in rows if r.strip()]
    print(
        tabulate(
            table,
            headers,
            tablefmt,
            floatfmt=floatfmt,
            intfmt=intfmt,
            colalign=colalign,
        ),
        file=file,
    )


if __name__ == "__main__":
    _main()
