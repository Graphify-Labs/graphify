from __future__ import annotations

import collections.abc as cabc
import json
import typing as t

from .encoding import want_bytes
from .exc import BadPayload
from .exc import BadSignature
from .signer import _make_keys_list
from .signer import Signer

if t.TYPE_CHECKING:
    import typing_extensions as te

    # This should be either be str or bytes. To avoid having to specify the
    # bound type, it falls back to a union if structural matching fails.
    _TSerialized = te.TypeVar(
        "_TSerialized", bound=t.Union[str, bytes], default=t.Union[str, bytes]
    )
else:
    # Still available at runtime on Python < 3.13, but without the default.
    _TSerialized = t.TypeVar("_TSerialized", bound=t.Union[str, bytes])


class _PDataSerializer(t.Protocol[_TSerialized]):
    def loads(self, payload: _TSerialized, /) -> t.Any: ...
    # A signature with additional arguments is not handled correctly by type
    # checkers right now, so an overload is used below for serializers that
    # don't match this strict protocol.
    def dumps(self, obj: t.Any, /) -> _TSerialized: ...


# Use TypeIs once it's available in typing_extensions or 3.13.
def is_text_serializer(
    serializer: _PDataSerializer[t.Any],
) -> te.TypeGuard[_PDataSerializer[str]]:
    """Checks whether a serializer generates text or binary."""
    return isinstance(serializer.dumps({}), str)


