"""Persistent Maya optionVar backed settings."""

from __future__ import annotations

from dataclasses import dataclass

from ..constants import DEFAULT_TEXTURE_SIZES, OPTION_PREFIX
from .maya_api import MayaUnavailable, cmds


def _key(name: str) -> str:
    return "{}_{}".format(OPTION_PREFIX, name)


def get_option(name: str, default):
    try:
        maya_cmds = cmds()
    except MayaUnavailable:
        return default
    key = _key(name)
    if not maya_cmds.optionVar(exists=key):
        return default
    value = maya_cmds.optionVar(q=key)
    return value


def set_option(name: str, value) -> None:
    maya_cmds = cmds()
    key = _key(name)
    if isinstance(value, bool):
        maya_cmds.optionVar(iv=(key, int(value)))
    elif isinstance(value, int):
        maya_cmds.optionVar(iv=(key, value))
    elif isinstance(value, float):
        maya_cmds.optionVar(fv=(key, value))
    else:
        maya_cmds.optionVar(sv=(key, str(value)))


@dataclass
class Settings:
    align_mode: str = "AUTO"
    udim: bool = False
    symmetry_uv_axis: str = "X"
    symmetry_3d_axis: str = "AUTO"
    default_symmetry_priority: str = "POSITIVE"
    checker_map_size: str = "2048"
    texture_size_x: str = "2048"
    texture_size_y: str = "2048"
    texture_size_link: bool = True
    texel_density: float = 256.0
    texel_preset_buttons: bool = False
    gridify_ratio_influence: float = 0.5
    gridify_shape_blend: float = 0.0
    gridify_normalize: bool = False
    gridify_keep_aspect: bool = False

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            align_mode=str(get_option("alignMode", "AUTO")),
            udim=bool(int(get_option("udim", 0))),
            symmetry_uv_axis=str(get_option("symmetryUvAxis", "X")),
            symmetry_3d_axis=str(get_option("symmetry3dAxis", "AUTO")),
            default_symmetry_priority=str(get_option("defaultSymmetryPriority", "POSITIVE")),
            checker_map_size=str(get_option("checkerMapSize", "2048")),
            texture_size_x=str(get_option("textureSizeX", "2048")),
            texture_size_y=str(get_option("textureSizeY", "2048")),
            texture_size_link=bool(int(get_option("textureSizeLink", 1))),
            texel_density=float(get_option("texelDensity", 256.0)),
            texel_preset_buttons=bool(int(get_option("texelPresetButtons", 0))),
            gridify_ratio_influence=float(get_option("gridifyRatioInfluence", 0.5)),
            gridify_shape_blend=float(get_option("gridifyShapeBlend", 0.0)),
            gridify_normalize=bool(int(get_option("gridifyNormalize", 0))),
            gridify_keep_aspect=bool(int(get_option("gridifyKeepAspect", 0))),
        )

    def save(self) -> None:
        if self.checker_map_size not in DEFAULT_TEXTURE_SIZES:
            self.checker_map_size = "2048"
        self.gridify_ratio_influence = max(0.0, min(float(self.gridify_ratio_influence), 1.0))
        self.gridify_shape_blend = max(0.0, min(float(self.gridify_shape_blend), 1.0))
        set_option("alignMode", self.align_mode)
        set_option("udim", self.udim)
        set_option("symmetryUvAxis", self.symmetry_uv_axis)
        set_option("symmetry3dAxis", self.symmetry_3d_axis)
        set_option("defaultSymmetryPriority", self.default_symmetry_priority)
        set_option("checkerMapSize", self.checker_map_size)
        set_option("textureSizeX", self.texture_size_x)
        set_option("textureSizeY", self.texture_size_y)
        set_option("textureSizeLink", self.texture_size_link)
        set_option("texelDensity", self.texel_density)
        set_option("texelPresetButtons", self.texel_preset_buttons)
        set_option("gridifyRatioInfluence", self.gridify_ratio_influence)
        set_option("gridifyShapeBlend", self.gridify_shape_blend)
        set_option("gridifyNormalize", self.gridify_normalize)
        set_option("gridifyKeepAspect", self.gridify_keep_aspect)
