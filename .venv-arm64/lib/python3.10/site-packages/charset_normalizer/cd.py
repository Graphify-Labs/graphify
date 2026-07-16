from __future__ import annotations

import importlib
from codecs import IncrementalDecoder
from functools import lru_cache

from .constant import (
    FREQUENCIES,
    KO_NAMES,
    LANGUAGE_SUPPORTED_COUNT,
    TOO_SMALL_SEQUENCE,
    ZH_NAMES,
    _FREQUENCIES_SET,
    _FREQUENCIES_RANK,
)
from .md import _ASCII_CHAR_INFO, _char_info, is_suspiciously_successive_range
from .models import CoherenceMatches
from .utils import (
    is_multi_byte_encoding,
    is_unicode_range_secondary,
)


def encoding_unicode_range(iana_name: str) -> list[str]:
    """
    Return associated unicode ranges in a single byte code page.
    """
    if is_multi_byte_encoding(iana_name):
        raise OSError(  # Defensive:
            "Function not supported on multi-byte code page"
        )

    decoder = importlib.import_module(f"encodings.{iana_name}").IncrementalDecoder

    p: IncrementalDecoder = decoder(errors="ignore")
    seen_ranges: dict[str, int] = {}
    character_count: int = 0

    for i in range(0x40, 0xFF):
        chunk: str = p.decode(bytes([i]))

        if chunk:
            chunk_codepoint = ord(chunk)
            character_range: str | None = (
                _ASCII_CHAR_INFO[chunk_codepoint].range
                if chunk_codepoint < 128
                else _char_info(chunk).range
            )

            if character_range is None:
                continue

            if not is_unicode_range_secondary(character_range):
                if character_range not in seen_ranges:
                    seen_ranges[character_range] = 0
                seen_ranges[character_range] += 1
                character_count += 1

    return sorted(
        [
            character_range
            for character_range in seen_ranges
            if seen_ranges[character_range] / character_count >= 0.15
        ]
    )


def unicode_range_languages(primary_range: str) -> list[str]:
    """
    Return inferred languages used with a unicode range.
    """
    languages: list[str] = []

    for language, characters in FREQUENCIES.items():
        for character in characters:
            codepoint = ord(character)
            info = (
                _ASCII_CHAR_INFO[codepoint]
                if codepoint < 128
                else _char_info(character)
            )
            if info.range == primary_range:
                languages.append(language)
                break

    return languages


@lru_cache()
def encoding_languages(iana_name: str) -> list[str]:
    """
    Single-byte encoding language association. Some code page are heavily linked to particular language(s).
    This function does the correspondence.
    """
    try:
        unicode_ranges: list[str] = encoding_unicode_range(iana_name)
    except ImportError:  # Defensive: encoding unavailable on this build.
        return []

    primary_range: str | None = None

    for specified_range in unicode_ranges:
        if "Latin" not in specified_range:
            primary_range = specified_range
            break

    if primary_range is None:
        return ["Latin Based"]

    return unicode_range_languages(primary_range)


@lru_cache()
def mb_encoding_languages(iana_name: str) -> list[str]:
    """
    Multi-byte encoding language association. Some code page are heavily linked to particular language(s).
    This function does the correspondence.
    """
    if (
        iana_name.startswith("shift_")
        or iana_name.startswith("iso2022_jp")
        or iana_name.startswith("euc_j")
        or iana_name == "cp932"
    ):
        return ["Japanese"]
    if iana_name.startswith("gb") or iana_name in ZH_NAMES:
        return ["Chinese"]
    if iana_name.startswith("iso2022_kr") or iana_name in KO_NAMES:
        return ["Korean"]

    return []


@lru_cache(maxsize=LANGUAGE_SUPPORTED_COUNT)
def get_target_features(language: str) -> tuple[bool, bool]:
    """
    Determine main aspects from a supported language if it contains accents and if is pure Latin.
    """
    target_have_accents: bool = False
    target_pure_latin: bool = True

    for character in FREQUENCIES[language]:
        codepoint = ord(character)
        info = _ASCII_CHAR_INFO[codepoint] if codepoint < 128 else _char_info(character)
        if not target_have_accents and info.accentuated:
            target_have_accents = True
        if target_pure_latin and not info.latin:
            target_pure_latin = False

    return target_have_accents, target_pure_latin


