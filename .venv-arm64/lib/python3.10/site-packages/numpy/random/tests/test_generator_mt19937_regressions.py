from numpy.testing import (assert_, assert_array_equal)
import numpy as np
import pytest
from numpy.random import Generator, MT19937


class TestRegression:

    def setup_method(self):
        self.mt19937 = Generator(MT19937(121263137472525314065))

    def test_vonmises_range(self):
        # Make sure generated random variables are in [-pi, pi].
        # Regression test for ticket #986.
        for mu in np.linspace(-7., 7., 5):
            r = self.mt19937.vonmises(mu, 1, 50)
            assert_(np.all(r > -np.pi) and np.all(r <= np.pi))

    def test_hypergeometric_range(self):
        # Test for ticket #921
        assert_(np.all(self.mt19937.hypergeometric(3, 18, 11, size=10) < 4))
        assert_(np.all(self.mt19937.hypergeometric(18, 3, 11, size=10) > 0))

        # Test for ticket #5623
        args = (2**20 - 2, 2**20 - 2, 2**20 - 2)  # Check for 32-bit systems
        assert_(self.mt19937.hypergeometric(*args) > 0)

    def test_logseries_convergence(self):
        # Test for ticket #923
        N = 1000
        rvsn = self.mt19937.logseries(0.8, size=N)
        # these two frequency counts should be close to theoretical
        # numbers with this large sample
        # theoretical large N result is 0.49706795
        freq = np.sum(rvsn == 1) / N
        msg = f'Frequency was {freq:f}, should be > 0.45'
        assert_(freq > 0.45, msg)
        # theoretical large N result is 0.19882718
        freq = np.sum(rvsn == 2) / N
        msg = f'Frequency was {freq:f}, should be < 0.23'
        assert_(freq < 0.23, msg)

    def test_shuffle_mixed_dimension(self):
        # Test for trac ticket #2074
        for t in [[1, 2, 3, None],
                  [(1, 1), (2, 2), (3, 3), None],
                  [1, (2, 2), (3, 3), None],
                  [(1, 1), 2, 3, None]]:
            mt19937 = Generator(MT19937(12345))
            shuffled = np.array(t, dtype=object)
            mt19937.shuffle(shuffled)
            expected = np.array([t[2], t[0], t[3], t[1]], dtype=object)
            assert_array_equal(np.array(shuffled, dtype=object), expected)

    def test_call_within_randomstate(self):
        # Check that custom BitGenerator does not call into global state
        res = np.array([1, 8, 0, 1, 5, 3, 3, 8, 1, 4])
        for i in range(3):
            mt19937 = Generator(MT19937(i))
            m = Generator(MT19937(4321))
            # If m.state is not honored, the result will change
            assert_array_equal(m.choice(10, size=10, p=np.ones(10)/10.), res)

    def test_multivariate_normal_size_types(self):
        # Test for multivariate_normal issue with 'size' argument.
        # Check that the multivariate_normal size argument can be a
        # numpy integer.
        self.mt19937.multivariate_normal([0], [[0]], size=1)
        self.mt19937.multivariate_normal([0], [[0]], size=np.int_(1))
        self.mt19937.multivariate_normal([0], [[0]], size=np.int64(1))

    def test_beta_small_parameters(self):
        # Test that beta with small a and b parameters does not produce
        # NaNs due to roundoff errors causing 0 / 0, gh-5851
        x = self.mt19937.beta(0.0001, 0.0001, size=100)
        assert_(not np.any(np.isnan(x)), 'Nans in mt19937.beta')

    def test_beta_very_small_parameters(self):
        # gh-24203: beta would hang with very small parameters.
        self.mt19937.beta(1e-49, 1e-40)

    def test_beta_ridiculously_small_parameters(self):
        # gh-24266: beta would generate nan when the parameters
        # were subnormal or a small multiple of the smallest normal.
        tiny = np.finfo(1.0).tiny
        x = self.mt19937.beta(tiny/32, tiny/40, size=50)
        assert not np.any(np.isnan(x))

    def test_beta_expected_zero_frequency(self):
        # gh-24475: For small a and b (e.g. a=0.0025, b=0.0025), beta
        # would generate too many zeros.
        a = 0.0025
        b = 0.0025
        n = 1000000
        x = self.mt19937.beta(a, b, size=n)
        nzeros = np.count_nonzero(x == 0)
        # beta CDF at x = np.finfo(np.double).smallest_subnormal/2
        # is p = 0.0776169083131899, e.g,
        #
        #    import numpy as np
        #    from mpmath import mp
        #    mp.dps = 160
        #    x = mp.mpf(np.finfo(np.float64).smallest_subnormal)/2
        #    # CDF of the beta distribution at x:
        #    p = mp.betainc(a, b, x1=0, x2=x, regularized=True)
        #    n = 1000000
        #    exprected_freq = float(n*p)
        #
        expected_freq = 77616.90831318991
        assert 0.95*expected_freq < nzeros < 1.05*expected_freq

    def test_choice_sum_of_probs_tolerance(self):
        # The sum of probs should be 1.0 with some tolerance.
        # For low precision dtypes the tolerance was too tight.
        # See numpy github issue 6123.
        a = [1, 2, 3]
        counts = [4, 4, 2]
        for dt in np.float16, np.float32, np.float64:
            probs = np.array(counts, dtype=dt) / sum(counts)
            c = self.mt19937.choice(a, p=probs)
            assert_(c in a)
            with pytest.raises(ValueError):
                self.mt19937.choice(a, p=probs*0.9)

    def test_shuffle_of_array_of_different_length_strings(self):
        # Test that permuting an array of different length strings
        # will not cause a segfault on garbage collection
        # Tests gh-7710

        a = np.array(['a', 'a' * 1000])

        for _ in range(100):
            self.mt19937.shuffle(a)

        # Force Garbage Collection - should not segfault.
        import gc
        gc.collect()

    def test_shuffle_of_array_of_objects(self):
        # Test that permuting an array of objects will not cause
        # a segfault on garbage collection.
        # See gh-7719
        a = np.array([np.arange(1), np.arange(4)], dtype=object)

        for _ in range(1000):
            self.mt19937.shuffle(a)

        # Force Garbage Collection - should not segfault.
        import gc
        gc.collect()

    def test_permutation_subclass(self):

        class N(np.ndarray):
            pass

        mt19937 = Generator(MT19937(1))
        orig = np.arange(3).view(N)
        perm = mt19937.permutation(orig)
        assert_array_equal(perm, np.array([2, 0, 1]))
        assert_array_equal(orig, np.arange(3).view(N))

        class M:
            a = np.arange(5)

            def __array__(self, dtype=None, copy=None):
                return self.a

        mt19937 = Generator(MT19937(1))
        m = M()
        perm = mt19937.permutation(m)
        assert_array_equal(perm, np.array([4, 1, 3, 0, 2]))
        assert_array_equal(m.__array__(), np.arange(5))

    def test_gamma_0(self):
        assert self.mt19937.standard_gamma(0.0) == 0.0
        assert_array_equal(self.mt19937.standard_gamma([0.0]), 0.0)

        actual = self.mt19937.standard_gamma([0.0], dtype='float')
        expected = np.array([0.], dtype=np.float32)
        assert_array_equal(actual, expected)

    def test_geometric_tiny_prob(self):
        # Regression test for gh-17007.
        # When p = 1e-30, the probability that a sample will exceed 2**63-1
        # is 0.9999999999907766, so we expect the result to be all 2**63-1.
        assert_array_equal(self.mt19937.geometric(p=1e-30, size=3),
                           np.iinfo(np.int64).max)

    def test_zipf_large_parameter(self):
        # Regression test for part of gh-9829: a call such as rng.zipf(10000)
        # would hang.
        n = 8
        sample = self.mt19937.zipf(10000, size=n)
        assert_array_equal(sample, np.ones(n, dtype=np.int64))

    def test_zipf_a_near_1(self):
        # Regression test for gh-9829: a call such as rng.zipf(1.0000000000001)
        # would hang.
        n = 100000
        sample = self.mt19937.zipf(1.0000000000001, size=n)
        # Not much of a test, but let's do something more than verify that
        # it doesn't hang.  Certainly for a monotonically decreasing
        # discrete distribution truncated to signed 64 bit integers, more
        # than half should be less than 2**62.
        assert np.count_nonzero(sample < 2**62) > n/2
