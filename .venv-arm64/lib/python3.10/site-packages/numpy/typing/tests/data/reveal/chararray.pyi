from typing import Any

import numpy as np
import numpy.typing as npt

from typing_extensions import assert_type

AR_U: np.char.chararray[tuple[int, ...], np.dtype[np.str_]]
AR_S: np.char.chararray[tuple[int, ...], np.dtype[np.bytes_]]

assert_type(AR_U == AR_U, npt.NDArray[np.bool])
assert_type(AR_S == AR_S, npt.NDArray[np.bool])

assert_type(AR_U != AR_U, npt.NDArray[np.bool])
assert_type(AR_S != AR_S, npt.NDArray[np.bool])

assert_type(AR_U >= AR_U, npt.NDArray[np.bool])
assert_type(AR_S >= AR_S, npt.NDArray[np.bool])

assert_type(AR_U <= AR_U, npt.NDArray[np.bool])
assert_type(AR_S <= AR_S, npt.NDArray[np.bool])

assert_type(AR_U > AR_U, npt.NDArray[np.bool])
assert_type(AR_S > AR_S, npt.NDArray[np.bool])

assert_type(AR_U < AR_U, npt.NDArray[np.bool])
assert_type(AR_S < AR_S, npt.NDArray[np.bool])

assert_type(AR_U * 5, np.char.chararray[tuple[int, ...], np.dtype[np.str_]])
assert_type(AR_S * [5], np.char.chararray[tuple[int, ...], np.dtype[np.bytes_]])

assert_type(AR_U % "test", np.char.chararray[tuple[int, ...], np.dtype[np.str_]])
assert_type(AR_S % b"test", np.char.chararray[tuple[int, ...], np.dtype[np.bytes_]])

assert_type(AR_U.capitalize(), np.char.chararray[tuple[int, ...], np.dtype[np.str_]])
assert_type(AR_S.capitalize(), np.char.chararray[tuple[int, ...], np.dtype[np.bytes_]])

assert_type(AR_U.center(5), np.char.chararray[tuple[int, ...], np.dtype[np.str_]])
assert_type(AR_S.center([2, 3, 4], b"a"), np.char.chararray[tuple[int, ...], np.dtype[np.bytes_]])

assert_type(AR_U.encode(), np.char.chararray[tuple[int, ...], np.dtype[np.bytes_]])
assert_type(AR_S.decode(), np.char.chararray[tuple[int, ...], np.dtype[np.str_]])

assert_type(AR_U.expandtabs(), np.char.chararray[tuple[int, ...], np.dtype[np.str_]])
assert_type(AR_S.expandtabs(tabsize=4), np.char.chararray[tuple[int, ...], np.dtype[np.bytes_]])

assert_type(AR_U.join("_"), np.char.chararray[tuple[int, ...], np.dtype[np.str_]])
assert_type(AR_S.join([b"_", b""]), np.char.chararray[tuple[int, ...], np.dtype[np.bytes_]])

assert_type(AR_U.ljust(5), np.char.chararray[tuple[int, ...], np.dtype[np.str_]])
assert_type(AR_S.ljust([4, 3, 1], fillchar=[b"a", b"b", b"c"]), np.char.chararray[tuple[int, ...], np.dtype[np.bytes_]])
assert_type(AR_U.rjust(5), np.char.chararray[tuple[int, ...], np.dtype[np.str_]])
assert_type(AR_S.rjust([4, 3, 1], fillchar=[b"a", b"b", b"c"]), np.char.chararray[tuple[int, ...], np.dtype[np.bytes_]])

assert_type(AR_U.lstrip(), np.char.chararray[tuple[int, ...], np.dtype[np.str_]])
assert_type(AR_S.lstrip(chars=b"_"), np.char.chararray[tuple[int, ...], np.dtype[np.bytes_]])
assert_type(AR_U.rstrip(), np.char.chararray[tuple[int, ...], np.dtype[np.str_]])
assert_type(AR_S.rstrip(chars=b"_"), np.char.chararray[tuple[int, ...], np.dtype[np.bytes_]])
assert_type(AR_U.strip(), np.char.chararray[tuple[int, ...], np.dtype[np.str_]])
assert_type(AR_S.strip(chars=b"_"), np.char.chararray[tuple[int, ...], np.dtype[np.bytes_]])

assert_type(AR_U.partition("\n"), np.char.chararray[tuple[int, ...], np.dtype[np.str_]])
assert_type(AR_S.partition([b"a", b"b", b"c"]), np.char.chararray[tuple[int, ...], np.dtype[np.bytes_]])
assert_type(AR_U.rpartition("\n"), np.char.chararray[tuple[int, ...], np.dtype[np.str_]])
assert_type(AR_S.rpartition([b"a", b"b", b"c"]), np.char.chararray[tuple[int, ...], np.dtype[np.bytes_]])

