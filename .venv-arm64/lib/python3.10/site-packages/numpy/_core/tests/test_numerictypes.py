import sys
import itertools

import pytest
import numpy as np
import numpy._core.numerictypes as nt
from numpy._core.numerictypes import (
    issctype, sctype2char, maximum_sctype, sctypes
)
from numpy.testing import (
    assert_, assert_equal, assert_raises, assert_raises_regex, IS_PYPY
)

# This is the structure of the table used for plain objects:
#
# +-+-+-+
# |x|y|z|
# +-+-+-+

# Structure of a plain array description:
Pdescr = [
    ('x', 'i4', (2,)),
    ('y', 'f8', (2, 2)),
    ('z', 'u1')]

# A plain list of tuples with values for testing:
PbufferT = [
    # x     y                  z
    ([3, 2], [[6., 4.], [6., 4.]], 8),
    ([4, 3], [[7., 5.], [7., 5.]], 9),
    ]


# This is the structure of the table used for nested objects (DON'T PANIC!):
#
# +-+---------------------------------+-----+----------+-+-+
# |x|Info                             |color|info      |y|z|
# | +-----+--+----------------+----+--+     +----+-----+ | |
# | |value|y2|Info2           |name|z2|     |Name|Value| | |
# | |     |  +----+-----+--+--+    |  |     |    |     | | |
# | |     |  |name|value|y3|z3|    |  |     |    |     | | |
# +-+-----+--+----+-----+--+--+----+--+-----+----+-----+-+-+
#

# The corresponding nested array description:
Ndescr = [
    ('x', 'i4', (2,)),
    ('Info', [
        ('value', 'c16'),
        ('y2', 'f8'),
        ('Info2', [
            ('name', 'S2'),
            ('value', 'c16', (2,)),
            ('y3', 'f8', (2,)),
            ('z3', 'u4', (2,))]),
        ('name', 'S2'),
        ('z2', 'b1')]),
    ('color', 'S2'),
    ('info', [
        ('Name', 'U8'),
        ('Value', 'c16')]),
    ('y', 'f8', (2, 2)),
    ('z', 'u1')]

NbufferT = [
    # x     Info                                                color info        y                  z
    #       value y2 Info2                            name z2         Name Value
    #                name   value    y3       z3
    ([3, 2], (6j, 6., (b'nn', [6j, 4j], [6., 4.], [1, 2]), b'NN', True),
     b'cc', ('NN', 6j), [[6., 4.], [6., 4.]], 8),
    ([4, 3], (7j, 7., (b'oo', [7j, 5j], [7., 5.], [2, 1]), b'OO', False),
     b'dd', ('OO', 7j), [[7., 5.], [7., 5.]], 9),
    ]


byteorder = {'little':'<', 'big':'>'}[sys.byteorder]

def normalize_descr(descr):
    "Normalize a description adding the platform byteorder."

    out = []
    for item in descr:
        dtype = item[1]
        if isinstance(dtype, str):
            if dtype[0] not in ['|', '<', '>']:
                onebyte = dtype[1:] == "1"
                if onebyte or dtype[0] in ['S', 'V', 'b']:
                    dtype = "|" + dtype
                else:
                    dtype = byteorder + dtype
            if len(item) > 2 and np.prod(item[2]) > 1:
                nitem = (item[0], dtype, item[2])
            else:
                nitem = (item[0], dtype)
            out.append(nitem)
        elif isinstance(dtype, list):
            l = normalize_descr(dtype)
            out.append((item[0], l))
        else:
            raise ValueError("Expected a str or list and got %s" %
                             (type(item)))
    return out


############################################################
#    Creation tests
############################################################

