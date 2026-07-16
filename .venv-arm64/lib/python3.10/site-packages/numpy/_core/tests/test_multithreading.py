import concurrent.futures
import threading
import string

import numpy as np
import pytest

from numpy.testing import IS_WASM, IS_64BIT
from numpy.testing._private.utils import run_threaded
from numpy._core import _rational_tests

if IS_WASM:
    pytest.skip(allow_module_level=True, reason="no threading support in wasm")


def test_parallel_randomstate_creation():
    # if the coercion cache is enabled and not thread-safe, creating
    # RandomState instances simultaneously leads to a data race
    def func(seed):
        np.random.RandomState(seed)

    run_threaded(func, 500, pass_count=True)


def test_parallel_ufunc_execution():
    # if the loop data cache or dispatch cache are not thread-safe
    # computing ufuncs simultaneously in multiple threads leads
    # to a data race that causes crashes or spurious exceptions
    def func():
        arr = np.random.random((25,))
        np.isnan(arr)

    run_threaded(func, 500)

    # see gh-26690
    NUM_THREADS = 50

    a = np.ones(1000)

    def f(b):
        b.wait()
        return a.sum()

    run_threaded(f, NUM_THREADS, pass_barrier=True)


def test_temp_elision_thread_safety():
    amid = np.ones(50000)
    bmid = np.ones(50000)
    alarge = np.ones(1000000)
    blarge = np.ones(1000000)

    def func(count):
        if count % 4 == 0:
            (amid * 2) + bmid
        elif count % 4 == 1:
            (amid + bmid) - 2
        elif count % 4 == 2:
            (alarge * 2) + blarge
        else:
            (alarge + blarge) - 2

    run_threaded(func, 100, pass_count=True)


def test_eigvalsh_thread_safety():
    # if lapack isn't thread safe this will randomly segfault or error
    # see gh-24512
    rng = np.random.RandomState(873699172)
    matrices = (
        rng.random((5, 10, 10, 3, 3)),
        rng.random((5, 10, 10, 3, 3)),
    )

    run_threaded(lambda i: np.linalg.eigvalsh(matrices[i]), 2,
                 pass_count=True)


def test_printoptions_thread_safety():
    # until NumPy 2.1 the printoptions state was stored in globals
    # this verifies that they are now stored in a context variable
    b = threading.Barrier(2)

    def legacy_113():
        np.set_printoptions(legacy='1.13', precision=12)
        b.wait()
        po = np.get_printoptions()
        assert po['legacy'] == '1.13'
        assert po['precision'] == 12
        orig_linewidth = po['linewidth']
        with np.printoptions(linewidth=34, legacy='1.21'):
            po = np.get_printoptions()
            assert po['legacy'] == '1.21'
            assert po['precision'] == 12
            assert po['linewidth'] == 34
        po = np.get_printoptions()
        assert po['linewidth'] == orig_linewidth
        assert po['legacy'] == '1.13'
        assert po['precision'] == 12

    def legacy_125():
        np.set_printoptions(legacy='1.25', precision=7)
        b.wait()
        po = np.get_printoptions()
        assert po['legacy'] == '1.25'
        assert po['precision'] == 7
        orig_linewidth = po['linewidth']
        with np.printoptions(linewidth=6, legacy='1.13'):
            po = np.get_printoptions()
            assert po['legacy'] == '1.13'
            assert po['precision'] == 7
            assert po['linewidth'] == 6
        po = np.get_printoptions()
        assert po['linewidth'] == orig_linewidth
        assert po['legacy'] == '1.25'
        assert po['precision'] == 7

    task1 = threading.Thread(target=legacy_113)
    task2 = threading.Thread(target=legacy_125)

    task1.start()
    task2.start()


def test_parallel_reduction():
    # gh-28041
    NUM_THREADS = 50

    x = np.arange(1000)

    def closure(b):
        b.wait()
        np.sum(x)

    run_threaded(closure, NUM_THREADS, pass_barrier=True)


def test_parallel_flat_iterator():
    # gh-28042
    x = np.arange(20).reshape(5, 4).T

    def closure(b):
        b.wait()
        for _ in range(100):
            list(x.flat)

    run_threaded(closure, outer_iterations=100, pass_barrier=True)

    # gh-28143
    def prepare_args():
        return [np.arange(10)]

    def closure(x, b):
        b.wait()
        for _ in range(100):
            y = np.arange(10)
            y.flat[x] = x

    run_threaded(closure, pass_barrier=True, prepare_args=prepare_args)


