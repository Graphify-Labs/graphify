from __future__ import annotations

from typing import Any, TYPE_CHECKING
from functools import partial

import pytest
import numpy as np

if TYPE_CHECKING:
    from collections.abc import Callable

AR = np.array(0)
AR.setflags(write=False)

KACF = frozenset({None, "K", "A", "C", "F"})
ACF = frozenset({None, "A", "C", "F"})
CF = frozenset({None, "C", "F"})

order_list: list[tuple[frozenset[str | None], Callable[..., Any]]] = [
    (KACF, partial(np.ndarray, 1)),
    (KACF, AR.tobytes),
    (KACF, partial(AR.astype, int)),
    (KACF, AR.copy),
    (ACF, partial(AR.reshape, 1)),
    (KACF, AR.flatten),
    (KACF, AR.ravel),
    (KACF, partial(np.array, 1)),
    # NOTE: __call__ is needed due to mypy 1.11 bugs (#17620, #17631)
    (CF, partial(np.zeros.__call__, 1)),
    (CF, partial(np.ones.__call__, 1)),
    (CF, partial(np.empty.__call__, 1)),
    (CF, partial(np.full, 1, 1)),
    (KACF, partial(np.zeros_like, AR)),
    (KACF, partial(np.ones_like, AR)),
    (KACF, partial(np.empty_like, AR)),
    (KACF, partial(np.full_like, AR, 1)),
    (KACF, partial(np.add.__call__, 1, 1)),  # i.e. np.ufunc.__call__
    (ACF, partial(np.reshape, AR, 1)),
    (KACF, partial(np.ravel, AR)),
    (KACF, partial(np.asarray, 1)),
    (KACF, partial(np.asanyarray, 1)),
]

for order_set, func in order_list:
    for order in order_set:
        func(order=order)

    invalid_orders = KACF - order_set
    for order in invalid_orders:
        with pytest.raises(ValueError):
            func(order=order)
