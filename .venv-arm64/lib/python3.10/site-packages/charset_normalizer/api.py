from __future__ import annotations

import logging
from functools import lru_cache
from os import PathLike
from typing import BinaryIO

from .cd import (
    coherence_ratio,
    encoding_languages,
    mb_encoding_languages,
    merge_coherence_ratios,
)
from .constant import (
    IANA_SUPPORTED,
    IANA_SUPPORTED_SIMILAR,
    TOO_BIG_SEQUENCE,
    TOO_SMALL_SEQUENCE,
    TRACE,
)
from .md import mess_ratio
from .models import CharsetMatch, CharsetMatches
from .utils import (
    any_specified_encoding,
    cut_sequence_chunks,
    iana_name,
    identify_sig_or_bom,
    is_multi_byte_encoding,
    should_strip_sig_or_bom,
)

logger = logging.getLogger("charset_normalizer")
explain_handler = logging.StreamHandler()
explain_handler.setFormatter(
    logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
)

# Pre-compute a reordered encoding list: multibyte first, then single-byte.
# This allows the mb_definitive_match optimization to fire earlier, skipping
# all single-byte encodings for genuine CJK content. Multibyte codecs
# hard-fail (UnicodeDecodeError) on single-byte data almost instantly, so
# testing them first costs negligible time for non-CJK files.
# Stable sort on a boolean key: multibyte (False) first, IANA order kept
# within each group.
IANA_SUPPORTED_MB_FIRST: list[str] = sorted(
    IANA_SUPPORTED, key=lambda encoding: not is_multi_byte_encoding(encoding)
)


