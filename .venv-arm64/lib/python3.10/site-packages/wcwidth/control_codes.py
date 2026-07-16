"""
Control character sets for terminal handling.

This module provides the control character sets used by the width() function to handle terminal
control characters.
"""

# Illegal C0/C1 control characters.
# These raise ValueError in 'strict' mode.
ILLEGAL_CTRL = frozenset(
    chr(c) for c in (
        list(range(0x01, 0x07)) +    # SOH, STX, ETX (^C), EOT (^D), ENQ, ACK
        list(range(0x10, 0x1b)) +    # DLE through SUB (^Z)
        list(range(0x1c, 0x20)) +    # FS, GS, RS, US
        [0x7f] +                      # DEL
        list(range(0x80, 0xa0))       # C1 control characters
    )
)

# Vertical movement control characters.
# These raise ValueError in 'strict' mode (indeterminate horizontal position).
VERTICAL_CTRL = frozenset({
    '\x0a',  # LF (line feed)
    '\x0b',  # VT (vertical tab)
    '\x0c',  # FF (form feed)
})

# Horizontal movement control characters.
# These affect cursor position and are tracked in 'strict' and 'parse' modes.
HORIZONTAL_CTRL = frozenset({
    '\x08',  # BS (backspace) - cursor left 1
    '\x09',  # HT (horizontal tab) - advance to next tab stop
    '\x0d',  # CR (carriage return) - cursor to column 0
})

# Terminal-valid zero-width control characters.
# These are allowed in all modes (zero-width, no movement).
ZERO_WIDTH_CTRL = frozenset({
    '\x00',  # NUL
    '\x07',  # BEL (bell)
    '\x0e',  # SO (shift out)
    '\x0f',  # SI (shift in)
})

# All control characters that need special handling (not regular printable).
ALL_CTRL = ILLEGAL_CTRL | VERTICAL_CTRL | HORIZONTAL_CTRL | ZERO_WIDTH_CTRL | {'\x1b'}
