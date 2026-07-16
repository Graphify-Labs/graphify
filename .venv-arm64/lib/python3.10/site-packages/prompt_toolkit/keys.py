from __future__ import annotations

from enum import Enum

__all__ = [
    "Keys",
    "ALL_KEYS",
]


class Keys(str, Enum):
    """
    List of keys for use in key bindings.

    Note that this is an "StrEnum", all values can be compared against
    strings.
    """

    value: str

    Escape = "escape"  # Also Control-[
    ShiftEscape = "s-escape"

    ControlAt = "c-@"  # Also Control-Space.

    ControlA = "c-a"
    ControlB = "c-b"
    ControlC = "c-c"
    ControlD = "c-d"
    ControlE = "c-e"
    ControlF = "c-f"
    ControlG = "c-g"
    ControlH = "c-h"
    ControlI = "c-i"  # Tab
    ControlJ = "c-j"  # Newline
    ControlK = "c-k"
    ControlL = "c-l"
    ControlM = "c-m"  # Carriage return
    ControlN = "c-n"
    ControlO = "c-o"
    ControlP = "c-p"
    ControlQ = "c-q"
    ControlR = "c-r"
    ControlS = "c-s"
    ControlT = "c-t"
    ControlU = "c-u"
    ControlV = "c-v"
    ControlW = "c-w"
    ControlX = "c-x"
    ControlY = "c-y"
    ControlZ = "c-z"

    Control1 = "c-1"
    Control2 = "c-2"
    Control3 = "c-3"
    Control4 = "c-4"
    Control5 = "c-5"
    Control6 = "c-6"
    Control7 = "c-7"
    Control8 = "c-8"
    Control9 = "c-9"
    Control0 = "c-0"

    ControlShift1 = "c-s-1"
    ControlShift2 = "c-s-2"
    ControlShift3 = "c-s-3"
    ControlShift4 = "c-s-4"
    ControlShift5 = "c-s-5"
    ControlShift6 = "c-s-6"
    ControlShift7 = "c-s-7"
    ControlShift8 = "c-s-8"
    ControlShift9 = "c-s-9"
    ControlShift0 = "c-s-0"

    ControlBackslash = "c-\\"
    ControlSquareClose = "c-]"
    ControlCircumflex = "c-^"
    ControlUnderscore = "c-_"

    Left = "left"
    Right = "right"
    Up = "up"
    Down = "down"
    Home = "home"
    End = "end"
    Insert = "insert"
    Delete = "delete"
    PageUp = "pageup"
    PageDown = "pagedown"

    ControlLeft = "c-left"
    ControlRight = "c-right"
    ControlUp = "c-up"
    ControlDown = "c-down"
    ControlHome = "c-home"
    ControlEnd = "c-end"
    ControlInsert = "c-insert"
    ControlDelete = "c-delete"
    ControlPageUp = "c-pageup"
    ControlPageDown = "c-pagedown"

    ShiftLeft = "s-left"
    ShiftRight = "s-right"
    ShiftUp = "s-up"
    ShiftDown = "s-down"
    ShiftHome = "s-home"
    ShiftEnd = "s-end"
    ShiftInsert = "s-insert"
    ShiftDelete = "s-delete"
    ShiftPageUp = "s-pageup"
    ShiftPageDown = "s-pagedown"

    ControlShiftLeft = "c-s-left"
    ControlShiftRight = "c-s-right"
    ControlShiftUp = "c-s-up"
    ControlShiftDown = "c-s-down"
    ControlShiftHome = "c-s-home"
    ControlShiftEnd = "c-s-end"
    ControlShiftInsert = "c-s-insert"
    ControlShiftDelete = "c-s-delete"
    ControlShiftPageUp = "c-s-pageup"
    ControlShiftPageDown = "c-s-pagedown"

    BackTab = "s-tab"  # shift + tab

    F1 = "f1"
    F2 = "f2"
    F3 = "f3"
    F4 = "f4"
    F5 = "f5"
    F6 = "f6"
    F7 = "f7"
    F8 = "f8"
    F9 = "f9"
    F10 = "f10"
    F11 = "f11"
    F12 = "f12"
    F13 = "f13"
    F14 = "f14"
    F15 = "f15"
    F16 = "f16"
    F17 = "f17"
    F18 = "f18"
    F19 = "f19"
    F20 = "f20"
    F21 = "f21"
    F22 = "f22"
    F23 = "f23"
    F24 = "f24"

    ControlF1 = "c-f1"
    ControlF2 = "c-f2"
    ControlF3 = "c-f3"
    ControlF4 = "c-f4"
    ControlF5 = "c-f5"
    ControlF6 = "c-f6"
    ControlF7 = "c-f7"
    ControlF8 = "c-f8"
    ControlF9 = "c-f9"
    ControlF10 = "c-f10"
    ControlF11 = "c-f11"
    ControlF12 = "c-f12"
    ControlF13 = "c-f13"
    ControlF14 = "c-f14"
    ControlF15 = "c-f15"
    ControlF16 = "c-f16"
    ControlF17 = "c-f17"
    ControlF18 = "c-f18"
    ControlF19 = "c-f19"
    ControlF20 = "c-f20"
    ControlF21 = "c-f21"
    ControlF22 = "c-f22"
    ControlF23 = "c-f23"
    ControlF24 = "c-f24"

    # Matches any key.
    Any = "<any>"

    # Special.
    ScrollUp = "<scroll-up>"
    ScrollDown = "<scroll-down>"

    CPRResponse = "<cursor-position-response>"
    Vt100MouseEvent = "<vt100-mouse-event>"
    WindowsMouseEvent = "<windows-mouse-event>"
    BracketedPaste = "<bracketed-paste>"

    SIGINT = "<sigint>"

    # For internal use: key which is ignored.
    # (The key binding for this key should not do anything.)
    Ignore = "<ignore>"

    # Some 'Key' aliases (for backwards-compatibility).
    ControlSpace = ControlAt
    Tab = ControlI
    Enter = ControlM
    Backspace = ControlH

    # ShiftControl was renamed to ControlShift in
    # 888fcb6fa4efea0de8333177e1bbc792f3ff3c24 (20 Feb 2020).
    ShiftControlLeft = ControlShiftLeft
    ShiftControlRight = ControlShiftRight
    ShiftControlHome = ControlShiftHome
    ShiftControlEnd = ControlShiftEnd


ALL_KEYS: list[str] = [k.value for k in Keys]


# Aliases.
KEY_ALIASES: dict[str, str] = {
    "backspace": "c-h",
    "c-space": "c-@",
    "enter": "c-m",
    "tab": "c-i",
    # ShiftControl was renamed to ControlShift.
    "s-c-left": "c-s-left",
    "s-c-right": "c-s-right",
    "s-c-home": "c-s-home",
    "s-c-end": "c-s-end",
}
