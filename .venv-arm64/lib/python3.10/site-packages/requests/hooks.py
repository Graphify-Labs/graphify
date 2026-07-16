"""
requests.hooks
~~~~~~~~~~~~~~

This module provides the capabilities for the Requests hooks system.

Available hooks:

``response``:
    The response generated from a Request.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from . import _types as _t
    from .models import Response

HOOKS: list[str] = ["response"]


def default_hooks() -> dict[str, list[_t.HookType]]:
    return {event: [] for event in HOOKS}


# TODO: response is the only one


def dispatch_hook(
    key: str,
    hooks: _t.HooksInputType | None,
    hook_data: Response,
    **kwargs: Any,
) -> Response:
    """Dispatches a hook dictionary on a given piece of data."""
    hooks_dict = hooks or {}
    hook_list: Iterable[_t.HookType] | _t.HookType | None = hooks_dict.get(key)
    if hook_list:
        if isinstance(hook_list, Callable):
            hook_list = [hook_list]
        for hook in hook_list:
            _hook_data = hook(hook_data, **kwargs)
            if _hook_data is not None:
                hook_data = _hook_data
    return hook_data
