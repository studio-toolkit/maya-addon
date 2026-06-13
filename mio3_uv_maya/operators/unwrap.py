"""Unwrap operators.

Maya's native UV projection/unfold behavior differs from Blender's unwrap
operators. This module intentionally wraps deterministic native commands first
and leaves advanced parity algorithms behind explicit placeholders.
"""

from __future__ import annotations

from .base import Action, warn
from ..core.maya_api import cmds


def maya_unfold():
    maya_cmds = cmds()
    selection = maya_cmds.ls(sl=True, fl=True) or []
    if not selection:
        warn("Select UVs, faces, edges, or a mesh first.")
        return False
    try:
        maya_cmds.unfold(selection, i=5000, ss=0.001, gb=0, gmb=0.5, pub=False, ps=0, oa=2, us=False)
    except Exception:
        try:
            maya_cmds.polyLayoutUV(selection, layout=0, ps=0.2)
        except Exception as exc:
            warn("Maya unfold failed: {}".format(exc))
            return False
    return True


def projection_unwrap():
    maya_cmds = cmds()
    selection = maya_cmds.ls(sl=True, fl=True) or []
    if not selection:
        warn("Select faces first.")
        return False
    try:
        maya_cmds.polyProjection(selection, type="Planar", md="b")
    except Exception as exc:
        warn("Projection unwrap failed: {}".format(exc))
        return False
    return True


def not_ready(name: str):
    warn("{} is scaffolded for the parity phase and is not implemented yet.".format(name))
    return False


ACTIONS = [
    Action("unwrap", "Unwrap", "Use Maya unfold on the current selection.", maya_unfold, "unwrap"),
    Action("unwrap_project", "Project", "Planar project selected faces.", projection_unwrap, "camera"),
    Action("straight", "Straight", "Parity placeholder.", lambda: not_ready("Straight"), "straight"),
    Action("gridify", "Gridify", "Parity placeholder.", lambda: not_ready("Gridify"), "grid"),
    Action("rectify", "Rectify", "Parity placeholder.", lambda: not_ready("Rectify"), "rectify"),
    Action("virtual_mirror", "Virtual Mirror", "Parity placeholder.", lambda: not_ready("Virtual Mirror"), "mirror_uv"),
]

