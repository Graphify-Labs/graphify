from __future__ import annotations

import json as _json
import typing as t


class _CompactJSON:
    """Wrapper around json module that strips whitespace."""

    @staticmethod
    def loads(payload: str | bytes) -> t.Any:
        return _json.loads(payload)

    @staticmethod
    def dumps(obj: t.Any, **kwargs: t.Any) -> str:
        kwargs.setdefault("ensure_ascii", False)
        kwargs.setdefault("separators", (",", ":"))
        return _json.dumps(obj, **kwargs)
