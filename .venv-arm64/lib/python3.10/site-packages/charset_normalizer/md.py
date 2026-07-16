from __future__ import annotations

import sys
from functools import lru_cache
from logging import getLogger

if sys.version_info >= (3, 8):
    from typing import final
else:
    try:
        from typing_extensions import final
    except ImportError:

        def final(cls):  # type: ignore[misc,no-untyped-def]
            return cls


from .constant import (
    COMMON_CJK_CHARACTERS,
    COMMON_SAFE_ASCII_CHARACTERS,
    TRACE,
    UNICODE_SECONDARY_RANGE_KEYWORD,
    _ACCENTUATED,
    _ARABIC,
    _ARABIC_ISOLATED_FORM,
    _CJK,
    _HANGUL,
    _HIRAGANA,
    _KATAKANA,
    _LATIN,
    _THAI,
)
from .utils import (
    _character_flags,
    is_emoticon,
    is_punctuation,
    is_separator,
    is_symbol,
    remove_accent,
    unicode_range,
)

# Combined bitmask for CJK/Hangul/Katakana/Hiragana/Thai glyph detection.
_GLYPH_MASK: int = _CJK | _HANGUL | _KATAKANA | _HIRAGANA | _THAI


@final
class CharInfo:
    """Pre-computed character properties shared across all detectors."""

    __slots__ = (
        "character",
        "printable",
        "alpha",
        "upper",
        "lower",
        "space",
        "digit",
        "is_ascii",
        "case_variable",
        "flags",
        "accentuated",
        "latin",
        "is_cjk",
        "is_arabic",
        "is_glyph",
        "punct",
        "sym",
        "range",
        "sep",
        "emoticon",
        "safe",
        "common_cjk",
    )

    character: str
    printable: bool
    alpha: bool
    upper: bool
    lower: bool
    space: bool
    digit: bool
    is_ascii: bool
    case_variable: bool
    flags: int
    accentuated: bool
    latin: bool
    is_cjk: bool
    is_arabic: bool
    is_glyph: bool
    punct: bool
    sym: bool
    range: str | None
    sep: bool
    emoticon: bool
    safe: bool
    common_cjk: bool

    def __init__(self, character: str) -> None:
        """Compute all properties for *character* (built once per codepoint,
        every branch assigns every slot)."""
        self.character = character

        # ASCII fast-path: for characters with ord < 128, we can skip
        # _character_flags() entirely and derive most properties from ord.
        o: int = ord(character)
        if o < 128:
            self.is_ascii = True
            self.accentuated = False
            self.is_cjk = False
            self.is_arabic = False
            self.is_glyph = False
            # ASCII alpha: a-z (97-122) or A-Z (65-90)
            if 65 <= o <= 90:
                # Uppercase ASCII letter
                self.alpha = True
                self.upper = True
                self.lower = False
                self.space = False
                self.digit = False
                self.printable = True
                self.case_variable = True
                self.flags = _LATIN
                self.latin = True
                self.punct = False
                self.sym = False
            elif 97 <= o <= 122:
                # Lowercase ASCII letter
                self.alpha = True
                self.upper = False
                self.lower = True
                self.space = False
                self.digit = False
                self.printable = True
                self.case_variable = True
                self.flags = _LATIN
                self.latin = True
                self.punct = False
                self.sym = False
            elif 48 <= o <= 57:
                # ASCII digit 0-9
                self.alpha = False
                self.upper = False
                self.lower = False
                self.space = False
                self.digit = True
                self.printable = True
                self.case_variable = False
                self.flags = 0
                self.latin = False
                self.punct = False
                self.sym = False
            elif o == 32 or (9 <= o <= 13):
                # Space, tab, newline, etc.
                self.alpha = False
                self.upper = False
                self.lower = False
                self.space = True
                self.digit = False
                self.printable = o == 32
                self.case_variable = False
                self.flags = 0
                self.latin = False
                self.punct = False
                self.sym = False
            else:
                # Other ASCII (punctuation, symbols, control chars)
                self.printable = character.isprintable()
                self.alpha = False
                self.upper = False
                self.lower = False
                self.space = False
                self.digit = False
                self.case_variable = False
                self.flags = 0
                self.latin = False
                self.punct = is_punctuation(character) if self.printable else False
                self.sym = is_symbol(character) if self.printable else False
        else:
            # Non-ASCII path
            self.is_ascii = False
            self.printable = character.isprintable()
            self.alpha = character.isalpha()
            self.upper = character.isupper()
            self.lower = character.islower()
            self.space = character.isspace()
            self.digit = character.isdigit()
            self.case_variable = self.lower != self.upper

            # Flag-based classification (single unicodedata.name() call, lru-cached)
            flags: int
            if self.alpha:
                flags = _character_flags(character)
            else:
                flags = 0
            self.flags = flags
            self.accentuated = bool(flags & _ACCENTUATED)
            self.latin = bool(flags & _LATIN)
            self.is_cjk = bool(flags & _CJK)
            self.is_arabic = bool(flags & _ARABIC)
            self.is_glyph = bool(flags & _GLYPH_MASK)

            # Eagerly compute punct and sym (avoids property dispatch overhead
            # on 300K+ accesses in the hot loop).
            self.punct = is_punctuation(character) if self.printable else False
            self.sym = is_symbol(character) if self.printable else False

        self.range = unicode_range(character)
        self.sep = is_separator(character)
        self.emoticon = is_emoticon(character)
        self.safe = character in COMMON_SAFE_ASCII_CHARACTERS
        self.common_cjk = character in COMMON_CJK_CHARACTERS


