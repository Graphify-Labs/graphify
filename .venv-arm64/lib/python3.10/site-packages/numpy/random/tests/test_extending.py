from importlib.util import spec_from_file_location, module_from_spec
import os
import pytest
import shutil
import subprocess
import sys
import sysconfig
import warnings

import numpy as np
from numpy.testing import IS_WASM, IS_EDITABLE


try:
    import cffi
except ImportError:
    cffi = None

if sys.flags.optimize > 1:
    # no docstrings present to inspect when PYTHONOPTIMIZE/Py_OptimizeFlag > 1
    # cffi cannot succeed
    cffi = None

try:
    with warnings.catch_warnings(record=True) as w:
        # numba issue gh-4733
        warnings.filterwarnings('always', '', DeprecationWarning)
        import numba
except (ImportError, SystemError):
    # Certain numpy/numba versions trigger a SystemError due to a numba bug
    numba = None

try:
    import cython
    from Cython.Compiler.Version import version as cython_version
except ImportError:
    cython = None
else:
    from numpy._utils import _pep440
    # Note: keep in sync with the one in pyproject.toml
    required_version = '3.0.6'
    if _pep440.parse(cython_version) < _pep440.Version(required_version):
        # too old or wrong cython, skip the test
        cython = None


@pytest.mark.skipif(
    IS_EDITABLE,
    reason='Editable install cannot find .pxd headers'
)
@pytest.mark.skipif(
        sys.platform == "win32" and sys.maxsize < 2**32,
        reason="Failing in 32-bit Windows wheel build job, skip for now"
)
@pytest.mark.skipif(IS_WASM, reason="Can't start subprocess")
@pytest.mark.skipif(cython is None, reason="requires cython")
@pytest.mark.slow
def test_cython(tmp_path):
    import glob
    # build the examples in a temporary directory
    srcdir = os.path.join(os.path.dirname(__file__), '..')
    shutil.copytree(srcdir, tmp_path / 'random')
    build_dir = tmp_path / 'random' / '_examples' / 'cython'
    target_dir = build_dir / "build"
    os.makedirs(target_dir, exist_ok=True)
    # Ensure we use the correct Python interpreter even when `meson` is
    # installed in a different Python environment (see gh-24956)
    native_file = str(build_dir / 'interpreter-native-file.ini')
    with open(native_file, 'w') as f:
        f.write("[binaries]\n")
        f.write(f"python = '{sys.executable}'\n")
        f.write(f"python3 = '{sys.executable}'")
    if sys.platform == "win32":
        subprocess.check_call(["meson", "setup",
                               "--buildtype=release",
                               "--vsenv", "--native-file", native_file,
                               str(build_dir)],
                              cwd=target_dir,
                              )
    else:
        subprocess.check_call(["meson", "setup",
                               "--native-file", native_file, str(build_dir)],
                              cwd=target_dir
                              )
    subprocess.check_call(["meson", "compile", "-vv"], cwd=target_dir)

    # gh-16162: make sure numpy's __init__.pxd was used for cython
    # not really part of this test, but it is a convenient place to check

    g = glob.glob(str(target_dir / "*" / "extending.pyx.c"))
    with open(g[0]) as fid:
        txt_to_find = 'NumPy API declarations from "numpy/__init__'
        for line in fid:
            if txt_to_find in line:
                break
        else:
            assert False, ("Could not find '{}' in C file, "
                           "wrong pxd used".format(txt_to_find))
    # import without adding the directory to sys.path
    suffix = sysconfig.get_config_var('EXT_SUFFIX')

    def load(modname):
        so = (target_dir / modname).with_suffix(suffix)
        spec = spec_from_file_location(modname, so)
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    # test that the module can be imported
    load("extending")
    load("extending_cpp")
    # actually test the cython c-extension
    extending_distributions = load("extending_distributions")
    from numpy.random import PCG64
    values = extending_distributions.uniforms_ex(PCG64(0), 10, 'd')
    assert values.shape == (10,)
    assert values.dtype == np.float64

@pytest.mark.skipif(numba is None or cffi is None,
                    reason="requires numba and cffi")
def test_numba():
    from numpy.random._examples.numba import extending  # noqa: F401

@pytest.mark.skipif(cffi is None, reason="requires cffi")
def test_cffi():
    from numpy.random._examples.cffi import extending  # noqa: F401
