"""
Thin wrappers around `itertools`.
"""
import itertools
import math

from ..auto import tqdm as tqdm_auto

__author__ = {"github.com/": ["casperdcl"]}
__all__ = [
    'chain', 'product', 'permutations', 'combinations', 'combinations_with_replacement', 'batched']


def chain(*iterables, total=None, tqdm_class=tqdm_auto, **kwargs):
    """Equivalent of `itertools.chain`."""
    if total is None:
        try:
            total = sum(map(len, iterables))
        except (TypeError, AttributeError):
            pass
    return tqdm_class(itertools.chain(*iterables), total=total, **kwargs)


def product(*iterables, repeat=1, total=None, tqdm_class=tqdm_auto, **kwargs):
    """Equivalent of `itertools.product`."""
    if total is None:
        try:
            lens = list(map(len, iterables))
        except (TypeError, AttributeError):
            pass
        else:
            total = math.prod(lens) ** repeat
    yield from tqdm_class(itertools.product(*iterables, repeat=repeat), total=total, **kwargs)


def permutations(iterable, r=None, total=None, tqdm_class=tqdm_auto, **kwargs):
    """Equivalent of `itertools.permutations`."""
    if total is None:
        try:
            n = len(iterable)
        except (TypeError, AttributeError):
            pass
        else:
            r = n if r is None else r
            if r > n:
                total = 0
            else:
                total = math.perm(n, r)
    return tqdm_class(itertools.permutations(iterable, r), total=total, **kwargs)


def combinations(iterable, r, total=None, tqdm_class=tqdm_auto, **kwargs):
    """Equivalent of `itertools.combinations`."""
    if total is None:
        try:
            n = len(iterable)
        except (TypeError, AttributeError):
            pass
        else:
            if r > n:
                total = 0
            else:
                total = math.comb(n, r)
    return tqdm_class(itertools.combinations(iterable, r), total=total, **kwargs)


def combinations_with_replacement(iterable, r, total=None, tqdm_class=tqdm_auto, **kwargs):
    """Equivalent of `itertools.combinations_with_replacement`."""
    if total is None:
        try:
            n = len(iterable)
        except (TypeError, AttributeError):
            pass
        else:
            total = 1
            for i in range(n+r-1, n-1, -1):
                total *= i
            for i in range(1, r+1):
                total //= i
    return tqdm_class(itertools.combinations_with_replacement(iterable, r), total=total, **kwargs)


def batched(iterable, n, total=None, tqdm_class=tqdm_auto, **kwargs):
    """Equivalent of `itertools.batched`."""
    if total is None:
        try:
            total = len(iterable)
        except (TypeError, AttributeError):
            pass
    return tqdm_class(itertools.batched(iterable, n), unit_scale=n,
                      total=(total+n-1) // n if total is not None else None,
                      **kwargs)
