import numpy as np
import numpy.typing as npt
import numpy._typing as np_t

from typing_extensions import assert_type
from typing import TypeAlias

AR_U: npt.NDArray[np.str_]
AR_S: npt.NDArray[np.bytes_]
AR_T: np.ndarray[np_t._Shape, np.dtypes.StringDType]

AR_T_alias: TypeAlias = np.ndarray[np_t._Shape, np.dtypes.StringDType]
AR_TU_alias: TypeAlias = AR_T_alias | npt.NDArray[np.str_]

assert_type(np.strings.equal(AR_U, AR_U), npt.NDArray[np.bool])
assert_type(np.strings.equal(AR_S, AR_S), npt.NDArray[np.bool])
assert_type(np.strings.equal(AR_T, AR_T), npt.NDArray[np.bool])

assert_type(np.strings.not_equal(AR_U, AR_U), npt.NDArray[np.bool])
assert_type(np.strings.not_equal(AR_S, AR_S), npt.NDArray[np.bool])
assert_type(np.strings.not_equal(AR_T, AR_T), npt.NDArray[np.bool])

assert_type(np.strings.greater_equal(AR_U, AR_U), npt.NDArray[np.bool])
assert_type(np.strings.greater_equal(AR_S, AR_S), npt.NDArray[np.bool])
assert_type(np.strings.greater_equal(AR_T, AR_T), npt.NDArray[np.bool])

assert_type(np.strings.less_equal(AR_U, AR_U), npt.NDArray[np.bool])
assert_type(np.strings.less_equal(AR_S, AR_S), npt.NDArray[np.bool])
assert_type(np.strings.less_equal(AR_T, AR_T), npt.NDArray[np.bool])

assert_type(np.strings.greater(AR_U, AR_U), npt.NDArray[np.bool])
assert_type(np.strings.greater(AR_S, AR_S), npt.NDArray[np.bool])
assert_type(np.strings.greater(AR_T, AR_T), npt.NDArray[np.bool])

assert_type(np.strings.less(AR_U, AR_U), npt.NDArray[np.bool])
assert_type(np.strings.less(AR_S, AR_S), npt.NDArray[np.bool])
assert_type(np.strings.less(AR_T, AR_T), npt.NDArray[np.bool])

assert_type(np.strings.add(AR_U, AR_U), npt.NDArray[np.str_])
assert_type(np.strings.add(AR_S, AR_S), npt.NDArray[np.bytes_])
assert_type(np.strings.add(AR_T, AR_T), AR_T_alias)

assert_type(np.strings.multiply(AR_U, 5), npt.NDArray[np.str_])
assert_type(np.strings.multiply(AR_S, [5, 4, 3]), npt.NDArray[np.bytes_])
assert_type(np.strings.multiply(AR_T, 5), AR_T_alias)

assert_type(np.strings.mod(AR_U, "test"), npt.NDArray[np.str_])
assert_type(np.strings.mod(AR_S, "test"), npt.NDArray[np.bytes_])
assert_type(np.strings.mod(AR_T, "test"), AR_T_alias)

assert_type(np.strings.capitalize(AR_U), npt.NDArray[np.str_])
assert_type(np.strings.capitalize(AR_S), npt.NDArray[np.bytes_])
assert_type(np.strings.capitalize(AR_T), AR_T_alias)

assert_type(np.strings.center(AR_U, 5), npt.NDArray[np.str_])
assert_type(np.strings.center(AR_S, [2, 3, 4], b"a"), npt.NDArray[np.bytes_])
assert_type(np.strings.center(AR_T, 5), AR_T_alias)

assert_type(np.strings.encode(AR_U), npt.NDArray[np.bytes_])
assert_type(np.strings.encode(AR_T), npt.NDArray[np.bytes_])
assert_type(np.strings.decode(AR_S), npt.NDArray[np.str_])

assert_type(np.strings.expandtabs(AR_U), npt.NDArray[np.str_])
assert_type(np.strings.expandtabs(AR_S, tabsize=4), npt.NDArray[np.bytes_])
assert_type(np.strings.expandtabs(AR_T), AR_T_alias)

assert_type(np.strings.ljust(AR_U, 5), npt.NDArray[np.str_])
assert_type(np.strings.ljust(AR_S, [4, 3, 1], fillchar=[b"a", b"b", b"c"]), npt.NDArray[np.bytes_])
assert_type(np.strings.ljust(AR_T, 5), AR_T_alias)
assert_type(np.strings.ljust(AR_T, [4, 2, 1], fillchar=["a", "b", "c"]), AR_T_alias)

