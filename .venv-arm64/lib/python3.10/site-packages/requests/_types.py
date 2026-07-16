"""
requests._types
~~~~~~~~~~~~~~~

This module contains type aliases used internally by the Requests library.
These types are not part of the public API and must not be relied upon
by external code.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence
from typing import (
    TYPE_CHECKING,
    Any,
    Protocol,
    TypeAlias,
    TypeVar,
    runtime_checkable,
)

_T_co = TypeVar("_T_co", covariant=True)
_KT_co = TypeVar("_KT_co", covariant=True)
_VT_co = TypeVar("_VT_co", covariant=True)


@runtime_checkable
class SupportsRead(Protocol[_T_co]):
    def read(self, length: int = ..., /) -> _T_co: ...


@runtime_checkable
class SupportsItems(Protocol[_KT_co, _VT_co]):
    def items(self) -> Iterable[tuple[_KT_co, _VT_co]]: ...


# These are needed at runtime for default_hooks() return type
HookType: TypeAlias = Callable[["Response"], Any]
HooksInputType: TypeAlias = Mapping[str, Iterable[HookType] | HookType]


def is_prepared(request: PreparedRequest) -> TypeIs[_ValidatedRequest]:
    """Verify a PreparedRequest has been fully prepared."""
    if TYPE_CHECKING:
        return request.url is not None and request.method is not None
    # noop at runtime to avoid AssertionError
    return True


if TYPE_CHECKING:
    from http.cookiejar import CookieJar
    from typing import TypeAlias, TypedDict

    from typing_extensions import (
        Buffer,  # TODO: move to collections.abc when Python >= 3.12
        TypeIs,  # TODO: move to typing when Python >= 3.13
    )

    from .auth import AuthBase
    from .cookies import RequestsCookieJar
    from .models import PreparedRequest, Response
    from .structures import CaseInsensitiveDict

    class _ValidatedRequest(PreparedRequest):
        """Subtype asserting a PreparedRequest has been fully prepared before calling.

        The override suppression is required because mutable attribute types are
        invariant (Liskov), but we only narrow after preparation is complete. This
        is the explicit contract for Requests but Python's typing doesn't have a
        better way to represent the requirement.
        """

        url: str  # type: ignore[reportIncompatibleVariableOverride]
        method: str  # type: ignore[reportIncompatibleVariableOverride]

    # Type aliases for core API concepts (ordered by request() signature)
    UriType: TypeAlias = str | bytes

    _ParamsMappingKeyType: TypeAlias = str | bytes | int | float
    _ParamsMappingValueType: TypeAlias = (
        str | bytes | int | float | Iterable[str | bytes | int | float] | None
    )
    ParamsType: TypeAlias = (
        SupportsItems[_ParamsMappingKeyType, _ParamsMappingValueType]
        | tuple[tuple[_ParamsMappingKeyType, _ParamsMappingValueType], ...]
        | Iterable[tuple[_ParamsMappingKeyType, _ParamsMappingValueType]]
        | str
        | bytes
        | None
    )

    KVDataType: TypeAlias = Iterable[tuple[Any, Any]] | SupportsItems[Any, Any]

    RawDataType: TypeAlias = KVDataType | str | bytes
    StreamDataType: TypeAlias = SupportsRead[str | bytes]
    EncodableDataType: TypeAlias = RawDataType | StreamDataType

    DataType: TypeAlias = (
        KVDataType
        | Iterable[bytes | str]
        | str
        | bytes
        | Buffer
        | SupportsRead[str | bytes]
        | None
    )

    BodyType: TypeAlias = (
        bytes | str | Iterable[bytes | str] | SupportsRead[bytes | str] | None
    )

    HeadersType: TypeAlias = Mapping[str, str | bytes] | None

    CookiesType: TypeAlias = RequestsCookieJar | Mapping[str, str]

    # Building blocks for FilesType
    _FileName: TypeAlias = str | None
    _FileContent: TypeAlias = SupportsRead[str | bytes] | str | bytes
    _FileSpecBasic: TypeAlias = tuple[_FileName, _FileContent]
    _FileSpecWithContentType: TypeAlias = tuple[_FileName, _FileContent, str]
    _FileSpecWithHeaders: TypeAlias = tuple[
        _FileName, _FileContent, str, CaseInsensitiveDict[str] | Mapping[str, str]
    ]
    _FileSpec: TypeAlias = (
        _FileContent | _FileSpecBasic | _FileSpecWithContentType | _FileSpecWithHeaders
    )
    FilesType: TypeAlias = (
        Mapping[str, _FileSpec] | Iterable[tuple[str, _FileSpec]] | None
    )

    AuthType: TypeAlias = (
        tuple[str, str] | AuthBase | Callable[[PreparedRequest], PreparedRequest] | None
    )

    TimeoutType: TypeAlias = float | tuple[float | None, float | None] | None
    ProxiesType: TypeAlias = MutableMapping[str, str]
    HooksType: TypeAlias = dict[str, list[HookType]] | None
    VerifyType: TypeAlias = bool | str
    CertType: TypeAlias = str | tuple[str, str] | None
    JsonType: TypeAlias = (
        None
        | bool
        | int
        | float
        | str
        | Sequence["JsonType"]
        | Mapping[str, "JsonType"]
    )

    # TypedDicts for Unpack kwargs (PEP 692)

    class BaseRequestKwargs(TypedDict, total=False):
        headers: HeadersType
        cookies: RequestsCookieJar | CookieJar | dict[str, str] | None
        files: FilesType
        auth: AuthType
        timeout: TimeoutType
        allow_redirects: bool
        proxies: dict[str, str] | None
        hooks: HooksInputType | None
        stream: bool | None
        verify: VerifyType | None
        cert: CertType

    class RequestKwargs(BaseRequestKwargs, total=False):
        """kwargs for request(), options(), head(), delete()."""

        params: ParamsType
        data: DataType
        json: JsonType

    class GetKwargs(BaseRequestKwargs, total=False):
        data: DataType
        json: JsonType

    class PostKwargs(BaseRequestKwargs, total=False):
        params: ParamsType

    class DataKwargs(BaseRequestKwargs, total=False):
        """kwargs for put(), patch()."""

        params: ParamsType
        json: JsonType