def from_bytes(
    sequences: bytes | bytearray,
    steps: int = 5,
    chunk_size: int = 512,
    threshold: float = 0.2,
    cp_isolation: list[str] | None = None,
    cp_exclusion: list[str] | None = None,
    preemptive_behaviour: bool = True,
    explain: bool = False,
    language_threshold: float = 0.1,
    enable_fallback: bool = True,
) -> CharsetMatches:
    """
    Given a raw bytes sequence, return the best possibles charset usable to render str objects.
    If there is no results, it is a strong indicator that the source is binary/not text.
    By default, the process will extract 5 blocks of 512o each to assess the mess and coherence of a given sequence.
    And will give up a particular code page after 20% of measured mess. Those criteria are customizable at will.

    The preemptive behavior DOES NOT replace the traditional detection workflow, it prioritize a particular code page
    but never take it for granted. Can improve the performance.

    You may want to focus your attention to some code page or/and not others, use cp_isolation and cp_exclusion for that
    purpose.

    This function will strip the SIG in the payload/sequence every time except on UTF-16, UTF-32.
    By default the library does not setup any handler other than the NullHandler, if you choose to set the 'explain'
    toggle to True it will alter the logger configuration to add a StreamHandler that is suitable for debugging.
    Custom logging format and handler can be set manually.
    """

    if not isinstance(sequences, (bytearray, bytes)):
        raise TypeError(
            "Expected object of type bytes or bytearray, got: {}".format(
                type(sequences)
            )
        )

    if explain:
        previous_logger_level: int = logger.level
        logger.addHandler(explain_handler)
        logger.setLevel(TRACE)

    length: int = len(sequences)

    if length == 0:
        logger.debug("Encoding detection on empty bytes, assuming utf_8 intention.")
        if explain:  # Defensive: ensure exit path clean handler
            logger.removeHandler(explain_handler)
            logger.setLevel(previous_logger_level)
        return CharsetMatches([CharsetMatch(sequences, "utf_8", 0.0, False, [], "")])

    if cp_isolation is not None:
        logger.log(
            TRACE,
            "cp_isolation is set. use this flag for debugging purpose. "
            "limited list of encoding allowed : %s.",
            ", ".join(cp_isolation),
        )
        cp_isolation = [iana_name(cp, False) for cp in cp_isolation]
    else:
        cp_isolation = []

    if cp_exclusion is not None:
        logger.log(
            TRACE,
            "cp_exclusion is set. use this flag for debugging purpose. "
            "limited list of encoding excluded : %s.",
            ", ".join(cp_exclusion),
        )
        cp_exclusion = [iana_name(cp, False) for cp in cp_exclusion]
    else:
        cp_exclusion = []

    if length <= (chunk_size * steps):
        logger.log(
            TRACE,
            "override steps (%i) and chunk_size (%i) as content does not fit (%i byte(s) given) parameters.",
            steps,
            chunk_size,
            length,
        )
        steps = 1
        chunk_size = length

    if steps > 1 and length / steps < chunk_size:
        chunk_size = int(length / steps)

    is_too_small_sequence: bool = len(sequences) < TOO_SMALL_SEQUENCE
    is_too_large_sequence: bool = len(sequences) >= TOO_BIG_SEQUENCE

    if is_too_small_sequence:
        logger.log(
            TRACE,
            "Trying to detect encoding from a tiny portion of ({}) byte(s).".format(
                length
            ),
        )
    elif is_too_large_sequence:
        logger.log(
            TRACE,
            "Using lazy str decoding because the payload is quite large, ({}) byte(s).".format(
                length
            ),
        )

    prioritized_encodings: list[str] = []

    specified_encoding: str | None = (
        any_specified_encoding(sequences) if preemptive_behaviour else None
    )

    if specified_encoding is not None:
        prioritized_encodings.append(specified_encoding)
        logger.log(
            TRACE,
            "Detected declarative mark in sequence. Priority +1 given for %s.",
            specified_encoding,
        )

    tested: set[str] = set()
    tested_but_hard_failure: list[str] = []
    tested_but_soft_failure: list[str] = []
    soft_failure_skip: set[str] = set()
    success_fast_tracked: set[str] = set()

    # Cache for decoded payload deduplication: hash(decoded_payload) -> (mean_mess_ratio, cd_ratios_merged, passed)
    # When multiple encodings decode to the exact same string, we can skip the expensive
    # mess_ratio and coherence_ratio analysis and reuse the results from the first encoding.
    payload_result_cache: dict[int, tuple[float, list[tuple[str, float]], bool]] = {}

    # Avoid unoptimized RSS usage.
    # this cache is mostly interesting for
    # local usage. Garbage collected at the
    # end. Like it should.
    cached_mess_ratio = lru_cache(maxsize=None)(mess_ratio)
    cached_coherence_ratio = lru_cache(maxsize=None)(coherence_ratio)

    # When a definitive result (chaos=0.0 and good coherence) is found after testing
    # the prioritized encodings (ascii, utf_8), we can significantly reduce the remaining
    # work. Encodings that target completely different language families (e.g., Cyrillic
    # when the definitive match is Latin) are skipped entirely.
    # Additionally, for same-family encodings that pass chaos probing, we reuse the
    # definitive match's coherence ratios instead of recomputing them — a major savings
    # since coherence_ratio accounts for ~30% of total time on slow Latin files.
    definitive_match_found: bool = False
    definitive_target_languages: set[str] = set()
    # After the definitive match fires, we cap the number of additional same-family
    # single-byte encodings that pass chaos probing. Once we've accumulated enough
    # good candidates (N), further same-family SB encodings are unlikely to produce
    # a better best() result and just waste mess_ratio + coherence_ratio time.
    # The first encoding to trigger the definitive match is NOT counted (it's already in).
    post_definitive_sb_success_count: int = 0
    POST_DEFINITIVE_SB_CAP: int = 7

    # When a non-UTF multibyte encoding passes chaos probing with significant multibyte
    # content (decoded length < 98% of raw length), skip all remaining single-byte encodings.
    # Rationale: multi-byte decoders (CJK) have strict byte-sequence validation — if they
    # decode without error AND pass chaos probing with substantial multibyte content, the
    # data is genuinely multibyte encoded. Single-byte encodings will always decode (every
    # byte maps to something) but waste time on mess_ratio before failing.
    # The 98% threshold prevents false triggers on files that happen to have a few valid
    # multibyte pairs (e.g., cp424/_ude_1.txt where big5 decodes with 99% ratio).
    mb_definitive_match_found: bool = False

    fallback_ascii: CharsetMatch | None = None
    fallback_u8: CharsetMatch | None = None
    fallback_specified: CharsetMatch | None = None

    results: CharsetMatches = CharsetMatches()

    early_stop_results: CharsetMatches = CharsetMatches()

    sig_encoding, sig_payload = identify_sig_or_bom(sequences)

    if sig_encoding is not None:
        prioritized_encodings.append(sig_encoding)
        logger.log(
            TRACE,
            "Detected a SIG or BOM mark on first %i byte(s). Priority +1 given for %s.",
            len(sig_payload),
            sig_encoding,
        )

    prioritized_encodings.append("ascii")

    if "utf_8" not in prioritized_encodings:
        prioritized_encodings.append("utf_8")

    for encoding_iana in prioritized_encodings + IANA_SUPPORTED_MB_FIRST:
        if cp_isolation and encoding_iana not in cp_isolation:
            continue

        if cp_exclusion and encoding_iana in cp_exclusion:
            continue

        if encoding_iana in tested:
            continue

        tested.add(encoding_iana)

        decoded_payload: str | None = None
        bom_or_sig_available: bool = sig_encoding == encoding_iana
        strip_sig_or_bom: bool = bom_or_sig_available and should_strip_sig_or_bom(
            encoding_iana
        )

        if encoding_iana in {"utf_16", "utf_32"} and not bom_or_sig_available:
            logger.log(
                TRACE,
                "Encoding %s won't be tested as-is because it require a BOM. Will try some sub-encoder LE/BE.",
                encoding_iana,
            )
            continue
        if encoding_iana in {"utf_7"} and not bom_or_sig_available:
            logger.log(
                TRACE,
                "Encoding %s won't be tested as-is because detection is unreliable without BOM/SIG.",
                encoding_iana,
            )
            continue

        # Skip encodings similar to ones that already soft-failed (high mess ratio).
        # Checked BEFORE the expensive decode attempt.
        if encoding_iana in soft_failure_skip:
            logger.log(
                TRACE,
                "%s is deemed too similar to a code page that was already considered unsuited. Continuing!",
                encoding_iana,
            )
            continue

        # Skip encodings that were already fast-tracked from a similar successful encoding.
        if encoding_iana in success_fast_tracked:
            logger.log(
                TRACE,
                "Skipping %s: already fast-tracked from a similar successful encoding.",
                encoding_iana,
            )
            continue

        try:
            is_multi_byte_decoder: bool = is_multi_byte_encoding(encoding_iana)
        except (ModuleNotFoundError, ImportError):  # Defensive:
            logger.log(
                TRACE,
                "Encoding %s does not provide an IncrementalDecoder",
                encoding_iana,
            )
            continue

        # When we've already found a definitive match (chaos=0.0 with good coherence)
        # after testing the prioritized encodings, skip encodings that target
        # completely different language families. This avoids running expensive
        # mess_ratio + coherence_ratio on clearly unrelated candidates (e.g., Cyrillic
        # when the definitive match is Latin-based).
        if definitive_match_found:
            if not is_multi_byte_decoder:
                enc_languages = set(encoding_languages(encoding_iana))
            else:
                enc_languages = set(mb_encoding_languages(encoding_iana))
            if not enc_languages.intersection(definitive_target_languages):
                logger.log(
                    TRACE,
                    "Skipping %s: definitive match already found, this encoding targets different languages (%s vs %s).",
                    encoding_iana,
                    enc_languages,
                    definitive_target_languages,
                )
                continue

        # After the definitive match, cap the number of additional same-family
        # single-byte encodings that pass chaos probing. This avoids testing the
        # tail of rare, low-value same-family encodings (mac_iceland, cp860, etc.)
        # that almost never change best() but each cost ~1-2ms of mess_ratio + coherence.
        if (
            definitive_match_found
            and not is_multi_byte_decoder
            and post_definitive_sb_success_count >= POST_DEFINITIVE_SB_CAP
        ):
            logger.log(
                TRACE,
                "Skipping %s: already accumulated %d same-family results after definitive match (cap=%d).",
                encoding_iana,
                post_definitive_sb_success_count,
                POST_DEFINITIVE_SB_CAP,
            )
            continue

        # When a multibyte encoding with significant multibyte content has already
        # passed chaos probing, skip all single-byte encodings. They will either fail
        # chaos probing (wasting mess_ratio time) or produce inferior results.
        if mb_definitive_match_found and not is_multi_byte_decoder:
            logger.log(
                TRACE,
                "Skipping single-byte %s: multi-byte definitive match already found.",
                encoding_iana,
            )
            continue

        # Single-byte candidates of regular size defer the expensive whole
        # payload decode until after chunk probing: single-byte codecs are
        # stateless (1 byte == 1 char) so decoding chunk slices is provably
        # identical to slicing the decoded payload, and candidates rejected
        # by chaos probing (the common case) never pay the full decode nor
        # the payload hash.
        deferred_decoding: bool = (
            not is_multi_byte_decoder and not is_too_large_sequence
        )

        try:
            if is_too_large_sequence and not is_multi_byte_decoder:
                str(
                    (
                        sequences[: int(50e4)]
                        if not strip_sig_or_bom
                        else sequences[len(sig_payload) : int(50e4)]
                    ),
                    encoding=encoding_iana,
                )
            elif not deferred_decoding:
                # UTF-7 BOM is encoded in modified Base64 whose byte boundary
                # can overlap with the next character. Stripping raw SIG bytes
                # before decoding may leave stray bytes that decode as garbage.
                # Decode the full sequence and remove the leading BOM char instead.
                # see https://github.com/jawah/charset_normalizer/issues/718
                # and https://github.com/jawah/charset_normalizer/issues/716
                if encoding_iana == "utf_7" and bom_or_sig_available:
                    decoded_payload = str(
                        sequences,
                        encoding=encoding_iana,
                    )
                    if decoded_payload and decoded_payload[0] == "\ufeff":
                        decoded_payload = decoded_payload[1:]
                else:
                    decoded_payload = str(
                        (
                            sequences
                            if not strip_sig_or_bom
                            else sequences[len(sig_payload) :]
                        ),
                        encoding=encoding_iana,
                    )
        except (UnicodeDecodeError, LookupError) as e:
            if not isinstance(e, LookupError):
                logger.log(
                    TRACE,
                    "Code page %s does not fit given bytes sequence at ALL. %s",
                    encoding_iana,
                    str(e),
                )
            tested_but_hard_failure.append(encoding_iana)
            continue

        r_ = range(
            0 if not bom_or_sig_available else len(sig_payload),
            length,
            int(length / steps),
        )

        multi_byte_bonus: bool = (
            is_multi_byte_decoder
            and decoded_payload is not None
            and len(decoded_payload) < length
        )

        if multi_byte_bonus:
            logger.log(
                TRACE,
                "Code page %s is a multi byte encoding table and it appear that at least one character "
                "was encoded using n-bytes.",
                encoding_iana,
            )

        max_chunk_gave_up: int = int(len(r_) / 4)

        max_chunk_gave_up = max(max_chunk_gave_up, 2)
        early_stop_count: int = 0
        lazy_str_hard_failure = False

        md_chunks: list[str] = []
        md_ratios = []

        try:
            for chunk in cut_sequence_chunks(
                sequences,
                encoding_iana,
                r_,
                chunk_size,
                bom_or_sig_available,
                strip_sig_or_bom,
                sig_payload,
                is_multi_byte_decoder,
                decoded_payload,
                deferred_decoding,
            ):
                md_chunks.append(chunk)

                md_ratios.append(
                    cached_mess_ratio(
                        chunk,
                        threshold,
                        explain and 1 <= len(cp_isolation) <= 2,
                    )
                )

                if md_ratios[-1] >= threshold:
                    early_stop_count += 1

                if (early_stop_count >= max_chunk_gave_up) or (
                    bom_or_sig_available and not strip_sig_or_bom
                ):
                    break
        except (
            UnicodeDecodeError,
            LookupError,
        ) as e:  # Lazy str loading may have missed something there
            if deferred_decoding:
                # Deferred single-byte validation failed on a chunk (or the
                # codec is unavailable on this interpreter build): identical
                # outcome and bookkeeping to the eager full-decode failure.
                logger.log(
                    TRACE,
                    "Code page %s does not fit given bytes sequence at ALL. %s",
                    encoding_iana,
                    str(e),
                )
                tested_but_hard_failure.append(encoding_iana)
                continue
            logger.log(
                TRACE,
                "LazyStr Loading: After MD chunk decode, code page %s does not fit given bytes sequence at ALL. %s",
                encoding_iana,
                str(e),
            )
            early_stop_count = max_chunk_gave_up
            lazy_str_hard_failure = True

        # We might want to check the sequence again with the whole content
        # Only if initial MD tests passes
        if (
            not lazy_str_hard_failure
            and is_too_large_sequence
            and not is_multi_byte_decoder
        ):
            try:
                sequences[int(50e3) :].decode(encoding_iana, errors="strict")
            except UnicodeDecodeError as e:
                logger.log(
                    TRACE,
                    "LazyStr Loading: After final lookup, code page %s does not fit given bytes sequence at ALL. %s",
                    encoding_iana,
                    str(e),
                )
                tested_but_hard_failure.append(encoding_iana)
                continue

        mean_mess_ratio: float = sum(md_ratios) / len(md_ratios) if md_ratios else 0.0
        if mean_mess_ratio >= threshold or early_stop_count >= max_chunk_gave_up:
            tested_but_soft_failure.append(encoding_iana)
            if encoding_iana in IANA_SUPPORTED_SIMILAR:
                soft_failure_skip.update(IANA_SUPPORTED_SIMILAR[encoding_iana])
            # Cache this soft-failure so identical decoding from other encodings
            # can be skipped immediately.
            if decoded_payload is not None and not is_multi_byte_decoder:
                payload_result_cache.setdefault(
                    hash(decoded_payload), (mean_mess_ratio, [], False)
                )
            logger.log(
                TRACE,
                "%s was excluded because of initial chaos probing. Gave up %i time(s). "
                "Computed mean chaos is %f %%.",
                encoding_iana,
                early_stop_count,
                round(mean_mess_ratio * 100, ndigits=3),
            )
            # Preparing those fallbacks in case we got nothing.
            if (
                enable_fallback
                and encoding_iana
                in ["ascii", "utf_8", specified_encoding, "utf_16", "utf_32"]
                and not lazy_str_hard_failure
            ):
                # Always fully decode payload before.
                # We've missed a UnicodeDecodeError proof
                # while issuing release 3.4.8
                # see https://github.com/jawah/charset_normalizer/issues/771
                if decoded_payload is None:
                    try:
                        decoded_payload = str(
                            (
                                sequences
                                if not strip_sig_or_bom
                                else sequences[len(sig_payload) :]
                            ),
                            encoding=encoding_iana,
                        )
                    except (UnicodeDecodeError, LookupError):
                        logger.log(
                            TRACE,
                            "%s does not decode the whole payload: fallback entry withheld.",
                            encoding_iana,
                        )
                        continue
                    if is_too_large_sequence:
                        # Don't retain huge payload in RAM.
                        decoded_payload = None

                fallback_entry = CharsetMatch(
                    sequences,
                    encoding_iana,
                    threshold,
                    bom_or_sig_available,
                    [],
                    decoded_payload,
                    preemptive_declaration=specified_encoding,
                )
                if encoding_iana == specified_encoding:
                    fallback_specified = fallback_entry
                elif encoding_iana == "ascii":
                    fallback_ascii = fallback_entry
                else:
                    fallback_u8 = fallback_entry
            continue

        if deferred_decoding:
            # The candidate passed chaos probing: perform the whole payload
            # decode (validation + payload reuse) that was deferred earlier.
            try:
                decoded_payload = str(
                    (
                        sequences
                        if not strip_sig_or_bom
                        else sequences[len(sig_payload) :]
                    ),
                    encoding=encoding_iana,
                )
            except (UnicodeDecodeError, LookupError) as e:
                logger.log(
                    TRACE,
                    "Code page %s does not fit given bytes sequence at ALL. %s",
                    encoding_iana,
                    str(e),
                )
                tested_but_hard_failure.append(encoding_iana)
                continue

        # Payload-hash deduplication: if another encoding already decoded to the
        # exact same string, reuse its mess_ratio and coherence results entirely.
        # This is strictly more general than the old IANA_SUPPORTED_SIMILAR approach
        # because it catches ALL identical decoding, not just pre-mapped ones.
        if decoded_payload is not None and not is_multi_byte_decoder:
            payload_hash: int = hash(decoded_payload)
            cached = payload_result_cache.get(payload_hash)
            if cached is not None:
                cached_mess, cached_cd, cached_passed = cached
                if cached_passed:
                    # The previous encoding with identical output passed chaos probing.
                    fast_match = CharsetMatch(
                        sequences,
                        encoding_iana,
                        cached_mess,
                        bom_or_sig_available,
                        cached_cd,
                        (
                            decoded_payload
                            if (
                                not is_too_large_sequence
                                or encoding_iana
                                in [specified_encoding, "ascii", "utf_8"]
                            )
                            else None
                        ),
                        preemptive_declaration=specified_encoding,
                    )
                    results.append(fast_match)
                    success_fast_tracked.add(encoding_iana)
                    logger.log(
                        TRACE,
                        "%s fast-tracked (identical decoded payload to a prior encoding, chaos=%f %%).",
                        encoding_iana,
                        round(cached_mess * 100, ndigits=3),
                    )

                    if (
                        encoding_iana in [specified_encoding, "ascii", "utf_8"]
                        and cached_mess < 0.1
                    ):
                        if cached_mess == 0.0:
                            logger.debug(
                                "Encoding detection: %s is most likely the one.",
                                fast_match.encoding,
                            )
                            if explain:
                                logger.removeHandler(explain_handler)
                                logger.setLevel(previous_logger_level)
                            return CharsetMatches([fast_match])
                        early_stop_results.append(fast_match)

                    if (
                        len(early_stop_results)
                        and (specified_encoding is None or specified_encoding in tested)
                        and "ascii" in tested
                        and "utf_8" in tested
                    ):
                        probable_result: CharsetMatch = early_stop_results.best()  # type: ignore[assignment]
                        logger.debug(
                            "Encoding detection: %s is most likely the one.",
                            probable_result.encoding,
                        )
                        if explain:
                            logger.removeHandler(explain_handler)
                            logger.setLevel(previous_logger_level)
                        return CharsetMatches([probable_result])

                    continue
                else:
                    # The previous encoding with identical output failed chaos
                    # probing. Unreachable when the current candidate passed
                    # probing on the identical payload (deterministic ratios),
                    # kept for structural parity with the historic flow.
                    tested_but_soft_failure.append(encoding_iana)
                    logger.log(
                        TRACE,
                        "%s fast-skipped (identical decoded payload to a prior encoding that failed chaos probing).",
                        encoding_iana,
                    )
                    # Prepare fallbacks for special encodings even when skipped.
                    if enable_fallback and encoding_iana in [
                        "ascii",
                        "utf_8",
                        specified_encoding,
                        "utf_16",
                        "utf_32",
                    ]:
                        fallback_entry = CharsetMatch(
                            sequences,
                            encoding_iana,
                            threshold,
                            bom_or_sig_available,
                            [],
                            decoded_payload,
                            preemptive_declaration=specified_encoding,
                        )
                        if encoding_iana == specified_encoding:
                            fallback_specified = fallback_entry
                        elif encoding_iana == "ascii":
                            fallback_ascii = fallback_entry
                        else:
                            fallback_u8 = fallback_entry
                    continue

        logger.log(
            TRACE,
            "%s passed initial chaos probing. Mean measured chaos is %f %%",
            encoding_iana,
            round(mean_mess_ratio * 100, ndigits=3),
        )

        if not is_multi_byte_decoder:
            target_languages: list[str] = encoding_languages(encoding_iana)
        else:
            target_languages = mb_encoding_languages(encoding_iana)

        if target_languages:
            logger.log(
                TRACE,
                "{} should target any language(s) of {}".format(
                    encoding_iana, str(target_languages)
                ),
            )

        cd_ratios = []

        # Run coherence detection on all chunks. We previously tried limiting to
        # 1-2 chunks for post-definitive encodings to save time, but this caused
        # coverage regressions by producing unrepresentative coherence scores.
        # The SB cap and language-family skip optimizations provide sufficient
        # speedup without sacrificing coherence accuracy.
        if encoding_iana != "ascii":
            # We shall skip the CD when its about ASCII
            # Most of the time its not relevant to run "language-detection" on it.
            lg_inclusion: str | None = (
                ",".join(target_languages) if target_languages else None
            )

            for chunk in md_chunks:
                chunk_languages = cached_coherence_ratio(
                    chunk,
                    language_threshold,
                    lg_inclusion,
                )

                cd_ratios.append(chunk_languages)

        cd_ratios_merged = merge_coherence_ratios(cd_ratios)

        if cd_ratios_merged:
            logger.log(
                TRACE,
                "We detected language {} using {}".format(
                    cd_ratios_merged, encoding_iana
                ),
            )

        current_match = CharsetMatch(
            sequences,
            encoding_iana,
            mean_mess_ratio,
            bom_or_sig_available,
            cd_ratios_merged,
            (
                decoded_payload
                if (
                    not is_too_large_sequence
                    or encoding_iana in [specified_encoding, "ascii", "utf_8"]
                )
                else None
            ),
            preemptive_declaration=specified_encoding,
        )

        results.append(current_match)

        # Cache the successful result for payload-hash deduplication.
        if decoded_payload is not None and not is_multi_byte_decoder:
            payload_result_cache.setdefault(
                hash(decoded_payload),
                (mean_mess_ratio, cd_ratios_merged, True),
            )

        # Count post-definitive same-family SB successes for the early termination cap.
        # Only count low-mess encodings (< 2%) toward the cap. High-mess encodings are
        # marginal results that shouldn't prevent better-quality candidates from being
        # tested. For example, iso8859_4 (mess=0%) should not be skipped just because
        # 7 high-mess Latin encodings (cp1252 at 8%, etc.) were tried first.
        if (
            definitive_match_found
            and not is_multi_byte_decoder
            and mean_mess_ratio < 0.02
        ):
            post_definitive_sb_success_count += 1

        if (
            encoding_iana in [specified_encoding, "ascii", "utf_8"]
            and mean_mess_ratio < 0.1
        ):
            # If md says nothing to worry about, then... stop immediately!
            if mean_mess_ratio == 0.0:
                logger.debug(
                    "Encoding detection: %s is most likely the one.",
                    current_match.encoding,
                )
                if explain:  # Defensive: ensure exit path clean handler
                    logger.removeHandler(explain_handler)
                    logger.setLevel(previous_logger_level)
                return CharsetMatches([current_match])

            early_stop_results.append(current_match)

        if (
            len(early_stop_results)
            and (specified_encoding is None or specified_encoding in tested)
            and "ascii" in tested
            and "utf_8" in tested
        ):
            probable_result = early_stop_results.best()  # type: ignore[assignment]
            logger.debug(
                "Encoding detection: %s is most likely the one.",
                probable_result.encoding,  # type: ignore[union-attr]
            )
            if explain:  # Defensive: ensure exit path clean handler
                logger.removeHandler(explain_handler)
                logger.setLevel(previous_logger_level)

            return CharsetMatches([probable_result])

        # Once we find a result with good coherence (>= 0.5) after testing the
        # prioritized encodings (ascii, utf_8), activate "definitive mode": skip
        # encodings that target completely different language families. This avoids
        # running expensive mess_ratio + coherence_ratio on clearly unrelated
        # candidates (e.g., Cyrillic encodings when the match is Latin-based).
        # We require coherence >= 0.5 to avoid false positives (e.g., cp1251 decoding
        # Hebrew text with 0.0 chaos but wrong language detection at coherence 0.33).
        if not definitive_match_found and not is_multi_byte_decoder:
            best_coherence = (
                max((v for _, v in cd_ratios_merged), default=0.0)
                if cd_ratios_merged
                else 0.0
            )
            if best_coherence >= 0.5 and "ascii" in tested and "utf_8" in tested:
                definitive_match_found = True
                definitive_target_languages.update(target_languages)
                logger.log(
                    TRACE,
                    "Definitive match found: %s (chaos=%.3f, coherence=%.2f). Encodings targeting different language families will be skipped.",
                    encoding_iana,
                    mean_mess_ratio,
                    best_coherence,
                )

        # When a non-UTF multibyte encoding passes chaos probing with significant
        # multibyte content (decoded < 98% of raw), activate mb_definitive_match.
        # This skips all remaining single-byte encodings which would either soft-fail
        # (running expensive mess_ratio for nothing) or produce inferior results.
        if (
            not mb_definitive_match_found
            and is_multi_byte_decoder
            and multi_byte_bonus
            and decoded_payload is not None
            and len(decoded_payload) < length * 0.98
            and encoding_iana
            not in {
                "utf_8",
                "utf_8_sig",
                "utf_16",
                "utf_16_be",
                "utf_16_le",
                "utf_32",
                "utf_32_be",
                "utf_32_le",
                "utf_7",
            }
            and "ascii" in tested
            and "utf_8" in tested
        ):
            mb_definitive_match_found = True
            logger.log(
                TRACE,
                "Multi-byte definitive match: %s (chaos=%.3f, decoded=%d/%d=%.1f%%). Single-byte encodings will be skipped.",
                encoding_iana,
                mean_mess_ratio,
                len(decoded_payload),
                length,
                len(decoded_payload) / length * 100,
            )

        if encoding_iana == sig_encoding:
            logger.debug(
                "Encoding detection: %s is most likely the one as we detected a BOM or SIG within "
                "the beginning of the sequence.",
                encoding_iana,
            )
            if explain:  # Defensive: ensure exit path clean handler
                logger.removeHandler(explain_handler)
                logger.setLevel(previous_logger_level)
            return CharsetMatches([results[encoding_iana]])

    if len(results) == 0:
        if fallback_u8 or fallback_ascii or fallback_specified:
            logger.log(
                TRACE,
                "Nothing got out of the detection process. Using ASCII/UTF-8/Specified fallback.",
            )

        if fallback_specified:
            logger.debug(
                "Encoding detection: %s will be used as a fallback match",
                fallback_specified.encoding,
            )
            results.append(fallback_specified)
        elif (
            (fallback_u8 and fallback_ascii is None)
            or (
                fallback_u8
                and fallback_ascii
                and fallback_u8.fingerprint != fallback_ascii.fingerprint
            )
            or (fallback_u8 is not None)
        ):
            logger.debug("Encoding detection: utf_8 will be used as a fallback match")
            results.append(fallback_u8)
        elif fallback_ascii:
            logger.debug("Encoding detection: ascii will be used as a fallback match")
            results.append(fallback_ascii)

    if results:
        logger.debug(
            "Encoding detection: Found %s as plausible (best-candidate) for content. With %i alternatives.",
            results.best().encoding,  # type: ignore
            len(results) - 1,
        )
    else:
        logger.debug("Encoding detection: Unable to determine any suitable charset.")

    if explain:
        logger.removeHandler(explain_handler)
        logger.setLevel(previous_logger_level)

    return results


