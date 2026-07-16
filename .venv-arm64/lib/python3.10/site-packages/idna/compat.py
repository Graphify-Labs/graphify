from typing import Any, Union

from .core import decode, encode


def ToASCII(label: str) -> bytes:
    """Compatibility shim for :rfc:`3490` ``ToASCII``.

    Delegates to :func:`idna.encode` (IDNA 2008). Provided to ease porting
    of code written against the legacy :mod:`encodings.idna` API; new code
    should call :func:`idna.encode` directly.

    :param label: The label or domain to encode.
    :returns: The encoded form as ASCII :class:`bytes`.
    """
    return encode(label)


def ToUnicode(label: Union[bytes, bytearray]) -> str:
    """Compatibility shim for :rfc:`3490` ``ToUnicode``.

    Delegates to :func:`idna.decode` (IDNA 2008). Provided to ease porting
    of code written against the legacy :mod:`encodings.idna` API; new code
    should call :func:`idna.decode` directly.

    :param label: The label or domain to decode.
    :returns: The decoded Unicode form.
    """
    return decode(label)


def nameprep(s: Any) -> None:
    """Stub for :rfc:`3491` Nameprep, which is not used by IDNA 2008.

    IDNA 2008 (:rfc:`5891`) replaces Nameprep with the per-codepoint
    validity classes from :rfc:`5892`; this function exists only to
    return a clear error if legacy code attempts to call it.

    :raises NotImplementedError: Always.
    """
    raise NotImplementedError("IDNA 2008 does not utilise nameprep protocol")