# Per-codepoint cache of CharInfo instances
# At most UTF-8 size allocated.
@lru_cache(maxsize=None)
def _char_info(character: str) -> CharInfo:
    """Build (once per codepoint) and cache the CharInfo for *character*."""
    return CharInfo(character)


# ASCII table indexed by codepoint.
_ASCII_CHAR_INFO: list[CharInfo] = [
    CharInfo(chr(_codepoint)) for _codepoint in range(128)
]


class MessDetectorPlugin:
    """
    Base abstract class used for mess detection plugins.
    All detectors MUST extend and implement given methods.
    """

    __slots__ = ()

    def feed_info(self, character: str, info: CharInfo) -> None:
        """
        The main routine to be executed upon character.
        Insert the logic in witch the text would be considered chaotic.
        """
        raise NotImplementedError  # Defensive:

    def reset(self) -> None:  # Defensive:
        """
        Permit to reset the plugin to the initial state.
        """
        raise NotImplementedError

    @property
    def ratio(self) -> float:
        """
        Compute the chaos ratio based on what your feed() has seen.
        Must NOT be lower than 0.; No restriction gt 0.
        """
        raise NotImplementedError  # Defensive:


@final
class TooManySymbolOrPunctuationPlugin(MessDetectorPlugin):
    __slots__ = (
        "_punctuation_count",
        "_symbol_count",
        "_character_count",
        "_last_printable_char",
        "_frenzy_symbol_in_word",
    )

    def __init__(self) -> None:
        self._punctuation_count: int = 0
        self._symbol_count: int = 0
        self._character_count: int = 0

        self._last_printable_char: str | None = None
        self._frenzy_symbol_in_word: bool = False

    def feed_info(self, character: str, info: CharInfo) -> None:
        """Optimized feed using pre-computed character info."""
        self._character_count += 1

        if character != self._last_printable_char and not info.safe:
            if info.punct:
                self._punctuation_count += 1
            elif not info.digit and info.sym and not info.emoticon:
                self._symbol_count += 2

        self._last_printable_char = character

    def reset(self) -> None:  # Abstract
        self._punctuation_count = 0
        self._character_count = 0
        self._symbol_count = 0

    @property
    def ratio(self) -> float:
        if self._character_count == 0:
            return 0.0

        ratio_of_punctuation: float = (
            self._punctuation_count + self._symbol_count
        ) / self._character_count

        return ratio_of_punctuation if ratio_of_punctuation >= 0.3 else 0.0


@final
class TooManyAccentuatedPlugin(MessDetectorPlugin):
    __slots__ = ("_character_count", "_accentuated_count")

    def __init__(self) -> None:
        self._character_count: int = 0
        self._accentuated_count: int = 0

    def feed_info(self, character: str, info: CharInfo) -> None:
        """Optimized feed using pre-computed character info."""
        self._character_count += 1

        if info.accentuated:
            self._accentuated_count += 1

    def reset(self) -> None:  # Abstract
        self._character_count = 0
        self._accentuated_count = 0

    @property
    def ratio(self) -> float:
        if self._character_count < 8:
            return 0.0

        ratio_of_accentuation: float = self._accentuated_count / self._character_count
        return ratio_of_accentuation if ratio_of_accentuation >= 0.35 else 0.0


