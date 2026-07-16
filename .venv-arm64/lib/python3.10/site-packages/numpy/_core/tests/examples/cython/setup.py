"""
Provide python-space access to the functions exposed in numpy/__init__.pxd
for testing.
"""

import Cython
import numpy as np
from numpy._utils import _pep440
from distutils.core import setup
from Cython.Build import cythonize
from setuptools.extension import Extension
import os

macros = [
    ("NPY_NO_DEPRECATED_API", 0),
    # Require 1.25+ to test datetime additions
    ("NPY_TARGET_VERSION", "NPY_2_0_API_VERSION"),
]

checks = Extension(
    "checks",
    sources=[os.path.join('.', "checks.pyx")],
    include_dirs=[np.get_include()],
    define_macros=macros,
)

extensions = [checks]

compiler_directives = {}
if _pep440.parse(Cython.__version__) >= _pep440.parse("3.1.0a0"):
    compiler_directives['freethreading_compatible'] = True

setup(
    ext_modules=cythonize(
        extensions,
        compiler_directives=compiler_directives)
)
