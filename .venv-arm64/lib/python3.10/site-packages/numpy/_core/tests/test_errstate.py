import pytest
import sysconfig

import numpy as np
from numpy.testing import assert_, assert_raises, IS_WASM

# The floating point emulation on ARM EABI systems lacking a hardware FPU is
# known to be buggy. This is an attempt to identify these hosts. It may not
# catch all possible cases, but it catches the known cases of gh-413 and
# gh-15562.
hosttype = sysconfig.get_config_var('HOST_GNU_TYPE')
arm_softfloat = False if hosttype is None else hosttype.endswith('gnueabi')

class TestErrstate:
    @pytest.mark.skipif(IS_WASM, reason="fp errors don't work in wasm")
    @pytest.mark.skipif(arm_softfloat,
                        reason='platform/cpu issue with FPU (gh-413,-15562)')
    def test_invalid(self):
        with np.errstate(all='raise', under='ignore'):
            a = -np.arange(3)
            # This should work
            with np.errstate(invalid='ignore'):
                np.sqrt(a)
            # While this should fail!
            with assert_raises(FloatingPointError):
                np.sqrt(a)

    @pytest.mark.skipif(IS_WASM, reason="fp errors don't work in wasm")
    @pytest.mark.skipif(arm_softfloat,
                        reason='platform/cpu issue with FPU (gh-15562)')
    def test_divide(self):
        with np.errstate(all='raise', under='ignore'):
            a = -np.arange(3)
            # This should work
            with np.errstate(divide='ignore'):
                a // 0
            # While this should fail!
            with assert_raises(FloatingPointError):
                a // 0
            # As should this, see gh-15562
            with assert_raises(FloatingPointError):
                a // a

    @pytest.mark.skipif(IS_WASM, reason="fp errors don't work in wasm")
    @pytest.mark.skipif(arm_softfloat,
                        reason='platform/cpu issue with FPU (gh-15562)')
    def test_errcall(self):
        count = 0
        def foo(*args):
            nonlocal count
            count += 1

        olderrcall = np.geterrcall()
        with np.errstate(call=foo):
            assert np.geterrcall() is foo
            with np.errstate(call=None):
                assert np.geterrcall() is None
        assert np.geterrcall() is olderrcall
        assert count == 0

        with np.errstate(call=foo, invalid="call"):
            np.array(np.inf) - np.array(np.inf)

        assert count == 1

    def test_errstate_decorator(self):
        @np.errstate(all='ignore')
        def foo():
            a = -np.arange(3)
            a // 0

        foo()

    def test_errstate_enter_once(self):
        errstate = np.errstate(invalid="warn")
        with errstate:
            pass

        # The errstate context cannot be entered twice as that would not be
        # thread-safe
        with pytest.raises(TypeError,
                match="Cannot enter `np.errstate` twice"):
            with errstate:
                pass

    @pytest.mark.skipif(IS_WASM, reason="wasm doesn't support asyncio")
    def test_asyncio_safe(self):
        # asyncio may not always work, lets assume its fine if missing
        # Pyodide/wasm doesn't support it.  If this test makes problems,
        # it should just be skipped liberally (or run differently).
        asyncio = pytest.importorskip("asyncio")

        @np.errstate(invalid="ignore")
        def decorated():
            # Decorated non-async function (it is not safe to decorate an
            # async one)
            assert np.geterr()["invalid"] == "ignore"

        async def func1():
            decorated()
            await asyncio.sleep(0.1)
            decorated()

        async def func2():
            with np.errstate(invalid="raise"):
                assert np.geterr()["invalid"] == "raise"
                await asyncio.sleep(0.125)
                assert np.geterr()["invalid"] == "raise"

        # for good sport, a third one with yet another state:
        async def func3():
            with np.errstate(invalid="print"):
                assert np.geterr()["invalid"] == "print"
                await asyncio.sleep(0.11)
                assert np.geterr()["invalid"] == "print"

        async def main():
            # simply run all three function multiple times:
            await asyncio.gather(
                    func1(), func2(), func3(), func1(), func2(), func3(),
                    func1(), func2(), func3(), func1(), func2(), func3())

        loop = asyncio.new_event_loop()
        with np.errstate(invalid="warn"):
            asyncio.run(main())
            assert np.geterr()["invalid"] == "warn"

        assert np.geterr()["invalid"] == "warn"  # the default
        loop.close()