@final
class UnprintablePlugin(MessDetectorPlugin):
    __slots__ = ("_unprintable_count", "_character_count")

    def __init__(self) -> None:
        self._unprintable_count: int = 0
        self._character_count: int = 0

    def feed_info(self, character: str, info: CharInfo) -> None:
        """Optimized feed using pre-computed character info."""
        if (
            not info.space
            and not info.printable
            and character != "\x1a"
            and character != "\ufeff"
        ):
            self._unprintable_count += 1
        self._character_count += 1

    def reset(self) -> None:  # Abstract
        self._unprintable_count = 0

    @property
    def ratio(self) -> float:
        if self._character_count == 0:  # Defensive:
            return 0.0

        return (self._unprintable_count * 8) / self._character_count


@final
class SuspiciousDuplicateAccentPlugin(MessDetectorPlugin):
    __slots__ = (
        "_successive_count",
        "_character_count",
        "_last_latin_character",
        "_last_was_accentuated",
    )

    def __init__(self) -> None:
        self._successive_count: int = 0
        self._character_count: int = 0

        self._last_latin_character: str | None = None
        self._last_was_accentuated: bool = False

    def feed_info(self, character: str, info: CharInfo) -> None:
        """Optimized feed using pre-computed character info."""
        self._character_count += 1
        if (
            self._last_latin_character is not None
            and info.accentuated
            and self._last_was_accentuated
        ):
            if info.upper and self._last_latin_character.isupper():
                self._successive_count += 1
            if remove_accent(character) == remove_accent(self._last_latin_character):
                self._successive_count += 1
        self._last_latin_character = character
        self._last_was_accentuated = info.accentuated

    def reset(self) -> None:  # Abstract
        self._successive_count = 0
        self._character_count = 0
        self._last_latin_character = None
        self._last_was_accentuated = False

    @property
    def ratio(self) -> float:
        if self._character_count == 0:
            return 0.0

        return (self._successive_count * 2) / self._character_count


@final
class SuspiciousRange(MessDetectorPlugin):
    __slots__ = (
        "_suspicious_successive_range_count",
        "_character_count",
        "_last_printable_seen",
        "_last_printable_range",
    )

    def __init__(self) -> None:
        self._suspicious_successive_range_count: int = 0
        self._character_count: int = 0
        self._last_printable_seen: str | None = None
        self._last_printable_range: str | None = None

    def feed_info(self, character: str, info: CharInfo) -> None:
        """Optimized feed using pre-computed character info."""
        self._character_count += 1

        if info.space or info.punct or info.safe:
            self._last_printable_seen = None
            self._last_printable_range = None
            return

        if self._last_printable_seen is None:
            self._last_printable_seen = character
            self._last_printable_range = info.range
            return

        unicode_range_a: str | None = self._last_printable_range
        unicode_range_b: str | None = info.range

        # Identical non-None ranges can never be suspicious.
        if unicode_range_a != unicode_range_b or unicode_range_a is None:
            if is_suspiciously_successive_range(unicode_range_a, unicode_range_b):
                self._suspicious_successive_range_count += 1

        self._last_printable_seen = character
        self._last_printable_range = unicode_range_b

    def reset(self) -> None:  # Abstract
        self._character_count = 0
        self._suspicious_successive_range_count = 0
        self._last_printable_seen = None
        self._last_printable_range = None

    @property
    def ratio(self) -> float:
        if self._character_count <= 13:
            return 0.0

        ratio_of_suspicious_range_usage: float = (
            self._suspicious_successive_range_count * 2
        ) / self._character_count

        return ratio_of_suspicious_range_usage


