"""`tqdm` version detector. Precedence: installed dist, git, 'UNKNOWN'."""
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version('tqdm')
except PackageNotFoundError:
    __version__ = "UNKNOWN"