class CreateZeros:
    """Check the creation of heterogeneous arrays zero-valued"""

    def test_zeros0D(self):
        """Check creation of 0-dimensional objects"""
        h = np.zeros((), dtype=self._descr)
        assert_(normalize_descr(self._descr) == h.dtype.descr)
        assert_(h.dtype.fields['x'][0].name[:4] == 'void')
        assert_(h.dtype.fields['x'][0].char == 'V')
        assert_(h.dtype.fields['x'][0].type == np.void)
        # A small check that data is ok
        assert_equal(h['z'], np.zeros((), dtype='u1'))

    def test_zerosSD(self):
        """Check creation of single-dimensional objects"""
        h = np.zeros((2,), dtype=self._descr)
        assert_(normalize_descr(self._descr) == h.dtype.descr)
        assert_(h.dtype['y'].name[:4] == 'void')
        assert_(h.dtype['y'].char == 'V')
        assert_(h.dtype['y'].type == np.void)
        # A small check that data is ok
        assert_equal(h['z'], np.zeros((2,), dtype='u1'))

    def test_zerosMD(self):
        """Check creation of multi-dimensional objects"""
        h = np.zeros((2, 3), dtype=self._descr)
        assert_(normalize_descr(self._descr) == h.dtype.descr)
        assert_(h.dtype['z'].name == 'uint8')
        assert_(h.dtype['z'].char == 'B')
        assert_(h.dtype['z'].type == np.uint8)
        # A small check that data is ok
        assert_equal(h['z'], np.zeros((2, 3), dtype='u1'))


class TestCreateZerosPlain(CreateZeros):
    """Check the creation of heterogeneous arrays zero-valued (plain)"""
    _descr = Pdescr

class TestCreateZerosNested(CreateZeros):
    """Check the creation of heterogeneous arrays zero-valued (nested)"""
    _descr = Ndescr


class CreateValues:
    """Check the creation of heterogeneous arrays with values"""

    def test_tuple(self):
        """Check creation from tuples"""
        h = np.array(self._buffer, dtype=self._descr)
        assert_(normalize_descr(self._descr) == h.dtype.descr)
        if self.multiple_rows:
            assert_(h.shape == (2,))
        else:
            assert_(h.shape == ())

    def test_list_of_tuple(self):
        """Check creation from list of tuples"""
        h = np.array([self._buffer], dtype=self._descr)
        assert_(normalize_descr(self._descr) == h.dtype.descr)
        if self.multiple_rows:
            assert_(h.shape == (1, 2))
        else:
            assert_(h.shape == (1,))

    def test_list_of_list_of_tuple(self):
        """Check creation from list of list of tuples"""
        h = np.array([[self._buffer]], dtype=self._descr)
        assert_(normalize_descr(self._descr) == h.dtype.descr)
        if self.multiple_rows:
            assert_(h.shape == (1, 1, 2))
        else:
            assert_(h.shape == (1, 1))


class TestCreateValuesPlainSingle(CreateValues):
    """Check the creation of heterogeneous arrays (plain, single row)"""
    _descr = Pdescr
    multiple_rows = 0
    _buffer = PbufferT[0]

class TestCreateValuesPlainMultiple(CreateValues):
    """Check the creation of heterogeneous arrays (plain, multiple rows)"""
    _descr = Pdescr
    multiple_rows = 1
    _buffer = PbufferT

class TestCreateValuesNestedSingle(CreateValues):
    """Check the creation of heterogeneous arrays (nested, single row)"""
    _descr = Ndescr
    multiple_rows = 0
    _buffer = NbufferT[0]

class TestCreateValuesNestedMultiple(CreateValues):
    """Check the creation of heterogeneous arrays (nested, multiple rows)"""
    _descr = Ndescr
    multiple_rows = 1
    _buffer = NbufferT


############################################################
#    Reading tests
############################################################

class ReadValuesPlain:
    """Check the reading of values in heterogeneous arrays (plain)"""

    def test_access_fields(self):
        h = np.array(self._buffer, dtype=self._descr)
        if not self.multiple_rows:
            assert_(h.shape == ())
            assert_equal(h['x'], np.array(self._buffer[0], dtype='i4'))
            assert_equal(h['y'], np.array(self._buffer[1], dtype='f8'))
            assert_equal(h['z'], np.array(self._buffer[2], dtype='u1'))
        else:
            assert_(len(h) == 2)
            assert_equal(h['x'], np.array([self._buffer[0][0],
                                             self._buffer[1][0]], dtype='i4'))
            assert_equal(h['y'], np.array([self._buffer[0][1],
                                             self._buffer[1][1]], dtype='f8'))
            assert_equal(h['z'], np.array([self._buffer[0][2],
                                             self._buffer[1][2]], dtype='u1'))


