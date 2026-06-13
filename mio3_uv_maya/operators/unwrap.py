"""Unwrap operators.

Maya's native UV projection/unfold behavior differs from Blender's unwrap
operators. This module intentionally wraps deterministic native commands first
and leaves advanced parity algorithms behind explicit placeholders.
"""

from __future__ import annotations

from . import align
from .base import Action, warn
from ..core.gridify import gridify_islands
from ..core.maya_api import cmds
from ..core.mesh import MayaUVIslandManager
from ..core.rectify import RectifyOptions, rectify_islands
from ..core.settings import Settings


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


def gridify():
    manager = MayaUVIslandManager.from_selection()
    if not manager.islands:
        warn("Select quad UV shells first.")
        return False

    settings = Settings.load()
    result = gridify_islands(
        manager.islands,
        ratio_influence=settings.gridify_ratio_influence,
        shape_blend=settings.gridify_shape_blend,
        selected_face_ids_by_shape=getattr(manager, "selected_face_ids_by_shape", {}),
    )
    if result.quad_islands <= 0:
        warn("Gridify needs at least one quad UV island.")
        return False

    if settings.gridify_normalize:
        align.normalize(keep_aspect=settings.gridify_keep_aspect)

    if result.changed_islands <= 0 and result.already_rectangular:
        warn("Gridify found only already rectangular quad islands.")
    elif result.changed_islands <= 0:
        warn("Gridify did not change the current selection.")
    return True


def rectify():
    manager = MayaUVIslandManager.from_selection(include_all_if_no_components=False)
    if not manager.islands:
        warn("Select at least four UVs on a UV island first.")
        return False

    settings = Settings.load()
    options = RectifyOptions(
        bbox_type=settings.rectify_bbox_type,
        distribute=settings.rectify_distribute,
        unwrap_method=settings.rectify_unwrap_method,
        unwrap=settings.rectify_unwrap,
        stretch=settings.rectify_stretch,
        pin=settings.rectify_pin,
    )
    result = rectify_islands(manager.islands, getattr(manager, "selected_uvs_by_shape", {}), options)
    if result.valid_islands <= 0:
        warn("Rectify needs at least four selected UV reference points.")
        return False
    if result.changed_islands <= 0:
        warn("Rectify did not change the current selection.")
    return True


def not_ready(name: str):
    warn("{} is scaffolded for the parity phase and is not implemented yet.".format(name))
    return False


ACTIONS = [
    Action("unwrap", "Unwrap", "Use Maya unfold on the current selection.", maya_unfold, "unwrap"),
    Action("unwrap_project", "Project", "Planar project selected faces.", projection_unwrap, "camera"),
    Action("straight", "Straight", "Parity placeholder.", lambda: not_ready("Straight"), "straight"),
    Action("gridify", "Gridify", "Align selected quad UV shells into a grid.", gridify, "grid"),
    Action("rectify", "Rectify", "Unwrap selected UV boundaries into a rectangle.", rectify, "rectify"),
    Action("virtual_mirror", "Virtual Mirror", "Parity placeholder.", lambda: not_ready("Virtual Mirror"), "mirror_uv"),
]
