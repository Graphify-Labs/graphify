import pytest

import numpy as np
from numpy._core.multiarray import _vec_string
from numpy.testing import (
    assert_, assert_equal, assert_array_equal, assert_raises,
    assert_raises_regex
    )

kw_unicode_true = {'unicode': True}  # make 2to3 work properly
kw_unicode_false = {'unicode': False}

class TestBasic:
    def test_from_object_array(self):
        A = np.array([['abc', 2],
                      ['long   ', '0123456789']], dtype='O')
        B = np.char.array(A)
        assert_equal(B.dtype.itemsize, 10)
        assert_array_equal(B, [[b'abc', b'2'],
                               [b'long', b'0123456789']])

    def test_from_object_array_unicode(self):
        A = np.array([['abc', 'Sigma \u03a3'],
                      ['long   ', '0123456789']], dtype='O')
        assert_raises(ValueError, np.char.array, (A,))
        B = np.char.array(A, **kw_unicode_true)
        assert_equal(B.dtype.itemsize, 10 * np.array('a', 'U').dtype.itemsize)
        assert_array_equal(B, [['abc', 'Sigma \u03a3'],
                               ['long', '0123456789']])

    def test_from_string_array(self):
        A = np.array([[b'abc', b'foo'],
                      [b'long   ', b'0123456789']])
        assert_equal(A.dtype.type, np.bytes_)
        B = np.char.array(A)
        assert_array_equal(B, A)
        assert_equal(B.dtype, A.dtype)
        assert_equal(B.shape, A.shape)
        B[0, 0] = 'changed'
        assert_(B[0, 0] != A[0, 0])
        C = np.char.asarray(A)
        assert_array_equal(C, A)
        assert_equal(C.dtype, A.dtype)
        C[0, 0] = 'changed again'
        assert_(C[0, 0] != B[0, 0])
        assert_(C[0, 0] == A[0, 0])

    def test_from_unicode_array(self):
        A = np.array([['abc', 'Sigma \u03a3'],
                      ['long   ', '0123456789']])
        assert_equal(A.dtype.type, np.str_)
        B = np.char.array(A)
        assert_array_equal(B, A)
        assert_equal(B.dtype, A.dtype)
        assert_equal(B.shape, A.shape)
        B = np.char.array(A, **kw_unicode_true)
        assert_array_equal(B, A)
        assert_equal(B.dtype, A.dtype)
        assert_equal(B.shape, A.shape)

        def fail():
            np.char.array(A, **kw_unicode_false)

        assert_raises(UnicodeEncodeError, fail)

    def test_unicode_upconvert(self):
        A = np.char.array(['abc'])
        B = np.char.array(['\u03a3'])
        assert_(issubclass((A + B).dtype.type, np.str_))

    def test_from_string(self):
        A = np.char.array(b'abc')
        assert_equal(len(A), 1)
        assert_equal(len(A[0]), 3)
        assert_(issubclass(A.dtype.type, np.bytes_))

    def test_from_unicode(self):
        A = np.char.array('\u03a3')
        assert_equal(len(A), 1)
        assert_equal(len(A[0]), 1)
        assert_equal(A.itemsize, 4)
        assert_(issubclass(A.dtype.type, np.str_))

class TestVecString:
    def test_non_existent_method(self):

        def fail():
            _vec_string('a', np.bytes_, 'bogus')

        assert_raises(AttributeError, fail)

    def test_non_string_array(self):

        def fail():
            _vec_string(1, np.bytes_, 'strip')

        assert_raises(TypeError, fail)

    def test_invalid_args_tuple(self):

        def fail():
            _vec_string(['a'], np.bytes_, 'strip', 1)

        assert_raises(TypeError, fail)

    def test_invalid_type_descr(self):

        def fail():
            _vec_string(['a'], 'BOGUS', 'strip')

        assert_raises(TypeError, fail)

    def test_invalid_function_args(self):

        def fail():
            _vec_string(['a'], np.bytes_, 'strip', (1,))

        assert_raises(TypeError, fail)

    def test_invalid_result_type(self):

        def fail():
            _vec_string(['a'], np.int_, 'strip')

        assert_raises(TypeError, fail)

    def test_broadcast_error(self):

        def fail():
            _vec_string([['abc', 'def']], np.int_, 'find', (['a', 'd', 'j'],))

        assert_raises(ValueError, fail)


