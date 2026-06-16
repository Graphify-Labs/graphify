from __future__ import annotations
from pathlib import Path
from .registry import register
from .base import BasePlatformInstaller


@register("claw")
class ClawInstaller(BasePlatformInstaller):
    name = "claw"

    def install(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        from .. import __main__

        __main__._agents_install(project_dir or Path("."), "claw")

    def uninstall(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        from .. import __main__

        __main__._agents_uninstall(project_dir or Path("."), platform="claw")
