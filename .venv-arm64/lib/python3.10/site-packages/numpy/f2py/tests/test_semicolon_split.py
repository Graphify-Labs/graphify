import platform
import pytest

from numpy.testing import IS_64BIT

from . import util


@pytest.mark.skipif(
    platform.system() == "Darwin",
    reason="Prone to error when run with numpy/f2py/tests on mac os, "
    "but not when run in isolation",
)
@pytest.mark.skipif(
    not IS_64BIT, reason="32-bit builds are buggy"
)
class TestMultiline(util.F2PyTest):
    suffix = ".pyf"
    module_name = "multiline"
    code = f"""
python module {module_name}
    usercode '''
void foo(int* x) {{
    char dummy = ';';
    *x = 42;
}}
'''
    interface
        subroutine foo(x)
            intent(c) foo
            integer intent(out) :: x
        end subroutine foo
    end interface
end python module {module_name}
    """

    def test_multiline(self):
        assert self.module.foo() == 42


@pytest.mark.skipif(
    platform.system() == "Darwin",
    reason="Prone to error when run with numpy/f2py/tests on mac os, "
    "but not when run in isolation",
)
@pytest.mark.skipif(
    not IS_64BIT, reason="32-bit builds are buggy"
)
@pytest.mark.slow
class TestCallstatement(util.F2PyTest):
    suffix = ".pyf"
    module_name = "callstatement"
    code = f"""
python module {module_name}
    usercode '''
void foo(int* x) {{
}}
'''
    interface
        subroutine foo(x)
            intent(c) foo
            integer intent(out) :: x
            callprotoargument int*
            callstatement {{ &
                ; &
                x = 42; &
            }}
        end subroutine foo
    end interface
end python module {module_name}
    """

    def test_callstatement(self):
        assert self.module.foo() == 42