def from_fp(
    fp: BinaryIO,
    steps: int = 5,
    chunk_size: int = 512,
    threshold: float = 0.20,
    cp_isolation: list[str] | None = None,
    cp_exclusion: list[str] | None = None,
    preemptive_behaviour: bool = True,
    explain: bool = False,
    language_threshold: float = 0.1,
    enable_fallback: bool = True,
) -> CharsetMatches:
    """
    Same thing than the function from_bytes but using a file pointer that is already ready.
    Will not close the file pointer.
    """
    return from_bytes(
        fp.read(),
        steps,
        chunk_size,
        threshold,
        cp_isolation,
        cp_exclusion,
        preemptive_behaviour,
        explain,
        language_threshold,
        enable_fallback,
    )


def from_path(
    path: str | bytes | PathLike,  # type: ignore[type-arg]
    steps: int = 5,
    chunk_size: int = 512,
    threshold: float = 0.20,
    cp_isolation: list[str] | None = None,
    cp_exclusion: list[str] | None = None,
    preemptive_behaviour: bool = True,
    explain: bool = False,
    language_threshold: float = 0.1,
    enable_fallback: bool = True,
) -> CharsetMatches:
    """
    Same thing than the function from_bytes but with one extra step. Opening and reading given file path in binary mode.
    Can raise IOError.
    """
    with open(path, "rb") as fp:
        return from_fp(
            fp,
            steps,
            chunk_size,
            threshold,
            cp_isolation,
            cp_exclusion,
            preemptive_behaviour,
            explain,
            language_threshold,
            enable_fallback,
        )


