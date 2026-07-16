"""
Mappings from VT100 (ANSI) escape sequences to the corresponding prompt_toolkit
keys.

We are not using the terminfo/termcap databases to detect the ANSI escape
sequences for the input. Instead, we recognize 99% of the most common
sequences. This works well, because in practice, every modern terminal is
mostly Xterm compatible.

Some useful docs:
- Mintty: https://github.com/mintty/mintty/blob/master/wiki/Keycodes.md
"""

from __future__ import annotations

from ..keys import Keys

__all__ = [
    "ANSI_SEQUENCES",
    "REVERSE_ANSI_SEQUENCES",
]

# Mapping of vt100 escape codes to Keys.
ANSI_SEQUENCES: dict[str, Keys | tuple[Keys, ...]] = {
    # Control keys.
    "\x00": Keys.ControlAt,  # Control-At (Also for Ctrl-Space)
    "\x01": Keys.ControlA,  # Control-A (home)
    "\x02": Keys.ControlB,  # Control-B (emacs cursor left)
    "\x03": Keys.ControlC,  # Control-C (interrupt)
    "\x04": Keys.ControlD,  # Control-D (exit)
    "\x05": Keys.ControlE,  # Control-E (end)
    "\x06": Keys.ControlF,  # Control-F (cursor forward)
    "\x07": Keys.ControlG,  # Control-G
    "\x08": Keys.ControlH,  # Control-H (8) (Identical to '\b')
    "\x09": Keys.ControlI,  # Control-I (9) (Identical to '\t')
    "\x0a": Keys.ControlJ,  # Control-J (10) (Identical to '\n')
    "\x0b": Keys.ControlK,  # Control-K (delete until end of line; vertical tab)
    "\x0c": Keys.ControlL,  # Control-L (clear; form feed)
    "\x0d": Keys.ControlM,  # Control-M (13) (Identical to '\r')
    "\x0e": Keys.ControlN,  # Control-N (14) (history forward)
    "\x0f": Keys.ControlO,  # Control-O (15)
    "\x10": Keys.ControlP,  # Control-P (16) (history back)
    "\x11": Keys.ControlQ,  # Control-Q
    "\x12": Keys.ControlR,  # Control-R (18) (reverse search)
    "\x13": Keys.ControlS,  # Control-S (19) (forward search)
    "\x14": Keys.ControlT,  # Control-T
    "\x15": Keys.ControlU,  # Control-U
    "\x16": Keys.ControlV,  # Control-V
    "\x17": Keys.ControlW,  # Control-W
    "\x18": Keys.ControlX,  # Control-X
    "\x19": Keys.ControlY,  # Control-Y (25)
    "\x1a": Keys.ControlZ,  # Control-Z
    "\x1b": Keys.Escape,  # Also Control-[
    "\x9b": Keys.ShiftEscape,
    "\x1c": Keys.ControlBackslash,  # Both Control-\ (also Ctrl-| )
    "\x1d": Keys.ControlSquareClose,  # Control-]
    "\x1e": Keys.ControlCircumflex,  # Control-^
    "\x1f": Keys.ControlUnderscore,  # Control-underscore (Also for Ctrl-hyphen.)
    # ASCII Delete (0x7f)
    # Vt220 (and Linux terminal) send this when pressing backspace. We map this
    # to ControlH, because that will make it easier to create key bindings that
    # work everywhere, with the trade-off that it's no longer possible to
    # handle backspace and control-h individually for the few terminals that
    # support it. (Most terminals send ControlH when backspace is pressed.)
    # See: http://www.ibb.net/~anne/keyboard.html
    "\x7f": Keys.ControlH,
    # --
    # Various
    "\x1b[1~": Keys.Home,  # tmux
    "\x1b[2~": Keys.Insert,
    "\x1b[3~": Keys.Delete,
    "\x1b[4~": Keys.End,  # tmux
    "\x1b[5~": Keys.PageUp,
    "\x1b[6~": Keys.PageDown,
    "\x1b[7~": Keys.Home,  # xrvt
    "\x1b[8~": Keys.End,  # xrvt
    "\x1b[Z": Keys.BackTab,  # shift + tab
    "\x1b\x09": Keys.BackTab,  # Linux console
    "\x1b[~": Keys.BackTab,  # Windows console
    # --
    # Function keys.
    "\x1bOP": Keys.F1,
    "\x1bOQ": Keys.F2,
    "\x1bOR": Keys.F3,
    "\x1bOS": Keys.F4,
    "\x1b[[A": Keys.F1,  # Linux console.
    "\x1b[[B": Keys.F2,  # Linux console.
    "\x1b[[C": Keys.F3,  # Linux console.
    "\x1b[[D": Keys.F4,  # Linux console.
    "\x1b[[E": Keys.F5,  # Linux console.
    "\x1b[11~": Keys.F1,  # rxvt-unicode
    "\x1b[12~": Keys.F2,  # rxvt-unicode
    "\x1b[13~": Keys.F3,  # rxvt-unicode
    "\x1b[14~": Keys.F4,  # rxvt-unicode
    "\x1b[15~": Keys.F5,
    "\x1b[17~": Keys.F6,
    "\x1b[18~": Keys.F7,
    "\x1b[19~": Keys.F8,
    "\x1b[20~": Keys.F9,
    "\x1b[21~": Keys.F10,
    "\x1b[23~": Keys.F11,
    "\x1b[24~": Keys.F12,
    "\x1b[25~": Keys.F13,
    "\x1b[26~": Keys.F14,
    "\x1b[28~": Keys.F15,
    "\x1b[29~": Keys.F16,
    "\x1b[31~": Keys.F17,
    "\x1b[32~": Keys.F18,
    "\x1b[33~": Keys.F19,
    "\x1b[34~": Keys.F20,
    # Xterm
    "\x1b[1;2P": Keys.F13,
    "\x1b[1;2Q": Keys.F14,
    # '\x1b[1;2R': Keys.F15,  # Conflicts with CPR response.
    "\x1b[1;2S": Keys.F16,
    "\x1b[15;2~": Keys.F17,
    "\x1b[17;2~": Keys.F18,
    "\x1b[18;2~": Keys.F19,
    "\x1b[19;2~": Keys.F20,
    "\x1b[20;2~": Keys.F21,
    "\x1b[21;2~": Keys.F22,
    "\x1b[23;2~": Keys.F23,
    "\x1b[24;2~": Keys.F24,
    # --
    # CSI 27 disambiguated modified "other" keys (xterm)
    # Ref: https://invisible-island.net/xterm/modified-keys.html
    # These are currently unsupported, so just re-map some common ones to the
    # unmodified versions
    "\x1b[27;2;13~": Keys.ControlM,  # Shift + Enter
    "\x1b[27;5;13~": Keys.ControlM,  # Ctrl + Enter
    "\x1b[27;6;13~": Keys.ControlM,  # Ctrl + Shift + Enter
    # --
    # Control + function keys.
    "\x1b[1;5P": Keys.ControlF1,
    "\x1b[1;5Q": Keys.ControlF2,
    # "\x1b[1;5R": Keys.ControlF3,  # Conflicts with CPR response.
    "\x1b[1;5S": Keys.ControlF4,
    "\x1b[15;5~": Keys.ControlF5,
    "\x1b[17;5~": Keys.ControlF6,
    "\x1b[18;5~": Keys.ControlF7,
    "\x1b[19;5~": Keys.ControlF8,
    "\x1b[20;5~": Keys.ControlF9,
    "\x1b[21;5~": Keys.ControlF10,
    "\x1b[23;5~": Keys.ControlF11,
    "\x1b[24;5~": Keys.ControlF12,
    "\x1b[1;6P": Keys.ControlF13,
    "\x1b[1;6Q": Keys.ControlF14,
    # "\x1b[1;6R": Keys.ControlF15,  # Conflicts with CPR response.
    "\x1b[1;6S": Keys.ControlF16,
    "\x1b[15;6~": Keys.ControlF17,
    "\x1b[17;6~": Keys.ControlF18,
    "\x1b[18;6~": Keys.ControlF19,
    "\x1b[19;6~": Keys.ControlF20,
    "\x1b[20;6~": Keys.ControlF21,
    "\x1b[21;6~": Keys.ControlF22,
    "\x1b[23;6~": Keys.ControlF23,
    "\x1b[24;6~": Keys.ControlF24,
    # --
    # Tmux (Win32 subsystem) sends the following scroll events.
    "\x1b[62~": Keys.ScrollUp,
    "\x1b[63~": Keys.ScrollDown,
    "\x1b[200~": Keys.BracketedPaste,  # Start of bracketed paste.
    # --
    # Sequences generated by numpad 5. Not sure what it means. (It doesn't
    # appear in 'infocmp'. Just ignore.
    "\x1b[E": Keys.Ignore,  # Xterm.
    "\x1b[G": Keys.Ignore,  # Linux console.
    # --
    # Meta/control/escape + pageup/pagedown/insert/delete.
    "\x1b[3;2~": Keys.ShiftDelete,  # xterm, gnome-terminal.
    "\x1b[5;2~": Keys.ShiftPageUp,
    "\x1b[6;2~": Keys.ShiftPageDown,
    "\x1b[2;3~": (Keys.Escape, Keys.Insert),
    "\x1b[3;3~": (Keys.Escape, Keys.Delete),
    "\x1b[5;3~": (Keys.Escape, Keys.PageUp),
    "\x1b[6;3~": (Keys.Escape, Keys.PageDown),
    "\x1b[2;4~": (Keys.Escape, Keys.ShiftInsert),
    "\x1b[3;4~": (Keys.Escape, Keys.ShiftDelete),
    "\x1b[5;4~": (Keys.Escape, Keys.ShiftPageUp),
    "\x1b[6;4~": (Keys.Escape, Keys.ShiftPageDown),
    "\x1b[3;5~": Keys.ControlDelete,  # xterm, gnome-terminal.
    "\x1b[5;5~": Keys.ControlPageUp,
    "\x1b[6;5~": Keys.ControlPageDown,
    "\x1b[3;6~": Keys.ControlShiftDelete,
    "\x1b[5;6~": Keys.ControlShiftPageUp,
    "\x1b[6;6~": Keys.ControlShiftPageDown,
    "\x1b[2;7~": (Keys.Escape, Keys.ControlInsert),
    "\x1b[5;7~": (Keys.Escape, Keys.ControlPageDown),
    "\x1b[6;7~": (Keys.Escape, Keys.ControlPageDown),
    "\x1b[2;8~": (Keys.Escape, Keys.ControlShiftInsert),
    "\x1b[5;8~": (Keys.Escape, Keys.ControlShiftPageDown),
    "\x1b[6;8~": (Keys.Escape, Keys.ControlShiftPageDown),
    # --
    # Arrows.
    # (Normal cursor mode).
    "\x1b[A": Keys.Up,
    "\x1b[B": Keys.Down,
    "\x1b[C": Keys.Right,
    "\x1b[D": Keys.Left,
    "\x1b[H": Keys.Home,
    "\x1b[F": Keys.End,
    # Tmux sends following keystrokes when control+arrow is pressed, but for
    # Emacs ansi-term sends the same sequences for normal arrow keys. Consider
    # it a normal arrow press, because that's more important.
    # (Application cursor mode).
    "\x1bOA": Keys.Up,
    "\x1bOB": Keys.Down,
    "\x1bOC": Keys.Right,
    "\x1bOD": Keys.Left,
    "\x1bOF": Keys.End,
    "\x1bOH": Keys.Home,
    # Shift + arrows.
    "\x1b[1;2A": Keys.ShiftUp,
    "\x1b[1;2B": Keys.ShiftDown,
    "\x1b[1;2C": Keys.ShiftRight,
    "\x1b[1;2D": Keys.ShiftLeft,
    "\x1b[1;2F": Keys.ShiftEnd,
    "\x1b[1;2H": Keys.ShiftHome,
    # Meta + arrow keys. Several terminals handle this differently.
    # The following sequences are for xterm and gnome-terminal.
    #     (Iterm sends ESC followed by the normal arrow_up/down/left/right
    #     sequences, and the OSX Terminal sends ESCb and ESCf for "alt
    #     arrow_left" and "alt arrow_right." We don't handle these
    #     explicitly, in here, because would could not distinguish between
    #     pressing ESC (to go to Vi navigation mode), followed by just the
    #     'b' or 'f' key. These combinations are handled in
    #     the input processor.)
    "\x1b[1;3A": (Keys.Escape, Keys.Up),
    "\x1b[1;3B": (Keys.Escape, Keys.Down),
    "\x1b[1;3C": (Keys.Escape, Keys.Right),
    "\x1b[1;3D": (Keys.Escape, Keys.Left),
    "\x1b[1;3F": (Keys.Escape, Keys.End),
    "\x1b[1;3H": (Keys.Escape, Keys.Home),
    # Alt+shift+number.
    "\x1b[1;4A": (Keys.Escape, Keys.ShiftDown),
    "\x1b[1;4B": (Keys.Escape, Keys.ShiftUp),
    "\x1b[1;4C": (Keys.Escape, Keys.ShiftRight),
    "\x1b[1;4D": (Keys.Escape, Keys.ShiftLeft),
    "\x1b[1;4F": (Keys.Escape, Keys.ShiftEnd),
    "\x1b[1;4H": (Keys.Escape, Keys.ShiftHome),
    # Control + arrows.
    "\x1b[1;5A": Keys.ControlUp,  # Cursor Mode
    "\x1b[1;5B": Keys.ControlDown,  # Cursor Mode
    "\x1b[1;5C": Keys.ControlRight,  # Cursor Mode
    "\x1b[1;5D": Keys.ControlLeft,  # Cursor Mode
    "\x1b[1;5F": Keys.ControlEnd,
    "\x1b[1;5H": Keys.ControlHome,
    # Tmux sends following keystrokes when control+arrow is pressed, but for
    # Emacs ansi-term sends the same sequences for normal arrow keys. Consider
    # it a normal arrow press, because that's more important.
    "\x1b[5A": Keys.ControlUp,
    "\x1b[5B": Keys.ControlDown,
    "\x1b[5C": Keys.ControlRight,
    "\x1b[5D": Keys.ControlLeft,
    "\x1bOc": Keys.ControlRight,  # rxvt
    "\x1bOd": Keys.ControlLeft,  # rxvt
    # Control + shift + arrows.
    "\x1b[1;6A": Keys.ControlShiftDown,
    "\x1b[1;6B": Keys.ControlShiftUp,
    "\x1b[1;6C": Keys.ControlShiftRight,
    "\x1b[1;6D": Keys.ControlShiftLeft,
    "\x1b[1;6F": Keys.ControlShiftEnd,
    "\x1b[1;6H": Keys.ControlShiftHome,
    # Control + Meta + arrows.
    "\x1b[1;7A": (Keys.Escape, Keys.ControlDown),
    "\x1b[1;7B": (Keys.Escape, Keys.ControlUp),
    "\x1b[1;7C": (Keys.Escape, Keys.ControlRight),
    "\x1b[1;7D": (Keys.Escape, Keys.ControlLeft),
    "\x1b[1;7F": (Keys.Escape, Keys.ControlEnd),
    "\x1b[1;7H": (Keys.Escape, Keys.ControlHome),
    # Meta + Shift + arrows.
    "\x1b[1;8A": (Keys.Escape, Keys.ControlShiftDown),
    "\x1b[1;8B": (Keys.Escape, Keys.ControlShiftUp),
    "\x1b[1;8C": (Keys.Escape, Keys.ControlShiftRight),
    "\x1b[1;8D": (Keys.Escape, Keys.ControlShiftLeft),
    "\x1b[1;8F": (Keys.Escape, Keys.ControlShiftEnd),
    "\x1b[1;8H": (Keys.Escape, Keys.ControlShiftHome),
    # Meta + arrow on (some?) Macs when using iTerm defaults (see issue #483).
    "\x1b[1;9A": (Keys.Escape, Keys.Up),
    "\x1b[1;9B": (Keys.Escape, Keys.Down),
    "\x1b[1;9C": (Keys.Escape, Keys.Right),
    "\x1b[1;9D": (Keys.Escape, Keys.Left),
    # --
    # Control/shift/meta + number in mintty.
    # (c-2 will actually send c-@ and c-6 will send c-^.)
    "\x1b[1;5p": Keys.Control0,
    "\x1b[1;5q": Keys.Control1,
    "\x1b[1;5r": Keys.Control2,
    "\x1b[1;5s": Keys.Control3,
    "\x1b[1;5t": Keys.Control4,
    "\x1b[1;5u": Keys.Control5,
    "\x1b[1;5v": Keys.Control6,
    "\x1b[1;5w": Keys.Control7,
    "\x1b[1;5x": Keys.Control8,
    "\x1b[1;5y": Keys.Control9,
    "\x1b[1;6p": Keys.ControlShift0,
    "\x1b[1;6q": Keys.ControlShift1,
    "\x1b[1;6r": Keys.ControlShift2,
    "\x1b[1;6s": Keys.ControlShift3,
    "\x1b[1;6t": Keys.ControlShift4,
    "\x1b[1;6u": Keys.ControlShift5,
    "\x1b[1;6v": Keys.ControlShift6,
    "\x1b[1;6w": Keys.ControlShift7,
    "\x1b[1;6x": Keys.ControlShift8,
    "\x1b[1;6y": Keys.ControlShift9,
    "\x1b[1;7p": (Keys.Escape, Keys.Control0),
    "\x1b[1;7q": (Keys.Escape, Keys.Control1),
    "\x1b[1;7r": (Keys.Escape, Keys.Control2),
    "\x1b[1;7s": (Keys.Escape, Keys.Control3),
    "\x1b[1;7t": (Keys.Escape, Keys.Control4),
    "\x1b[1;7u": (Keys.Escape, Keys.Control5),
    "\x1b[1;7v": (Keys.Escape, Keys.Control6),
    "\x1b[1;7w": (Keys.Escape, Keys.Control7),
    "\x1b[1;7x": (Keys.Escape, Keys.Control8),
    "\x1b[1;7y": (Keys.Escape, Keys.Control9),
    "\x1b[1;8p": (Keys.Escape, Keys.ControlShift0),
    "\x1b[1;8q": (Keys.Escape, Keys.ControlShift1),
    "\x1b[1;8r": (Keys.Escape, Keys.ControlShift2),
    "\x1b[1;8s": (Keys.Escape, Keys.ControlShift3),
    "\x1b[1;8t": (Keys.Escape, Keys.ControlShift4),
    "\x1b[1;8u": (Keys.Escape, Keys.ControlShift5),
    "\x1b[1;8v": (Keys.Escape, Keys.ControlShift6),
    "\x1b[1;8w": (Keys.Escape, Keys.ControlShift7),
    "\x1b[1;8x": (Keys.Escape, Keys.ControlShift8),
    "\x1b[1;8y": (Keys.Escape, Keys.ControlShift9),
}


def _get_reverse_ansi_sequences() -> dict[Keys, str]:
    """
    Create a dictionary that maps prompt_toolkit keys back to the VT100 escape
    sequences.
    """
    result: dict[Keys, str] = {}

    for sequence, key in ANSI_SEQUENCES.items():
        if not isinstance(key, tuple):
            if key not in result:
                result[key] = sequence

    return result


REVERSE_ANSI_SEQUENCES = _get_reverse_ansi_sequences()
