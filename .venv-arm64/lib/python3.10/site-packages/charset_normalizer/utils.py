from __future__ import annotations

import importlib
import logging
import unicodedata
from bisect import bisect_right
from codecs import IncrementalDecoder
from encodings.aliases import aliases
from functools import lru_cache
from re import findall
from typing import Generator

from .constant import (
    ENCODING_MARKS,
    IANA_SUPPORTED_SIMILAR,
    RE_POSSIBLE_ENCODING_INDICATION,
    UNICODE_RANGES_COMBINED,
    _SECONDARY_RANGE_NAMES,
    UTF8_MAXIMAL_ALLOCATION,
    COMMON_CJK_CHARACTERS,
    _LATIN,
    _CJK,
    _HANGUL,
    _KATAKANA,
    _HIRAGANA,
    _THAI,
    _ARABIC,
    _ARABIC_ISOLATED_FORM,
    _ACCENT_KEYWORDS,
    _ACCENTUATED,
)


def _character_flags(character: str) -> int:
    """Compute all name-based classification flags with a single unicodedata.name() call."""
    try:
        desc: str = unicodedata.name(character)
    except ValueError:
        return 0

    flags: int = 0

    if "LATIN" in desc:
        flags |= _LATIN
    if "CJK" in desc:
        flags |= _CJK
    if "HANGUL" in desc:
        flags |= _HANGUL
    if "KATAKANA" in desc:
        flags |= _KATAKANA
    if "HIRAGANA" in desc:
        flags |= _HIRAGANA
    if "THAI" in desc:
        flags |= _THAI
    if "ARABIC" in desc:
        flags |= _ARABIC
        if "ISOLATED FORM" in desc:
            flags |= _ARABIC_ISOLATED_FORM

    for kw in _ACCENT_KEYWORDS:
        if kw in desc:
            flags |= _ACCENTUATED
            break

    return flags


def is_accentuated(character: str) -> bool:
    return bool(_character_flags(character) & _ACCENTUATED)


@lru_cache(maxsize=UTF8_MAXIMAL_ALLOCATION)
def remove_accent(character: str) -> str:
    decomposed: str = unicodedata.decomposition(character)
    if not decomposed:
        return character

    codes: list[str] = decomposed.split(" ")

    return chr(int(codes[0], 16))


# Pre-built sorted lookup table for O(log n) binary search in unicode_range().
# Each entry is (range_start, range_end_exclusive, range_name).
_UNICODE_RANGES_SORTED: list[tuple[int, int, str]] = sorted(
    (ord_range.start, ord_range.stop, name)
    for name, ord_range in UNICODE_RANGES_COMBINED.items()
)
_UNICODE_RANGE_STARTS: list[int] = [e[0] for e in _UNICODE_RANGES_SORTED]


def unicode_range(character: str) -> str | None:
    """
    Retrieve the Unicode range official name from a single character.
    """
    character_ord: int = ord(character)

    # Binary search: find the rightmost range whose start <= character_ord
    idx = bisect_right(_UNICODE_RANGE_STARTS, character_ord) - 1
    if idx >= 0:
        start, stop, name = _UNICODE_RANGES_SORTED[idx]
        if character_ord < stop:
            return name

    return None


def is_latin(character: str) -> bool:
    return bool(_character_flags(character) & _LATIN)


def is_punctuation(character: str) -> bool:
    character_category: str = unicodedata.category(character)

    if "P" in character_category:
        return True

    character_range: str | None = unicode_range(character)

    if character_range is None:
        return False

    return "Punctuation" in character_range


def is_symbol(character: str) -> bool:
    character_category: str = unicodedata.category(character)

    if "S" in character_category or "N" in character_category:
        return True

    character_range: str | None = unicode_range(character)

    if character_range is None:
        return False

    return "Forms" in character_range and character_category != "Lo"


def is_emoticon(character: str) -> bool:
    character_range: str | None = unicode_range(character)

    if character_range is None:
        return False

    return "Emoticons" in character_range or "Pictographs" in character_range


def is_separator(character: str) -> bool:
    if character.isspace() or character in {"｜", "+", "<", ">"}:
        return True

    character_category: str = unicodedata.category(character)

    return "Z" in character_category or character_category in {"Po", "Pd", "Pc"}


@lru_cache(maxsize=UTF8_MAXIMAL_ALLOCATION)
def is_case_variable(character: str) -> bool:
    return character.islower() != character.isupper()


@lru_cache(maxsize=UTF8_MAXIMAL_ALLOCATION)
def is_cjk(character: str) -> bool:
    return bool(_character_flags(character) & _CJK)


