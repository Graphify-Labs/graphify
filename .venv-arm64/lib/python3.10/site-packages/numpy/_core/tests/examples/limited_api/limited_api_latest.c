#if Py_LIMITED_API != PY_VERSION_HEX & 0xffff0000
    # error "Py_LIMITED_API not defined to Python major+minor version"
#endif

#include <Python.h>
#include <numpy/arrayobject.h>
#include <numpy/ufuncobject.h>

static PyModuleDef moduledef = {
    .m_base = PyModuleDef_HEAD_INIT,
    .m_name = "limited_api_latest"
};

PyMODINIT_FUNC PyInit_limited_api_latest(void)
{
    import_array();
    import_umath();
    return PyModule_Create(&moduledef);
}
