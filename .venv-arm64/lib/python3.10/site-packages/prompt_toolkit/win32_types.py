from __future__ import annotations

from ctypes import Structure, Union, c_char, c_long, c_short, c_ulong
from ctypes.wintypes import BOOL, DWORD, LPVOID, WCHAR, WORD
from typing import TYPE_CHECKING

# Input/Output standard device numbers. Note that these are not handle objects.
# It's the `windll.kernel32.GetStdHandle` system call that turns them into a
# real handle object.
STD_INPUT_HANDLE = c_ulong(-10)
STD_OUTPUT_HANDLE = c_ulong(-11)
STD_ERROR_HANDLE = c_ulong(-12)


class COORD(Structure):
    """
    Struct in wincon.h
    http://msdn.microsoft.com/en-us/library/windows/desktop/ms682119(v=vs.85).aspx
    """

    if TYPE_CHECKING:
        X: int
        Y: int

    _fields_ = [
        ("X", c_short),  # Short
        ("Y", c_short),  # Short
    ]

    def __repr__(self) -> str:
        return "{}(X={!r}, Y={!r}, type_x={!r}, type_y={!r})".format(
            self.__class__.__name__,
            self.X,
            self.Y,
            type(self.X),
            type(self.Y),
        )


class UNICODE_OR_ASCII(Union):
    if TYPE_CHECKING:
        AsciiChar: bytes
        UnicodeChar: str

    _fields_ = [
        ("AsciiChar", c_char),
        ("UnicodeChar", WCHAR),
    ]


class KEY_EVENT_RECORD(Structure):
    """
    http://msdn.microsoft.com/en-us/library/windows/desktop/ms684166(v=vs.85).aspx
    """

    if TYPE_CHECKING:
        KeyDown: int
        RepeatCount: int
        VirtualKeyCode: int
        VirtualScanCode: int
        uChar: UNICODE_OR_ASCII
        ControlKeyState: int

    _fields_ = [
        ("KeyDown", c_long),  # bool
        ("RepeatCount", c_short),  # word
        ("VirtualKeyCode", c_short),  # word
        ("VirtualScanCode", c_short),  # word
        ("uChar", UNICODE_OR_ASCII),  # Unicode or ASCII.
        ("ControlKeyState", c_long),  # double word
    ]


class MOUSE_EVENT_RECORD(Structure):
    """
    http://msdn.microsoft.com/en-us/library/windows/desktop/ms684239(v=vs.85).aspx
    """

    if TYPE_CHECKING:
        MousePosition: COORD
        ButtonState: int
        ControlKeyState: int
        EventFlags: int

    _fields_ = [
        ("MousePosition", COORD),
        ("ButtonState", c_long),  # dword
        ("ControlKeyState", c_long),  # dword
        ("EventFlags", c_long),  # dword
    ]


class WINDOW_BUFFER_SIZE_RECORD(Structure):
    """
    http://msdn.microsoft.com/en-us/library/windows/desktop/ms687093(v=vs.85).aspx
    """

    if TYPE_CHECKING:
        Size: COORD

    _fields_ = [("Size", COORD)]


class MENU_EVENT_RECORD(Structure):
    """
    http://msdn.microsoft.com/en-us/library/windows/desktop/ms684213(v=vs.85).aspx
    """

    if TYPE_CHECKING:
        CommandId: int

    _fields_ = [("CommandId", c_long)]  # uint


class FOCUS_EVENT_RECORD(Structure):
    """
    http://msdn.microsoft.com/en-us/library/windows/desktop/ms683149(v=vs.85).aspx
    """

    if TYPE_CHECKING:
        SetFocus: int

    _fields_ = [("SetFocus", c_long)]  # bool


class EVENT_RECORD(Union):
    if TYPE_CHECKING:
        KeyEvent: KEY_EVENT_RECORD
        MouseEvent: MOUSE_EVENT_RECORD
        WindowBufferSizeEvent: WINDOW_BUFFER_SIZE_RECORD
        MenuEvent: MENU_EVENT_RECORD
        FocusEvent: FOCUS_EVENT_RECORD

    _fields_ = [
        ("KeyEvent", KEY_EVENT_RECORD),
        ("MouseEvent", MOUSE_EVENT_RECORD),
        ("WindowBufferSizeEvent", WINDOW_BUFFER_SIZE_RECORD),
        ("MenuEvent", MENU_EVENT_RECORD),
        ("FocusEvent", FOCUS_EVENT_RECORD),
    ]


class INPUT_RECORD(Structure):
    """
    http://msdn.microsoft.com/en-us/library/windows/desktop/ms683499(v=vs.85).aspx
    """

    if TYPE_CHECKING:
        EventType: int
        Event: EVENT_RECORD

    _fields_ = [("EventType", c_short), ("Event", EVENT_RECORD)]  # word  # Union.


EventTypes = {
    1: "KeyEvent",
    2: "MouseEvent",
    4: "WindowBufferSizeEvent",
    8: "MenuEvent",
    16: "FocusEvent",
}


class SMALL_RECT(Structure):
    """struct in wincon.h."""

    if TYPE_CHECKING:
        Left: int
        Top: int
        Right: int
        Bottom: int

    _fields_ = [
        ("Left", c_short),
        ("Top", c_short),
        ("Right", c_short),
        ("Bottom", c_short),
    ]


class CONSOLE_SCREEN_BUFFER_INFO(Structure):
    """struct in wincon.h."""

    if TYPE_CHECKING:
        dwSize: COORD
        dwCursorPosition: COORD
        wAttributes: int
        srWindow: SMALL_RECT
        dwMaximumWindowSize: COORD

    _fields_ = [
        ("dwSize", COORD),
        ("dwCursorPosition", COORD),
        ("wAttributes", WORD),
        ("srWindow", SMALL_RECT),
        ("dwMaximumWindowSize", COORD),
    ]

    def __repr__(self) -> str:
        return "CONSOLE_SCREEN_BUFFER_INFO({!r},{!r},{!r},{!r},{!r},{!r},{!r},{!r},{!r},{!r},{!r})".format(
            self.dwSize.Y,
            self.dwSize.X,
            self.dwCursorPosition.Y,
            self.dwCursorPosition.X,
            self.wAttributes,
            self.srWindow.Top,
            self.srWindow.Left,
            self.srWindow.Bottom,
            self.srWindow.Right,
            self.dwMaximumWindowSize.Y,
            self.dwMaximumWindowSize.X,
        )


class SECURITY_ATTRIBUTES(Structure):
    """
    http://msdn.microsoft.com/en-us/library/windows/desktop/aa379560(v=vs.85).aspx
    """

    if TYPE_CHECKING:
        nLength: int
        lpSecurityDescriptor: int
        bInheritHandle: int  # BOOL comes back as 'int'.

    _fields_ = [
        ("nLength", DWORD),
        ("lpSecurityDescriptor", LPVOID),
        ("bInheritHandle", BOOL),
    ]