@lru_cache(maxsize=UTF8_MAXIMAL_ALLOCATION)
def is_hiragana(character: str) -> bool:
    return bool(_character_flags(character) & _HIRAGANA)


@lru_cache(maxsize=UTF8_MAXIMAL_ALLOCATION)
def is_katakana(character: str) -> bool:
    return bool(_character_flags(character) & _KATAKANA)


@lru_cache(maxsize=UTF8_MAXIMAL_ALLOCATION)
def is_hangul(character: str) -> bool:
    return bool(_character_flags(character) & _HANGUL)


@lru_cache(maxsize=UTF8_MAXIMAL_ALLOCATION)
def is_thai(character: str) -> bool:
    return bool(_character_flags(character) & _THAI)


@lru_cache(maxsize=UTF8_MAXIMAL_ALLOCATION)
def is_arabic(character: str) -> bool:
    return bool(_character_flags(character) & _ARABIC)


@lru_cache(maxsize=UTF8_MAXIMAL_ALLOCATION)
def is_arabic_isolated_form(character: str) -> bool:
    return bool(_character_flags(character) & _ARABIC_ISOLATED_FORM)


@lru_cache(maxsize=UTF8_MAXIMAL_ALLOCATION)
def is_cjk_uncommon(character: str) -> bool:
    return character not in COMMON_CJK_CHARACTERS


def is_unicode_range_secondary(range_name: str) -> bool:
    return range_name in _SECONDARY_RANGE_NAMES


@lru_cache(maxsize=UTF8_MAXIMAL_ALLOCATION)
def is_unprintable(character: str) -> bool:
    return (
        not character.isspace()  # includes \n \t \r \v
        and not character.isprintable()
        and character != "\x1a"  # Why? Its the ASCII substitute character.
        and character != "\ufeff"  # bug discovered in Python,
        # Zero Width No-Break Space located in 	Arabic Presentation Forms-B, Unicode 1.1 not acknowledged as space.
    )


def any_specified_encoding(
    sequence: bytes | bytearray, search_zone: int = 8192
) -> str | None:
    """
    Extract using ASCII-only decoder any specified encoding in the first n-bytes.
    """
    if not isinstance(sequence, (bytes, bytearray)):
        raise TypeError

    seq_len: int = len(sequence)

    decoded_zone: str = sequence[: min(seq_len, search_zone)].decode(
        "ascii", errors="ignore"
    )

    # Cheap literal pre-filter.
    lowered_zone: str = decoded_zone.lower()
    if "coding" not in lowered_zone and "charset" not in lowered_zone:
        return None

    results: list[str] = findall(
        RE_POSSIBLE_ENCODING_INDICATION,
        decoded_zone,
    )

    if len(results) == 0:
        return None

    for specified_encoding in results:
        specified_encoding = specified_encoding.lower().replace("-", "_")

        encoding_alias: str
        encoding_iana: str

        for encoding_alias, encoding_iana in aliases.items():
            if encoding_alias == specified_encoding:
                return encoding_iana
            if encoding_iana == specified_encoding:
                return encoding_iana

    return None


@lru_cache(maxsize=128)
def is_multi_byte_encoding(name: str) -> bool:
    """
    Verify is a specific encoding is a multi byte one based on it IANA name
    """
    if name in {
        "utf_8",
        "utf_8_sig",
        "utf_16",
        "utf_16_be",
        "utf_16_le",
        "utf_32",
        "utf_32_le",
        "utf_32_be",
        "utf_7",
    }:
        return True

    # Besides the Unicode family above, every multibyte codec shipped with
    # Python is implemented by _multibytecodec through exactly one of the six
    # cjkcodecs providers below. Probing those providers directly (getcodec)
    # classifies a name without importing its "encodings.<name>" module:
    # classifying the whole IANA_SUPPORTED list would otherwise import many
    # modules and dominate "import charset_normalizer" wall time.
    # see https://github.com/jawah/charset_normalizer/issues/742
    for provider in (
        "_codecs_cn",
        "_codecs_hk",
        "_codecs_iso2022",
        "_codecs_jp",
        "_codecs_kr",
        "_codecs_tw",
    ):
        try:
            importlib.import_module(provider).getcodec(name)  # type: ignore[attr-defined]
        except (ImportError, AttributeError, LookupError):  # Defensive: edge cases
            continue
        return True

    return False


def identify_sig_or_bom(sequence: bytes | bytearray) -> tuple[str | None, bytes]:
    """
    Identify and extract SIG/BOM in given sequence.
    """

    for iana_encoding in ENCODING_MARKS:
        marks: bytes | list[bytes] = ENCODING_MARKS[iana_encoding]

        if isinstance(marks, bytes):
            marks = [marks]

        for mark in marks:
            if sequence.startswith(mark):
                return iana_encoding, mark

    return None, b""