assert_type(np.strings.rjust(AR_U, 5), npt.NDArray[np.str_])
assert_type(np.strings.rjust(AR_S, [4, 3, 1], fillchar=[b"a", b"b", b"c"]), npt.NDArray[np.bytes_])
assert_type(np.strings.rjust(AR_T, 5), AR_T_alias)
assert_type(np.strings.rjust(AR_T, [4, 2, 1], fillchar=["a", "b", "c"]), AR_T_alias)

assert_type(np.strings.lstrip(AR_U), npt.NDArray[np.str_])
assert_type(np.strings.lstrip(AR_S, b"_"), npt.NDArray[np.bytes_])
assert_type(np.strings.lstrip(AR_T), AR_T_alias)
assert_type(np.strings.lstrip(AR_T, "_"), AR_T_alias)

assert_type(np.strings.rstrip(AR_U), npt.NDArray[np.str_])
assert_type(np.strings.rstrip(AR_S, b"_"), npt.NDArray[np.bytes_])
assert_type(np.strings.rstrip(AR_T), AR_T_alias)
assert_type(np.strings.rstrip(AR_T, "_"), AR_T_alias)

assert_type(np.strings.strip(AR_U), npt.NDArray[np.str_])
assert_type(np.strings.strip(AR_S, b"_"), npt.NDArray[np.bytes_])
assert_type(np.strings.strip(AR_T), AR_T_alias)
assert_type(np.strings.strip(AR_T, "_"), AR_T_alias)

assert_type(np.strings.count(AR_U, "a", start=[1, 2, 3]), npt.NDArray[np.int_])
assert_type(np.strings.count(AR_S, [b"a", b"b", b"c"], end=9), npt.NDArray[np.int_])
assert_type(np.strings.count(AR_T, "a", start=[1, 2, 3]), npt.NDArray[np.int_])
assert_type(np.strings.count(AR_T, ["a", "b", "c"], end=9), npt.NDArray[np.int_])

assert_type(np.strings.partition(AR_U, "\n"), npt.NDArray[np.str_])
assert_type(np.strings.partition(AR_S, [b"a", b"b", b"c"]), npt.NDArray[np.bytes_])
assert_type(np.strings.partition(AR_T, "\n"), AR_TU_alias)

assert_type(np.strings.rpartition(AR_U, "\n"), npt.NDArray[np.str_])
assert_type(np.strings.rpartition(AR_S, [b"a", b"b", b"c"]), npt.NDArray[np.bytes_])
assert_type(np.strings.rpartition(AR_T, "\n"), AR_TU_alias)

assert_type(np.strings.replace(AR_U, "_", "-"), npt.NDArray[np.str_])
assert_type(np.strings.replace(AR_S, [b"_", b""], [b"a", b"b"]), npt.NDArray[np.bytes_])
assert_type(np.strings.replace(AR_T, "_", "_"), AR_TU_alias)

assert_type(np.strings.lower(AR_U), npt.NDArray[np.str_])
assert_type(np.strings.lower(AR_S), npt.NDArray[np.bytes_])
assert_type(np.strings.lower(AR_T), AR_T_alias)

assert_type(np.strings.upper(AR_U), npt.NDArray[np.str_])
assert_type(np.strings.upper(AR_S), npt.NDArray[np.bytes_])
assert_type(np.strings.upper(AR_T), AR_T_alias)

assert_type(np.strings.swapcase(AR_U), npt.NDArray[np.str_])
assert_type(np.strings.swapcase(AR_S), npt.NDArray[np.bytes_])
assert_type(np.strings.swapcase(AR_T), AR_T_alias)

assert_type(np.strings.title(AR_U), npt.NDArray[np.str_])
assert_type(np.strings.title(AR_S), npt.NDArray[np.bytes_])
assert_type(np.strings.title(AR_T), AR_T_alias)

assert_type(np.strings.zfill(AR_U, 5), npt.NDArray[np.str_])
assert_type(np.strings.zfill(AR_S, [2, 3, 4]), npt.NDArray[np.bytes_])
assert_type(np.strings.zfill(AR_T, 5), AR_T_alias)

assert_type(np.strings.endswith(AR_U, "a", start=[1, 2, 3]), npt.NDArray[np.bool])
assert_type(np.strings.endswith(AR_S, [b"a", b"b", b"c"], end=9), npt.NDArray[np.bool])
assert_type(np.strings.endswith(AR_T, "a", start=[1, 2, 3]), npt.NDArray[np.bool])

