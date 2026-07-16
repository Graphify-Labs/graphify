"""
Utilities for generating random numbers, random sequences, and
random selections.
"""

import networkx as nx
from networkx.utils import py_random_state

__all__ = [
    "powerlaw_sequence",
    "zipf_rv",
    "cumulative_distribution",
    "discrete_sequence",
    "random_weighted_sample",
    "weighted_choice",
]


# The same helpers for choosing random sequences from distributions
# uses Python's random module
# https://docs.python.org/3/library/random.html


@py_random_state(2)
def powerlaw_sequence(n, exponent=2.0, seed=None):
    """
    Return sample sequence of length n from a power law distribution.
    """
    return [seed.paretovariate(exponent - 1) for i in range(n)]


@py_random_state(2)
def zipf_rv(alpha, xmin=1, seed=None):
    r"""Returns a random value chosen from the Zipf distribution.

    The return value is an integer drawn from the probability distribution

    .. math::

        p(x)=\frac{x^{-\alpha}}{\zeta(\alpha, x_{\min})},

    where $\zeta(\alpha, x_{\min})$ is the Hurwitz zeta function.

    Parameters
    ----------
    alpha : float
      Exponent value of the distribution
    xmin : int
      Minimum value
    seed : integer, random_state, or None (default)
        Indicator of random number generation state.
        See :ref:`Randomness<randomness>`.

    Returns
    -------
    x : int
      Random value from Zipf distribution

    Raises
    ------
    ValueError:
      If xmin < 1 or
      If alpha <= 1

    Notes
    -----
    The rejection algorithm generates random values for a the power-law
    distribution in uniformly bounded expected time dependent on
    parameters.  See [1]_ for details on its operation.

    Examples
    --------
    >>> nx.utils.zipf_rv(alpha=2, xmin=3, seed=42)
    8

    References
    ----------
    .. [1] Luc Devroye, Non-Uniform Random Variate Generation,
       Springer-Verlag, New York, 1986.
    """
    if xmin < 1:
        raise ValueError("xmin < 1")
    if alpha <= 1:
        raise ValueError("a <= 1.0")
    a1 = alpha - 1.0
    b = 2**a1
    while True:
        u = 1.0 - seed.random()  # u in (0,1]
        v = seed.random()  # v in [0,1)
        x = int(xmin * u ** -(1.0 / a1))
        t = (1.0 + (1.0 / x)) ** a1
        if v * x * (t - 1.0) / (b - 1.0) <= t / b:
            break
    return x


def cumulative_distribution(distribution):
    """Returns normalized cumulative distribution from discrete distribution."""

    cdf = [0.0]
    psum = sum(distribution)
    for i in range(len(distribution)):
        cdf.append(cdf[i] + distribution[i] / psum)
    return cdf


@py_random_state(3)
def discrete_sequence(n, distribution=None, cdistribution=None, seed=None):
    """
    Return sample sequence of length n from a given discrete distribution
    or discrete cumulative distribution.

    One of the following must be specified.

    distribution = histogram of values, will be normalized

    cdistribution = normalized discrete cumulative distribution

    """
    import bisect

    if cdistribution is not None:
        cdf = cdistribution
    elif distribution is not None:
        cdf = cumulative_distribution(distribution)
    else:
        raise nx.NetworkXError(
            "discrete_sequence: distribution or cdistribution missing"
        )

    # get a uniform random number
    inputseq = [seed.random() for i in range(n)]

    # choose from CDF
    seq = [bisect.bisect_left(cdf, s) - 1 for s in inputseq]
    return seq


@py_random_state(2)
def random_weighted_sample(mapping, k, seed=None):
    """Returns k items without replacement from a weighted sample.

    The input is a dictionary of items with weights as values.
    """
    if k > len(mapping):
        raise ValueError("sample larger than population")
    sample = set()
    while len(sample) < k:
        sample.add(weighted_choice(mapping, seed))
    return list(sample)


@py_random_state(1)
def weighted_choice(mapping, seed=None):
    """Returns a single element from a weighted sample.

    The input is a dictionary of items with weights as values.
    """
    # use roulette method
    rnd = seed.random() * sum(mapping.values())
    for k, w in mapping.items():
        rnd -= w
        if rnd < 0:
            return k
