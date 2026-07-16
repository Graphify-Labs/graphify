"""
prompt_toolkit
==============

Author: Jonathan Slenders

Description: prompt_toolkit is a Library for building powerful interactive
             command lines in Python.  It can be a replacement for GNU
             Readline, but it can be much more than that.

See the examples directory to learn about the usage.

Probably, to get started, you might also want to have a look at
`prompt_toolkit.shortcuts.prompt`.
"""

from __future__ import annotations

import re
from importlib import metadata

# note: this is a bit more lax than the actual pep 440 to allow for a/b/rc/dev without a number
pep440 = re.compile(
    r"^([1-9]\d*!)?(0|[1-9]\d*)(\.(0|[1-9]\d*))*((a|b|rc)(0|[1-9]\d*)?)?(\.post(0|[1-9]\d*))?(\.dev(0|[1-9]\d*)?)?$",
    re.UNICODE,
)
from .application import Application
from .formatted_text import ANSI, HTML
from .shortcuts import PromptSession, choice, print_formatted_text, prompt

# Don't forget to update in `docs/conf.py`!
__version__ = metadata.version("prompt_toolkit")

assert pep440.match(__version__)

# Version tuple.
VERSION = tuple(int(v.rstrip("abrc")) for v in __version__.split(".")[:3])


__all__ = [
    # Application.
    "Application",
    # Shortcuts.
    "prompt",
    "choice",
    "PromptSession",
    "print_formatted_text",
    # Formatted text.
    "HTML",
    "ANSI",
    # Version info.
    "__version__",
    "VERSION",
]
