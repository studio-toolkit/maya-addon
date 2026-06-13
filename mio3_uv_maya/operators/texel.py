"""Texel density operators."""

from __future__ import annotations

import math

from .base import Action, warn
from ..core.mesh import MayaUVIslandManager
from ..core.mathutils import polygon_area
from ..core.settings import Settings


def coverage():
    manager = MayaUVIslandManager.from_selection()
    if not manager.islands:
        warn("Select UV shells first.")
        return False
    total = 0.0
    for island in manager.islands:
        for face_id in {face for uv_id in island.uv_ids for face in island.obj.uv_to_faces.get(uv_id, set())}:
            face = island.obj.faces[face_id]
            points = [island.obj.uv_positions[uv_id] for uv_id in face.uv_ids]
            total += abs(polygon_area(points))
    settings = Settings.load()
    settings.texel_density = max(0.0, min(total * 100.0, 10000.0))
    settings.save()
    warn("UV coverage estimate: {:.4f}%".format(total * 100.0))
    return total


def texel_density_get():
    manager = MayaUVIslandManager.from_selection()
    if not manager.islands:
        warn("Select UV shells first.")
        return False
    mesh_area = 0.0
    uv_area = 0.0
    for island in manager.islands:
        for face_id in {face for uv_id in island.uv_ids for face in island.obj.uv_to_faces.get(uv_id, set())}:
            face = island.obj.faces[face_id]
            uv_points = [island.obj.uv_positions[uv_id] for uv_id in face.uv_ids]
            uv_area += abs(polygon_area(uv_points))
            if len(face.vertex_ids) >= 3:
                verts = [island.obj.vertex_positions[v] for v in face.vertex_ids]
                base = verts[0]
                for i in range(1, len(verts) - 1):
                    a = verts[i] - base
                    b = verts[i + 1] - base
                    cross_len = math.sqrt(
                        (a.y * b.z - a.z * b.y) ** 2
                        + (a.z * b.x - a.x * b.z) ** 2
                        + (a.x * b.y - a.y * b.x) ** 2
                    )
                    mesh_area += cross_len * 0.5
    if mesh_area <= 0 or uv_area <= 0:
        warn("Unable to calculate texel density from the current selection.")
        return False
    settings = Settings.load()
    texture_size = float(settings.texture_size_x)
    td = math.sqrt(uv_area / mesh_area) * texture_size
    settings.texel_density = td
    settings.save()
    warn("Texel density estimate: {:.4f}".format(td))
    return td


def texel_density_set():
    warn("Texel Density Set is scaffolded for the parity phase and is not implemented yet.")
    return False


ACTIONS = [
    Action("texel_density_get", "TD Get", "Estimate texel density.", texel_density_get, "td_get"),
    Action("texel_density_set", "TD Set", "Parity placeholder.", texel_density_set, "td_set"),
    Action("texel_coverage", "Coverage", "Estimate selected UV coverage.", coverage, "options"),
]

