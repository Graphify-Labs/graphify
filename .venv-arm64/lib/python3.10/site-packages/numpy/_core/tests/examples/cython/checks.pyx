#cython: language_level=3

"""
Functions in this module give python-space wrappers for cython functions
exposed in numpy/__init__.pxd, so they can be tested in test_cython.py
"""
cimport numpy as cnp
cnp.import_array()


def is_td64(obj):
    return cnp.is_timedelta64_object(obj)


def is_dt64(obj):
    return cnp.is_datetime64_object(obj)


def get_dt64_value(obj):
    return cnp.get_datetime64_value(obj)


def get_td64_value(obj):
    return cnp.get_timedelta64_value(obj)


def get_dt64_unit(obj):
    return cnp.get_datetime64_unit(obj)


def is_integer(obj):
    return isinstance(obj, (cnp.integer, int))


def get_datetime_iso_8601_strlen():
    return cnp.get_datetime_iso_8601_strlen(0, cnp.NPY_FR_ns)


def convert_datetime64_to_datetimestruct():
    cdef:
        cnp.npy_datetimestruct dts
        cnp.PyArray_DatetimeMetaData meta
        cnp.int64_t value = 1647374515260292
        # i.e. (time.time() * 10**6) at 2022-03-15 20:01:55.260292 UTC

    meta.base = cnp.NPY_FR_us
    meta.num = 1
    cnp.convert_datetime64_to_datetimestruct(&meta, value, &dts)
    return dts


def make_iso_8601_datetime(dt: "datetime"):
    cdef:
        cnp.npy_datetimestruct dts
        char result[36]  # 36 corresponds to NPY_FR_s passed below
        int local = 0
        int utc = 0
        int tzoffset = 0

    dts.year = dt.year
    dts.month = dt.month
    dts.day = dt.day
    dts.hour = dt.hour
    dts.min = dt.minute
    dts.sec = dt.second
    dts.us = dt.microsecond
    dts.ps = dts.as = 0

    cnp.make_iso_8601_datetime(
        &dts,
        result,
        sizeof(result),
        local,
        utc,
        cnp.NPY_FR_s,
        tzoffset,
        cnp.NPY_NO_CASTING,
    )
    return result


cdef cnp.broadcast multiiter_from_broadcast_obj(object bcast):
    cdef dict iter_map = {
        1: cnp.PyArray_MultiIterNew1,
        2: cnp.PyArray_MultiIterNew2,
        3: cnp.PyArray_MultiIterNew3,
        4: cnp.PyArray_MultiIterNew4,
        5: cnp.PyArray_MultiIterNew5,
    }
    arrays = [x.base for x in bcast.iters]
    cdef cnp.broadcast result = iter_map[len(arrays)](*arrays)
    return result


def get_multiiter_size(bcast: "broadcast"):
    cdef cnp.broadcast multi = multiiter_from_broadcast_obj(bcast)
    return multi.size


def get_multiiter_number_of_dims(bcast: "broadcast"):
    cdef cnp.broadcast multi = multiiter_from_broadcast_obj(bcast)
    return multi.nd


def get_multiiter_current_index(bcast: "broadcast"):
    cdef cnp.broadcast multi = multiiter_from_broadcast_obj(bcast)
    return multi.index


def get_multiiter_num_of_iterators(bcast: "broadcast"):
    cdef cnp.broadcast multi = multiiter_from_broadcast_obj(bcast)
    return multi.numiter


def get_multiiter_shape(bcast: "broadcast"):
    cdef cnp.broadcast multi = multiiter_from_broadcast_obj(bcast)
    return tuple([multi.dimensions[i] for i in range(bcast.nd)])


def get_multiiter_iters(bcast: "broadcast"):
    cdef cnp.broadcast multi = multiiter_from_broadcast_obj(bcast)
    return tuple([<cnp.flatiter>multi.iters[i] for i in range(bcast.numiter)])


def get_default_integer():
    if cnp.NPY_DEFAULT_INT == cnp.NPY_LONG:
        return cnp.dtype("long")
    if cnp.NPY_DEFAULT_INT == cnp.NPY_INTP:
        return cnp.dtype("intp")
    return None

def get_ravel_axis():
    return cnp.NPY_RAVEL_AXIS


def conv_intp(cnp.intp_t val):
    return val


def get_dtype_flags(cnp.dtype dtype):
    return dtype.flags


cdef cnp.NpyIter* npyiter_from_nditer_obj(object it):
    """A function to create a NpyIter struct from a nditer object.

    This function is only meant for testing purposes and only extracts the
    necessary info from nditer to test the functionality of NpyIter methods
    """
    cdef:
        cnp.NpyIter* cit
        cnp.PyArray_Descr* op_dtypes[3]
        cnp.npy_uint32 op_flags[3]
        cnp.PyArrayObject* ops[3]
        cnp.npy_uint32 flags = 0

    if it.has_index:
        flags |= cnp.NPY_ITER_C_INDEX
    if it.has_delayed_bufalloc:
        flags |= cnp.NPY_ITER_BUFFERED | cnp.NPY_ITER_DELAY_BUFALLOC
    if it.has_multi_index:
        flags |= cnp.NPY_ITER_MULTI_INDEX

    # one of READWRITE, READONLY and WRTIEONLY at the minimum must be specified for op_flags
    for i in range(it.nop):
        op_flags[i] = cnp.NPY_ITER_READONLY

    for i in range(it.nop):
        op_dtypes[i] = cnp.PyArray_DESCR(it.operands[i])
        ops[i] = <cnp.PyArrayObject*>it.operands[i]

    cit = cnp.NpyIter_MultiNew(it.nop, &ops[0], flags, cnp.NPY_KEEPORDER,
                               cnp.NPY_NO_CASTING, &op_flags[0],
                               <cnp.PyArray_Descr**>NULL)
    return cit


