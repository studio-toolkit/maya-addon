"""Mio3 UV Maya port package.

This package is a Maya 2022-2024 oriented Python/PySide2 port scaffold for
the Blender Mio3 UV add-on reference stored in ``Blender-Addon/``.
"""

from .constants import DISPLAY_NAME, VERSION


def show():
    """Open the dockable Maya UI."""
    from .ui.dock import show as show_ui

    return show_ui()


def reload_package():
    """Reload package modules during Maya development."""
    from .core.reload import reload_mio3_uv_maya

    return reload_mio3_uv_maya()


__all__ = ["DISPLAY_NAME", "VERSION", "show", "reload_package"]

