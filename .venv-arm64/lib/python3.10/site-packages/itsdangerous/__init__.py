from __future__ import annotations

import typing as t

from .encoding import base64_decode as base64_decode
from .encoding import base64_encode as base64_encode
from .encoding import want_bytes as want_bytes
from .exc import BadData as BadData
from .exc import BadHeader as BadHeader
from .exc import BadPayload as BadPayload
from .exc import BadSignature as BadSignature
from .exc import BadTimeSignature as BadTimeSignature
from .exc import SignatureExpired as SignatureExpired
from .serializer import Serializer as Serializer
from .signer import HMACAlgorithm as HMACAlgorithm
from .signer import NoneAlgorithm as NoneAlgorithm
from .signer import Signer as Signer
from .timed import TimedSerializer as TimedSerializer
from .timed import TimestampSigner as TimestampSigner
from .url_safe import URLSafeSerializer as URLSafeSerializer
from .url_safe import URLSafeTimedSerializer as URLSafeTimedSerializer


def __getattr__(name: str) -> t.Any:
    if name == "__version__":
        import importlib.metadata
        import warnings

        warnings.warn(
            "The '__version__' attribute is deprecated and will be removed in"
            " ItsDangerous 2.3. Use feature detection or"
            " 'importlib.metadata.version(\"itsdangerous\")' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return importlib.metadata.version("itsdangerous")

    raise AttributeError(name)
