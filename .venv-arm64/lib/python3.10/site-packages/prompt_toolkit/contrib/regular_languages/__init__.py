r"""
Tool for expressing the grammar of an input as a regular language.
==================================================================

The grammar for the input of many simple command line interfaces can be
expressed by a regular language. Examples are PDB (the Python debugger); a
simple (bash-like) shell with "pwd", "cd", "cat" and "ls" commands; arguments
that you can pass to an executable; etc. It is possible to use regular
expressions for validation and parsing of such a grammar. (More about regular
languages: http://en.wikipedia.org/wiki/Regular_language)

Example
-------

Let's take the pwd/cd/cat/ls example. We want to have a shell that accepts
these three commands. "cd" is followed by a quoted directory name and "cat" is
followed by a quoted file name. (We allow quotes inside the filename when
they're escaped with a backslash.) We could define the grammar using the
following regular expression::

    grammar = \s* (
        pwd |
        ls |
        (cd  \s+ " ([^"]|\.)+ ") |
        (cat \s+ " ([^"]|\.)+ ")
    ) \s*


What can we do with this grammar?
---------------------------------

- Syntax highlighting: We could use this for instance to give file names
                       different color.
- Parse the result: .. We can extract the file names and commands by using a
                       regular expression with named groups.
- Input validation: .. Don't accept anything that does not match this grammar.
                       When combined with a parser, we can also recursively do
                       filename validation (and accept only existing files.)
- Autocompletion: .... Each part of the grammar can have its own autocompleter.
                       "cat" has to be completed using file names, while "cd"
                       has to be completed using directory names.

How does it work?
-----------------

As a user of this library, you have to define the grammar of the input as a
regular expression. The parts of this grammar where autocompletion, validation
or any other processing is required need to be marked using a regex named
group. Like ``(?P<varname>...)`` for instance.

When the input is processed for validation (for instance), the regex will
execute, the named group is captured, and the validator associated with this
named group will test the captured string.

There is one tricky bit:

    Often we operate on incomplete input (this is by definition the case for
    autocompletion) and we have to decide for the cursor position in which
    possible state the grammar it could be and in which way variables could be
    matched up to that point.

To solve this problem, the compiler takes the original regular expression and
translates it into a set of other regular expressions which each match certain
prefixes of the original regular expression. We generate one prefix regular
expression for every named variable (with this variable being the end of that
expression).


TODO: some examples of:
    - How to create a highlighter from this grammar.
    - How to create a validator from this grammar.
    - How to create an autocompleter from this grammar.
    - How to create a parser from this grammar.
"""

from __future__ import annotations

from .compiler import compile

__all__ = ["compile"]