def test_multithreaded_repeat():
    x0 = np.arange(10)

    def closure(b):
        b.wait()
        for _ in range(100):
            x = np.repeat(x0, 2, axis=0)[::2]

    run_threaded(closure, max_workers=10, pass_barrier=True)


def test_structured_advanced_indexing():
    # Test that copyswap(n) used by integer array indexing is threadsafe
    # for structured datatypes, see gh-15387. This test can behave randomly.

    # Create a deeply nested dtype to make a failure more likely:
    dt = np.dtype([("", "f8")])
    dt = np.dtype([("", dt)] * 2)
    dt = np.dtype([("", dt)] * 2)
    # The array should be large enough to likely run into threading issues
    arr = np.random.uniform(size=(6000, 8)).view(dt)[:, 0]

    rng = np.random.default_rng()

    def func(arr):
        indx = rng.integers(0, len(arr), size=6000, dtype=np.intp)
        arr[indx]

    tpe = concurrent.futures.ThreadPoolExecutor(max_workers=8)
    futures = [tpe.submit(func, arr) for _ in range(10)]
    for f in futures:
        f.result()

    assert arr.dtype is dt


def test_structured_threadsafety2():
    # Nonzero (and some other functions) should be threadsafe for
    # structured datatypes, see gh-15387. This test can behave randomly.
    from concurrent.futures import ThreadPoolExecutor

    # Create a deeply nested dtype to make a failure more likely:
    dt = np.dtype([("", "f8")])
    dt = np.dtype([("", dt)])
    dt = np.dtype([("", dt)] * 2)
    # The array should be large enough to likely run into threading issues
    arr = np.random.uniform(size=(5000, 4)).view(dt)[:, 0]

    def func(arr):
        arr.nonzero()

    tpe = ThreadPoolExecutor(max_workers=8)
    futures = [tpe.submit(func, arr) for _ in range(10)]
    for f in futures:
        f.result()

    assert arr.dtype is dt


def test_stringdtype_multithreaded_access_and_mutation(
        dtype, random_string_list):
    # this test uses an RNG and may crash or cause deadlocks if there is a
    # threading bug
    rng = np.random.default_rng(0x4D3D3D3)

    chars = list(string.ascii_letters + string.digits)
    chars = np.array(chars, dtype="U1")
    ret = rng.choice(chars, size=100 * 10, replace=True)
    random_string_list = ret.view("U100")

    def func(arr):
        rnd = rng.random()
        # either write to random locations in the array, compute a ufunc, or
        # re-initialize the array
        if rnd < 0.25:
            num = np.random.randint(0, arr.size)
            arr[num] = arr[num] + "hello"
        elif rnd < 0.5:
            if rnd < 0.375:
                np.add(arr, arr)
            else:
                np.add(arr, arr, out=arr)
        elif rnd < 0.75:
            if rnd < 0.875:
                np.multiply(arr, np.int64(2))
            else:
                np.multiply(arr, np.int64(2), out=arr)
        else:
            arr[:] = random_string_list

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as tpe:
        arr = np.array(random_string_list, dtype=dtype)
        futures = [tpe.submit(func, arr) for _ in range(500)]

        for f in futures:
            f.result()


@pytest.mark.skipif(
    not IS_64BIT,
    reason="Sometimes causes failures or crashes due to OOM on 32 bit runners"
)
def test_legacy_usertype_cast_init_thread_safety():
    def closure(b):
        b.wait()
        np.full((10, 10), 1, _rational_tests.rational)

    run_threaded(closure, 250, pass_barrier=True)

@pytest.mark.parametrize("dtype", [bool, int, float])
def test_nonzero(dtype):
    # See: gh-28361
    #
    # np.nonzero uses np.count_nonzero to determine the size of the output array
    # In a second pass the indices of the non-zero elements are determined, but they can have changed
    #
    # This test triggers a data race which is suppressed in the TSAN CI. The test is to ensure
    # np.nonzero does not generate a segmentation fault
    x = np.random.randint(4, size=10_000).astype(dtype)

    def func(index):
        for _ in range(10):
            if index == 0:
                x[::2] = np.random.randint(2)
            else:
                try:
                    _ = np.nonzero(x)
                except RuntimeError as ex:
                    assert 'number of non-zero array elements changed during function execution' in str(ex)

    run_threaded(func, max_workers=10, pass_count=True, outer_iterations=50)