def get_npyiter_size(it: "nditer"):
    cdef cnp.NpyIter* cit = npyiter_from_nditer_obj(it)
    result = cnp.NpyIter_GetIterSize(cit)
    cnp.NpyIter_Deallocate(cit)
    return result


def get_npyiter_ndim(it: "nditer"):
    cdef cnp.NpyIter* cit = npyiter_from_nditer_obj(it)
    result = cnp.NpyIter_GetNDim(cit)
    cnp.NpyIter_Deallocate(cit)
    return result


def get_npyiter_nop(it: "nditer"):
    cdef cnp.NpyIter* cit = npyiter_from_nditer_obj(it)
    result = cnp.NpyIter_GetNOp(cit)
    cnp.NpyIter_Deallocate(cit)
    return result


def get_npyiter_operands(it: "nditer"):
    cdef cnp.NpyIter* cit = npyiter_from_nditer_obj(it)
    try:
        arr = cnp.NpyIter_GetOperandArray(cit)
        return tuple([<cnp.ndarray>arr[i] for i in range(it.nop)])
    finally:
        cnp.NpyIter_Deallocate(cit)


def get_npyiter_itviews(it: "nditer"):
    cdef cnp.NpyIter* cit = npyiter_from_nditer_obj(it)
    result = tuple([cnp.NpyIter_GetIterView(cit, i) for i in range(it.nop)])
    cnp.NpyIter_Deallocate(cit)
    return result


def get_npyiter_dtypes(it: "nditer"):
    cdef cnp.NpyIter* cit = npyiter_from_nditer_obj(it)
    try:
        arr = cnp.NpyIter_GetDescrArray(cit)
        return tuple([<cnp.dtype>arr[i] for i in range(it.nop)])
    finally:
        cnp.NpyIter_Deallocate(cit)


def npyiter_has_delayed_bufalloc(it: "nditer"):
    cdef cnp.NpyIter* cit = npyiter_from_nditer_obj(it)
    result = cnp.NpyIter_HasDelayedBufAlloc(cit)
    cnp.NpyIter_Deallocate(cit)
    return result


def npyiter_has_index(it: "nditer"):
    cdef cnp.NpyIter* cit = npyiter_from_nditer_obj(it)
    result = cnp.NpyIter_HasIndex(cit)
    cnp.NpyIter_Deallocate(cit)
    return result


def npyiter_has_multi_index(it: "nditer"):
    cdef cnp.NpyIter* cit = npyiter_from_nditer_obj(it)
    result = cnp.NpyIter_HasMultiIndex(cit)
    cnp.NpyIter_Deallocate(cit)
    return result


def test_get_multi_index_iter_next(it: "nditer", cnp.ndarray[cnp.float64_t, ndim=2] arr):
    cdef cnp.NpyIter* cit = npyiter_from_nditer_obj(it)
    cdef cnp.NpyIter_GetMultiIndexFunc get_multi_index = \
        cnp.NpyIter_GetGetMultiIndex(cit, NULL)
    cdef cnp.NpyIter_IterNextFunc iternext = \
        cnp.NpyIter_GetIterNext(cit, NULL)
    return 1


def npyiter_has_finished(it: "nditer"):
    cdef cnp.NpyIter* cit
    try:
        cit = npyiter_from_nditer_obj(it)
        cnp.NpyIter_GotoIterIndex(cit, it.index)
        return not (cnp.NpyIter_GetIterIndex(cit) < cnp.NpyIter_GetIterSize(cit))
    finally:
        cnp.NpyIter_Deallocate(cit)

def compile_fillwithbyte():
    # Regression test for gh-25878, mostly checks it compiles.
    cdef cnp.npy_intp dims[2]
    dims = (1, 2)
    pos = cnp.PyArray_ZEROS(2, dims, cnp.NPY_UINT8, 0)
    cnp.PyArray_FILLWBYTE(pos, 1)
    return pos

def inc2_cfloat_struct(cnp.ndarray[cnp.cfloat_t] arr):
    # This works since we compile in C mode, it will fail in cpp mode
    arr[1].real += 1
    arr[1].imag += 1
    # This works in both modes
    arr[1].real = arr[1].real + 1
    arr[1].imag = arr[1].imag + 1


def check_npy_uintp_type_enum():
    # Regression test for gh-27890: cnp.NPY_UINTP was not defined.
    # Cython would fail to compile this before gh-27890 was fixed.
    return cnp.NPY_UINTP > 0