def is_binary(
    fp_or_path_or_payload: PathLike | str | BinaryIO | bytes,  # type: ignore[type-arg]
    steps: int = 5,
    chunk_size: int = 512,
    threshold: float = 0.20,
    cp_isolation: list[str] | None = None,
    cp_exclusion: list[str] | None = None,
    preemptive_behaviour: bool = True,
    explain: bool = False,
    language_threshold: float = 0.1,
    enable_fallback: bool = False,
) -> bool:
    """
    Detect if the given input (file, bytes, or path) points to a binary file. aka. not a string.
    Based on the same main heuristic algorithms and default kwargs at the sole exception that fallbacks match
    are disabled to be stricter around ASCII-compatible but unlikely to be a string.
    """
    if isinstance(fp_or_path_or_payload, (str, PathLike)):
        guesses = from_path(
            fp_or_path_or_payload,
            steps=steps,
            chunk_size=chunk_size,
            threshold=threshold,
            cp_isolation=cp_isolation,
            cp_exclusion=cp_exclusion,
            preemptive_behaviour=preemptive_behaviour,
            explain=explain,
            language_threshold=language_threshold,
            enable_fallback=enable_fallback,
        )
    elif isinstance(
        fp_or_path_or_payload,
        (
            bytes,
            bytearray,
        ),
    ):
        guesses = from_bytes(
            fp_or_path_or_payload,
            steps=steps,
            chunk_size=chunk_size,
            threshold=threshold,
            cp_isolation=cp_isolation,
            cp_exclusion=cp_exclusion,
            preemptive_behaviour=preemptive_behaviour,
            explain=explain,
            language_threshold=language_threshold,
            enable_fallback=enable_fallback,
        )
    else:
        guesses = from_fp(
            fp_or_path_or_payload,
            steps=steps,
            chunk_size=chunk_size,
            threshold=threshold,
            cp_isolation=cp_isolation,
            cp_exclusion=cp_exclusion,
            preemptive_behaviour=preemptive_behaviour,
            explain=explain,
            language_threshold=language_threshold,
            enable_fallback=enable_fallback,
        )

    return not guesses
