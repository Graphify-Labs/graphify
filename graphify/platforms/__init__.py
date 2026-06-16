"""Platform installers for graphify."""

from __future__ import annotations

from . import aider
from . import amp
from . import antigravity
from . import claude
from . import claw
from . import codebuddy
from . import codex
from . import copilot
from . import cursor
from . import devin
from . import droid
from . import gemini
from . import kilo
from . import kiro
from . import opencode
from . import pi
from . import trae
from . import vscode

from .registry import get_installer, get_all_platforms, is_registered, register
from .base import PlatformInstaller, BasePlatformInstaller

__all__ = [
    "get_installer",
    "get_all_platforms",
    "is_registered",
    "register",
    "PlatformInstaller",
    "BasePlatformInstaller",
]
