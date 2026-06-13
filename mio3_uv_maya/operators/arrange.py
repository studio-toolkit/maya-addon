"""Arrange operators."""

from __future__ import annotations

import math
import random

from .base import Action, warn
from ..core.mathutils import Vec2
from ..core.mesh import MayaUVIslandManager


def _manager() -> MayaUVIslandManager | None:
    manager = MayaUVIslandManager.from_selection()
    if not manager.islands:
        warn("Select a mesh or UV components first.")
        return None
    return manager


def stack():
    manager = _manager()
    if manager is None or len(manager.islands) < 2:
        warn("Select at least two UV shells to stack.")
        return False
    target = manager.islands[0]
    target_bounds = target.bounds
    for island in manager.islands[1:]:
        bounds = island.bounds
        if bounds.width == 0 or bounds.height == 0:
            continue
        sx = target_bounds.width / bounds.width if bounds.width else 1.0
        sy = target_bounds.height / bounds.height if bounds.height else 1.0
        island.transform(scale=Vec2(sx, sy), origin=bounds.center)
        island.move(target_bounds.center - island.bounds.center)
    return True


def shuffle():
    manager = _manager()
    if manager is None or len(manager.islands) < 2:
        warn("Select at least two UV shells to shuffle.")
        return False
    centers = [island.center for island in manager.islands]
    shuffled = list(centers)
    random.shuffle(shuffled)
    for island, target in zip(manager.islands, shuffled):
        island.move(target - island.center)
    return True


def circle():
    manager = _manager()
    if manager is None:
        return False
    for island in manager.islands:
        uv_ids = sorted(island.uv_ids)
        center = island.center
        points = island.points
        if len(points) < 3:
            continue
        radius = sum((point - center).length for point in points) / float(len(points))
        updates = {}
        for index, uv_id in enumerate(uv_ids):
            angle = math.tau * index / float(len(uv_ids))
            updates[uv_id] = Vec2(center.x + math.cos(angle) * radius, center.y + math.sin(angle) * radius)
        island.obj.set_uv_positions(updates)
    return True


def relax(iterations: int = 10, strength: float = 0.25):
    manager = _manager()
    if manager is None:
        return False
    for island in manager.islands:
        updates = {}
        for uv_id in island.uv_ids:
            linked = set()
            for face_id in island.obj.uv_to_faces.get(uv_id, set()):
                face = island.obj.faces[face_id]
                if uv_id not in face.uv_ids:
                    continue
                idx = face.uv_ids.index(uv_id)
                linked.add(face.uv_ids[idx - 1])
                linked.add(face.uv_ids[(idx + 1) % len(face.uv_ids)])
            linked.discard(uv_id)
            if not linked:
                continue
            current = island.obj.uv_positions[uv_id]
            avg = Vec2(
                sum(island.obj.uv_positions[n].x for n in linked) / len(linked),
                sum(island.obj.uv_positions[n].y for n in linked) / len(linked),
            )
            value = current
            for _ in range(iterations):
                value = value + (avg - value) * strength
            updates[uv_id] = value
        island.obj.set_uv_positions(updates)
    return True


def not_ready(name: str):
    warn("{} is scaffolded for the parity phase and is not implemented yet.".format(name))
    return False


ACTIONS = [
    Action("relax", "Relax", "Relax selected UV shells.", relax, "relax"),
    Action("circle", "Circle", "Shape selected UVs into a circle.", circle, "circle"),
    Action("stack", "Stack", "Stack selected UV shells.", stack, "stack"),
    Action("shuffle", "Shuffle", "Shuffle selected shell positions.", shuffle, "shuffle"),
    Action("merge", "Merge", "Parity placeholder.", lambda: not_ready("Merge"), "merge"),
    Action("offset", "Offset", "Parity placeholder.", lambda: not_ready("Offset"), "offset"),
    Action("align_seam", "Align Seam", "Parity placeholder.", lambda: not_ready("Align Seam"), "align_seam_y"),
    Action("stretch", "Stretch", "Parity placeholder.", lambda: not_ready("Stretch"), "stretch"),
    Action("stitch", "Stitch", "Parity placeholder.", lambda: not_ready("Stitch"), "stitch"),
    Action("unfoldify", "Unfoldify", "Parity placeholder.", lambda: not_ready("Unfoldify"), "map"),
    Action("body_parts", "Body Parts", "Parity placeholder.", lambda: not_ready("Body Parts"), "body"),
]

