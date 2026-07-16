import inspect
import typing as t
from functools import WRAPPER_ASSIGNMENTS
from functools import wraps

from .utils import _PassArg
from .utils import pass_eval_context

if t.TYPE_CHECKING:
    import typing_extensions as te

V = t.TypeVar("V")


def async_variant(normal_func):  # type: ignore
    def decorator(async_func):  # type: ignore
        pass_arg = _PassArg.from_obj(normal_func)
        need_eval_context = pass_arg is None

        if pass_arg is _PassArg.environment:

            def is_async(args: t.Any) -> bool:
                return t.cast(bool, args[0].is_async)

        else:

            def is_async(args: t.Any) -> bool:
                return t.cast(bool, args[0].environment.is_async)

        # Take the doc and annotations from the sync function, but the
        # name from the async function. Pallets-Sphinx-Themes
        # build_function_directive expects __wrapped__ to point to the
        # sync function.
        async_func_attrs = ("__module__", "__name__", "__qualname__")
        normal_func_attrs = tuple(set(WRAPPER_ASSIGNMENTS).difference(async_func_attrs))

        @wraps(normal_func, assigned=normal_func_attrs)
        @wraps(async_func, assigned=async_func_attrs, updated=())
        def wrapper(*args, **kwargs):  # type: ignore
            b = is_async(args)

            if need_eval_context:
                args = args[1:]

            if b:
                return async_func(*args, **kwargs)

            return normal_func(*args, **kwargs)

        if need_eval_context:
            wrapper = pass_eval_context(wrapper)

        wrapper.jinja_async_variant = True  # type: ignore[attr-defined]
        return wrapper

    return decorator


_common_primitives = {int, float, bool, str, list, dict, tuple, type(None)}


async def auto_await(value: t.Union[t.Awaitable["V"], "V"]) -> "V":
    # Avoid a costly call to isawaitable
    if type(value) in _common_primitives:
        return t.cast("V", value)

    if inspect.isawaitable(value):
        return await t.cast("t.Awaitable[V]", value)

    return value


class _IteratorToAsyncIterator(t.Generic[V]):
    def __init__(self, iterator: "t.Iterator[V]"):
        self._iterator = iterator

    def __aiter__(self) -> "te.Self":
        return self

    async def __anext__(self) -> V:
        try:
            return next(self._iterator)
        except StopIteration as e:
            raise StopAsyncIteration(e.value) from e


def auto_aiter(
    iterable: "t.Union[t.AsyncIterable[V], t.Iterable[V]]",
) -> "t.AsyncIterator[V]":
    if hasattr(iterable, "__aiter__"):
        return iterable.__aiter__()
    else:
        return _IteratorToAsyncIterator(iter(iterable))


async def auto_to_list(
    value: "t.Union[t.AsyncIterable[V], t.Iterable[V]]",
) -> t.List["V"]:
    return [x async for x in auto_aiter(value)]