class TestWhitespace:
    def setup_method(self):
        self.A = np.array([['abc ', '123  '],
                           ['789 ', 'xyz ']]).view(np.char.chararray)
        self.B = np.array([['abc', '123'],
                           ['789', 'xyz']]).view(np.char.chararray)

    def test1(self):
        assert_(np.all(self.A == self.B))
        assert_(np.all(self.A >= self.B))
        assert_(np.all(self.A <= self.B))
        assert_(not np.any(self.A > self.B))
        assert_(not np.any(self.A < self.B))
        assert_(not np.any(self.A != self.B))

class TestChar:
    def setup_method(self):
        self.A = np.array('abc1', dtype='c').view(np.char.chararray)

    def test_it(self):
        assert_equal(self.A.shape, (4,))
        assert_equal(self.A.upper()[:2].tobytes(), b'AB')

class TestComparisons:
    def setup_method(self):
        self.A = np.array([['abc', 'abcc', '123'],
                           ['789', 'abc', 'xyz']]).view(np.char.chararray)
        self.B = np.array([['efg', 'efg', '123  '],
                           ['051', 'efgg', 'tuv']]).view(np.char.chararray)

    def test_not_equal(self):
        assert_array_equal((self.A != self.B),
                           [[True, True, False], [True, True, True]])

    def test_equal(self):
        assert_array_equal((self.A == self.B),
                           [[False, False, True], [False, False, False]])

    def test_greater_equal(self):
        assert_array_equal((self.A >= self.B),
                           [[False, False, True], [True, False, True]])

    def test_less_equal(self):
        assert_array_equal((self.A <= self.B),
                           [[True, True, True], [False, True, False]])

    def test_greater(self):
        assert_array_equal((self.A > self.B),
                           [[False, False, False], [True, False, True]])

    def test_less(self):
        assert_array_equal((self.A < self.B),
                           [[True, True, False], [False, True, False]])

    def test_type(self):
        out1 = np.char.equal(self.A, self.B)
        out2 = np.char.equal('a', 'a')
        assert_(isinstance(out1, np.ndarray))
        assert_(isinstance(out2, np.ndarray))

class TestComparisonsMixed1(TestComparisons):
    """Ticket #1276"""

    def setup_method(self):
        TestComparisons.setup_method(self)
        self.B = np.array(
            [['efg', 'efg', '123  '],
             ['051', 'efgg', 'tuv']], np.str_).view(np.char.chararray)

class TestComparisonsMixed2(TestComparisons):
    """Ticket #1276"""

    def setup_method(self):
        TestComparisons.setup_method(self)
        self.A = np.array(
            [['abc', 'abcc', '123'],
             ['789', 'abc', 'xyz']], np.str_).view(np.char.chararray)

