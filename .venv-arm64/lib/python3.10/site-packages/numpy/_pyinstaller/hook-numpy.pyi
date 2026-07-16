from typing import Final

# from `PyInstaller.compat`
is_conda: Final[bool]
is_pure_conda: Final[bool]

# from `PyInstaller.utils.hooks`
def is_module_satisfies(requirements: str, version: None = None, version_attr: None = None) -> bool: ...

binaries: Final[list[tuple[str, str]]]

hiddenimports: Final[list[str]]
excludedimports: Final[list[str]]
