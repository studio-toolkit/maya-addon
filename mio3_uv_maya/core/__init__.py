"""Core Maya UV data layer."""

from .mathutils import Vec2, Vec3, Bounds2D
from .mesh import MayaUVObject, MayaUVIsland, MayaUVIslandManager
from .rectify import RectifyOptions, RectifyResult
from .uv_nodes import MayaUVNode, MayaUVNodeGroup, MayaUVNodeManager

__all__ = [
    "Bounds2D",
    "MayaUVIsland",
    "MayaUVIslandManager",
    "MayaUVNode",
    "MayaUVNodeGroup",
    "MayaUVNodeManager",
    "MayaUVObject",
    "RectifyOptions",
    "RectifyResult",
    "Vec2",
    "Vec3",
]
