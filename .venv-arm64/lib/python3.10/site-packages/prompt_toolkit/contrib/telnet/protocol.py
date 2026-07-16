"""
Parser for the Telnet protocol. (Not a complete implementation of the telnet
specification, but sufficient for a command line interface.)

Inspired by `Twisted.conch.telnet`.
"""

from __future__ import annotations

import struct
from typing import Callable, Generator

from .log import logger

__all__ = [
    "TelnetProtocolParser",
]


def int2byte(number: int) -> bytes:
    return bytes((number,))


# Telnet constants.
NOP = int2byte(0)
SGA = int2byte(3)

IAC = int2byte(255)
DO = int2byte(253)
DONT = int2byte(254)
LINEMODE = int2byte(34)
SB = int2byte(250)
WILL = int2byte(251)
WONT = int2byte(252)
MODE = int2byte(1)
SE = int2byte(240)
ECHO = int2byte(1)
NAWS = int2byte(31)
LINEMODE = int2byte(34)
SUPPRESS_GO_AHEAD = int2byte(3)

TTYPE = int2byte(24)
SEND = int2byte(1)
IS = int2byte(0)

DM = int2byte(242)
BRK = int2byte(243)
IP = int2byte(244)
AO = int2byte(245)
AYT = int2byte(246)
EC = int2byte(247)
EL = int2byte(248)
GA = int2byte(249)


class TelnetProtocolParser:
    """
    Parser for the Telnet protocol.
    Usage::

        def data_received(data):
            print(data)

        def size_received(rows, columns):
            print(rows, columns)

        p = TelnetProtocolParser(data_received, size_received)
        p.feed(binary_data)
    """

    def __init__(
        self,
        data_received_callback: Callable[[bytes], None],
        size_received_callback: Callable[[int, int], None],
        ttype_received_callback: Callable[[str], None],
    ) -> None:
        self.data_received_callback = data_received_callback
        self.size_received_callback = size_received_callback
        self.ttype_received_callback = ttype_received_callback

        self._parser = self._parse_coroutine()
        self._parser.send(None)  # type: ignore

    def received_data(self, data: bytes) -> None:
        self.data_received_callback(data)

    def do_received(self, data: bytes) -> None:
        """Received telnet DO command."""
        logger.info("DO %r", data)

    def dont_received(self, data: bytes) -> None:
        """Received telnet DONT command."""
        logger.info("DONT %r", data)

    def will_received(self, data: bytes) -> None:
        """Received telnet WILL command."""
        logger.info("WILL %r", data)

    def wont_received(self, data: bytes) -> None:
        """Received telnet WONT command."""
        logger.info("WONT %r", data)

    def command_received(self, command: bytes, data: bytes) -> None:
        if command == DO:
            self.do_received(data)

        elif command == DONT:
            self.dont_received(data)

        elif command == WILL:
            self.will_received(data)

        elif command == WONT:
            self.wont_received(data)

        else:
            logger.info("command received %r %r", command, data)

    def naws(self, data: bytes) -> None:
        """
        Received NAWS. (Window dimensions.)
        """
        if len(data) == 4:
            # NOTE: the first parameter of struct.unpack should be
            # a 'str' object. Both on Py2/py3. This crashes on OSX
            # otherwise.
            columns, rows = struct.unpack("!HH", data)
            self.size_received_callback(rows, columns)
        else:
            logger.warning("Wrong number of NAWS bytes")

    def ttype(self, data: bytes) -> None:
        """
        Received terminal type.
        """
        subcmd, data = data[0:1], data[1:]
        if subcmd == IS:
            ttype = data.decode("ascii")
            self.ttype_received_callback(ttype)
        else:
            logger.warning("Received a non-IS terminal type Subnegotiation")

    def negotiate(self, data: bytes) -> None:
        """
        Got negotiate data.
        """
        command, payload = data[0:1], data[1:]

        if command == NAWS:
            self.naws(payload)
        elif command == TTYPE:
            self.ttype(payload)
        else:
            logger.info("Negotiate (%r got bytes)", len(data))

    def _parse_coroutine(self) -> Generator[None, bytes, None]:
        """
        Parser state machine.
        Every 'yield' expression returns the next byte.
        """
        while True:
            d = yield

            if d == int2byte(0):
                pass  # NOP

            # Go to state escaped.
            elif d == IAC:
                d2 = yield

                if d2 == IAC:
                    self.received_data(d2)

                # Handle simple commands.
                elif d2 in (NOP, DM, BRK, IP, AO, AYT, EC, EL, GA):
                    self.command_received(d2, b"")

                # Handle IAC-[DO/DONT/WILL/WONT] commands.
                elif d2 in (DO, DONT, WILL, WONT):
                    d3 = yield
                    self.command_received(d2, d3)

                # Subnegotiation
                elif d2 == SB:
                    # Consume everything until next IAC-SE
                    data = []

                    while True:
                        d3 = yield

                        if d3 == IAC:
                            d4 = yield
                            if d4 == SE:
                                break
                            else:
                                data.append(d4)
                        else:
                            data.append(d3)

                    self.negotiate(b"".join(data))
            else:
                self.received_data(d)

    def feed(self, data: bytes) -> None:
        """
        Feed data to the parser.
        """
        for b in data:
            self._parser.send(int2byte(b))
