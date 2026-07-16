from numpy.lib import NumpyVersion

from typing_extensions import assert_type

version = NumpyVersion("1.8.0")

assert_type(version.vstring, str)
assert_type(version.version, str)
assert_type(version.major, int)
assert_type(version.minor, int)
assert_type(version.bugfix, int)
assert_type(version.pre_release, str)
assert_type(version.is_devversion, bool)

assert_type(version == version, bool)
assert_type(version != version, bool)
assert_type(version < "1.8.0", bool)
assert_type(version <= version, bool)
assert_type(version > version, bool)
assert_type(version >= "1.8.0", bool)
