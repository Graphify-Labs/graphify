import os
import pytest
import platform

import numpy as np
import numpy.testing as npt

from . import util


class TestIntentInOut(util.F2PyTest):
    # Check that intent(in out) translates as intent(inout)
    sources = [util.getpath("tests", "src", "regression", "inout.f90")]

    @pytest.mark.slow
    def test_inout(self):
        # non-contiguous should raise error
        x = np.arange(6, dtype=np.float32)[::2]
        pytest.raises(ValueError, self.module.foo, x)

        # check values with contiguous array
        x = np.arange(3, dtype=np.float32)
        self.module.foo(x)
        assert np.allclose(x, [3, 1, 2])


class TestDataOnlyMultiModule(util.F2PyTest):
    # Check that modules without subroutines work
    sources = [util.getpath("tests", "src", "regression", "datonly.f90")]

    @pytest.mark.slow
    def test_mdat(self):
        assert self.module.datonly.max_value == 100
        assert self.module.dat.max_ == 1009
        int_in = 5
        assert self.module.simple_subroutine(5) == 1014


class TestNegativeBounds(util.F2PyTest):
    # Check that negative bounds work correctly
    sources = [util.getpath("tests", "src", "negative_bounds", "issue_20853.f90")]

    @pytest.mark.slow
    def test_negbound(self):
        xvec = np.arange(12)
        xlow = -6
        xhigh = 4
        # Calculate the upper bound,
        # Keeping the 1 index in mind
        def ubound(xl, xh):
            return xh - xl + 1
        rval = self.module.foo(is_=xlow, ie_=xhigh,
                        arr=xvec[:ubound(xlow, xhigh)])
        expval = np.arange(11, dtype = np.float32)
        assert np.allclose(rval, expval)


class TestNumpyVersionAttribute(util.F2PyTest):
    # Check that th attribute __f2py_numpy_version__ is present
    # in the compiled module and that has the value np.__version__.
    sources = [util.getpath("tests", "src", "regression", "inout.f90")]

    @pytest.mark.slow
    def test_numpy_version_attribute(self):

        # Check that self.module has an attribute named "__f2py_numpy_version__"
        assert hasattr(self.module, "__f2py_numpy_version__")

        # Check that the attribute __f2py_numpy_version__ is a string
        assert isinstance(self.module.__f2py_numpy_version__, str)

        # Check that __f2py_numpy_version__ has the value numpy.__version__
        assert np.__version__ == self.module.__f2py_numpy_version__


def test_include_path():
    incdir = np.f2py.get_include()
    fnames_in_dir = os.listdir(incdir)
    for fname in ("fortranobject.c", "fortranobject.h"):
        assert fname in fnames_in_dir


class TestIncludeFiles(util.F2PyTest):
    sources = [util.getpath("tests", "src", "regression", "incfile.f90")]
    options = [f"-I{util.getpath('tests', 'src', 'regression')}",
               f"--include-paths {util.getpath('tests', 'src', 'regression')}"]

    @pytest.mark.slow
    def test_gh25344(self):
        exp = 7.0
        res = self.module.add(3.0, 4.0)
        assert  exp == res

class TestF77Comments(util.F2PyTest):
    # Check that comments are stripped from F77 continuation lines
    sources = [util.getpath("tests", "src", "regression", "f77comments.f")]

    @pytest.mark.slow
    def test_gh26148(self):
        x1 = np.array(3, dtype=np.int32)
        x2 = np.array(5, dtype=np.int32)
        res=self.module.testsub(x1, x2)
        assert(res[0] == 8)
        assert(res[1] == 15)

    @pytest.mark.slow
    def test_gh26466(self):
        # Check that comments after PARAMETER directions are stripped
        expected = np.arange(1, 11, dtype=np.float32)*2
        res=self.module.testsub2()
        npt.assert_allclose(expected, res)

class TestF90Contiuation(util.F2PyTest):
    # Check that comments are stripped from F90 continuation lines
    sources = [util.getpath("tests", "src", "regression", "f90continuation.f90")]

    @pytest.mark.slow
    def test_gh26148b(self):
        x1 = np.array(3, dtype=np.int32)
        x2 = np.array(5, dtype=np.int32)
        res=self.module.testsub(x1, x2)
        assert(res[0] == 8)
        assert(res[1] == 15)

class TestLowerF2PYDirectives(util.F2PyTest):
    # Check variables are cased correctly
    sources = [util.getpath("tests", "src", "regression", "lower_f2py_fortran.f90")]

    @pytest.mark.slow
    def test_gh28014(self):
        self.module.inquire_next(3)
        assert True

@pytest.mark.slow
def test_gh26623():
    # Including libraries with . should not generate an incorrect meson.build
    try:
        aa = util.build_module(
            [util.getpath("tests", "src", "regression", "f90continuation.f90")],
            ["-lfoo.bar"],
            module_name="Blah",
        )
    except RuntimeError as rerr:
        assert "lparen got assign" not in str(rerr)


@pytest.mark.slow
@pytest.mark.skipif(platform.system() not in ['Linux', 'Darwin'], reason='Unsupported on this platform for now')
def test_gh25784():
    # Compile dubious file using passed flags
    try:
        aa = util.build_module(
            [util.getpath("tests", "src", "regression", "f77fixedform.f95")],
            options=[
                # Meson will collect and dedup these to pass to fortran_args:
                "--f77flags='-ffixed-form -O2'",
                "--f90flags=\"-ffixed-form -Og\"",
            ],
            module_name="Blah",
        )
    except ImportError as rerr:
        assert "unknown_subroutine_" in str(rerr)


@pytest.mark.slow
class TestAssignmentOnlyModules(util.F2PyTest):
    # Ensure that variables are exposed without functions or subroutines in a module
    sources = [util.getpath("tests", "src", "regression", "assignOnlyModule.f90")]

    @pytest.mark.slow
    def test_gh27167(self):
        assert (self.module.f_globals.n_max == 16)
        assert (self.module.f_globals.i_max == 18)
        assert (self.module.f_globals.j_max == 72)