class TestInformation:
    def setup_method(self):
        self.A = np.array([[' abc ', ''],
                           ['12345', 'MixedCase'],
                           ['123 \t 345 \0 ', 'UPPER']]) \
                            .view(np.char.chararray)
        self.B = np.array([[' \u03a3 ', ''],
                           ['12345', 'MixedCase'],
                           ['123 \t 345 \0 ', 'UPPER']]) \
                            .view(np.char.chararray)
        # Array with longer strings, > MEMCHR_CUT_OFF in code.
        self.C = (np.array(['ABCDEFGHIJKLMNOPQRSTUVWXYZ',
                            '01234567890123456789012345'])
                  .view(np.char.chararray))

    def test_len(self):
        assert_(issubclass(np.char.str_len(self.A).dtype.type, np.integer))
        assert_array_equal(np.char.str_len(self.A), [[5, 0], [5, 9], [12, 5]])
        assert_array_equal(np.char.str_len(self.B), [[3, 0], [5, 9], [12, 5]])

    def test_count(self):
        assert_(issubclass(self.A.count('').dtype.type, np.integer))
        assert_array_equal(self.A.count('a'), [[1, 0], [0, 1], [0, 0]])
        assert_array_equal(self.A.count('123'), [[0, 0], [1, 0], [1, 0]])
        # Python doesn't seem to like counting NULL characters
        # assert_array_equal(self.A.count('\0'), [[0, 0], [0, 0], [1, 0]])
        assert_array_equal(self.A.count('a', 0, 2), [[1, 0], [0, 0], [0, 0]])
        assert_array_equal(self.B.count('a'), [[0, 0], [0, 1], [0, 0]])
        assert_array_equal(self.B.count('123'), [[0, 0], [1, 0], [1, 0]])
        # assert_array_equal(self.B.count('\0'), [[0, 0], [0, 0], [1, 0]])

    def test_endswith(self):
        assert_(issubclass(self.A.endswith('').dtype.type, np.bool))
        assert_array_equal(self.A.endswith(' '), [[1, 0], [0, 0], [1, 0]])
        assert_array_equal(self.A.endswith('3', 0, 3), [[0, 0], [1, 0], [1, 0]])

        def fail():
            self.A.endswith('3', 'fdjk')

        assert_raises(TypeError, fail)

    @pytest.mark.parametrize(
        "dtype, encode",
        [("U", str),
         ("S", lambda x: x.encode('ascii')),
         ])
    def test_find(self, dtype, encode):
        A = self.A.astype(dtype)
        assert_(issubclass(A.find(encode('a')).dtype.type, np.integer))
        assert_array_equal(A.find(encode('a')),
                           [[1, -1], [-1, 6], [-1, -1]])
        assert_array_equal(A.find(encode('3')),
                           [[-1, -1], [2, -1], [2, -1]])
        assert_array_equal(A.find(encode('a'), 0, 2),
                           [[1, -1], [-1, -1], [-1, -1]])
        assert_array_equal(A.find([encode('1'), encode('P')]),
                           [[-1, -1], [0, -1], [0, 1]])
        C = self.C.astype(dtype)
        assert_array_equal(C.find(encode('M')), [12, -1])

    def test_index(self):

        def fail():
            self.A.index('a')

        assert_raises(ValueError, fail)
        assert_(np.char.index('abcba', 'b') == 1)
        assert_(issubclass(np.char.index('abcba', 'b').dtype.type, np.integer))

    def test_isalnum(self):
        assert_(issubclass(self.A.isalnum().dtype.type, np.bool))
        assert_array_equal(self.A.isalnum(), [[False, False], [True, True], [False, True]])

    def test_isalpha(self):
        assert_(issubclass(self.A.isalpha().dtype.type, np.bool))
        assert_array_equal(self.A.isalpha(), [[False, False], [False, True], [False, True]])

    def test_isdigit(self):
        assert_(issubclass(self.A.isdigit().dtype.type, np.bool))
        assert_array_equal(self.A.isdigit(), [[False, False], [True, False], [False, False]])

    def test_islower(self):
        assert_(issubclass(self.A.islower().dtype.type, np.bool))
        assert_array_equal(self.A.islower(), [[True, False], [False, False], [False, False]])

    def test_isspace(self):
        assert_(issubclass(self.A.isspace().dtype.type, np.bool))
        assert_array_equal(self.A.isspace(), [[False, False], [False, False], [False, False]])

    def test_istitle(self):
        assert_(issubclass(self.A.istitle().dtype.type, np.bool))
        assert_array_equal(self.A.istitle(), [[False, False], [False, False], [False, False]])

    def test_isupper(self):
        assert_(issubclass(self.A.isupper().dtype.type, np.bool))
        assert_array_equal(self.A.isupper(), [[False, False], [False, False], [False, True]])

    def test_rfind(self):
        assert_(issubclass(self.A.rfind('a').dtype.type, np.integer))
        assert_array_equal(self.A.rfind('a'), [[1, -1], [-1, 6], [-1, -1]])
        assert_array_equal(self.A.rfind('3'), [[-1, -1], [2, -1], [6, -1]])
        assert_array_equal(self.A.rfind('a', 0, 2), [[1, -1], [-1, -1], [-1, -1]])
        assert_array_equal(self.A.rfind(['1', 'P']), [[-1, -1], [0, -1], [0, 2]])

    def test_rindex(self):

        def fail():
            self.A.rindex('a')

        assert_raises(ValueError, fail)
        assert_(np.char.rindex('abcba', 'b') == 3)
        assert_(issubclass(np.char.rindex('abcba', 'b').dtype.type, np.integer))

    def test_startswith(self):
        assert_(issubclass(self.A.startswith('').dtype.type, np.bool))
        assert_array_equal(self.A.startswith(' '), [[1, 0], [0, 0], [0, 0]])
        assert_array_equal(self.A.startswith('1', 0, 3), [[0, 0], [1, 0], [1, 0]])

        def fail():
            self.A.startswith('3', 'fdjk')

        assert_raises(TypeError, fail)


