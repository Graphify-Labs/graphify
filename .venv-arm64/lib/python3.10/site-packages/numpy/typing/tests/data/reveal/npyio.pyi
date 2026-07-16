import re
import zipfile
import pathlib
from typing import IO, Any
from collections.abc import Mapping

import numpy.typing as npt
import numpy as np
from numpy.lib._npyio_impl import BagObj

from typing_extensions import assert_type

str_path: str
pathlib_path: pathlib.Path
str_file: IO[str]
bytes_file: IO[bytes]

npz_file: np.lib.npyio.NpzFile

AR_i8: npt.NDArray[np.int64]
AR_LIKE_f8: list[float]

class BytesWriter:
    def write(self, data: bytes) -> None: ...

class BytesReader:
    def read(self, n: int = ...) -> bytes: ...
    def seek(self, offset: int, whence: int = ...) -> int: ...

bytes_writer: BytesWriter
bytes_reader: BytesReader

assert_type(npz_file.zip, zipfile.ZipFile)
assert_type(npz_file.fid, None | IO[str])
assert_type(npz_file.files, list[str])
assert_type(npz_file.allow_pickle, bool)
assert_type(npz_file.pickle_kwargs, None | Mapping[str, Any])
assert_type(npz_file.f, BagObj[np.lib.npyio.NpzFile])
assert_type(npz_file["test"], npt.NDArray[Any])
assert_type(len(npz_file), int)
with npz_file as f:
    assert_type(f, np.lib.npyio.NpzFile)

assert_type(np.load(bytes_file), Any)
assert_type(np.load(pathlib_path, allow_pickle=True), Any)
assert_type(np.load(str_path, encoding="bytes"), Any)
assert_type(np.load(bytes_reader), Any)

assert_type(np.save(bytes_file, AR_LIKE_f8), None)
assert_type(np.save(pathlib_path, AR_i8, allow_pickle=True), None)
assert_type(np.save(str_path, AR_LIKE_f8), None)
assert_type(np.save(bytes_writer, AR_LIKE_f8), None)

assert_type(np.savez(bytes_file, AR_LIKE_f8), None)
assert_type(np.savez(pathlib_path, ar1=AR_i8, ar2=AR_i8), None)
assert_type(np.savez(str_path, AR_LIKE_f8, ar1=AR_i8), None)
assert_type(np.savez(bytes_writer, AR_LIKE_f8, ar1=AR_i8), None)

assert_type(np.savez_compressed(bytes_file, AR_LIKE_f8), None)
assert_type(np.savez_compressed(pathlib_path, ar1=AR_i8, ar2=AR_i8), None)
assert_type(np.savez_compressed(str_path, AR_LIKE_f8, ar1=AR_i8), None)
assert_type(np.savez_compressed(bytes_writer, AR_LIKE_f8, ar1=AR_i8), None)

assert_type(np.loadtxt(bytes_file), npt.NDArray[np.float64])
assert_type(np.loadtxt(pathlib_path, dtype=np.str_), npt.NDArray[np.str_])
assert_type(np.loadtxt(str_path, dtype=str, skiprows=2), npt.NDArray[Any])
assert_type(np.loadtxt(str_file, comments="test"), npt.NDArray[np.float64])
assert_type(np.loadtxt(str_file, comments=None), npt.NDArray[np.float64])
assert_type(np.loadtxt(str_path, delimiter="\n"), npt.NDArray[np.float64])
assert_type(np.loadtxt(str_path, ndmin=2), npt.NDArray[np.float64])
assert_type(np.loadtxt(["1", "2", "3"]), npt.NDArray[np.float64])

assert_type(np.fromregex(bytes_file, "test", np.float64), npt.NDArray[np.float64])
assert_type(np.fromregex(str_file, b"test", dtype=float), npt.NDArray[Any])
assert_type(np.fromregex(str_path, re.compile("test"), dtype=np.str_, encoding="utf8"), npt.NDArray[np.str_])
assert_type(np.fromregex(pathlib_path, "test", np.float64), npt.NDArray[np.float64])
assert_type(np.fromregex(bytes_reader, "test", np.float64), npt.NDArray[np.float64])

assert_type(np.genfromtxt(bytes_file), npt.NDArray[Any])
assert_type(np.genfromtxt(pathlib_path, dtype=np.str_), npt.NDArray[np.str_])
assert_type(np.genfromtxt(str_path, dtype=str, skip_header=2), npt.NDArray[Any])
assert_type(np.genfromtxt(str_file, comments="test"), npt.NDArray[Any])
assert_type(np.genfromtxt(str_path, delimiter="\n"), npt.NDArray[Any])
assert_type(np.genfromtxt(str_path, ndmin=2), npt.NDArray[Any])
assert_type(np.genfromtxt(["1", "2", "3"], ndmin=2), npt.NDArray[Any])