assert_type(AR_U.replace("_", "-"), np.char.chararray[tuple[int, ...], np.dtype[np.str_]])
assert_type(AR_S.replace([b"_", b""], [b"a", b"b"]), np.char.chararray[tuple[int, ...], np.dtype[np.bytes_]])

assert_type(AR_U.split("_"), npt.NDArray[np.object_])
assert_type(AR_S.split(maxsplit=[1, 2, 3]), npt.NDArray[np.object_])
assert_type(AR_U.rsplit("_"), npt.NDArray[np.object_])
assert_type(AR_S.rsplit(maxsplit=[1, 2, 3]), npt.NDArray[np.object_])

assert_type(AR_U.splitlines(), npt.NDArray[np.object_])
assert_type(AR_S.splitlines(keepends=[True, True, False]), npt.NDArray[np.object_])

assert_type(AR_U.swapcase(), np.char.chararray[tuple[int, ...], np.dtype[np.str_]])
assert_type(AR_S.swapcase(), np.char.chararray[tuple[int, ...], np.dtype[np.bytes_]])

assert_type(AR_U.title(), np.char.chararray[tuple[int, ...], np.dtype[np.str_]])
assert_type(AR_S.title(), np.char.chararray[tuple[int, ...], np.dtype[np.bytes_]])

assert_type(AR_U.upper(), np.char.chararray[tuple[int, ...], np.dtype[np.str_]])
assert_type(AR_S.upper(), np.char.chararray[tuple[int, ...], np.dtype[np.bytes_]])

assert_type(AR_U.zfill(5), np.char.chararray[tuple[int, ...], np.dtype[np.str_]])
assert_type(AR_S.zfill([2, 3, 4]), np.char.chararray[tuple[int, ...], np.dtype[np.bytes_]])

assert_type(AR_U.count("a", start=[1, 2, 3]), npt.NDArray[np.int_])
assert_type(AR_S.count([b"a", b"b", b"c"], end=9), npt.NDArray[np.int_])

assert_type(AR_U.endswith("a", start=[1, 2, 3]), npt.NDArray[np.bool])
assert_type(AR_S.endswith([b"a", b"b", b"c"], end=9), npt.NDArray[np.bool])
assert_type(AR_U.startswith("a", start=[1, 2, 3]), npt.NDArray[np.bool])
assert_type(AR_S.startswith([b"a", b"b", b"c"], end=9), npt.NDArray[np.bool])

assert_type(AR_U.find("a", start=[1, 2, 3]), npt.NDArray[np.int_])
assert_type(AR_S.find([b"a", b"b", b"c"], end=9), npt.NDArray[np.int_])
assert_type(AR_U.rfind("a", start=[1, 2, 3]), npt.NDArray[np.int_])
assert_type(AR_S.rfind([b"a", b"b", b"c"], end=9), npt.NDArray[np.int_])

assert_type(AR_U.index("a", start=[1, 2, 3]), npt.NDArray[np.int_])
assert_type(AR_S.index([b"a", b"b", b"c"], end=9), npt.NDArray[np.int_])
assert_type(AR_U.rindex("a", start=[1, 2, 3]), npt.NDArray[np.int_])
assert_type(AR_S.rindex([b"a", b"b", b"c"], end=9), npt.NDArray[np.int_])

assert_type(AR_U.isalpha(), npt.NDArray[np.bool])
assert_type(AR_S.isalpha(), npt.NDArray[np.bool])

assert_type(AR_U.isalnum(), npt.NDArray[np.bool])
assert_type(AR_S.isalnum(), npt.NDArray[np.bool])

assert_type(AR_U.isdecimal(), npt.NDArray[np.bool])
assert_type(AR_S.isdecimal(), npt.NDArray[np.bool])

assert_type(AR_U.isdigit(), npt.NDArray[np.bool])
assert_type(AR_S.isdigit(), npt.NDArray[np.bool])

assert_type(AR_U.islower(), npt.NDArray[np.bool])
assert_type(AR_S.islower(), npt.NDArray[np.bool])

assert_type(AR_U.isnumeric(), npt.NDArray[np.bool])
assert_type(AR_S.isnumeric(), npt.NDArray[np.bool])

assert_type(AR_U.isspace(), npt.NDArray[np.bool])
assert_type(AR_S.isspace(), npt.NDArray[np.bool])

assert_type(AR_U.istitle(), npt.NDArray[np.bool])
assert_type(AR_S.istitle(), npt.NDArray[np.bool])

assert_type(AR_U.isupper(), npt.NDArray[np.bool])
assert_type(AR_S.isupper(), npt.NDArray[np.bool])

assert_type(AR_U.__array_finalize__(object()), None)
assert_type(AR_S.__array_finalize__(object()), None)
