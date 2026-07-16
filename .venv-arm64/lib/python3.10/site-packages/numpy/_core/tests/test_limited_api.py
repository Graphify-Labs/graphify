import os
import subprocess
import sys
import sysconfig
import pytest

from numpy.testing import IS_WASM, IS_PYPY, NOGIL_BUILD, IS_EDITABLE

# This import is copied from random.tests.test_extending
try:
    import cython
    from Cython.Compiler.Version import version as cython_version
except ImportError:
    cython = None
else:
    from numpy._utils import _pep440

    # Note: keep in sync with the one in pyproject.toml
    required_version = "3.0.6"
    if _pep440.parse(cython_version) < _pep440.Version(required_version):
        # too old or wrong cython, skip the test
        cython = None

pytestmark = pytest.mark.skipif(cython is None, reason="requires cython")


if IS_EDITABLE:
    pytest.skip(
        "Editable install doesn't support tests with a compile step",
        allow_module_level=True
    )


@pytest.fixture(scope='module')
def install_temp(tmpdir_factory):
    # Based in part on test_cython from random.tests.test_extending
    if IS_WASM:
        pytest.skip("No subprocess")

    srcdir = os.path.join(os.path.dirname(__file__), 'examples', 'limited_api')
    build_dir = tmpdir_factory.mktemp("limited_api") / "build"
    os.makedirs(build_dir, exist_ok=True)
    # Ensure we use the correct Python interpreter even when `meson` is
    # installed in a different Python environment (see gh-24956)
    native_file = str(build_dir / 'interpreter-native-file.ini')
    with open(native_file, 'w') as f:
        f.write("[binaries]\n")
        f.write(f"python = '{sys.executable}'\n")
        f.write(f"python3 = '{sys.executable}'")

    try:
        subprocess.check_call(["meson", "--version"])
    except FileNotFoundError:
        pytest.skip("No usable 'meson' found")
    if sys.platform == "win32":
        subprocess.check_call(["meson", "setup",
                               "--werror",
                               "--buildtype=release",
                               "--vsenv", "--native-file", native_file,
                               str(srcdir)],
                              cwd=build_dir,
                              )
    else:
        subprocess.check_call(["meson", "setup", "--werror",
                               "--native-file", native_file, str(srcdir)],
                              cwd=build_dir
                              )
    try:
        subprocess.check_call(
            ["meson", "compile", "-vv"], cwd=build_dir)
    except subprocess.CalledProcessError as p:
        print(f"{p.stdout=}")
        print(f"{p.stderr=}")
        raise

    sys.path.append(str(build_dir))



@pytest.mark.skipif(IS_WASM, reason="Can't start subprocess")
@pytest.mark.xfail(
    sysconfig.get_config_var("Py_DEBUG"),
    reason=(
        "Py_LIMITED_API is incompatible with Py_DEBUG, Py_TRACE_REFS, "
        "and Py_REF_DEBUG"
    ),
)
@pytest.mark.xfail(
    NOGIL_BUILD,
    reason="Py_GIL_DISABLED builds do not currently support the limited API",
)
@pytest.mark.skipif(IS_PYPY, reason="no support for limited API in PyPy")
def test_limited_api(install_temp):
    """Test building a third-party C extension with the limited API
    and building a cython extension with the limited API
    """

    import limited_api1  # Earliest (3.6)
    import limited_api_latest  # Latest version (current Python)
    import limited_api2  # cython