assert_type(np.strings.startswith(AR_U, "a", start=[1, 2, 3]), npt.NDArray[np.bool])
assert_type(np.strings.startswith(AR_S, [b"a", b"b", b"c"], end=9), npt.NDArray[np.bool])
assert_type(np.strings.startswith(AR_T, "a", start=[1, 2, 3]), npt.NDArray[np.bool])

assert_type(np.strings.find(AR_U, "a", start=[1, 2, 3]), npt.NDArray[np.int_])
assert_type(np.strings.find(AR_S, [b"a", b"b", b"c"], end=9), npt.NDArray[np.int_])
assert_type(np.strings.find(AR_T, "a", start=[1, 2, 3]), npt.NDArray[np.int_])

assert_type(np.strings.rfind(AR_U, "a", start=[1, 2, 3]), npt.NDArray[np.int_])
assert_type(np.strings.rfind(AR_S, [b"a", b"b", b"c"], end=9), npt.NDArray[np.int_])
assert_type(np.strings.rfind(AR_T, "a", start=[1, 2, 3]), npt.NDArray[np.int_])

assert_type(np.strings.index(AR_U, "a", start=[1, 2, 3]), npt.NDArray[np.int_])
assert_type(np.strings.index(AR_S, [b"a", b"b", b"c"], end=9), npt.NDArray[np.int_])
assert_type(np.strings.index(AR_T, "a", start=[1, 2, 3]), npt.NDArray[np.int_])

assert_type(np.strings.rindex(AR_U, "a", start=[1, 2, 3]), npt.NDArray[np.int_])
assert_type(np.strings.rindex(AR_S, [b"a", b"b", b"c"], end=9), npt.NDArray[np.int_])
assert_type(np.strings.rindex(AR_T, "a", start=[1, 2, 3]), npt.NDArray[np.int_])

assert_type(np.strings.isalpha(AR_U), npt.NDArray[np.bool])
assert_type(np.strings.isalpha(AR_S), npt.NDArray[np.bool])
assert_type(np.strings.isalpha(AR_T), npt.NDArray[np.bool])

assert_type(np.strings.isalnum(AR_U), npt.NDArray[np.bool])
assert_type(np.strings.isalnum(AR_S), npt.NDArray[np.bool])
assert_type(np.strings.isalnum(AR_T), npt.NDArray[np.bool])

assert_type(np.strings.isdecimal(AR_U), npt.NDArray[np.bool])
assert_type(np.strings.isdecimal(AR_T), npt.NDArray[np.bool])

assert_type(np.strings.isdigit(AR_U), npt.NDArray[np.bool])
assert_type(np.strings.isdigit(AR_S), npt.NDArray[np.bool])
assert_type(np.strings.isdigit(AR_T), npt.NDArray[np.bool])

assert_type(np.strings.islower(AR_U), npt.NDArray[np.bool])
assert_type(np.strings.islower(AR_S), npt.NDArray[np.bool])
assert_type(np.strings.islower(AR_T), npt.NDArray[np.bool])

assert_type(np.strings.isnumeric(AR_U), npt.NDArray[np.bool])
assert_type(np.strings.isnumeric(AR_T), npt.NDArray[np.bool])

assert_type(np.strings.isspace(AR_U), npt.NDArray[np.bool])
assert_type(np.strings.isspace(AR_S), npt.NDArray[np.bool])
assert_type(np.strings.isspace(AR_T), npt.NDArray[np.bool])

assert_type(np.strings.istitle(AR_U), npt.NDArray[np.bool])
assert_type(np.strings.istitle(AR_S), npt.NDArray[np.bool])
assert_type(np.strings.istitle(AR_T), npt.NDArray[np.bool])

assert_type(np.strings.isupper(AR_U), npt.NDArray[np.bool])
assert_type(np.strings.isupper(AR_S), npt.NDArray[np.bool])
assert_type(np.strings.isupper(AR_T), npt.NDArray[np.bool])

assert_type(np.strings.str_len(AR_U), npt.NDArray[np.int_])
assert_type(np.strings.str_len(AR_S), npt.NDArray[np.int_])
assert_type(np.strings.str_len(AR_T), npt.NDArray[np.int_])

assert_type(np.strings.translate(AR_U, ""), npt.NDArray[np.str_])
assert_type(np.strings.translate(AR_S, ""), npt.NDArray[np.bytes_])
assert_type(np.strings.translate(AR_T, ""), AR_T_alias)