class TestReadValuesPlainSingle(ReadValuesPlain):
    """Check the creation of heterogeneous arrays (plain, single row)"""
    _descr = Pdescr
    multiple_rows = 0
    _buffer = PbufferT[0]

class TestReadValuesPlainMultiple(ReadValuesPlain):
    """Check the values of heterogeneous arrays (plain, multiple rows)"""
    _descr = Pdescr
    multiple_rows = 1
    _buffer = PbufferT

class ReadValuesNested:
    """Check the reading of values in heterogeneous arrays (nested)"""

    def test_access_top_fields(self):
        """Check reading the top fields of a nested array"""
        h = np.array(self._buffer, dtype=self._descr)
        if not self.multiple_rows:
            assert_(h.shape == ())
            assert_equal(h['x'], np.array(self._buffer[0], dtype='i4'))
            assert_equal(h['y'], np.array(self._buffer[4], dtype='f8'))
            assert_equal(h['z'], np.array(self._buffer[5], dtype='u1'))
        else:
            assert_(len(h) == 2)
            assert_equal(h['x'], np.array([self._buffer[0][0],
                                           self._buffer[1][0]], dtype='i4'))
            assert_equal(h['y'], np.array([self._buffer[0][4],
                                           self._buffer[1][4]], dtype='f8'))
            assert_equal(h['z'], np.array([self._buffer[0][5],
                                           self._buffer[1][5]], dtype='u1'))

    def test_nested1_acessors(self):
        """Check reading the nested fields of a nested array (1st level)"""
        h = np.array(self._buffer, dtype=self._descr)
        if not self.multiple_rows:
            assert_equal(h['Info']['value'],
                         np.array(self._buffer[1][0], dtype='c16'))
            assert_equal(h['Info']['y2'],
                         np.array(self._buffer[1][1], dtype='f8'))
            assert_equal(h['info']['Name'],
                         np.array(self._buffer[3][0], dtype='U2'))
            assert_equal(h['info']['Value'],
                         np.array(self._buffer[3][1], dtype='c16'))
        else:
            assert_equal(h['Info']['value'],
                         np.array([self._buffer[0][1][0],
                                self._buffer[1][1][0]],
                                dtype='c16'))
            assert_equal(h['Info']['y2'],
                         np.array([self._buffer[0][1][1],
                                self._buffer[1][1][1]],
                                dtype='f8'))
            assert_equal(h['info']['Name'],
                         np.array([self._buffer[0][3][0],
                                self._buffer[1][3][0]],
                               dtype='U2'))
            assert_equal(h['info']['Value'],
                         np.array([self._buffer[0][3][1],
                                self._buffer[1][3][1]],
                               dtype='c16'))

    def test_nested2_acessors(self):
        """Check reading the nested fields of a nested array (2nd level)"""
        h = np.array(self._buffer, dtype=self._descr)
        if not self.multiple_rows:
            assert_equal(h['Info']['Info2']['value'],
                         np.array(self._buffer[1][2][1], dtype='c16'))
            assert_equal(h['Info']['Info2']['z3'],
                         np.array(self._buffer[1][2][3], dtype='u4'))
        else:
            assert_equal(h['Info']['Info2']['value'],
                         np.array([self._buffer[0][1][2][1],
                                self._buffer[1][1][2][1]],
                               dtype='c16'))
            assert_equal(h['Info']['Info2']['z3'],
                         np.array([self._buffer[0][1][2][3],
                                self._buffer[1][1][2][3]],
                               dtype='u4'))

    def test_nested1_descriptor(self):
        """Check access nested descriptors of a nested array (1st level)"""
        h = np.array(self._buffer, dtype=self._descr)
        assert_(h.dtype['Info']['value'].name == 'complex128')
        assert_(h.dtype['Info']['y2'].name == 'float64')
        assert_(h.dtype['info']['Name'].name == 'str256')
        assert_(h.dtype['info']['Value'].name == 'complex128')

    def test_nested2_descriptor(self):
        """Check access nested descriptors of a nested array (2nd level)"""
        h = np.array(self._buffer, dtype=self._descr)
        assert_(h.dtype['Info']['Info2']['value'].name == 'void256')
        assert_(h.dtype['Info']['Info2']['z3'].name == 'void64')