class Serializer(t.Generic[_TSerialized]):
    """A serializer wraps a :class:`~itsdangerous.signer.Signer` to
    enable serializing and securely signing data other than bytes. It
    can unsign to verify that the data hasn't been changed.

    The serializer provides :meth:`dumps` and :meth:`loads`, similar to
    :mod:`json`, and by default uses :mod:`json` internally to serialize
    the data to bytes.

    The secret key should be a random string of ``bytes`` and should not
    be saved to code or version control. Different salts should be used
    to distinguish signing in different contexts. See :doc:`/concepts`
    for information about the security of the secret key and salt.

    :param secret_key: The secret key to sign and verify with. Can be a
        list of keys, oldest to newest, to support key rotation.
    :param salt: Extra key to combine with ``secret_key`` to distinguish
        signatures in different contexts.
    :param serializer: An object that provides ``dumps`` and ``loads``
        methods for serializing data to a string. Defaults to
        :attr:`default_serializer`, which defaults to :mod:`json`.
    :param serializer_kwargs: Keyword arguments to pass when calling
        ``serializer.dumps``.
    :param signer: A ``Signer`` class to instantiate when signing data.
        Defaults to :attr:`default_signer`, which defaults to
        :class:`~itsdangerous.signer.Signer`.
    :param signer_kwargs: Keyword arguments to pass when instantiating
        the ``Signer`` class.
    :param fallback_signers: List of signer parameters to try when
        unsigning with the default signer fails. Each item can be a dict
        of ``signer_kwargs``, a ``Signer`` class, or a tuple of
        ``(signer, signer_kwargs)``. Defaults to
        :attr:`default_fallback_signers`.

    .. versionchanged:: 2.0
        Added support for key rotation by passing a list to
        ``secret_key``.

    .. versionchanged:: 2.0
        Removed the default SHA-512 fallback signer from
        ``default_fallback_signers``.

    .. versionchanged:: 1.1
        Added support for ``fallback_signers`` and configured a default
        SHA-512 fallback. This fallback is for users who used the yanked
        1.0.0 release which defaulted to SHA-512.

    .. versionchanged:: 0.14
        The ``signer`` and ``signer_kwargs`` parameters were added to
        the constructor.
    """

    #: The default serialization module to use to serialize data to a
    #: string internally. The default is :mod:`json`, but can be changed
    #: to any object that provides ``dumps`` and ``loads`` methods.
    default_serializer: _PDataSerializer[t.Any] = json

    #: The default ``Signer`` class to instantiate when signing data.
    #: The default is :class:`itsdangerous.signer.Signer`.
    default_signer: type[Signer] = Signer

    #: The default fallback signers to try when unsigning fails.
    default_fallback_signers: list[
        dict[str, t.Any] | tuple[type[Signer], dict[str, t.Any]] | type[Signer]
    ] = []

    # Serializer[str] if no data serializer is provided, or if it returns str.
    @t.overload
    def __init__(
        self: Serializer[str],
        secret_key: str | bytes | cabc.Iterable[str] | cabc.Iterable[bytes],
        salt: str | bytes | None = b"itsdangerous",
        serializer: None | _PDataSerializer[str] = None,
        serializer_kwargs: dict[str, t.Any] | None = None,
        signer: type[Signer] | None = None,
        signer_kwargs: dict[str, t.Any] | None = None,
        fallback_signers: list[
            dict[str, t.Any] | tuple[type[Signer], dict[str, t.Any]] | type[Signer]
        ]
        | None = None,
    ): ...

    # Serializer[bytes] with a bytes data serializer positional argument.
    @t.overload
    def __init__(
        self: Serializer[bytes],
        secret_key: str | bytes | cabc.Iterable[str] | cabc.Iterable[bytes],
        salt: str | bytes | None,
        serializer: _PDataSerializer[bytes],
        serializer_kwargs: dict[str, t.Any] | None = None,
        signer: type[Signer] | None = None,
        signer_kwargs: dict[str, t.Any] | None = None,
        fallback_signers: list[
            dict[str, t.Any] | tuple[type[Signer], dict[str, t.Any]] | type[Signer]
        ]
        | None = None,
    ): ...

    # Serializer[bytes] with a bytes data serializer keyword argument.
    @t.overload
    def __init__(
        self: Serializer[bytes],
        secret_key: str | bytes | cabc.Iterable[str] | cabc.Iterable[bytes],
        salt: str | bytes | None = b"itsdangerous",
        *,
        serializer: _PDataSerializer[bytes],
        serializer_kwargs: dict[str, t.Any] | None = None,
        signer: type[Signer] | None = None,
        signer_kwargs: dict[str, t.Any] | None = None,
        fallback_signers: list[
            dict[str, t.Any] | tuple[type[Signer], dict[str, t.Any]] | type[Signer]
        ]
        | None = None,
    ): ...

    # Fall back with a positional argument. If the strict signature of
    # _PDataSerializer doesn't match, fall back to a union, requiring the user
    # to specify the type.
    @t.overload
    def __init__(
        self,
        secret_key: str | bytes | cabc.Iterable[str] | cabc.Iterable[bytes],
        salt: str | bytes | None,
        serializer: t.Any,
        serializer_kwargs: dict[str, t.Any] | None = None,
        signer: type[Signer] | None = None,
        signer_kwargs: dict[str, t.Any] | None = None,
        fallback_signers: list[
            dict[str, t.Any] | tuple[type[Signer], dict[str, t.Any]] | type[Signer]
        ]
        | None = None,
    ): ...

    # Fall back with a keyword argument.
    @t.overload
    def __init__(
        self,
        secret_key: str | bytes | cabc.Iterable[str] | cabc.Iterable[bytes],
        salt: str | bytes | None = b"itsdangerous",
        *,
        serializer: t.Any,
        serializer_kwargs: dict[str, t.Any] | None = None,
        signer: type[Signer] | None = None,
        signer_kwargs: dict[str, t.Any] | None = None,
        fallback_signers: list[
            dict[str, t.Any] | tuple[type[Signer], dict[str, t.Any]] | type[Signer]
        ]
        | None = None,
    ): ...

    def __init__(
        self,
        secret_key: str | bytes | cabc.Iterable[str] | cabc.Iterable[bytes],
        salt: str | bytes | None = b"itsdangerous",
        serializer: t.Any | None = None,
        serializer_kwargs: dict[str, t.Any] | None = None,
        signer: type[Signer] | None = None,
        signer_kwargs: dict[str, t.Any] | None = None,
        fallback_signers: list[
            dict[str, t.Any] | tuple[type[Signer], dict[str, t.Any]] | type[Signer]
        ]
        | None = None,
    ):
        #: The list of secret keys to try for verifying signatures, from
        #: oldest to newest. The newest (last) key is used for signing.
        #:
        #: This allows a key rotation system to keep a list of allowed
        #: keys and remove expired ones.
        self.secret_keys: list[bytes] = _make_keys_list(secret_key)

        if salt is not None:
            salt = want_bytes(salt)
            # if salt is None then the signer's default is used

        self.salt = salt

        if serializer is None:
            serializer = self.default_serializer

        self.serializer: _PDataSerializer[_TSerialized] = serializer
        self.is_text_serializer: bool = is_text_serializer(serializer)

        if signer is None:
            signer = self.default_signer

        self.signer: type[Signer] = signer
        self.signer_kwargs: dict[str, t.Any] = signer_kwargs or {}

        if fallback_signers is None:
            fallback_signers = list(self.default_fallback_signers)

        self.fallback_signers: list[
            dict[str, t.Any] | tuple[type[Signer], dict[str, t.Any]] | type[Signer]
        ] = fallback_signers
        self.serializer_kwargs: dict[str, t.Any] = serializer_kwargs or {}

    @property
    def secret_key(self) -> bytes:
        """The newest (last) entry in the :attr:`secret_keys` list. This
        is for compatibility from before key rotation support was added.
        """
        return self.secret_keys[-1]

    def load_payload(
        self, payload: bytes, serializer: _PDataSerializer[t.Any] | None = None
    ) -> t.Any:
        """Loads the encoded object. This function raises
        :class:`.BadPayload` if the payload is not valid. The
        ``serializer`` parameter can be used to override the serializer
        stored on the class. The encoded ``payload`` should always be
        bytes.
        """
        if serializer is None:
            use_serializer = self.serializer
            is_text = self.is_text_serializer
        else:
            use_serializer = serializer
            is_text = is_text_serializer(serializer)

        try:
            if is_text:
                return use_serializer.loads(payload.decode("utf-8"))  # type: ignore[arg-type]

            return use_serializer.loads(payload)  # type: ignore[arg-type]
        except Exception as e:
            raise BadPayload(
                "Could not load the payload because an exception"
                " occurred on unserializing the data.",
                original_error=e,
            ) from e

    def dump_payload(self, obj: t.Any) -> bytes:
        """Dumps the encoded object. The return value is always bytes.
        If the internal serializer returns text, the value will be
        encoded as UTF-8.
        """
        return want_bytes(self.serializer.dumps(obj, **self.serializer_kwargs))

    def make_signer(self, salt: str | bytes | None = None) -> Signer:
        """Creates a new instance of the signer to be used. The default
        implementation uses the :class:`.Signer` base class.
        """
        if salt is None:
            salt = self.salt

        return self.signer(self.secret_keys, salt=salt, **self.signer_kwargs)

    def iter_unsigners(self, salt: str | bytes | None = None) -> cabc.Iterator[Signer]:
        """Iterates over all signers to be tried for unsigning. Starts
        with the configured signer, then constructs each signer
        specified in ``fallback_signers``.
        """
        if salt is None:
            salt = self.salt

        yield self.make_signer(salt)

        for fallback in self.fallback_signers:
            if isinstance(fallback, dict):
                kwargs = fallback
                fallback = self.signer
            elif isinstance(fallback, tuple):
                fallback, kwargs = fallback
            else:
                kwargs = self.signer_kwargs

            for secret_key in self.secret_keys:
                yield fallback(secret_key, salt=salt, **kwargs)

    def dumps(self, obj: t.Any, salt: str | bytes | None = None) -> _TSerialized:
        """Returns a signed string serialized with the internal
        serializer. The return value can be either a byte or unicode
        string depending on the format of the internal serializer.
        """
        payload = want_bytes(self.dump_payload(obj))
        rv = self.make_signer(salt).sign(payload)

        if self.is_text_serializer:
            return rv.decode("utf-8")  # type: ignore[return-value]

        return rv  # type: ignore[return-value]

    def dump(self, obj: t.Any, f: t.IO[t.Any], salt: str | bytes | None = None) -> None:
        """Like :meth:`dumps` but dumps into a file. The file handle has
        to be compatible with what the internal serializer expects.
        """
        f.write(self.dumps(obj, salt))

    def loads(
        self, s: str | bytes, salt: str | bytes | None = None, **kwargs: t.Any
    ) -> t.Any:
        """Reverse of :meth:`dumps`. Raises :exc:`.BadSignature` if the
        signature validation fails.
        """
        s = want_bytes(s)
        last_exception = None

        for signer in self.iter_unsigners(salt):
            try:
                return self.load_payload(signer.unsign(s))
            except BadSignature as err:
                last_exception = err

        raise t.cast(BadSignature, last_exception)

    def load(self, f: t.IO[t.Any], salt: str | bytes | None = None) -> t.Any:
        """Like :meth:`loads` but loads from a file."""
        return self.loads(f.read(), salt)

    def loads_unsafe(
        self, s: str | bytes, salt: str | bytes | None = None
    ) -> tuple[bool, t.Any]:
        """Like :meth:`loads` but without verifying the signature. This
        is potentially very dangerous to use depending on how your
        serializer works. The return value is ``(signature_valid,
        payload)`` instead of just the payload. The first item will be a
        boolean that indicates if the signature is valid. This function
        never fails.

        Use it for debugging only and if you know that your serializer
        module is not exploitable (for example, do not use it with a
        pickle serializer).

        .. versionadded:: 0.15
        """
        return self._loads_unsafe_impl(s, salt)

    def _loads_unsafe_impl(
        self,
        s: str | bytes,
        salt: str | bytes | None,
        load_kwargs: dict[str, t.Any] | None = None,
        load_payload_kwargs: dict[str, t.Any] | None = None,
    ) -> tuple[bool, t.Any]:
        """Low level helper function to implement :meth:`loads_unsafe`
        in serializer subclasses.
        """
        if load_kwargs is None:
            load_kwargs = {}

        try:
            return True, self.loads(s, salt=salt, **load_kwargs)
        except BadSignature as e:
            if e.payload is None:
                return False, None

            if load_payload_kwargs is None:
                load_payload_kwargs = {}

            try:
                return (
                    False,
                    self.load_payload(e.payload, **load_payload_kwargs),
                )
            except BadPayload:
                return False, None

    def load_unsafe(
        self, f: t.IO[t.Any], salt: str | bytes | None = None
    ) -> tuple[bool, t.Any]:
        """Like :meth:`loads_unsafe` but loads from a file.

        .. versionadded:: 0.15
        """
        return self.loads_unsafe(f.read(), salt=salt)
