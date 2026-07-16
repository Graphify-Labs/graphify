
"""
Module to expose more detailed version info for the installed `numpy`
"""
version = "2.2.6"
__version__ = version
full_version = version

git_revision = "2b686f659642080e2fc708719385de6e8be0955f"
release = 'dev' not in version and '+' not in version
short_version = version.split("+")[0]
