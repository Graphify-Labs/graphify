import codecs
from typing import Any, Optional

from .core import IDNAError, _unicode_dots_re, alabel, decode, encode, ulabel


class Codec(codecs.Codec):
    """Stateless IDNA 2008 codec.

    Implements the :class:`codecs.Codec` protocol so that the whole-domain
    encoder (:func:`idna.encode`) and decoder (:func:`idna.decode`) are
    accessible through the standard codec machinery as ``"idna2008"``.

    Only the ``"strict"`` error handler is supported; any other handler
    raises :exc:`~idna.IDNAError`.
    """

    def encode(self, data: str, errors: str = "strict") -> tuple[bytes, int]:  # ty: ignore[invalid-method-override]
        if errors != "strict":
            raise IDNAError(f'Unsupported error handling "{errors}"')

        if not data:
            return b"", 0

        return encode(data), len(data)

    def decode(self, data: bytes, errors: str = "strict") -> tuple[str, int]:  # ty: ignore[invalid-method-override]
        if errors != "strict":
            raise IDNAError(f'Unsupported error handling "{errors}"')

        if not data:
            return "", 0

        return decode(data), len(data)


class IncrementalEncoder(codecs.BufferedIncrementalEncoder):
    """Incremental IDNA 2008 encoder.

    Buffers a partial trailing label across calls until either the next
    label separator is seen or ``final=True``, so that streamed input is
    encoded one whole label at a time. Any of the four Unicode label
    separators (``U+002E``, ``U+3002``, ``U+FF0E``, ``U+FF61``) ends a
    label; the result always uses ``U+002E`` as the separator.

    Only the ``"strict"`` error handler is supported.
    """

    def _buffer_encode(self, data: str, errors: str, final: bool) -> tuple[bytes, int]:  # ty: ignore[invalid-method-override]
        if errors != "strict":
            raise IDNAError(f'Unsupported error handling "{errors}"')

        if not data:
            return b"", 0

        labels = _unicode_dots_re.split(data)
        trailing_dot = b""
        if labels:
            if not labels[-1]:
                trailing_dot = b"."
                del labels[-1]
            elif not final:
                # Keep potentially unfinished label until the next call
                del labels[-1]
                if labels:
                    trailing_dot = b"."

        result = []
        size = 0
        for label in labels:
            result.append(alabel(label))
            if size:
                size += 1
            size += len(label)

        # Join with U+002E
        result_bytes = b".".join(result) + trailing_dot
        size += len(trailing_dot)
        return result_bytes, size


class IncrementalDecoder(codecs.BufferedIncrementalDecoder):
    """Incremental IDNA 2008 decoder.

    Buffers a partial trailing label across calls until either the next
    label separator is seen or ``final=True``, so that streamed input is
    decoded one whole label at a time.

    Only the ``"strict"`` error handler is supported.
    """

    def _buffer_decode(self, data: Any, errors: str, final: bool) -> tuple[str, int]:  # ty: ignore[invalid-method-override]
        if errors != "strict":
            raise IDNAError(f'Unsupported error handling "{errors}"')

        if not data:
            return ("", 0)

        if not isinstance(data, str):
            data = str(data, "ascii")

        labels = _unicode_dots_re.split(data)
        trailing_dot = ""
        if labels:
            if not labels[-1]:
                trailing_dot = "."
                del labels[-1]
            elif not final:
                # Keep potentially unfinished label until the next call
                del labels[-1]
                if labels:
                    trailing_dot = "."

        result = []
        size = 0
        for label in labels:
            result.append(ulabel(label))
            if size:
                size += 1
            size += len(label)

        result_str = ".".join(result) + trailing_dot
        size += len(trailing_dot)
        return (result_str, size)


class StreamWriter(Codec, codecs.StreamWriter):
    pass


class StreamReader(Codec, codecs.StreamReader):
    pass


def search_function(name: str) -> Optional[codecs.CodecInfo]:
    """Codec search function registered with :mod:`codecs`.

    Returns a :class:`codecs.CodecInfo` for the ``"idna2008"`` codec name
    so that ``str.encode("idna2008")`` and ``bytes.decode("idna2008")``
    invoke the IDNA 2008 codec defined in this module.

    :param name: The codec name being looked up.
    :returns: A :class:`codecs.CodecInfo` instance if ``name`` is
        ``"idna2008"``, otherwise ``None``.
    """
    if name != "idna2008":
        return None
    return codecs.CodecInfo(
        name=name,
        encode=Codec().encode,
        decode=Codec().decode,  # type: ignore
        incrementalencoder=IncrementalEncoder,
        incrementaldecoder=IncrementalDecoder,
        streamwriter=StreamWriter,
        streamreader=StreamReader,
    )


codecs.register(search_function)
