"""Registry for the live ComfyUI generation managers.

The :class:`~justllama.server.skills.comfy_agent.ComfyAgentSkill` runs inside
the :class:`SkillsManager` worker pool and needs to reach the
``ImageGenManager`` / ``VideoGenManager`` instances created in ``main.py``.
Those managers are not singletons, so ``main.py`` registers them here at
startup. Accessors return ``None`` until registered, which the skill handles
gracefully.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from justllama.server.imagegen import ImageGenManager
    from justllama.server.videogen import VideoGenManager

_image_manager: "ImageGenManager | None" = None
_video_manager: "VideoGenManager | None" = None


def register_managers(image_manager, video_manager) -> None:
    """Store the active generation manager instances (called from main.py)."""
    global _image_manager, _video_manager
    _image_manager = image_manager
    _video_manager = video_manager


def get_image_manager():
    """Return the live ImageGenManager, or None if not registered."""
    return _image_manager


def get_video_manager():
    """Return the live VideoGenManager, or None if not registered."""
    return _video_manager
