from __future__ import annotations

import typing as t

from .accept import Accept as Accept
from .accept import CharsetAccept as CharsetAccept
from .accept import LanguageAccept as LanguageAccept
from .accept import MIMEAccept as MIMEAccept
from .auth import Authorization as Authorization
from .auth import WWWAuthenticate as WWWAuthenticate
from .cache_control import RequestCacheControl as RequestCacheControl
from .cache_control import ResponseCacheControl as ResponseCacheControl
from .csp import ContentSecurityPolicy as ContentSecurityPolicy
from .etag import ETags as ETags
from .file_storage import FileMultiDict as FileMultiDict
from .file_storage import FileStorage as FileStorage
from .headers import EnvironHeaders as EnvironHeaders
from .headers import Headers as Headers
from .mixins import ImmutableDictMixin as ImmutableDictMixin
from .mixins import ImmutableHeadersMixin as ImmutableHeadersMixin
from .mixins import ImmutableListMixin as ImmutableListMixin
from .mixins import ImmutableMultiDictMixin as ImmutableMultiDictMixin
from .mixins import UpdateDictMixin as UpdateDictMixin
from .range import ContentRange as ContentRange
from .range import IfRange as IfRange
from .range import Range as Range
from .structures import CallbackDict as CallbackDict
from .structures import CombinedMultiDict as CombinedMultiDict
from .structures import HeaderSet as HeaderSet
from .structures import ImmutableDict as ImmutableDict
from .structures import ImmutableList as ImmutableList
from .structures import ImmutableMultiDict as ImmutableMultiDict
from .structures import ImmutableTypeConversionDict as ImmutableTypeConversionDict
from .structures import iter_multi_items as iter_multi_items
from .structures import MultiDict as MultiDict
from .structures import TypeConversionDict as TypeConversionDict


def __getattr__(name: str) -> t.Any:
    import warnings

    if name == "OrderedMultiDict":
        from .structures import _OrderedMultiDict

        warnings.warn(
            "'OrderedMultiDict' is deprecated and will be removed in Werkzeug"
            " 3.2. Use 'MultiDict' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return _OrderedMultiDict

    if name == "ImmutableOrderedMultiDict":
        from .structures import _ImmutableOrderedMultiDict

        warnings.warn(
            "'OrderedMultiDict' is deprecated and will be removed in Werkzeug"
            " 3.2. Use 'ImmutableMultiDict' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return _ImmutableOrderedMultiDict

    raise AttributeError(name)
