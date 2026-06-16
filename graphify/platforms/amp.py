from __future__ import annotations

from pathlib import Path

from .base import BasePlatformInstaller
from .registry import register


@register("amp")
class AmpInstaller(BasePlatformInstaller):
    name = "amp"

    def install(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        from graphify.__main__ import (
            _agents_install,
            _amp_legacy_cleanup,
            _copy_skill_file,
        )

        _amp_legacy_cleanup()
        _copy_skill_file("amp")
        _agents_install(project_dir or Path("."), "amp")

    def uninstall(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        from graphify.__main__ import (
            _agents_uninstall,
            _remove_skill_file,
        )

        removed = _remove_skill_file("amp")
        if removed:
            print("skill removed")
        _agents_uninstall(project_dir or Path("."), platform="amp")
