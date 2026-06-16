"""Pi coding agent installer."""
from __future__ import annotations
from pathlib import Path
from .registry import register
from .base import BasePlatformInstaller


@register("pi")
class PiInstaller(BasePlatformInstaller):
    name = "pi"
    
    def install(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        from .. import __main__
        __main__._project_install("pi", project_dir)
    
    def uninstall(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        from .utils import remove_skill_file
        remove_skill_file("pi", project_dir, project)