@final
class SuperWeirdWordPlugin(MessDetectorPlugin):
    __slots__ = (
        "_word_count",
        "_bad_word_count",
        "_foreign_long_count",
        "_is_current_word_bad",
        "_foreign_long_watch",
        "_character_count",
        "_bad_character_count",
        "_buffer_length",
        "_buffer_last_char",
        "_buffer_last_char_accentuated",
        "_buffer_accent_count",
        "_buffer_glyph_count",
        "_buffer_upper_count",
        "_buffer_first_lower",
        "_buffer_has_non_ascii",
    )

    def __init__(self) -> None:
        self._word_count: int = 0
        self._bad_word_count: int = 0
        self._foreign_long_count: int = 0

        self._is_current_word_bad: bool = False
        self._foreign_long_watch: bool = False

        self._character_count: int = 0
        self._bad_character_count: int = 0

        self._buffer_length: int = 0
        self._buffer_last_char: str | None = None
        self._buffer_last_char_accentuated: bool = False
        self._buffer_accent_count: int = 0
        self._buffer_glyph_count: int = 0
        self._buffer_upper_count: int = 0
        self._buffer_first_lower: bool = False
        self._buffer_has_non_ascii: bool = False

    def feed_info(self, character: str, info: CharInfo) -> None:
        """Optimized feed using pre-computed character info."""
        if info.alpha:
            if self._buffer_length == 0:
                self._buffer_first_lower = info.lower
            self._buffer_length += 1
            self._buffer_last_char = character

            if info.upper:
                self._buffer_upper_count += 1
            if not info.is_ascii:
                self._buffer_has_non_ascii = True

            self._buffer_last_char_accentuated = info.accentuated

            if info.accentuated:
                self._buffer_accent_count += 1
            if (
                not self._foreign_long_watch
                and (not info.latin or info.accentuated)
                and not info.is_glyph
            ):
                self._foreign_long_watch = True
            if info.is_glyph:
                self._buffer_glyph_count += 1
            return
        if not self._buffer_length:
            return
        if info.space or info.punct or info.sep:
            self._word_count += 1
            buffer_length: int = self._buffer_length

            self._character_count += buffer_length

            if buffer_length >= 4:
                if self._buffer_accent_count / buffer_length >= 0.5:
                    self._is_current_word_bad = True
                elif (
                    self._buffer_last_char_accentuated
                    and self._buffer_last_char.isupper()  # type: ignore[union-attr]
                    and self._buffer_upper_count != buffer_length
                ):
                    self._foreign_long_count += 1
                    self._is_current_word_bad = True
                elif self._buffer_glyph_count == 1:
                    self._is_current_word_bad = True
                    self._foreign_long_count += 1
                elif (
                    self._buffer_has_non_ascii
                    and self._buffer_first_lower
                    and self._buffer_upper_count == buffer_length - 1
                ):
                    # Inverse capitalization detector.
                    # No natural writing produces such words.
                    # see https://github.com/jawah/charset_normalizer/issues/731
                    self._foreign_long_count += 1
                    self._is_current_word_bad = True
            if buffer_length >= 24 and self._foreign_long_watch:
                probable_camel_cased: bool = (
                    self._buffer_upper_count > 0
                    and self._buffer_upper_count / buffer_length <= 0.3
                )

                if not probable_camel_cased:
                    self._foreign_long_count += 1
                    self._is_current_word_bad = True

            if self._is_current_word_bad:
                self._bad_word_count += 1
                self._bad_character_count += buffer_length
                self._is_current_word_bad = False

            self._foreign_long_watch = False
            self._buffer_length = 0
            self._buffer_last_char = None
            self._buffer_last_char_accentuated = False
            self._buffer_accent_count = 0
            self._buffer_glyph_count = 0
            self._buffer_upper_count = 0
            self._buffer_first_lower = False
            self._buffer_has_non_ascii = False
        elif (
            character not in {"<", ">", "-", "=", "~", "|", "_"}
            and not info.digit
            and info.sym
        ):
            self._is_current_word_bad = True
            self._buffer_length += 1
            self._buffer_last_char = character
            self._buffer_last_char_accentuated = False

    def reset(self) -> None:  # Abstract
        self._buffer_length = 0
        self._buffer_last_char = None
        self._buffer_last_char_accentuated = False
        self._is_current_word_bad = False
        self._foreign_long_watch = False
        self._bad_word_count = 0
        self._word_count = 0
        self._character_count = 0
        self._bad_character_count = 0
        self._foreign_long_count = 0
        self._buffer_accent_count = 0
        self._buffer_glyph_count = 0
        self._buffer_upper_count = 0
        self._buffer_first_lower = False
        self._buffer_has_non_ascii = False

    @property
    def ratio(self) -> float:
        if self._word_count <= 10 and self._foreign_long_count == 0:
            return 0.0

        return self._bad_character_count / self._character_count