class TestMethods:
    def setup_method(self):
        self.A = np.array([[' abc ', ''],
                           ['12345', 'MixedCase'],
                           ['123 \t 345 \0 ', 'UPPER']],
                          dtype='S').view(np.char.chararray)
        self.B = np.array([[' \u03a3 ', ''],
                           ['12345', 'MixedCase'],
                           ['123 \t 345 \0 ', 'UPPER']]).view(
                                                            np.char.chararray)

    def test_capitalize(self):
        tgt = [[b' abc ', b''],
               [b'12345', b'Mixedcase'],
               [b'123 \t 345 \0 ', b'Upper']]
        assert_(issubclass(self.A.capitalize().dtype.type, np.bytes_))
        assert_array_equal(self.A.capitalize(), tgt)

        tgt = [[' \u03c3 ', ''],
               ['12345', 'Mixedcase'],
               ['123 \t 345 \0 ', 'Upper']]
        assert_(issubclass(self.B.capitalize().dtype.type, np.str_))
        assert_array_equal(self.B.capitalize(), tgt)

    def test_center(self):
        assert_(issubclass(self.A.center(10).dtype.type, np.bytes_))
        C = self.A.center([10, 20])
        assert_array_equal(np.char.str_len(C), [[10, 20], [10, 20], [12, 20]])

        C = self.A.center(20, b'#')
        assert_(np.all(C.startswith(b'#')))
        assert_(np.all(C.endswith(b'#')))

        C = np.char.center(b'FOO', [[10, 20], [15, 8]])
        tgt = [[b'   FOO    ', b'        FOO         '],
               [b'      FOO      ', b'  FOO   ']]
        assert_(issubclass(C.dtype.type, np.bytes_))
        assert_array_equal(C, tgt)

    def test_decode(self):
        A = np.char.array([b'\\u03a3'])
        assert_(A.decode('unicode-escape')[0] == '\u03a3')

    def test_encode(self):
        B = self.B.encode('unicode_escape')
        assert_(B[0][0] == str(' \\u03a3 ').encode('latin1'))

    def test_expandtabs(self):
        T = self.A.expandtabs()
        assert_(T[2, 0] == b'123      345 \0')

    def test_join(self):
        # NOTE: list(b'123') == [49, 50, 51]
        #       so that b','.join(b'123') results to an error on Py3
        A0 = self.A.decode('ascii')

        A = np.char.join([',', '#'], A0)
        assert_(issubclass(A.dtype.type, np.str_))
        tgt = np.array([[' ,a,b,c, ', ''],
                        ['1,2,3,4,5', 'M#i#x#e#d#C#a#s#e'],
                        ['1,2,3, ,\t, ,3,4,5, ,\x00, ', 'U#P#P#E#R']])
        assert_array_equal(np.char.join([',', '#'], A0), tgt)

    def test_ljust(self):
        assert_(issubclass(self.A.ljust(10).dtype.type, np.bytes_))

        C = self.A.ljust([10, 20])
        assert_array_equal(np.char.str_len(C), [[10, 20], [10, 20], [12, 20]])

        C = self.A.ljust(20, b'#')
        assert_array_equal(C.startswith(b'#'), [
                [False, True], [False, False], [False, False]])
        assert_(np.all(C.endswith(b'#')))

        C = np.char.ljust(b'FOO', [[10, 20], [15, 8]])
        tgt = [[b'FOO       ', b'FOO                 '],
               [b'FOO            ', b'FOO     ']]
        assert_(issubclass(C.dtype.type, np.bytes_))
        assert_array_equal(C, tgt)

    def test_lower(self):
        tgt = [[b' abc ', b''],
               [b'12345', b'mixedcase'],
               [b'123 \t 345 \0 ', b'upper']]
        assert_(issubclass(self.A.lower().dtype.type, np.bytes_))
        assert_array_equal(self.A.lower(), tgt)

        tgt = [[' \u03c3 ', ''],
               ['12345', 'mixedcase'],
               ['123 \t 345 \0 ', 'upper']]
        assert_(issubclass(self.B.lower().dtype.type, np.str_))
        assert_array_equal(self.B.lower(), tgt)

    def test_lstrip(self):
        tgt = [[b'abc ', b''],
               [b'12345', b'MixedCase'],
               [b'123 \t 345 \0 ', b'UPPER']]
        assert_(issubclass(self.A.lstrip().dtype.type, np.bytes_))
        assert_array_equal(self.A.lstrip(), tgt)

        tgt = [[b' abc', b''],
               [b'2345', b'ixedCase'],
               [b'23 \t 345 \x00', b'UPPER']]
        assert_array_equal(self.A.lstrip([b'1', b'M']), tgt)

        tgt = [['\u03a3 ', ''],
               ['12345', 'MixedCase'],
               ['123 \t 345 \0 ', 'UPPER']]
        assert_(issubclass(self.B.lstrip().dtype.type, np.str_))
        assert_array_equal(self.B.lstrip(), tgt)

    def test_partition(self):
        P = self.A.partition([b'3', b'M'])
        tgt = [[(b' abc ', b'', b''), (b'', b'', b'')],
               [(b'12', b'3', b'45'), (b'', b'M', b'ixedCase')],
               [(b'12', b'3', b' \t 345 \0 '), (b'UPPER', b'', b'')]]
        assert_(issubclass(P.dtype.type, np.bytes_))
        assert_array_equal(P, tgt)

    def test_replace(self):
        R = self.A.replace([b'3', b'a'],
                           [b'##########', b'@'])
        tgt = [[b' abc ', b''],
               [b'12##########45', b'MixedC@se'],
               [b'12########## \t ##########45 \x00 ', b'UPPER']]
        assert_(issubclass(R.dtype.type, np.bytes_))
        assert_array_equal(R, tgt)
        # Test special cases that should just return the input array,
        # since replacements are not possible or do nothing.
        S1 = self.A.replace(b'A very long byte string, longer than A', b'')
        assert_array_equal(S1, self.A)
        S2 = self.A.replace(b'', b'')
        assert_array_equal(S2, self.A)
        S3 = self.A.replace(b'3', b'3')
        assert_array_equal(S3, self.A)
        S4 = self.A.replace(b'3', b'', count=0)
        assert_array_equal(S4, self.A)

    def test_replace_count_and_size(self):
        a = np.array(['0123456789' * i for i in range(4)]
                     ).view(np.char.chararray)
        r1 = a.replace('5', 'ABCDE')
        assert r1.dtype.itemsize == (3*10 + 3*4) * 4
        assert_array_equal(r1, np.array(['01234ABCDE6789' * i
                                         for i in range(4)]))
        r2 = a.replace('5', 'ABCDE', count=1)
        assert r2.dtype.itemsize == (3*10 + 4) * 4
        r3 = a.replace('5', 'ABCDE', count=0)
        assert r3.dtype.itemsize == a.dtype.itemsize
        assert_array_equal(r3, a)
        # Negative values mean to replace all.
        r4 = a.replace('5', 'ABCDE', count=-1)
        assert r4.dtype.itemsize == (3*10 + 3*4) * 4
        assert_array_equal(r4, r1)
        # We can do count on an element-by-element basis.
        r5 = a.replace('5', 'ABCDE', count=[-1, -1, -1, 1])
        assert r5.dtype.itemsize == (3*10 + 4) * 4
        assert_array_equal(r5, np.array(
            ['01234ABCDE6789' * i for i in range(3)]
            + ['01234ABCDE6789' + '0123456789' * 2]))

    def test_replace_broadcasting(self):
        a = np.array('0,0,0').view(np.char.chararray)
        r1 = a.replace('0', '1', count=np.arange(3))
        assert r1.dtype == a.dtype
        assert_array_equal(r1, np.array(['0,0,0', '1,0,0', '1,1,0']))
        r2 = a.replace('0', [['1'], ['2']], count=np.arange(1, 4))
        assert_array_equal(r2, np.array([['1,0,0', '1,1,0', '1,1,1'],
                                         ['2,0,0', '2,2,0', '2,2,2']]))
        r3 = a.replace(['0', '0,0', '0,0,0'], 'X')
        assert_array_equal(r3, np.array(['X,X,X', 'X,0', 'X']))

    def test_rjust(self):
        assert_(issubclass(self.A.rjust(10).dtype.type, np.bytes_))

        C = self.A.rjust([10, 20])
        assert_array_equal(np.char.str_len(C), [[10, 20], [10, 20], [12, 20]])

        C = self.A.rjust(20, b'#')
        assert_(np.all(C.startswith(b'#')))
        assert_array_equal(C.endswith(b'#'),
                           [[False, True], [False, False], [False, False]])

        C = np.char.rjust(b'FOO', [[10, 20], [15, 8]])
        tgt = [[b'       FOO', b'                 FOO'],
               [b'            FOO', b'     FOO']]
        assert_(issubclass(C.dtype.type, np.bytes_))
        assert_array_equal(C, tgt)

    def test_rpartition(self):
        P = self.A.rpartition([b'3', b'M'])
        tgt = [[(b'', b'', b' abc '), (b'', b'', b'')],
               [(b'12', b'3', b'45'), (b'', b'M', b'ixedCase')],
               [(b'123 \t ', b'3', b'45 \0 '), (b'', b'', b'UPPER')]]
        assert_(issubclass(P.dtype.type, np.bytes_))
        assert_array_equal(P, tgt)

    def test_rsplit(self):
        A = self.A.rsplit(b'3')
        tgt = [[[b' abc '], [b'']],
               [[b'12', b'45'], [b'MixedCase']],
               [[b'12', b' \t ', b'45 \x00 '], [b'UPPER']]]
        assert_(issubclass(A.dtype.type, np.object_))
        assert_equal(A.tolist(), tgt)

    def test_rstrip(self):
        assert_(issubclass(self.A.rstrip().dtype.type, np.bytes_))

        tgt = [[b' abc', b''],
               [b'12345', b'MixedCase'],
               [b'123 \t 345', b'UPPER']]
        assert_array_equal(self.A.rstrip(), tgt)

        tgt = [[b' abc ', b''],
               [b'1234', b'MixedCase'],
               [b'123 \t 345 \x00', b'UPP']
               ]
        assert_array_equal(self.A.rstrip([b'5', b'ER']), tgt)

        tgt = [[' \u03a3', ''],
               ['12345', 'MixedCase'],
               ['123 \t 345', 'UPPER']]
        assert_(issubclass(self.B.rstrip().dtype.type, np.str_))
        assert_array_equal(self.B.rstrip(), tgt)

    def test_strip(self):
        tgt = [[b'abc', b''],
               [b'12345', b'MixedCase'],
               [b'123 \t 345', b'UPPER']]
        assert_(issubclass(self.A.strip().dtype.type, np.bytes_))
        assert_array_equal(self.A.strip(), tgt)

        tgt = [[b' abc ', b''],
               [b'234', b'ixedCas'],
               [b'23 \t 345 \x00', b'UPP']]
        assert_array_equal(self.A.strip([b'15', b'EReM']), tgt)

        tgt = [['\u03a3', ''],
               ['12345', 'MixedCase'],
               ['123 \t 345', 'UPPER']]
        assert_(issubclass(self.B.strip().dtype.type, np.str_))
        assert_array_equal(self.B.strip(), tgt)

    def test_split(self):
        A = self.A.split(b'3')
        tgt = [
               [[b' abc '], [b'']],
               [[b'12', b'45'], [b'MixedCase']],
               [[b'12', b' \t ', b'45 \x00 '], [b'UPPER']]]
        assert_(issubclass(A.dtype.type, np.object_))
        assert_equal(A.tolist(), tgt)

    def test_splitlines(self):
        A = np.char.array(['abc\nfds\nwer']).splitlines()
        assert_(issubclass(A.dtype.type, np.object_))
        assert_(A.shape == (1,))
        assert_(len(A[0]) == 3)

    def test_swapcase(self):
        tgt = [[b' ABC ', b''],
               [b'12345', b'mIXEDcASE'],
               [b'123 \t 345 \0 ', b'upper']]
        assert_(issubclass(self.A.swapcase().dtype.type, np.bytes_))
        assert_array_equal(self.A.swapcase(), tgt)

        tgt = [[' \u03c3 ', ''],
               ['12345', 'mIXEDcASE'],
               ['123 \t 345 \0 ', 'upper']]
        assert_(issubclass(self.B.swapcase().dtype.type, np.str_))
        assert_array_equal(self.B.swapcase(), tgt)

    def test_title(self):
        tgt = [[b' Abc ', b''],
               [b'12345', b'Mixedcase'],
               [b'123 \t 345 \0 ', b'Upper']]
        assert_(issubclass(self.A.title().dtype.type, np.bytes_))
        assert_array_equal(self.A.title(), tgt)

        tgt = [[' \u03a3 ', ''],
               ['12345', 'Mixedcase'],
               ['123 \t 345 \0 ', 'Upper']]
        assert_(issubclass(self.B.title().dtype.type, np.str_))
        assert_array_equal(self.B.title(), tgt)

    def test_upper(self):
        tgt = [[b' ABC ', b''],
               [b'12345', b'MIXEDCASE'],
               [b'123 \t 345 \0 ', b'UPPER']]
        assert_(issubclass(self.A.upper().dtype.type, np.bytes_))
        assert_array_equal(self.A.upper(), tgt)

        tgt = [[' \u03a3 ', ''],
               ['12345', 'MIXEDCASE'],
               ['123 \t 345 \0 ', 'UPPER']]
        assert_(issubclass(self.B.upper().dtype.type, np.str_))
        assert_array_equal(self.B.upper(), tgt)

    def test_isnumeric(self):

        def fail():
            self.A.isnumeric()

        assert_raises(TypeError, fail)
        assert_(issubclass(self.B.isnumeric().dtype.type, np.bool))
        assert_array_equal(self.B.isnumeric(), [
                [False, False], [True, False], [False, False]])

    def test_isdecimal(self):

        def fail():
            self.A.isdecimal()

        assert_raises(TypeError, fail)
        assert_(issubclass(self.B.isdecimal().dtype.type, np.bool))
        assert_array_equal(self.B.isdecimal(), [
                [False, False], [True, False], [False, False]])


