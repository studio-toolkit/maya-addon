"""Utility operators for Maya."""

from __future__ import annotations

import os

from .base import Action, warn
from ..constants import (
    CHECKER_FILE_PREFIX,
    CHECKER_PLACE2D_PREFIX,
    CHECKER_SHADER_PREFIX,
    CHECKER_SHADING_GROUP_PREFIX,
    UVMESH_GROUP,
)
from ..core.maya_api import cmds
from ..core.settings import Settings


def _asset_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets"))


def checker_map(size: str | None = None):
    maya_cmds = cmds()
    settings = Settings.load()
    size = size or settings.checker_map_size
    selected = maya_cmds.ls(sl=True, long=True) or []
    if not selected:
        warn("Select one or more objects for the checker map.")
        return False

    shader = CHECKER_SHADER_PREFIX + str(size)
    shading_group = CHECKER_SHADING_GROUP_PREFIX + str(size)
    file_node = CHECKER_FILE_PREFIX + str(size)
    place_node = CHECKER_PLACE2D_PREFIX + str(size)

    if not maya_cmds.objExists(shader):
        shader = maya_cmds.shadingNode("lambert", asShader=True, name=shader)
    if not maya_cmds.objExists(shading_group):
        shading_group = maya_cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=shading_group)
    if not maya_cmds.isConnected(shader + ".outColor", shading_group + ".surfaceShader"):
        maya_cmds.connectAttr(shader + ".outColor", shading_group + ".surfaceShader", force=True)
    if not maya_cmds.objExists(file_node):
        file_node = maya_cmds.shadingNode("file", asTexture=True, isColorManaged=True, name=file_node)
    if not maya_cmds.objExists(place_node):
        place_node = maya_cmds.shadingNode("place2dTexture", asUtility=True, name=place_node)

    for src, dst in [
        ("coverage", "coverage"),
        ("translateFrame", "translateFrame"),
        ("rotateFrame", "rotateFrame"),
        ("mirrorU", "mirrorU"),
        ("mirrorV", "mirrorV"),
        ("stagger", "stagger"),
        ("wrapU", "wrapU"),
        ("wrapV", "wrapV"),
        ("repeatUV", "repeatUV"),
        ("offset", "offset"),
        ("rotateUV", "rotateUV"),
        ("noiseUV", "noiseUV"),
        ("vertexUvOne", "vertexUvOne"),
        ("vertexUvTwo", "vertexUvTwo"),
        ("vertexUvThree", "vertexUvThree"),
        ("vertexCameraOne", "vertexCameraOne"),
    ]:
        source_attr = place_node + "." + src
        dest_attr = file_node + "." + dst
        if maya_cmds.objExists(source_attr) and maya_cmds.objExists(dest_attr) and not maya_cmds.isConnected(source_attr, dest_attr):
            maya_cmds.connectAttr(source_attr, dest_attr, force=True)
    if not maya_cmds.isConnected(place_node + ".outUV", file_node + ".uvCoord"):
        maya_cmds.connectAttr(place_node + ".outUV", file_node + ".uvCoord", force=True)
    if not maya_cmds.isConnected(place_node + ".outUvFilterSize", file_node + ".uvFilterSize"):
        maya_cmds.connectAttr(place_node + ".outUvFilterSize", file_node + ".uvFilterSize", force=True)
    if not maya_cmds.isConnected(file_node + ".outColor", shader + ".color"):
        maya_cmds.connectAttr(file_node + ".outColor", shader + ".color", force=True)

    image_path = os.path.join(_asset_root(), "checker_maps", "chocomint_{}.png".format(size))
    if os.path.exists(image_path):
        maya_cmds.setAttr(file_node + ".fileTextureName", image_path, type="string")
    else:
        warn("Checker image not found: {}".format(image_path))

    maya_cmds.sets(selected, edit=True, forceElement=shading_group)
    settings.checker_map_size = str(size)
    settings.save()
    return True


def checker_cleanup():
    maya_cmds = cmds()
    for node_type in ("shadingEngine", "lambert", "file", "place2dTexture"):
        for node in maya_cmds.ls(type=node_type) or []:
            if node.startswith((
                CHECKER_SHADER_PREFIX,
                CHECKER_SHADING_GROUP_PREFIX,
                CHECKER_FILE_PREFIX,
                CHECKER_PLACE2D_PREFIX,
            )):
                try:
                    maya_cmds.delete(node)
                except Exception:
                    pass
    return True


def uv_mesh_preview():
    maya_cmds = cmds()
    selected = maya_cmds.ls(sl=True, long=True) or []
    meshes = maya_cmds.ls(selected, dag=True, type="mesh", noIntermediate=True, long=True) or []
    if not meshes:
        warn("Select mesh objects for UV Mesh preview.")
        return False
    if maya_cmds.objExists(UVMESH_GROUP):
        maya_cmds.delete(UVMESH_GROUP)
    group = maya_cmds.group(empty=True, name=UVMESH_GROUP)
    for shape in meshes:
        transform = maya_cmds.listRelatives(shape, parent=True, fullPath=True)[0]
        duplicate = maya_cmds.duplicate(transform, name="{}_uvPreview".format(transform.split("|")[-1]))[0]
        maya_cmds.parent(duplicate, group)
        maya_cmds.setAttr(duplicate + ".translateZ", 0)
    warn("UV Mesh preview scaffold created as duplicate mesh group.")
    return True


def uv_mesh_clear():
    maya_cmds = cmds()
    if maya_cmds.objExists(UVMESH_GROUP):
        maya_cmds.delete(UVMESH_GROUP)
    return True


def padding_preview():
    warn("Padding overlay is scaffolded; UV Editor paint overlay will be implemented in the parity phase.")
    return False


def exposure_preview():
    warn("Exposure adjustment is Blender-specific; Maya viewport/material display mapping is pending.")
    return False


ACTIONS = [
    Action("checker_map", "Checker Map", "Assign Mio3 checker material.", checker_map, "color_grid"),
    Action("checker_cleanup", "Cleanup Checker", "Delete owned checker nodes.", checker_cleanup, "gear"),
    Action("padding_preview", "Padding", "Parity placeholder.", padding_preview, "padding"),
    Action("uv_mesh_preview", "UV Mesh", "Create duplicate preview scaffold.", uv_mesh_preview, "cube"),
    Action("uv_mesh_clear", "Clear UV Mesh", "Remove UV Mesh preview scaffold.", uv_mesh_clear, "merge"),
    Action("exposure_preview", "Exposure", "Parity placeholder.", exposure_preview, "options"),
]

