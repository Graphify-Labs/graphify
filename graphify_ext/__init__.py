"""graphify_ext — fork-owned extension layer on top of upstream graphify.

All code in this package is owned by this fork (BiomedicalEvidencePlatform/graphify)
and is never present upstream (safishamsi/graphify). Keeping our divergence here — in
new, additively-namespaced files — means `git merge upstream/v8` stays conflict-free:
upstream never touches these paths.

See ``FORK.md`` at the repo root for the full fork strategy.
"""

__all__ = ["__version__"]

# Version of the fork layer, independent of upstream's package version.
__version__ = "0.1.0"
