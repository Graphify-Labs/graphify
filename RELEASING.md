# Releasing graphify

Maintainer-facing release process. Contributors do not need this; see
[CONTRIBUTING.md](CONTRIBUTING.md) for how to propose changes.

graphify publishes to PyPI (package name `graphifyy`) automatically through
GitHub trusted publishing. There is no manual `twine` upload and no API token to
manage.

## Steps

1. **Bump the version.** Edit `version` in `pyproject.toml`.
2. **Update the changelog.** Add a dated section for the new version at the top of
   `CHANGELOG.md`, crediting each landed PR and its author.
3. **Refresh the lock.** Run `uv lock` so `uv.lock` records the new version (and
   any dependency changes).
4. **Test on both supported interpreters.** Run the full suite on Python 3.10 and
   3.13:
   ```bash
   uv run pytest
   # and against a 3.13 environment, e.g.
   uv run --python 3.13 pytest
   ```
5. **Commit and push `v8`.** Commit the version, changelog, and lock together,
   then `git push origin v8`.
6. **Cut the GitHub release.** Tag the release off `v8`:
   ```bash
   gh release create vX.Y.Z --repo Graphify-Labs/graphify --target v8 \
     --title "vX.Y.Z" --notes-file <notes>
   ```
   Publishing the release fires `publish.yml` on the `release-published` event,
   which builds the wheel/sdist and uploads to PyPI via trusted publishing. Do
   **not** run `twine` or pass a token.
7. **Verify the install** once PyPI has the new version (the JSON API updates
   before the install index; use `--refresh`):
   ```bash
   uvx --refresh --from graphifyy==X.Y.Z graphify --version
   ```

## Version numbering

Keep public versions contiguous. If a number was bumped locally but never
published to PyPI, reuse that number for the next release rather than leaving a
gap.

## Supported versions

Security fixes target only the latest released `0.9.x`. See
[SECURITY.md](SECURITY.md).
