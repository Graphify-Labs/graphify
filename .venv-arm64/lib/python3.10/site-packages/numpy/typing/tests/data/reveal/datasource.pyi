from pathlib import Path
from typing import IO, Any

import numpy as np

from typing_extensions import assert_type

path1: Path
path2: str

d1 = np.lib.npyio.DataSource(path1)
d2 = np.lib.npyio.DataSource(path2)
d3 = np.lib.npyio.DataSource(None)

assert_type(d1.abspath("..."), str)
assert_type(d2.abspath("..."), str)
assert_type(d3.abspath("..."), str)

assert_type(d1.exists("..."), bool)
assert_type(d2.exists("..."), bool)
assert_type(d3.exists("..."), bool)

assert_type(d1.open("...", "r"), IO[Any])
assert_type(d2.open("...", encoding="utf8"), IO[Any])
assert_type(d3.open("...", newline="/n"), IO[Any])