class TestReadValuesNestedSingle(ReadValuesNested):
    """Check the values of heterogeneous arrays (nested, single row)"""
    _descr = Ndescr
    multiple_rows = False
    _buffer = NbufferT[0]

class TestReadValuesNestedMultiple(ReadValuesNested):
    """Check the values of heterogeneous arrays (nested, multiple rows)"""
    _descr = Ndescr
    multiple_rows = True
    _buffer = NbufferT

class TestEmptyField:
    def test_assign(self):
        a = np.arange(10, dtype=np.float32)
        a.dtype = [("int",   "<0i4"), ("float", "<2f4")]
        assert_(a['int'].shape == (5, 0))
        assert_(a['float'].shape == (5, 2))


class TestMultipleFields:
    def setup_method(self):
        self.ary = np.array([(1, 2, 3, 4), (5, 6, 7, 8)], dtype='i4,f4,i2,c8')

    def _bad_call(self):
        return self.ary['f0', 'f1']

    def test_no_tuple(self):
        assert_raises(IndexError, self._bad_call)

    def test_return(self):
        res = self.ary[['f0', 'f2']].tolist()
        assert_(res == [(1, 3), (5, 7)])


class TestIsSubDType:
    # scalar types can be promoted into dtypes
    wrappers = [np.dtype, lambda x: x]

    def test_both_abstract(self):
        assert_(np.issubdtype(np.floating, np.inexact))
        assert_(not np.issubdtype(np.inexact, np.floating))

    def test_same(self):
        for cls in (np.float32, np.int32):
            for w1, w2 in itertools.product(self.wrappers, repeat=2):
                assert_(np.issubdtype(w1(cls), w2(cls)))

    def test_subclass(self):
        # note we cannot promote floating to a dtype, as it would turn into a
        # concrete type
        for w in self.wrappers:
            assert_(np.issubdtype(w(np.float32), np.floating))
            assert_(np.issubdtype(w(np.float64), np.floating))

    def test_subclass_backwards(self):
        for w in self.wrappers:
            assert_(not np.issubdtype(np.floating, w(np.float32)))
            assert_(not np.issubdtype(np.floating, w(np.float64)))

    def test_sibling_class(self):
        for w1, w2 in itertools.product(self.wrappers, repeat=2):
            assert_(not np.issubdtype(w1(np.float32), w2(np.float64)))
            assert_(not np.issubdtype(w1(np.float64), w2(np.float32)))

    def test_nondtype_nonscalartype(self):
        # See gh-14619 and gh-9505 which introduced the deprecation to fix
        # this. These tests are directly taken from gh-9505
        assert not np.issubdtype(np.float32, 'float64')
        assert not np.issubdtype(np.float32, 'f8')
        assert not np.issubdtype(np.int32, str)
        assert not np.issubdtype(np.int32, 'int64')
        assert not np.issubdtype(np.str_, 'void')
        # for the following the correct spellings are
        # np.integer, np.floating, or np.complexfloating respectively:
        assert not np.issubdtype(np.int8, int)  # np.int8 is never np.int_
        assert not np.issubdtype(np.float32, float)
        assert not np.issubdtype(np.complex64, complex)
        assert not np.issubdtype(np.float32, "float")
        assert not np.issubdtype(np.float64, "f")

        # Test the same for the correct first datatype and abstract one
        # in the case of int, float, complex:
        assert np.issubdtype(np.float64, 'float64')
        assert np.issubdtype(np.float64, 'f8')
        assert np.issubdtype(np.str_, str)
        assert np.issubdtype(np.int64, 'int64')
        assert np.issubdtype(np.void, 'void')
        assert np.issubdtype(np.int8, np.integer)
        assert np.issubdtype(np.float32, np.floating)
        assert np.issubdtype(np.complex64, np.complexfloating)
        assert np.issubdtype(np.float64, "float")
        assert np.issubdtype(np.float32, "f")


