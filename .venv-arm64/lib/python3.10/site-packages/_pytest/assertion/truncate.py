"""Utilities for truncating assertion output.

Current default behaviour is to truncate assertion explanations at
terminal lines, unless running with an assertions verbosity level of at least 2 or running on CI.
"""

from __future__ import annotations

from _pytest.compat import running_on_ci
from _pytest.config import Config
from _pytest.nodes import Item


DEFAULT_MAX_LINES = 8
DEFAULT_MAX_CHARS = DEFAULT_MAX_LINES * 80
USAGE_MSG = "use '-vv' to show"


def truncate_if_required(explanation: list[str], item: Item) -> list[str]:
    """Truncate this assertion explanation if the given test item is eligible."""
    should_truncate, max_lines, max_chars = _get_truncation_parameters(item)
    if should_truncate:
        return _truncate_explanation(
            explanation,
            max_lines=max_lines,
            max_chars=max_chars,
        )
    return explanation


def _get_truncation_parameters(item: Item) -> tuple[bool, int, int]:
    """Return the truncation parameters related to the given item, as (should truncate, max lines, max chars)."""
    # We do not need to truncate if one of conditions is met:
    # 1. Verbosity level is 2 or more;
    # 2. Test is being run in CI environment;
    # 3. Both truncation_limit_lines and truncation_limit_chars
    #    .ini parameters are set to 0 explicitly.
    max_lines = item.config.getini("truncation_limit_lines")
    max_lines = int(max_lines if max_lines is not None else DEFAULT_MAX_LINES)

    max_chars = item.config.getini("truncation_limit_chars")
    max_chars = int(max_chars if max_chars is not None else DEFAULT_MAX_CHARS)

    verbose = item.config.get_verbosity(Config.VERBOSITY_ASSERTIONS)

    should_truncate = verbose < 2 and not running_on_ci()
    should_truncate = should_truncate and (max_lines > 0 or max_chars > 0)

    return should_truncate, max_lines, max_chars


def _truncate_explanation(
    input_lines: list[str],
    max_lines: int,
    max_chars: int,
) -> list[str]:
    """Truncate given list of strings that makes up the assertion explanation.

    Truncates to either max_lines, or max_chars - whichever the input reaches
    first, taking the truncation explanation into account. The remaining lines
    will be replaced by a usage message.

    If max_chars=0, no truncation by character count is performed.
    If max_lines=0, no truncation by line count is performed.

    When this function is launched we know max_lines > 0 or max_chars > 0
    because _get_truncation_parameters was called first.
    """
    # The length of the truncation explanation depends on the number of lines
    # removed but is at least 68 characters:
    # The real value is
    # 64 (for the base message:
    # '...\n...Full output truncated (1 line hidden), use '-vv' to show")'
    # )
    # + 1 (for plural)
    # + int(math.log10(len(input_lines) - max_lines)) (number of hidden line, at least 1)
    # + 3 for the '...' added to the truncated line
    # But if there's more than 100 lines it's very likely that we're going to
    # truncate, so we don't need the exact value using log10.
    tolerable_max_chars = (
        max_chars + 70  # 64 + 1 (for plural) + 2 (for '99') + 3 for '...'
    )
    # The truncation explanation add two lines to the output
    if max_lines == 0 or len(input_lines) <= max_lines + 2:
        if max_chars == 0 or sum(len(s) for s in input_lines) <= tolerable_max_chars:
            return input_lines
        truncated_explanation = input_lines
    else:
        # Truncate first to max_lines, and then truncate to max_chars if necessary
        truncated_explanation = input_lines[:max_lines]
    # We reevaluate the need to truncate chars following removal of some lines
    need_to_truncate_char = (
        max_chars > 0
        and sum(len(e) for e in truncated_explanation) > tolerable_max_chars
    )
    if need_to_truncate_char:
        truncated_explanation = _truncate_by_char_count(
            truncated_explanation, max_chars
        )
    # Something was truncated, adding '...' at the end to show that
    truncated_explanation[-1] += "..."
    truncated_line_count = (
        len(input_lines) - len(truncated_explanation) + int(need_to_truncate_char)
    )
    return [
        *truncated_explanation,
        "",
        f"...Full output truncated ({truncated_line_count} line"
        f"{'' if truncated_line_count == 1 else 's'} hidden), {USAGE_MSG}",
    ]


def _truncate_by_char_count(input_lines: list[str], max_chars: int) -> list[str]:
    # Find point at which input length exceeds total allowed length
    iterated_char_count = 0
    for iterated_index, input_line in enumerate(input_lines):
        if iterated_char_count + len(input_line) > max_chars:
            break
        iterated_char_count += len(input_line)

    # Create truncated explanation with modified final line
    truncated_result = input_lines[:iterated_index]
    final_line = input_lines[iterated_index]
    if final_line:
        final_line_truncate_point = max_chars - iterated_char_count
        final_line = final_line[:final_line_truncate_point]
    truncated_result.append(final_line)
    return truncated_result
