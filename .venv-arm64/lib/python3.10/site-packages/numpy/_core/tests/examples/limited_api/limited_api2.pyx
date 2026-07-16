#cython: language_level=3

"""
Make sure cython can compile in limited API mode (see meson.build)
"""

cdef extern from "numpy/arrayobject.h":
    pass
cdef extern from "numpy/arrayscalars.h":
    pass

