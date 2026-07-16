from __future__ import annotations

import os
import select
from codecs import getincrementaldecoder

__all__ = [
    "PosixStdinReader",
]


class PosixStdinReader:
    """
    Wrapper around stdin which reads (nonblocking) the next available 1024
    bytes and decodes it.

    Note that you can't be sure that the input file is closed if the ``read``
    function returns an empty string. When ``errors=ignore`` is passed,
    ``read`` can return an empty string if all malformed input was replaced by
    an empty string. (We can't block here and wait for more input.) So, because
    of that, check the ``closed`` attribute, to be sure that the file has been
    closed.

    :param stdin_fd: File descriptor from which we read.
    :param errors:  Can be 'ignore', 'strict' or 'replace'.
        On Python3, this can be 'surrogateescape', which is the default.

        'surrogateescape' is preferred, because this allows us to transfer
        unrecognized bytes to the key bindings. Some terminals, like lxterminal
        and Guake, use the 'Mxx' notation to send mouse events, where each 'x'
        can be any possible byte.
    """

    # By default, we want to 'ignore' errors here. The input stream can be full
    # of junk.  One occurrence of this that I had was when using iTerm2 on OS X,
    # with "Option as Meta" checked (You should choose "Option as +Esc".)

    def __init__(
        self, stdin_fd: int, errors: str = "surrogateescape", encoding: str = "utf-8"
    ) -> None:
        self.stdin_fd = stdin_fd
        self.errors = errors

        # Create incremental decoder for decoding stdin.
        # We can not just do `os.read(stdin.fileno(), 1024).decode('utf-8')`, because
        # it could be that we are in the middle of a utf-8 byte sequence.
        self._stdin_decoder_cls = getincrementaldecoder(encoding)
        self._stdin_decoder = self._stdin_decoder_cls(errors=errors)

        #: True when there is nothing anymore to read.
        self.closed = False

    def read(self, count: int = 1024) -> str:
        # By default we choose a rather small chunk size, because reading
        # big amounts of input at once, causes the event loop to process
        # all these key bindings also at once without going back to the
        # loop. This will make the application feel unresponsive.
        """
        Read the input and return it as a string.

        Return the text. Note that this can return an empty string, even when
        the input stream was not yet closed. This means that something went
        wrong during the decoding.
        """
        if self.closed:
            return ""

        # Check whether there is some input to read. `os.read` would block
        # otherwise.
        # (Actually, the event loop is responsible to make sure that this
        # function is only called when there is something to read, but for some
        # reason this happens in certain situations.)
        try:
            if not select.select([self.stdin_fd], [], [], 0)[0]:
                return ""
        except OSError:
            # Happens for instance when the file descriptor was closed.
            # (We had this in ptterm, where the FD became ready, a callback was
            # scheduled, but in the meantime another callback closed it already.)
            self.closed = True

        # Note: the following works better than wrapping `self.stdin` like
        #       `codecs.getreader('utf-8')(stdin)` and doing `read(1)`.
        #       Somehow that causes some latency when the escape
        #       character is pressed. (Especially on combination with the `select`.)
        try:
            data = os.read(self.stdin_fd, count)

            # Nothing more to read, stream is closed.
            if data == b"":
                self.closed = True
                return ""
        except OSError:
            # In case of SIGWINCH
            data = b""

        return self._stdin_decoder.decode(data)
