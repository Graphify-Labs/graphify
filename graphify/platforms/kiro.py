from __future__ import annotations

from pathlib import Path

from .base import BasePlatformInstaller
from .registry import register


@register("kiro")
class KiroInstaller(BasePlatformInstaller):
    name = "kiro"

    def install(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        from graphify.__main__ import (
            _always_on,
            _copy_skill_file,
            _platform_skill_destination,
        )

        project_dir = project_dir or Path(".")

        _copy_skill_file("kiro", project=True, project_dir=project_dir)

        steering_dir = project_dir / ".kiro" / "steering"
        steering_dir.mkdir(parents=True, exist_ok=True)
        steering_dst = steering_dir / "graphify.md"
        if steering_dst.exists() and steering_dst.read_text(encoding="utf-8") == _always_on(
            "kiro-steering"
        ):
            print(f"  .kiro/steering/graphify.md  ->  already configured (no change)")
        else:
            action = "updated" if steering_dst.exists() else "written"
            steering_dst.write_text(_always_on("kiro-steering"), encoding="utf-8")
            print(f"  .kiro/steering/graphify.md  ->  always-on steering {action}")

        print()
        print("Kiro will now read the knowledge graph before every conversation.")
        print("Use /graphify to build or update the graph.")

    def uninstall(self, project_dir: Path | None = None, *, project: bool = False) -> None:
        from graphify.__main__ import (
            _platform_skill_destination,
            _remove_skill_file,
        )

        project_dir = project_dir or Path(".")
        removed = []

        skill_dst = _platform_skill_destination("kiro", project=True, project_dir=project_dir)
        if _remove_skill_file("kiro", project=True, project_dir=project_dir):
            removed.append(str(skill_dst.relative_to(project_dir)))

        steering_dst = project_dir / ".kiro" / "steering" / "graphify.md"
        if steering_dst.exists():
            steering_dst.unlink()
            removed.append(str(steering_dst.relative_to(project_dir)))

        print("Removed: " + (", ".join(removed) if removed else "nothing to remove"))
