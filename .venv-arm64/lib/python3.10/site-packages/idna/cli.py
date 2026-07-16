"""Command-line interface for the :mod:`idna` package.

Invoked via ``python -m idna``. See :func:`main` for the entry point.
"""

import argparse
import sys
from collections.abc import Iterable
from itertools import chain
from typing import IO, Optional

from . import IDNAError, decode, encode
from .core import _alabel_prefix, _unicode_dots_re
from .package_data import __version__


def _looks_like_alabel(s: str) -> bool:
    """Return True if any label in ``s`` carries the ``xn--`` ACE prefix."""
    prefix = _alabel_prefix.decode("ascii")
    return any(label.lower().startswith(prefix) for label in _unicode_dots_re.split(s))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m idna",
        description=(
            "Convert a domain name between its Unicode (U-label) and "
            "ASCII-compatible (A-label) forms. With no mode flag, the "
            "direction is chosen from the first input — if it contains "
            "an xn-- label the stream is decoded, otherwise it is "
            "encoded — and the same mode is applied to every remaining "
            "input. UTS #46 mapping is applied by default; pass "
            "--strict to disable it. When no domains are given on the "
            "command line and stdin is piped, one domain per line is "
            "read from stdin."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "-e",
        "--encode",
        dest="mode",
        action="store_const",
        const="encode",
        help="Encode the input to its ASCII A-label form.",
    )
    mode.add_argument(
        "-d",
        "--decode",
        dest="mode",
        action="store_const",
        const="decode",
        help="Decode the input from its ASCII A-label form.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Disable the default UTS #46 mapping and apply IDNA 2008 rules verbatim.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"idna {__version__}",
    )
    parser.add_argument(
        "domain",
        nargs="*",
        help="One or more domain names to convert. Omit to read from stdin.",
    )
    return parser


def _iter_stdin(stream: IO[str]) -> Iterable[str]:
    """Yield non-empty stripped lines from ``stream``, ignoring blanks."""
    for line in stream:
        stripped = line.strip()
        if stripped:
            yield stripped


def _convert_one(domain: str, mode: str, uts46: bool) -> bool:
    """Convert ``domain`` and write the result; return ``False`` on failure."""
    try:
        if mode == "decode":
            print(decode(domain, uts46=uts46))
        else:
            print(encode(domain, uts46=uts46).decode("ascii"))
    except IDNAError as err:
        print(f"idna: {mode} failed for {domain!r}: {err}", file=sys.stderr)
        return False
    return True


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point for ``python -m idna``.

    When more than one domain is supplied (via positional arguments or
    piped stdin) and no mode flag is given, the first input determines
    the direction and that mode is applied uniformly to the rest.

    :param argv: Argument list excluding the program name. Defaults to
        :data:`sys.argv` when ``None``.
    :returns: ``0`` on success, ``1`` if any conversion fails.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    uts46 = not args.strict

    if args.domain:
        domains: Iterable[str] = args.domain
    elif not sys.stdin.isatty():
        domains = _iter_stdin(sys.stdin)
    else:
        parser.error("a domain argument is required when stdin is a terminal")

    iterator = iter(domains)
    first = next(iterator, None)
    if first is None:
        return 0

    mode = args.mode or ("decode" if _looks_like_alabel(first) else "encode")

    results = [_convert_one(domain, mode, uts46) for domain in chain([first], iterator)]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
