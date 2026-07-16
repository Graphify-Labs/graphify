from typing import Any

import numpy as np
import numpy.typing as npt
from numpy.linalg._linalg import (
    QRResult, EigResult, EighResult, SVDResult, SlogdetResult
)

from typing_extensions import assert_type

AR_i8: npt.NDArray[np.int64]
AR_f8: npt.NDArray[np.float64]
AR_c16: npt.NDArray[np.complex128]
AR_O: npt.NDArray[np.object_]
AR_m: npt.NDArray[np.timedelta64]
AR_S: npt.NDArray[np.str_]
AR_b: npt.NDArray[np.bool]

assert_type(np.linalg.tensorsolve(AR_i8, AR_i8), npt.NDArray[np.float64])
assert_type(np.linalg.tensorsolve(AR_i8, AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.linalg.tensorsolve(AR_c16, AR_f8), npt.NDArray[np.complexfloating[Any, Any]])

assert_type(np.linalg.solve(AR_i8, AR_i8), npt.NDArray[np.float64])
assert_type(np.linalg.solve(AR_i8, AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.linalg.solve(AR_c16, AR_f8), npt.NDArray[np.complexfloating[Any, Any]])

assert_type(np.linalg.tensorinv(AR_i8), npt.NDArray[np.float64])
assert_type(np.linalg.tensorinv(AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.linalg.tensorinv(AR_c16), npt.NDArray[np.complexfloating[Any, Any]])

assert_type(np.linalg.inv(AR_i8), npt.NDArray[np.float64])
assert_type(np.linalg.inv(AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.linalg.inv(AR_c16), npt.NDArray[np.complexfloating[Any, Any]])

assert_type(np.linalg.matrix_power(AR_i8, -1), npt.NDArray[Any])
assert_type(np.linalg.matrix_power(AR_f8, 0), npt.NDArray[Any])
assert_type(np.linalg.matrix_power(AR_c16, 1), npt.NDArray[Any])
assert_type(np.linalg.matrix_power(AR_O, 2), npt.NDArray[Any])

assert_type(np.linalg.cholesky(AR_i8), npt.NDArray[np.float64])
assert_type(np.linalg.cholesky(AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.linalg.cholesky(AR_c16), npt.NDArray[np.complexfloating[Any, Any]])

assert_type(np.linalg.outer(AR_i8, AR_i8), npt.NDArray[np.signedinteger[Any]])
assert_type(np.linalg.outer(AR_f8, AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.linalg.outer(AR_c16, AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
assert_type(np.linalg.outer(AR_b, AR_b), npt.NDArray[np.bool])
assert_type(np.linalg.outer(AR_O, AR_O), npt.NDArray[np.object_])
assert_type(np.linalg.outer(AR_i8, AR_m), npt.NDArray[np.timedelta64])

assert_type(np.linalg.qr(AR_i8), QRResult)
assert_type(np.linalg.qr(AR_f8), QRResult)
assert_type(np.linalg.qr(AR_c16), QRResult)

assert_type(np.linalg.eigvals(AR_i8), npt.NDArray[np.float64] | npt.NDArray[np.complex128])
assert_type(np.linalg.eigvals(AR_f8), npt.NDArray[np.floating[Any]] | npt.NDArray[np.complexfloating[Any, Any]])
assert_type(np.linalg.eigvals(AR_c16), npt.NDArray[np.complexfloating[Any, Any]])

assert_type(np.linalg.eigvalsh(AR_i8), npt.NDArray[np.float64])
assert_type(np.linalg.eigvalsh(AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.linalg.eigvalsh(AR_c16), npt.NDArray[np.floating[Any]])

assert_type(np.linalg.eig(AR_i8), EigResult)
assert_type(np.linalg.eig(AR_f8), EigResult)
assert_type(np.linalg.eig(AR_c16), EigResult)

assert_type(np.linalg.eigh(AR_i8), EighResult)
assert_type(np.linalg.eigh(AR_f8), EighResult)
assert_type(np.linalg.eigh(AR_c16), EighResult)

assert_type(np.linalg.svd(AR_i8), SVDResult)
assert_type(np.linalg.svd(AR_f8), SVDResult)
assert_type(np.linalg.svd(AR_c16), SVDResult)
assert_type(np.linalg.svd(AR_i8, compute_uv=False), npt.NDArray[np.float64])
assert_type(np.linalg.svd(AR_f8, compute_uv=False), npt.NDArray[np.floating[Any]])
assert_type(np.linalg.svd(AR_c16, compute_uv=False), npt.NDArray[np.floating[Any]])

assert_type(np.linalg.cond(AR_i8), Any)
assert_type(np.linalg.cond(AR_f8), Any)
assert_type(np.linalg.cond(AR_c16), Any)

assert_type(np.linalg.matrix_rank(AR_i8), Any)
assert_type(np.linalg.matrix_rank(AR_f8), Any)
assert_type(np.linalg.matrix_rank(AR_c16), Any)

assert_type(np.linalg.pinv(AR_i8), npt.NDArray[np.float64])
assert_type(np.linalg.pinv(AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.linalg.pinv(AR_c16), npt.NDArray[np.complexfloating[Any, Any]])

assert_type(np.linalg.slogdet(AR_i8), SlogdetResult)
assert_type(np.linalg.slogdet(AR_f8), SlogdetResult)
assert_type(np.linalg.slogdet(AR_c16), SlogdetResult)

assert_type(np.linalg.det(AR_i8), Any)
assert_type(np.linalg.det(AR_f8), Any)
assert_type(np.linalg.det(AR_c16), Any)

assert_type(np.linalg.lstsq(AR_i8, AR_i8), tuple[npt.NDArray[np.float64], npt.NDArray[np.float64], np.int32, npt.NDArray[np.float64]])
assert_type(np.linalg.lstsq(AR_i8, AR_f8), tuple[npt.NDArray[np.floating[Any]], npt.NDArray[np.floating[Any]], np.int32, npt.NDArray[np.floating[Any]]])
assert_type(np.linalg.lstsq(AR_f8, AR_c16), tuple[npt.NDArray[np.complexfloating[Any, Any]], npt.NDArray[np.floating[Any]], np.int32, npt.NDArray[np.floating[Any]]])

assert_type(np.linalg.norm(AR_i8), np.floating[Any])
assert_type(np.linalg.norm(AR_f8), np.floating[Any])
assert_type(np.linalg.norm(AR_c16), np.floating[Any])
assert_type(np.linalg.norm(AR_S), np.floating[Any])
assert_type(np.linalg.norm(AR_f8, axis=0), Any)

assert_type(np.linalg.matrix_norm(AR_i8), np.floating[Any])
assert_type(np.linalg.matrix_norm(AR_f8), np.floating[Any])
assert_type(np.linalg.matrix_norm(AR_c16), np.floating[Any])
assert_type(np.linalg.matrix_norm(AR_S), np.floating[Any])

assert_type(np.linalg.vector_norm(AR_i8), np.floating[Any])
assert_type(np.linalg.vector_norm(AR_f8), np.floating[Any])
assert_type(np.linalg.vector_norm(AR_c16), np.floating[Any])
assert_type(np.linalg.vector_norm(AR_S), np.floating[Any])

assert_type(np.linalg.multi_dot([AR_i8, AR_i8]), Any)
assert_type(np.linalg.multi_dot([AR_i8, AR_f8]), Any)
assert_type(np.linalg.multi_dot([AR_f8, AR_c16]), Any)
assert_type(np.linalg.multi_dot([AR_O, AR_O]), Any)
assert_type(np.linalg.multi_dot([AR_m, AR_m]), Any)

assert_type(np.linalg.cross(AR_i8, AR_i8), npt.NDArray[np.signedinteger[Any]])
assert_type(np.linalg.cross(AR_f8, AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.linalg.cross(AR_c16, AR_c16), npt.NDArray[np.complexfloating[Any, Any]])

assert_type(np.linalg.matmul(AR_i8, AR_i8), npt.NDArray[np.signedinteger[Any]])
assert_type(np.linalg.matmul(AR_f8, AR_f8), npt.NDArray[np.floating[Any]])
assert_type(np.linalg.matmul(AR_c16, AR_c16), npt.NDArray[np.complexfloating[Any, Any]])