class TestIsDType:
    """
    Check correctness of `np.isdtype`. The test considers different argument
    configurations: `np.isdtype(dtype, k1)` and `np.isdtype(dtype, (k1, k2))`
    with concrete dtypes and dtype groups.
    """
    dtype_group_dict = {
        "signed integer": sctypes["int"],
        "unsigned integer": sctypes["uint"],
        "integral": sctypes["int"] + sctypes["uint"],
        "real floating": sctypes["float"],
        "complex floating": sctypes["complex"],
        "numeric": (
            sctypes["int"] + sctypes["uint"] + sctypes["float"] +
            sctypes["complex"]
        )
    }

    @pytest.mark.parametrize(
        "dtype,close_dtype",
        [
            (np.int64, np.int32), (np.uint64, np.uint32),
            (np.float64, np.float32), (np.complex128, np.complex64)
        ]
    )
    @pytest.mark.parametrize(
        "dtype_group",
        [
            None, "signed integer", "unsigned integer", "integral",
            "real floating", "complex floating", "numeric"
        ]
    )
    def test_isdtype(self, dtype, close_dtype, dtype_group):
        # First check if same dtypes return `true` and different ones
        # give `false` (even if they're close in the dtype hierarchy!)
        if dtype_group is None:
            assert np.isdtype(dtype, dtype)
            assert not np.isdtype(dtype, close_dtype)
            assert np.isdtype(dtype, (dtype, close_dtype))

        # Check that dtype and a dtype group that it belongs to
        # return `true`, and `false` otherwise.
        elif dtype in self.dtype_group_dict[dtype_group]:
            assert np.isdtype(dtype, dtype_group)
            assert np.isdtype(dtype, (close_dtype, dtype_group))
        else:
            assert not np.isdtype(dtype, dtype_group)

    def test_isdtype_invalid_args(self):
        with assert_raises_regex(TypeError, r".*must be a NumPy dtype.*"):
            np.isdtype("int64", np.int64)
        with assert_raises_regex(TypeError, r".*kind argument must.*"):
            np.isdtype(np.int64, 1)
        with assert_raises_regex(ValueError, r".*not a known kind name.*"):
            np.isdtype(np.int64, "int64")

    def test_sctypes_complete(self):
        # issue 26439: int32/intc were masking each other on 32-bit builds
        assert np.int32 in sctypes['int']
        assert np.intc in sctypes['int']
        assert np.int64 in sctypes['int']
        assert np.uint32 in sctypes['uint']
        assert np.uintc in sctypes['uint']
        assert np.uint64 in sctypes['uint']

class TestSctypeDict:
    def test_longdouble(self):
        assert_(np._core.sctypeDict['float64'] is not np.longdouble)
        assert_(np._core.sctypeDict['complex128'] is not np.clongdouble)

    def test_ulong(self):
        assert np._core.sctypeDict['ulong'] is np.ulong
        assert np.dtype(np.ulong) is np.dtype("ulong")
        assert np.dtype(np.ulong).itemsize == np.dtype(np.long).itemsize


