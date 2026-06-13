"""Texel density operators."""

from __future__ import annotations

import math

from .base import Action, warn
from ..core.mesh import MayaUVIslandManager
from ..core.mathutils import polygon_area
from ..core.settings import Settings


def _float_setting(value, fallback: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = fallback
    return max(1.0, result)


def _texture_sizes(settings: Settings) -> tuple[float, float]:
    return _float_setting(settings.texture_size_x, 2048.0), _float_setting(settings.texture_size_y, 2048.0)


def _face_uv_area(obj, face) -> float:
    points = [obj.uv_positions[uv_id] for uv_id in face.uv_ids if uv_id in obj.uv_positions]
    return abs(polygon_area(points))


def _face_world_area(obj, face) -> float:
    if len(face.vertex_ids) < 3:
        return 0.0
    verts = [obj.vertex_positions[v] for v in face.vertex_ids if v in obj.vertex_positions]
    if len(verts) < 3:
        return 0.0
    base = verts[0]
    total = 0.0
    for i in range(1, len(verts) - 1):
        a = verts[i] - base
        b = verts[i + 1] - base
        cross_len = math.sqrt(
            (a.y * b.z - a.z * b.y) ** 2
            + (a.z * b.x - a.x * b.z) ** 2
            + (a.x * b.y - a.y * b.x) ** 2
        )
        total += cross_len * 0.5
    return total


def _density_from_areas(mesh_area: float, uv_area: float, texture_size_x: float, texture_size_y: float) -> float:
    if mesh_area <= 0 or uv_area <= 0 or texture_size_x <= 0 or texture_size_y <= 0:
        return 0.0
    return math.sqrt((uv_area * texture_size_x * texture_size_y) / mesh_area)


def _island_face_ids(island) -> set[int]:
    return {face_id for uv_id in island.uv_ids for face_id in island.obj.uv_to_faces.get(uv_id, set())}


def _island_areas(island) -> tuple[float, float]:
    mesh_area = 0.0
    uv_area = 0.0
    for face_id in _island_face_ids(island):
        face = island.obj.faces[face_id]
        mesh_area += _face_world_area(island.obj, face)
        uv_area += _face_uv_area(island.obj, face)
    return mesh_area, uv_area


def _queue_update(update_bucket: dict[str, tuple[object, dict[int, object]]], obj, uv_id: int, uv) -> None:
    _obj, updates = update_bucket.setdefault(obj.shape, (obj, {}))
    updates[int(uv_id)] = uv


def _scale_islands_to_density(islands, target_density: float, texture_size_x: float, texture_size_y: float) -> int:
    update_bucket = {}
    changed = 0
    for island in islands:
        mesh_area, uv_area = _island_areas(island)
        current_density = _density_from_areas(mesh_area, uv_area, texture_size_x, texture_size_y)
        if current_density <= 0:
            continue
        scale_factor = target_density / current_density
        if scale_factor <= 0:
            continue
        center = island.center
        queued = False
        for uv_id in island.uv_ids:
            if uv_id not in island.obj.uv_positions:
                continue
            uv = island.obj.uv_positions[uv_id]
            _queue_update(update_bucket, island.obj, uv_id, center + (uv - center) * scale_factor)
            queued = True
        if queued:
            changed += 1
    for obj, updates in update_bucket.values():
        obj.set_uv_positions(updates)
    return changed


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
    settings = Settings.load()
    texture_size_x, texture_size_y = _texture_sizes(settings)
    mesh_area = 0.0
    weighted_density = 0.0
    for island in manager.islands:
        island_mesh_area, island_uv_area = _island_areas(island)
        density = _density_from_areas(island_mesh_area, island_uv_area, texture_size_x, texture_size_y)
        if density <= 0:
            continue
        mesh_area += island_mesh_area
        weighted_density += density * island_mesh_area
    if mesh_area <= 0:
        warn("Unable to calculate texel density from the current selection.")
        return False
    td = weighted_density / mesh_area
    settings.texel_density = td
    settings.save()
    warn("Texel density estimate: {:.4f}".format(td))
    return td


def texel_density_set():
    manager = MayaUVIslandManager.from_selection()
    if not manager.islands:
        warn("Select UV shells first.")
        return False

    settings = Settings.load()
    target_density = float(settings.texel_density)
    if target_density <= 0:
        warn("Texel density must be greater than zero.")
        return False

    texture_size_x, texture_size_y = _texture_sizes(settings)
    changed = _scale_islands_to_density(manager.islands, target_density, texture_size_x, texture_size_y)
    if changed <= 0:
        warn("Unable to set texel density from the current selection.")
        return False
    warn("Texel density set to {:.4f} on {} shell(s).".format(target_density, changed))
    return True


ACTIONS = [
    Action("texel_density_get", "TD Get", "Estimate texel density.", texel_density_get, "td_get"),
    Action("texel_density_set", "TD Set", "Scale selected UV shells to the stored texel density.", texel_density_set, "td_set"),
    Action("texel_coverage", "Coverage", "Estimate selected UV coverage.", coverage, "options"),
]