class TestOperations:
    def setup_method(self):
        self.A = np.array([['abc', '123'],
                           ['789', 'xyz']]).view(np.char.chararray)
        self.B = np.array([['efg', '456'],
                           ['051', 'tuv']]).view(np.char.chararray)

    def test_add(self):
        AB = np.array([['abcefg', '123456'],
                       ['789051', 'xyztuv']]).view(np.char.chararray)
        assert_array_equal(AB, (self.A + self.B))
        assert_(len((self.A + self.B)[0][0]) == 6)

    def test_radd(self):
        QA = np.array([['qabc', 'q123'],
                       ['q789', 'qxyz']]).view(np.char.chararray)
        assert_array_equal(QA, ('q' + self.A))

    def test_mul(self):
        A = self.A
        for r in (2, 3, 5, 7, 197):
            Ar = np.array([[A[0, 0]*r, A[0, 1]*r],
                           [A[1, 0]*r, A[1, 1]*r]]).view(np.char.chararray)

            assert_array_equal(Ar, (self.A * r))

        for ob in [object(), 'qrs']:
            with assert_raises_regex(ValueError,
                                     'Can only multiply by integers'):
                A*ob

    def test_rmul(self):
        A = self.A
        for r in (2, 3, 5, 7, 197):
            Ar = np.array([[A[0, 0]*r, A[0, 1]*r],
                           [A[1, 0]*r, A[1, 1]*r]]).view(np.char.chararray)
            assert_array_equal(Ar, (r * self.A))

        for ob in [object(), 'qrs']:
            with assert_raises_regex(ValueError,
                                     'Can only multiply by integers'):
                ob * A

    def test_mod(self):
        """Ticket #856"""
        F = np.array([['%d', '%f'], ['%s', '%r']]).view(np.char.chararray)
        C = np.array([[3, 7], [19, 1]], dtype=np.int64)
        FC = np.array([['3', '7.000000'],
                       ['19', 'np.int64(1)']]).view(np.char.chararray)
        assert_array_equal(FC, F % C)

        A = np.array([['%.3f', '%d'], ['%s', '%r']]).view(np.char.chararray)
        A1 = np.array([['1.000', '1'],
                       ['1', repr(np.array(1)[()])]]).view(np.char.chararray)
        assert_array_equal(A1, (A % 1))

        A2 = np.array([['1.000', '2'],
                       ['3', repr(np.array(4)[()])]]).view(np.char.chararray)
        assert_array_equal(A2, (A % [[1, 2], [3, 4]]))

    def test_rmod(self):
        assert_(("%s" % self.A) == str(self.A))
        assert_(("%r" % self.A) == repr(self.A))

        for ob in [42, object()]:
            with assert_raises_regex(
                    TypeError, "unsupported operand type.* and 'chararray'"):
                ob % self.A

    def test_slice(self):
        """Regression test for https://github.com/numpy/numpy/issues/5982"""

        arr = np.array([['abc ', 'def '], ['geh ', 'ijk ']],
                       dtype='S4').view(np.char.chararray)
        sl1 = arr[:]
        assert_array_equal(sl1, arr)
        assert_(sl1.base is arr)
        assert_(sl1.base.base is arr.base)

        sl2 = arr[:, :]
        assert_array_equal(sl2, arr)
        assert_(sl2.base is arr)
        assert_(sl2.base.base is arr.base)

        assert_(arr[0, 0] == b'abc')

    @pytest.mark.parametrize('data', [['plate', '   ', 'shrimp'],
                                      [b'retro', b'  ', b'encabulator']])
    def test_getitem_length_zero_item(self, data):
        # Regression test for gh-26375.
        a = np.char.array(data)
        # a.dtype.type() will be an empty string or bytes instance.
        # The equality test will fail if a[1] has the wrong type
        # or does not have length 0.
        assert_equal(a[1], a.dtype.type())