@pytest.mark.filterwarnings("ignore:.*maximum_sctype.*:DeprecationWarning")
class TestMaximumSctype:

    # note that parametrizing with sctype['int'] and similar would skip types
    # with the same size (gh-11923)

    @pytest.mark.parametrize(
        't', [np.byte, np.short, np.intc, np.long, np.longlong]
    )
    def test_int(self, t):
        assert_equal(maximum_sctype(t), np._core.sctypes['int'][-1])

    @pytest.mark.parametrize(
        't', [np.ubyte, np.ushort, np.uintc, np.ulong, np.ulonglong]
    )
    def test_uint(self, t):
        assert_equal(maximum_sctype(t), np._core.sctypes['uint'][-1])

    @pytest.mark.parametrize('t', [np.half, np.single, np.double, np.longdouble])
    def test_float(self, t):
        assert_equal(maximum_sctype(t), np._core.sctypes['float'][-1])

    @pytest.mark.parametrize('t', [np.csingle, np.cdouble, np.clongdouble])
    def test_complex(self, t):
        assert_equal(maximum_sctype(t), np._core.sctypes['complex'][-1])

    @pytest.mark.parametrize('t', [np.bool, np.object_, np.str_, np.bytes_,
                                   np.void])
    def test_other(self, t):
        assert_equal(maximum_sctype(t), t)


class Test_sctype2char:
    # This function is old enough that we're really just documenting the quirks
    # at this point.

    def test_scalar_type(self):
        assert_equal(sctype2char(np.double), 'd')
        assert_equal(sctype2char(np.long), 'l')
        assert_equal(sctype2char(np.int_), np.array(0).dtype.char)
        assert_equal(sctype2char(np.str_), 'U')
        assert_equal(sctype2char(np.bytes_), 'S')

    def test_other_type(self):
        assert_equal(sctype2char(float), 'd')
        assert_equal(sctype2char(list), 'O')
        assert_equal(sctype2char(np.ndarray), 'O')

    def test_third_party_scalar_type(self):
        from numpy._core._rational_tests import rational
        assert_raises(KeyError, sctype2char, rational)
        assert_raises(KeyError, sctype2char, rational(1))

    def test_array_instance(self):
        assert_equal(sctype2char(np.array([1.0, 2.0])), 'd')

    def test_abstract_type(self):
        assert_raises(KeyError, sctype2char, np.floating)

    def test_non_type(self):
        assert_raises(ValueError, sctype2char, 1)

@pytest.mark.parametrize("rep, expected", [
    (np.int32, True),
    (list, False),
    (1.1, False),
    (str, True),
    (np.dtype(np.float64), True),
    (np.dtype((np.int16, (3, 4))), True),
    (np.dtype([('a', np.int8)]), True),
    ])
def test_issctype(rep, expected):
    # ensure proper identification of scalar
    # data-types by issctype()
    actual = issctype(rep)
    assert type(actual) is bool
    assert_equal(actual, expected)


@pytest.mark.skipif(sys.flags.optimize > 1,
                    reason="no docstrings present to inspect when PYTHONOPTIMIZE/Py_OptimizeFlag > 1")
@pytest.mark.xfail(IS_PYPY,
                   reason="PyPy cannot modify tp_doc after PyType_Ready")
class TestDocStrings:
    def test_platform_dependent_aliases(self):
        if np.int64 is np.int_:
            assert_('int64' in np.int_.__doc__)
        elif np.int64 is np.longlong:
            assert_('int64' in np.longlong.__doc__)


class TestScalarTypeNames:
    # gh-9799

    numeric_types = [
        np.byte, np.short, np.intc, np.long, np.longlong,
        np.ubyte, np.ushort, np.uintc, np.ulong, np.ulonglong,
        np.half, np.single, np.double, np.longdouble,
        np.csingle, np.cdouble, np.clongdouble,
    ]

    def test_names_are_unique(self):
        # none of the above may be aliases for each other
        assert len(set(self.numeric_types)) == len(self.numeric_types)

        # names must be unique
        names = [t.__name__ for t in self.numeric_types]
        assert len(set(names)) == len(names)

    @pytest.mark.parametrize('t', numeric_types)
    def test_names_reflect_attributes(self, t):
        """ Test that names correspond to where the type is under ``np.`` """
        assert getattr(np, t.__name__) is t

    @pytest.mark.parametrize('t', numeric_types)
    def test_names_are_undersood_by_dtype(self, t):
        """ Test the dtype constructor maps names back to the type """
        assert np.dtype(t.__name__).type is t


class TestBoolDefinition:
    def test_bool_definition(self):
        assert nt.bool is np.bool
