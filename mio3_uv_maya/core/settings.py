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
        )

    def save(self) -> None:
        if self.checker_map_size not in DEFAULT_TEXTURE_SIZES:
            self.checker_map_size = "2048"
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