@final
class CjkUncommonPlugin(MessDetectorPlugin):
    """
    Detect messy CJK text that probably means nothing.
    """

    __slots__ = ("_character_count", "_uncommon_count")

    def __init__(self) -> None:
        self._character_count: int = 0
        self._uncommon_count: int = 0

    def feed_info(self, character: str, info: CharInfo) -> None:
        """Optimized feed using pre-computed character info."""
        self._character_count += 1

        if not info.common_cjk:
            self._uncommon_count += 1

    def reset(self) -> None:  # Abstract
        self._character_count = 0
        self._uncommon_count = 0

    @property
    def ratio(self) -> float:
        if self._character_count < 8:
            return 0.0

        uncommon_form_usage: float = self._uncommon_count / self._character_count

        # we can be pretty sure it's garbage when uncommon characters are widely
        # used. otherwise it could just be traditional chinese for example.
        return uncommon_form_usage / 10 if uncommon_form_usage > 0.5 else 0.0


@final
class ArchaicUpperLowerPlugin(MessDetectorPlugin):
    __slots__ = (
        "_buf",
        "_character_count_since_last_sep",
        "_successive_upper_lower_count",
        "_successive_upper_lower_count_final",
        "_character_count",
        "_last_alpha_seen",
        "_last_alpha_seen_upper",
        "_last_alpha_seen_lower",
        "_current_ascii_only",
    )

    def __init__(self) -> None:
        self._buf: bool = False

        self._character_count_since_last_sep: int = 0

        self._successive_upper_lower_count: int = 0
        self._successive_upper_lower_count_final: int = 0

        self._character_count: int = 0

        self._last_alpha_seen: str | None = None
        self._last_alpha_seen_upper: bool = False
        self._last_alpha_seen_lower: bool = False
        self._current_ascii_only: bool = True

    def feed_info(self, character: str, info: CharInfo) -> None:
        """Optimized feed using pre-computed character info."""
        is_concerned: bool = info.alpha and info.case_variable
        chunk_sep: bool = not is_concerned

        if chunk_sep and self._character_count_since_last_sep > 0:
            if (
                self._character_count_since_last_sep <= 64
                and not info.digit
                and not self._current_ascii_only
            ):
                self._successive_upper_lower_count_final += (
                    self._successive_upper_lower_count
                )

            self._successive_upper_lower_count = 0
            self._character_count_since_last_sep = 0
            self._last_alpha_seen = None
            self._buf = False
            self._character_count += 1
            self._current_ascii_only = True

            return

        if self._current_ascii_only and not info.is_ascii:
            self._current_ascii_only = False

        if self._last_alpha_seen is not None:
            if (info.upper and self._last_alpha_seen_lower) or (
                info.lower and self._last_alpha_seen_upper
            ):
                if self._buf:
                    self._successive_upper_lower_count += 2
                    self._buf = False
                else:
                    self._buf = True
            else:
                self._buf = False

        self._character_count += 1
        self._character_count_since_last_sep += 1
        self._last_alpha_seen = character
        self._last_alpha_seen_upper = info.upper
        self._last_alpha_seen_lower = info.lower

    def reset(self) -> None:  # Abstract
        self._character_count = 0
        self._character_count_since_last_sep = 0
        self._successive_upper_lower_count = 0
        self._successive_upper_lower_count_final = 0
        self._last_alpha_seen = None
        self._last_alpha_seen_upper = False
        self._last_alpha_seen_lower = False
        self._buf = False
        self._current_ascii_only = True

    @property
    def ratio(self) -> float:
        if self._character_count == 0:  # Defensive:
            return 0.0

        return self._successive_upper_lower_count_final / self._character_count