def alphabet_languages(
    characters: list[str], ignore_non_latin: bool = False
) -> list[str]:
    """
    Return associated languages associated to given characters.
    """
    languages: list[tuple[str, float]] = []

    characters_set: frozenset[str] = frozenset(characters)
    source_have_accents = False
    for character in characters:
        codepoint = ord(character)
        info = _ASCII_CHAR_INFO[codepoint] if codepoint < 128 else _char_info(character)
        if info.accentuated:
            source_have_accents = True
            break

    for language, language_characters in FREQUENCIES.items():
        target_have_accents, target_pure_latin = get_target_features(language)

        if ignore_non_latin and not target_pure_latin:
            continue

        if not target_have_accents and source_have_accents:
            continue

        character_count: int = len(language_characters)

        character_match_count: int = len(_FREQUENCIES_SET[language] & characters_set)

        ratio: float = character_match_count / character_count

        if ratio >= 0.2:
            languages.append((language, ratio))

    languages = sorted(languages, key=lambda x: x[1], reverse=True)

    return [compatible_language[0] for compatible_language in languages]


def characters_popularity_compare(
    language: str, ordered_characters: list[str]
) -> float:
    """
    Determine if a ordered characters list (by occurrence from most appearance to rarest) match a particular language.
    The result is a ratio between 0. (absolutely no correspondence) and 1. (near perfect fit).
    Beware that is function is not strict on the match in order to ease the detection. (Meaning close match is 1.)
    """
    if language not in FREQUENCIES:
        raise ValueError(f"{language} not available")  # Defensive:

    character_approved_count: int = 0
    lang_rank: dict[str, int] = _FREQUENCIES_RANK[language]

    ordered_characters_count: int = len(ordered_characters)
    target_language_characters_count: int = len(FREQUENCIES[language])

    large_alphabet: bool = target_language_characters_count > 26
    large_alphabet_threshold: float = target_language_characters_count / 3

    expected_projection_ratio: float = (
        target_language_characters_count / ordered_characters_count
    )

    # Single pass: characters present in the language vocabulary, as
    # (language rank, popularity rank) pairs. The scoring below only ever
    # needs ranks, never the characters themselves.
    common_lr: list[int] = []
    common_orr: list[int] = []
    for popularity_rank, character in enumerate(ordered_characters):
        language_rank = lang_rank.get(character)
        if language_rank is not None:
            common_lr.append(language_rank)
            common_orr.append(popularity_rank)

    for character_rank_in_language, character_rank in zip(common_lr, common_orr):
        character_rank_projection: int = int(character_rank * expected_projection_ratio)

        if (
            not large_alphabet
            and abs(character_rank_projection - character_rank_in_language) > 4
        ):
            continue

        if (
            large_alphabet
            and abs(character_rank_projection - character_rank_in_language)
            < large_alphabet_threshold
        ):
            character_approved_count += 1
            continue

        if character_rank_in_language == 0:
            # before_match_count is structurally 0 here (no pair can have a
            # smaller language rank): the historic "before <= 4" acceptance
            # always holds. (The symmetric "after_len == 0" case is
            # impossible: language ranks are strictly below the language
            # character count, hence after_len >= 1.)
            character_approved_count += 1
            continue

        after_len: int = target_language_characters_count - character_rank_in_language

        # Count how many characters appear "before" in both orderings, and
        # how many appear "at or after" in both orderings. Both counts grow
        # monotonically and the approval thresholds
        # (before / rank >= 0.4 or after / after_len >= 0.4) are known
        # upfront, expressed below as exact integer comparisons: exit as
        # soon as one is crossed.
        before_match_count: int = 0
        after_match_count: int = 0

        for lr_i, orr_i in zip(common_lr, common_orr):
            if lr_i < character_rank_in_language:
                if orr_i < character_rank:
                    before_match_count += 1
                    if 5 * before_match_count >= 2 * character_rank_in_language:
                        character_approved_count += 1
                        break
            else:
                if orr_i >= character_rank:
                    after_match_count += 1
                    if 5 * after_match_count >= 2 * after_len:
                        character_approved_count += 1
                        break

    return character_approved_count / len(ordered_characters)