class TestMethodsEmptyArray:
    def setup_method(self):
        self.U = np.array([], dtype='U')
        self.S = np.array([], dtype='S')

    def test_encode(self):
        res = np.char.encode(self.U)
        assert_array_equal(res, [])
        assert_(res.dtype.char == 'S')

    def test_decode(self):
        res = np.char.decode(self.S)
        assert_array_equal(res, [])
        assert_(res.dtype.char == 'U')

    def test_decode_with_reshape(self):
        res = np.char.decode(self.S.reshape((1, 0, 1)))
        assert_(res.shape == (1, 0, 1))


class TestMethodsScalarValues:
    def test_mod(self):
        A = np.array([[' abc ', ''],
                      ['12345', 'MixedCase'],
                      ['123 \t 345 \0 ', 'UPPER']], dtype='S')
        tgt = [[b'123 abc ', b'123'],
               [b'12312345', b'123MixedCase'],
               [b'123123 \t 345 \0 ', b'123UPPER']]
        assert_array_equal(np.char.mod(b"123%s", A), tgt)

    def test_decode(self):
        bytestring = b'\x81\xc1\x81\xc1\x81\xc1'
        assert_equal(np.char.decode(bytestring, encoding='cp037'),
                     'aAaAaA')

    def test_encode(self):
        unicode = 'aAaAaA'
        assert_equal(np.char.encode(unicode, encoding='cp037'),
                     b'\x81\xc1\x81\xc1\x81\xc1')

    def test_expandtabs(self):
        s = "\tone level of indentation\n\t\ttwo levels of indentation"
        assert_equal(
            np.char.expandtabs(s, tabsize=2),
            "  one level of indentation\n    two levels of indentation"
        )

    def test_join(self):
        seps = np.array(['-', '_'])
        assert_array_equal(np.char.join(seps, 'hello'),
                           ['h-e-l-l-o', 'h_e_l_l_o'])

    def test_partition(self):
        assert_equal(np.char.partition('This string', ' '),
                     ['This', ' ', 'string'])

    def test_rpartition(self):
        assert_equal(np.char.rpartition('This string here', ' '),
                     ['This string', ' ', 'here'])

    def test_replace(self):
        assert_equal(np.char.replace('Python is good', 'good', 'great'),
                     'Python is great')


def test_empty_indexing():
    """Regression test for ticket 1948."""
    # Check that indexing a chararray with an empty list/array returns an
    # empty chararray instead of a chararray with a single empty string in it.
    s = np.char.chararray((4,))
    assert_(s[[]].size == 0)
