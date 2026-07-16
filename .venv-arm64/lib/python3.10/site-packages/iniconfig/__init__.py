"""brain-dead simple parser for ini-style files.
(C) Ronny Pfannschmidt, Holger Krekel -- MIT licensed
"""

import os
from collections.abc import Callable
from collections.abc import Iterator
from collections.abc import Mapping
from typing import Final
from typing import TypeVar
from typing import overload

__all__ = ["IniConfig", "ParseError", "COMMENTCHARS", "iscommentline"]

from . import _parse
from ._parse import COMMENTCHARS
from ._parse import iscommentline
from .exceptions import ParseError

_D = TypeVar("_D")
_T = TypeVar("_T")


class SectionWrapper:
    config: Final["IniConfig"]
    name: Final[str]

    def __init__(self, config: "IniConfig", name: str) -> None:
        self.config = config
        self.name = name

    def lineof(self, name: str) -> int | None:
        return self.config.lineof(self.name, name)

    @overload
    def get(self, key: str) -> str | None: ...

    @overload
    def get(
        self,
        key: str,
        convert: Callable[[str], _T],
    ) -> _T | None: ...

    @overload
    def get(
        self,
        key: str,
        default: None,
        convert: Callable[[str], _T],
    ) -> _T | None: ...

    @overload
    def get(self, key: str, default: _D, convert: None = None) -> str | _D: ...

    @overload
    def get(
        self,
        key: str,
        default: _D,
        convert: Callable[[str], _T],
    ) -> _T | _D: ...

    # TODO: investigate possible mypy bug wrt matching the passed over data
    def get(  # type: ignore [misc]
        self,
        key: str,
        default: _D | None = None,
        convert: Callable[[str], _T] | None = None,
    ) -> _D | _T | str | None:
        return self.config.get(self.name, key, convert=convert, default=default)

    def __getitem__(self, key: str) -> str:
        return self.config.sections[self.name][key]

    def __iter__(self) -> Iterator[str]:
        section: Mapping[str, str] = self.config.sections.get(self.name, {})

        def lineof(key: str) -> int:
            return self.config.lineof(self.name, key)  # type: ignore[return-value]

        yield from sorted(section, key=lineof)

    def items(self) -> Iterator[tuple[str, str]]:
        for name in self:
            yield name, self[name]


class IniConfig:
    path: Final[str]
    sections: Final[Mapping[str, Mapping[str, str]]]
    _sources: Final[Mapping[tuple[str, str | None], int]]

    def __init__(
        self,
        path: str | os.PathLike[str],
        data: str | None = None,
        encoding: str = "utf-8",
        *,
        _sections: Mapping[str, Mapping[str, str]] | None = None,
        _sources: Mapping[tuple[str, str | None], int] | None = None,
    ) -> None:
        self.path = os.fspath(path)

        # Determine sections and sources
        if _sections is not None and _sources is not None:
            # Use provided pre-parsed data (called from parse())
            sections_data = _sections
            sources = _sources
        else:
            # Parse the data (backward compatible path)
            if data is None:
                with open(self.path, encoding=encoding) as fp:
                    data = fp.read()

            # Use old behavior (no stripping) for backward compatibility
            sections_data, sources = _parse.parse_ini_data(
                self.path, data, strip_inline_comments=False
            )

        # Assign once to Final attributes
        self._sources = sources
        self.sections = sections_data

    @classmethod
    def parse(
        cls,
        path: str | os.PathLike[str],
        data: str | None = None,
        encoding: str = "utf-8",
        *,
        strip_inline_comments: bool = True,
        strip_section_whitespace: bool = False,
    ) -> "IniConfig":
        """Parse an INI file.

        Args:
            path: Path to the INI file (used for error messages)
            data: Optional INI content as string. If None, reads from path.
            encoding: Encoding to use when reading the file (default: utf-8)
            strip_inline_comments: Whether to strip inline comments from values
                (default: True). When True, comments starting with # or ; are
                removed from values, matching the behavior for section comments.
            strip_section_whitespace: Whether to strip whitespace from section and key names
                (default: False). When True, strips Unicode whitespace from section and key names,
                addressing issue #4. When False, preserves existing behavior for backward compatibility.

        Returns:
            IniConfig instance with parsed configuration

        Example:
            # With comment stripping (default):
            config = IniConfig.parse("setup.cfg")
            # value = "foo" instead of "foo # comment"

            # Without comment stripping (old behavior):
            config = IniConfig.parse("setup.cfg", strip_inline_comments=False)
            # value = "foo # comment"

            # With section name stripping (opt-in for issue #4):
            config = IniConfig.parse("setup.cfg", strip_section_whitespace=True)
            # section names and keys have Unicode whitespace stripped
        """
        fspath = os.fspath(path)

        if data is None:
            with open(fspath, encoding=encoding) as fp:
                data = fp.read()

        sections_data, sources = _parse.parse_ini_data(
            fspath,
            data,
            strip_inline_comments=strip_inline_comments,
            strip_section_whitespace=strip_section_whitespace,
        )

        # Call constructor with pre-parsed sections and sources
        return cls(path=fspath, _sections=sections_data, _sources=sources)

    def lineof(self, section: str, name: str | None = None) -> int | None:
        lineno = self._sources.get((section, name))
        return None if lineno is None else lineno + 1

    @overload
    def get(
        self,
        section: str,
        name: str,
    ) -> str | None: ...

    @overload
    def get(
        self,
        section: str,
        name: str,
        convert: Callable[[str], _T],
    ) -> _T | None: ...

    @overload
    def get(
        self,
        section: str,
        name: str,
        default: None,
        convert: Callable[[str], _T],
    ) -> _T | None: ...

    @overload
    def get(
        self, section: str, name: str, default: _D, convert: None = None
    ) -> str | _D: ...

    @overload
    def get(
        self,
        section: str,
        name: str,
        default: _D,
        convert: Callable[[str], _T],
    ) -> _T | _D: ...

    def get(  # type: ignore
        self,
        section: str,
        name: str,
        default: _D | None = None,
        convert: Callable[[str], _T] | None = None,
    ) -> _D | _T | str | None:
        try:
            value: str = self.sections[section][name]
        except KeyError:
            return default
        else:
            if convert is not None:
                return convert(value)
            else:
                return value

    def __getitem__(self, name: str) -> SectionWrapper:
        if name not in self.sections:
            raise KeyError(name)
        return SectionWrapper(self, name)

    def __iter__(self) -> Iterator[SectionWrapper]:
        for name in sorted(self.sections, key=self.lineof):  # type: ignore
            yield SectionWrapper(self, name)

    def __contains__(self, arg: str) -> bool:
        return arg in self.sections
