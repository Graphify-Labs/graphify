import os
import subprocess
import sysconfig

import pytest
import numpy as np

from numpy.testing import IS_WASM


is_editable = not bool(np.__path__)
numpy_in_sitepackages = sysconfig.get_path('platlib') in np.__file__
# We only expect to have a `numpy-config` available if NumPy was installed via
# a build frontend (and not `spin` for example)
if not (numpy_in_sitepackages or is_editable):
    pytest.skip("`numpy-config` not expected to be installed",
                allow_module_level=True)


def check_numpyconfig(arg):
    p = subprocess.run(['numpy-config', arg], capture_output=True, text=True)
    p.check_returncode()
    return p.stdout.strip()

@pytest.mark.skipif(IS_WASM, reason="wasm interpreter cannot start subprocess")
def test_configtool_version():
    stdout = check_numpyconfig('--version')
    assert stdout == np.__version__

@pytest.mark.skipif(IS_WASM, reason="wasm interpreter cannot start subprocess")
def test_configtool_cflags():
    stdout = check_numpyconfig('--cflags')
    assert stdout.endswith(os.path.join('numpy', '_core', 'include'))

@pytest.mark.skipif(IS_WASM, reason="wasm interpreter cannot start subprocess")
def test_configtool_pkgconfigdir():
    stdout = check_numpyconfig('--pkgconfigdir')
    assert stdout.endswith(os.path.join('numpy', '_core', 'lib', 'pkgconfig'))

    if not is_editable:
        # Also check that the .pc file actually exists (unless we're using an
        # editable install, then it'll be hiding in the build dir)
        assert os.path.exists(os.path.join(stdout, 'numpy.pc'))