def alpha_unicode_split(decoded_sequence: str) -> list[str]:
    """
    Given a decoded text sequence, return a list of str. Unicode range / alphabet separation.
    Ex. a text containing English/Latin with a bit a Hebrew will return two items in the resulting list;
    One containing the latin letters and the other hebrew.
    """
    layers: dict[str, list[str]] = {}

    # Fast path: track single-layer key to skip dict iteration for single-script text.
    single_layer_key: str | None = None
    multi_layer: bool = False

    # Cache the last character_range and its resolved layer to avoid repeated
    # is_suspiciously_successive_range calls for consecutive same-range chars.
    prev_character_range: str | None = None
    prev_layer_target: str | None = None

    for character in decoded_sequence:
        # Reuse the per-codepoint CharInfo cache: info.alpha and info.range
        # are computed with the very same str.isalpha() / unicode_range()
        # calls this loop historically made per character occurrence.
        codepoint: int = ord(character)
        if codepoint < 128:
            info = _ASCII_CHAR_INFO[codepoint]
        else:
            info = _char_info(character)

        if not info.alpha:
            continue

        character_range: str | None = info.range

        if character_range is None:
            continue

        # Fast path: same range as previous character → reuse cached layer target.
        if character_range == prev_character_range:
            if prev_layer_target is not None:
                layers[prev_layer_target].append(character)
            continue

        layer_target_range: str | None = None

        if multi_layer:
            for discovered_range in layers:
                if not is_suspiciously_successive_range(
                    discovered_range, character_range
                ):
                    layer_target_range = discovered_range
                    break
        elif single_layer_key is not None:
            if not is_suspiciously_successive_range(single_layer_key, character_range):
                layer_target_range = single_layer_key

        if layer_target_range is None:
            layer_target_range = character_range

        if layer_target_range not in layers:
            layers[layer_target_range] = []
            if single_layer_key is None:
                single_layer_key = layer_target_range
            else:
                multi_layer = True

        layers[layer_target_range].append(character)

        # Cache for next iteration
        prev_character_range = character_range
        prev_layer_target = layer_target_range

    return ["".join(chars).lower() for chars in layers.values()]


def merge_coherence_ratios(results: list[CoherenceMatches]) -> CoherenceMatches:
    """
    This function merge results previously given by the function coherence_ratio.
    The return type is the same as coherence_ratio.
    """
    per_language_ratios: dict[str, list[float]] = {}
    for result in results:
        for sub_result in result:
            language, ratio = sub_result
            if language not in per_language_ratios:
                per_language_ratios[language] = [ratio]
                continue
            per_language_ratios[language].append(ratio)

    merge = [
        (
            language,
            round(
                sum(per_language_ratios[language]) / len(per_language_ratios[language]),
                4,
            ),
        )
        for language in per_language_ratios
    ]

    return sorted(merge, key=lambda x: x[1], reverse=True)


def filter_alt_coherence_matches(results: CoherenceMatches) -> CoherenceMatches:
    """
    We shall NOT return "English—" in CoherenceMatches because it is an alternative
    of "English". This function only keeps the best match and remove the em-dash in it.
    """
    index_results: dict[str, list[float]] = dict()

    for result in results:
        language, ratio = result
        no_em_name: str = language.replace("—", "")

        if no_em_name not in index_results:
            index_results[no_em_name] = []

        index_results[no_em_name].append(ratio)

    if any(len(index_results[e]) > 1 for e in index_results):
        filtered_results: CoherenceMatches = []

        for language in index_results:
            filtered_results.append((language, max(index_results[language])))

        return filtered_results

    return results


def coherence_ratio(
    decoded_sequence: str, threshold: float = 0.1, lg_inclusion: str | None = None
) -> CoherenceMatches:
    """
    Detect ANY language that can be identified in given sequence. The sequence will be analysed by layers.
    A layer = Character extraction by alphabets/ranges.
    """

    results: list[tuple[str, float]] = []
    ignore_non_latin: bool = False

    sufficient_match_count: int = 0

    lg_inclusion_list = lg_inclusion.split(",") if lg_inclusion is not None else []
    if "Latin Based" in lg_inclusion_list:
        ignore_non_latin = True
        lg_inclusion_list.remove("Latin Based")

    for layer in alpha_unicode_split(decoded_sequence):
        # Native counting + stable sort reproduce Counter.most_common()
        # ordering exactly (ties keep first-appearance order) without the
        # interpreted Counter machinery in the compiled hot path.
        char_counts: dict[str, int] = {}
        for layer_character in layer:
            char_counts[layer_character] = char_counts.get(layer_character, 0) + 1

        character_count: int = len(layer)

        if character_count <= TOO_SMALL_SEQUENCE:
            continue

        popular_character_ordered: list[str] = [
            item[0]
            for item in sorted(
                char_counts.items(), key=lambda item: item[1], reverse=True
            )
        ]

        for language in lg_inclusion_list or alphabet_languages(
            popular_character_ordered, ignore_non_latin
        ):
            ratio: float = characters_popularity_compare(
                language, popular_character_ordered
            )

            if ratio < threshold:
                continue
            elif ratio >= 0.8:
                sufficient_match_count += 1

            results.append((language, round(ratio, 4)))

            if sufficient_match_count >= 3:
                break

    return sorted(
        filter_alt_coherence_matches(results), key=lambda x: x[1], reverse=True
    )
