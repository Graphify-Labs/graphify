import numpy as np
import pytest

info = np.__array_namespace_info__()


def test_capabilities():
    caps = info.capabilities()
    assert caps["boolean indexing"] is True
    assert caps["data-dependent shapes"] is True

    # This will be added in the 2024.12 release of the array API standard.

    # assert caps["max rank"] == 64
    # np.zeros((1,)*64)
    # with pytest.raises(ValueError):
    #     np.zeros((1,)*65)


def test_default_device():
    assert info.default_device() == "cpu" == np.asarray(0).device


def test_default_dtypes():
    dtypes = info.default_dtypes()
    assert dtypes["real floating"] == np.float64 == np.asarray(0.0).dtype
    assert dtypes["complex floating"] == np.complex128 == \
        np.asarray(0.0j).dtype
    assert dtypes["integral"] == np.intp == np.asarray(0).dtype
    assert dtypes["indexing"] == np.intp == np.argmax(np.zeros(10)).dtype

    with pytest.raises(ValueError, match="Device not understood"):
        info.default_dtypes(device="gpu")


def test_dtypes_all():
    dtypes = info.dtypes()
    assert dtypes == {
        "bool": np.bool_,
        "int8": np.int8,
        "int16": np.int16,
        "int32": np.int32,
        "int64": np.int64,
        "uint8": np.uint8,
        "uint16": np.uint16,
        "uint32": np.uint32,
        "uint64": np.uint64,
        "float32": np.float32,
        "float64": np.float64,
        "complex64": np.complex64,
        "complex128": np.complex128,
    }


dtype_categories = {
    "bool": {"bool": np.bool_},
    "signed integer": {
        "int8": np.int8,
        "int16": np.int16,
        "int32": np.int32,
        "int64": np.int64,
    },
    "unsigned integer": {
        "uint8": np.uint8,
        "uint16": np.uint16,
        "uint32": np.uint32,
        "uint64": np.uint64,
    },
    "integral": ("signed integer", "unsigned integer"),
    "real floating": {"float32": np.float32, "float64": np.float64},
    "complex floating": {"complex64": np.complex64, "complex128":
                         np.complex128},
    "numeric": ("integral", "real floating", "complex floating"),
}


@pytest.mark.parametrize("kind", dtype_categories)
def test_dtypes_kind(kind):
    expected = dtype_categories[kind]
    if isinstance(expected, tuple):
        assert info.dtypes(kind=kind) == info.dtypes(kind=expected)
    else:
        assert info.dtypes(kind=kind) == expected


def test_dtypes_tuple():
    dtypes = info.dtypes(kind=("bool", "integral"))
    assert dtypes == {
        "bool": np.bool_,
        "int8": np.int8,
        "int16": np.int16,
        "int32": np.int32,
        "int64": np.int64,
        "uint8": np.uint8,
        "uint16": np.uint16,
        "uint32": np.uint32,
        "uint64": np.uint64,
    }


def test_dtypes_invalid_kind():
    with pytest.raises(ValueError, match="unsupported kind"):
        info.dtypes(kind="invalid")


def test_dtypes_invalid_device():
    with pytest.raises(ValueError, match="Device not understood"):
        info.dtypes(device="gpu")


def test_devices():
    assert info.devices() == ["cpu"]