@final
class ArabicIsolatedFormPlugin(MessDetectorPlugin):
    __slots__ = ("_character_count", "_isolated_form_count")

    def __init__(self) -> None:
        self._character_count: int = 0
        self._isolated_form_count: int = 0

    def reset(self) -> None:  # Abstract
        self._character_count = 0
        self._isolated_form_count = 0

    def feed_info(self, character: str, info: CharInfo) -> None:
        """Optimized feed using pre-computed character info."""
        self._character_count += 1

        if info.flags & _ARABIC_ISOLATED_FORM:
            self._isolated_form_count += 1

    @property
    def ratio(self) -> float:
        if self._character_count < 8:
            return 0.0

        isolated_form_usage: float = self._isolated_form_count / self._character_count

        return isolated_form_usage


@lru_cache(maxsize=1024)
def is_suspiciously_successive_range(
    unicode_range_a: str | None, unicode_range_b: str | None
) -> bool:
    """
    Determine if two Unicode range seen next to each other can be considered as suspicious.
    """
    if unicode_range_a is None or unicode_range_b is None:
        return True

    if unicode_range_a == unicode_range_b:
        return False

    if "Latin" in unicode_range_a and "Latin" in unicode_range_b:
        return False

    if "Emoticons" in unicode_range_a or "Emoticons" in unicode_range_b:
        return False

    # Latin characters can be accompanied with a combining diacritical mark
    # eg. Vietnamese.
    if ("Latin" in unicode_range_a or "Latin" in unicode_range_b) and (
        "Combining" in unicode_range_a or "Combining" in unicode_range_b
    ):
        return False

    keywords_range_a, keywords_range_b = (
        unicode_range_a.split(" "),
        unicode_range_b.split(" "),
    )

    for el in keywords_range_a:
        if el in UNICODE_SECONDARY_RANGE_KEYWORD:
            continue
        if el in keywords_range_b:
            return False

    # Japanese Exception
    range_a_jp_chars, range_b_jp_chars = (
        unicode_range_a
        in (
            "Hiragana",
            "Katakana",
        ),
        unicode_range_b in ("Hiragana", "Katakana"),
    )
    if (range_a_jp_chars or range_b_jp_chars) and (
        "CJK" in unicode_range_a or "CJK" in unicode_range_b
    ):
        return False
    if range_a_jp_chars and range_b_jp_chars:
        return False

    if "Hangul" in unicode_range_a or "Hangul" in unicode_range_b:
        if "CJK" in unicode_range_a or "CJK" in unicode_range_b:
            return False
        if unicode_range_a == "Basic Latin" or unicode_range_b == "Basic Latin":
            return False

    # Chinese/Japanese use dedicated range for punctuation and/or separators.
    if ("CJK" in unicode_range_a or "CJK" in unicode_range_b) or (
        unicode_range_a in ["Katakana", "Hiragana"]
        and unicode_range_b in ["Katakana", "Hiragana"]
    ):
        if "Punctuation" in unicode_range_a or "Punctuation" in unicode_range_b:
            return False
        if "Forms" in unicode_range_a or "Forms" in unicode_range_b:
            return False
        if unicode_range_a == "Basic Latin" or unicode_range_b == "Basic Latin":
            return False

    return True


