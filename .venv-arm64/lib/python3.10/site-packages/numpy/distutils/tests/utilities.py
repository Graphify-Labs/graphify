# Kanged out of numpy.f2py.tests.util for test_build_ext
from numpy.testing import IS_WASM
import textwrap
import shutil
import tempfile
import os
import re
import subprocess
import sys

#
# Check if compilers are available at all...
#

_compiler_status = None


def _get_compiler_status():
    global _compiler_status
    if _compiler_status is not None:
        return _compiler_status

    _compiler_status = (False, False, False)
    if IS_WASM:
        # Can't run compiler from inside WASM.
        return _compiler_status

    # XXX: this is really ugly. But I don't know how to invoke Distutils
    #      in a safer way...
    code = textwrap.dedent(
        f"""\
        import os
        import sys
        sys.path = {repr(sys.path)}

        def configuration(parent_name='',top_path=None):
            global config
            from numpy.distutils.misc_util import Configuration
            config = Configuration('', parent_name, top_path)
            return config

        from numpy.distutils.core import setup
        setup(configuration=configuration)

        config_cmd = config.get_config_cmd()
        have_c = config_cmd.try_compile('void foo() {{}}')
        print('COMPILERS:%%d,%%d,%%d' %% (have_c,
                                          config.have_f77c(),
                                          config.have_f90c()))
        sys.exit(99)
        """
    )
    code = code % dict(syspath=repr(sys.path))

    tmpdir = tempfile.mkdtemp()
    try:
        script = os.path.join(tmpdir, "setup.py")

        with open(script, "w") as f:
            f.write(code)

        cmd = [sys.executable, "setup.py", "config"]
        p = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=tmpdir
        )
        out, err = p.communicate()
    finally:
        shutil.rmtree(tmpdir)

    m = re.search(rb"COMPILERS:(\d+),(\d+),(\d+)", out)
    if m:
        _compiler_status = (
            bool(int(m.group(1))),
            bool(int(m.group(2))),
            bool(int(m.group(3))),
        )
    # Finished
    return _compiler_status


def has_c_compiler():
    return _get_compiler_status()[0]


def has_f77_compiler():
    return _get_compiler_status()[1]


def has_f90_compiler():
    return _get_compiler_status()[2]
