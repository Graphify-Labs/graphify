from numpy.testing import IS_WASM, IS_EDITABLE
import pytest

if IS_WASM:
    pytest.skip(
        "WASM/Pyodide does not use or support Fortran",
        allow_module_level=True
    )


if IS_EDITABLE:
    pytest.skip(
        "Editable install doesn't support tests with a compile step",
        allow_module_level=True
    )