def mess_ratio(
    decoded_sequence: str, maximum_threshold: float = 0.2, debug: bool = False
) -> float:
    """
    Compute a mess ratio given a decoded bytes sequence. The maximum threshold does stop the computation earlier.
    """

    seq_len: int = len(decoded_sequence)

    if seq_len < 511:
        step: int = 32
    elif seq_len < 1024:
        step = 64
    else:
        step = 128

    # str.isascii() is O(1) (the flag lives in the str header). Six of the
    # nine detectors provably keep a 0.0 ratio on ASCII-only input and are
    # therefore not fed at all.
    is_pure_ascii: bool = decoded_sequence.isascii()

    # Cached per-codepoint character properties (see CharInfo). ASCII
    # characters resolve through the immutable import-time table; anything
    # else goes through the lru_cache-backed slow path.
    ascii_info = _ASCII_CHAR_INFO
    char_info = _char_info

    mean_mess_ratio: float
    info: CharInfo

    # Create each detector as a named local variable (unrolled from the generic loop).
    # This eliminates per-character iteration over the detector list and
    # per-character eligible() virtual dispatch, while keeping every plugin class
    # intact and fully readable.
    d_sp: TooManySymbolOrPunctuationPlugin = TooManySymbolOrPunctuationPlugin()
    d_ta: TooManyAccentuatedPlugin = TooManyAccentuatedPlugin()
    d_up: UnprintablePlugin = UnprintablePlugin()
    d_sda: SuspiciousDuplicateAccentPlugin = SuspiciousDuplicateAccentPlugin()
    d_sr: SuspiciousRange = SuspiciousRange()
    d_sw: SuperWeirdWordPlugin = SuperWeirdWordPlugin()
    d_cu: CjkUncommonPlugin = CjkUncommonPlugin()
    d_au: ArchaicUpperLowerPlugin = ArchaicUpperLowerPlugin()
    d_ai: ArabicIsolatedFormPlugin = ArabicIsolatedFormPlugin()

    # Local references for feed_info methods called in the hot loop.
    d_sp_feed = d_sp.feed_info
    d_ta_feed = d_ta.feed_info
    d_up_feed = d_up.feed_info
    d_sda_feed = d_sda.feed_info
    d_sr_feed = d_sr.feed_info
    d_sw_feed = d_sw.feed_info
    d_cu_feed = d_cu.feed_info
    d_au_feed = d_au.feed_info
    d_ai_feed = d_ai.feed_info

    for block_start in range(0, seq_len, step):
        for character in decoded_sequence[block_start : block_start + step]:
            # Character properties computed once per distinct codepoint
            # (shared across all plugins and all mess_ratio calls).
            # ord() doubles as the ASCII table index and, unlike
            # str.isascii(), lowers to a mypyc primitive.
            codepoint: int = ord(character)
            if codepoint < 128:
                info = ascii_info[codepoint]
            else:
                info = char_info(character)

            # Detectors with eligible() == always True
            d_up_feed(character, info)
            d_sw_feed(character, info)

            if is_pure_ascii:
                # The six remaining detectors provably stay at 0.0 (see above).
                if info.printable:
                    d_sp_feed(character, info)
                continue

            d_au_feed(character, info)

            # Detectors with eligible() == isprintable
            if info.printable:
                d_sp_feed(character, info)
                d_sr_feed(character, info)

            # Detectors with eligible() == isalpha
            if info.alpha:
                d_ta_feed(character, info)
                # SuspiciousDuplicateAccent: isalpha() and is_latin()
                if info.latin:
                    d_sda_feed(character, info)
                # CjkUncommon: is_cjk()
                if info.is_cjk:
                    d_cu_feed(character, info)
                # ArabicIsolatedForm: is_arabic()
                if info.is_arabic:
                    d_ai_feed(character, info)

        mean_mess_ratio = (
            d_sp.ratio
            + d_ta.ratio
            + d_up.ratio
            + d_sda.ratio
            + d_sr.ratio
            + d_sw.ratio
            + d_cu.ratio
            + d_au.ratio
            + d_ai.ratio
        )

        if mean_mess_ratio >= maximum_threshold:
            break
    else:
        # Flush last word buffer in SuperWeirdWordPlugin via trailing newline.
        nl_info = ascii_info[10]  # "\n"
        d_sw_feed("\n", nl_info)
        if not is_pure_ascii:
            d_au_feed("\n", nl_info)
        d_up_feed("\n", nl_info)

        mean_mess_ratio = (
            d_sp.ratio
            + d_ta.ratio
            + d_up.ratio
            + d_sda.ratio
            + d_sr.ratio
            + d_sw.ratio
            + d_cu.ratio
            + d_au.ratio
            + d_ai.ratio
        )

    if debug:  # Defensive:
        logger = getLogger("charset_normalizer")

        logger.log(
            TRACE,
            "Mess-detector extended-analysis start. "
            f"intermediary_mean_mess_ratio_calc={step} mean_mess_ratio={mean_mess_ratio} "
            f"maximum_threshold={maximum_threshold}",
        )

        if seq_len > 16:
            logger.log(TRACE, f"Starting with: {decoded_sequence[:16]}")
            logger.log(TRACE, f"Ending with: {decoded_sequence[-16::]}")

        for dt in [d_sp, d_ta, d_up, d_sda, d_sr, d_sw, d_cu, d_au, d_ai]:
            logger.log(TRACE, f"{dt.__class__}: {dt.ratio}")

    return round(mean_mess_ratio, 3)
