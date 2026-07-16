#include <Python.h>

typedef struct TSLanguage TSLanguage;

TSLanguage *tree_sitter_php(void);
TSLanguage *tree_sitter_php_only(void);

static PyObject* _binding_language_php(PyObject *Py_UNUSED(self), PyObject *Py_UNUSED(args)) {
    return PyCapsule_New(tree_sitter_php(), "tree_sitter.Language", NULL);
}

static PyObject* _binding_language_php_only(PyObject *Py_UNUSED(self), PyObject *Py_UNUSED(args)) {
    return PyCapsule_New(tree_sitter_php_only(), "tree_sitter.Language", NULL);
}

static struct PyModuleDef_Slot slots[] = {
#ifdef Py_GIL_DISABLED
    {Py_mod_gil, Py_MOD_GIL_NOT_USED},
#endif
    {0, NULL}
};

static PyMethodDef methods[] = {
    {"language_php", _binding_language_php, METH_NOARGS,
     "Get the tree-sitter language for PHP."},
    {"language_php_only", _binding_language_php_only, METH_NOARGS,
     "Get the tree-sitter language for PHP-Only."},
    {NULL, NULL, 0, NULL}
};

static struct PyModuleDef module = {
    .m_base = PyModuleDef_HEAD_INIT,
    .m_name = "_binding",
    .m_doc = NULL,
    .m_size = 0,
    .m_methods = methods,
    .m_slots = slots,
};

PyMODINIT_FUNC PyInit__binding(void) {
    return PyModuleDef_Init(&module);
}
