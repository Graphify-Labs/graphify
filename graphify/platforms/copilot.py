"""GitHub Copilot CLI installer."""
from __future__ import annotations
from pathlib import Path
from .registry import register
from .base import BasePlatformInstaller


@register("copilot")
class CopilotInstaller(BasePlatformInstaller):
    name = "copilot"
    
    def install(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        from .. import __main__
        __main__._project_install("copilot", project_dir)
    
    def uninstall(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        from .utils import remove_skill_file
        remove_skill_file("copilot", project_dir, project)