def should_strip_sig_or_bom(iana_encoding: str) -> bool:
    return iana_encoding not in {"utf_16", "utf_32"}


def iana_name(cp_name: str, strict: bool = True) -> str:
    """Returns the Python normalized encoding name (Not the IANA official name)."""
    cp_name = cp_name.lower().replace("-", "_")

    encoding_alias: str
    encoding_iana: str

    for encoding_alias, encoding_iana in aliases.items():
        if cp_name in [encoding_alias, encoding_iana]:
            return encoding_iana

    if strict:
        raise ValueError(f"Unable to retrieve IANA for '{cp_name}'")

    return cp_name


def cp_similarity(iana_name_a: str, iana_name_b: str) -> float:
    if is_multi_byte_encoding(iana_name_a) or is_multi_byte_encoding(iana_name_b):
        return 0.0

    decoder_a = importlib.import_module(f"encodings.{iana_name_a}").IncrementalDecoder
    decoder_b = importlib.import_module(f"encodings.{iana_name_b}").IncrementalDecoder

    id_a: IncrementalDecoder = decoder_a(errors="ignore")
    id_b: IncrementalDecoder = decoder_b(errors="ignore")

    character_match_count: int = 0

    for i in range(256):
        to_be_decoded: bytes = bytes([i])
        if id_a.decode(to_be_decoded) == id_b.decode(to_be_decoded):
            character_match_count += 1

    return character_match_count / 256


def is_cp_similar(iana_name_a: str, iana_name_b: str) -> bool:
    """
    Determine if two code page are at least 80% similar. IANA_SUPPORTED_SIMILAR dict was generated using
    the function cp_similarity.
    """
    return (
        iana_name_a in IANA_SUPPORTED_SIMILAR
        and iana_name_b in IANA_SUPPORTED_SIMILAR[iana_name_a]
    )


def set_logging_handler(
    name: str = "charset_normalizer",
    level: int = logging.INFO,
    format_string: str = "%(asctime)s | %(levelname)s | %(message)s",
) -> None:
    logger = logging.getLogger(name)
    logger.setLevel(level)

    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(format_string))
    logger.addHandler(handler)


def cut_sequence_chunks(
    sequences: bytes | bytearray,
    encoding_iana: str,
    offsets: range,
    chunk_size: int,
    bom_or_sig_available: bool,
    strip_sig_or_bom: bool,
    sig_payload: bytes,
    is_multi_byte_decoder: bool,
    decoded_payload: str | None = None,
    deferred_decoding: bool = False,
) -> Generator[str, None, None]:
    if decoded_payload and not is_multi_byte_decoder:
        for i in offsets:
            chunk = decoded_payload[i : i + chunk_size]
            if not chunk:
                break
            yield chunk
    elif deferred_decoding:
        # Deferred single-byte probing: the whole payload is not decoded
        # yet. Single-byte codecs are stateless (1 byte == 1 char), hence
        # decode(base)[i:j] == decode(base[i:j]): slicing the raw bytes
        # yields exactly the chunks the branch above would have produced,
        # short trailing chunks included, and raises UnicodeDecodeError on
        # invalid bytes just like the whole-payload decode would.
        base_bytes = (
            sequences if not strip_sig_or_bom else sequences[len(sig_payload) :]
        )
        for i in offsets:
            cut_sequence = base_bytes[i : i + chunk_size]
            if not cut_sequence:
                break
            yield str(cut_sequence, encoding_iana)
    else:
        for i in offsets:
            chunk_end = i + chunk_size
            if chunk_end > len(sequences) + 8:
                continue

            cut_sequence = sequences[i : i + chunk_size]

            if bom_or_sig_available and not strip_sig_or_bom:
                cut_sequence = sig_payload + cut_sequence

            chunk = cut_sequence.decode(
                encoding_iana,
                errors="ignore" if is_multi_byte_decoder else "strict",
            )

            # multi-byte bad cutting detector and adjustment
            # not the cleanest way to perform that fix but clever enough for now.
            if is_multi_byte_decoder and i > 0:
                chunk_partial_size_chk: int = min(chunk_size, 16)

                if (
                    decoded_payload
                    and chunk[:chunk_partial_size_chk] not in decoded_payload
                ):
                    for j in range(i, i - 4, -1):
                        cut_sequence = sequences[j:chunk_end]

                        if bom_or_sig_available and not strip_sig_or_bom:
                            cut_sequence = sig_payload + cut_sequence

                        chunk = cut_sequence.decode(encoding_iana, errors="ignore")

                        if chunk[:chunk_partial_size_chk] in decoded_payload:
                            break

            yield chunk
