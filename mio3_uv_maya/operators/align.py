"""Layout and align operators."""

from __future__ import annotations

import math

from .base import Action, warn
from ..core.mathutils import Bounds2D, Vec2
from ..core.mesh import MayaUVIslandManager
from ..core.uv_nodes import MayaUVNodeManager


def _manager() -> MayaUVIslandManager | None:
    manager = MayaUVIslandManager.from_selection()
    if not manager.islands:
        warn("Select a mesh or UV components first.")
        return None
    return manager


def _selection_manager() -> MayaUVIslandManager | None:
    manager = MayaUVIslandManager.from_selection(include_all_if_no_components=False)
    if not manager.islands:
        warn("Select a mesh or UV components first.")
        return None
    return manager


def _has_component_uvs(manager: MayaUVIslandManager) -> bool:
    return any(bool(uv_ids) for uv_ids in manager.selected_uvs_by_shape.values())


def _has_node_component_selection(manager: MayaUVIslandManager) -> bool:
    node_kinds = {"uv", "edge", "vertex"}
    return any(bool(kinds.intersection(node_kinds)) for kinds in manager.selection_kinds_by_shape.values())


def _has_edge_align_selection(manager: MayaUVIslandManager) -> bool:
    edge_align_kinds = {"uv", "edge", "vertex"}
    return any(bool(kinds.intersection(edge_align_kinds)) for kinds in manager.selection_kinds_by_shape.values())


def _selected_bounds(manager: MayaUVIslandManager) -> Bounds2D:
    bounds = Bounds2D()
    for obj in manager.objects:
        for uv_id in manager.selected_uvs_by_shape.get(obj.shape, set()):
            if uv_id in obj.uv_positions:
                bounds.include(obj.uv_positions[uv_id])
    return bounds


def _align_selected_components(manager: MayaUVIslandManager, kind: str) -> bool:
    target = _selected_bounds(manager)
    if not target.is_valid:
        return False

    for obj in manager.objects:
        updates = {}
        for uv_id in manager.selected_uvs_by_shape.get(obj.shape, set()):
            if uv_id not in obj.uv_positions:
                continue
            uv = obj.uv_positions[uv_id]
            x = uv.x
            y = uv.y
            if "MIN_X" in kind:
                x = target.min_x
            elif "MAX_X" in kind:
                x = target.max_x
            elif kind in ("CENTER", "ALIGN_X"):
                x = target.center.x

            if "MIN_Y" in kind:
                y = target.min_y
            elif "MAX_Y" in kind:
                y = target.max_y
            elif kind in ("CENTER", "ALIGN_Y"):
                y = target.center.y

            updates[uv_id] = Vec2(x, y)
        obj.set_uv_positions(updates)
    return True


def _align_shells(manager: MayaUVIslandManager, kind: str) -> bool:
    target = manager.bounds()
    if not target.is_valid:
        return False
    for island in manager.islands:
        bounds = island.bounds
        if not bounds.is_valid:
            continue
        dx = dy = 0.0
        if "MIN_X" in kind:
            dx = target.min_x - bounds.min_x
        elif "MAX_X" in kind:
            dx = target.max_x - bounds.max_x
        elif kind in ("CENTER", "ALIGN_X"):
            dx = target.center.x - bounds.center.x
        if "MIN_Y" in kind:
            dy = target.min_y - bounds.min_y
        elif "MAX_Y" in kind:
            dy = target.max_y - bounds.max_y
        elif kind in ("CENTER", "ALIGN_Y"):
            dy = target.center.y - bounds.center.y
        island.move(Vec2(dx, dy))
    return True


def normalize(keep_aspect: bool = False, individual: bool = False):
    manager = _manager()
    if manager is None:
        return False
    islands = manager.islands if individual else [None]
    if individual:
        for island in islands:
            bounds = island.bounds
            if not bounds.is_valid or bounds.width == 0 or bounds.height == 0:
                continue
            sx = 1.0 / bounds.width
            sy = 1.0 / bounds.height
            if keep_aspect:
                scale = min(sx, sy)
                sx = sy = scale
            island.transform(scale=Vec2(sx, sy), offset=Vec2(-bounds.min_x * sx, -bounds.min_y * sy), origin=Vec2())
    else:
        bounds = manager.bounds()
        if not bounds.is_valid or bounds.width == 0 or bounds.height == 0:
            return False
        sx = 1.0 / bounds.width
        sy = 1.0 / bounds.height
        if keep_aspect:
            scale = min(sx, sy)
            sx = sy = scale
        for island in manager.islands:
            island.transform(scale=Vec2(sx, sy), offset=Vec2(-bounds.min_x * sx, -bounds.min_y * sy), origin=Vec2())
    return True


def align(kind: str):
    selection_manager = MayaUVIslandManager.from_selection(include_all_if_no_components=False)
    if selection_manager.islands and _has_node_component_selection(selection_manager):
        return _align_selected_components(selection_manager, kind)

    manager = _manager()
    if manager is None:
        return False
    return _align_shells(manager, kind)


def align_edges(axis: str = "X"):
    manager = _selection_manager()
    if manager is None:
        return False
    if not _has_component_uvs(manager) or not _has_edge_align_selection(manager):
        warn("Select UVs, UV edges, or UV vertices for Align Edges. Face/object selection is ignored.")
        return False

    return _align_edge_groups(manager, axis)


def _align_edge_groups(manager: MayaUVIslandManager, axis: str = "X") -> bool:
    node_manager = MayaUVNodeManager.from_island_manager(manager)
    if not node_manager.groups:
        warn("No connected UV edge groups found for Align Edges.")
        return False

    for group in node_manager.groups:
        bounds = group.bounds
        if not bounds.is_valid:
            continue
        updates = {}
        for uv_id in group.uv_ids:
            uv = group.obj.uv_positions[uv_id]
            if axis == "Y":
                updates[uv_id] = Vec2(bounds.center.x, uv.y)
            else:
                updates[uv_id] = Vec2(uv.x, bounds.center.y)
        group.obj.set_uv_positions(updates)
    return True


def mirror(axis: str = "X"):
    manager = _manager()
    if manager is None:
        return False
    origin = manager.bounds().center
    for island in manager.islands:
        scale = Vec2(-1.0, 1.0) if axis == "X" else Vec2(1.0, -1.0)
        island.transform(scale=scale, origin=origin)
    return True


def rotate(angle_degrees: float):
    manager = _manager()
    if manager is None:
        return False
    origin = manager.bounds().center
    angle = math.radians(angle_degrees)
    for island in manager.islands:
        island.transform(angle=angle, origin=origin)
    return True


def distribute(axis: str = "X"):
    manager = _manager()
    if manager is None or len(manager.islands) < 3:
        warn("Select at least three UV shells for distribute.")
        return False
    islands = sorted(manager.islands, key=lambda island: island.center.x if axis == "X" else island.center.y)
    first = islands[0].center.x if axis == "X" else islands[0].center.y
    last = islands[-1].center.x if axis == "X" else islands[-1].center.y
    step = (last - first) / float(len(islands) - 1)
    for index, island in enumerate(islands[1:-1], start=1):
        current = island.center.x if axis == "X" else island.center.y
        target = first + step * index
        offset = target - current
        island.move(Vec2(offset, 0.0) if axis == "X" else Vec2(0.0, offset))
    return True


def sort_by_3d(axis: str = "AUTO"):
    manager = _manager()
    if manager is None:
        return False
    islands = manager.islands
    if axis == "AUTO":
        centers = [island.center_3d for island in islands]
        ranges = {
            "X": max(c.x for c in centers) - min(c.x for c in centers),
            "Y": max(c.y for c in centers) - min(c.y for c in centers),
            "Z": max(c.z for c in centers) - min(c.z for c in centers),
        }
        axis = max(ranges, key=ranges.get)
    sorted_islands = sorted(islands, key=lambda island: island.center_3d.axis_value(axis))
    cursor = 0.0
    spacing = 0.02
    for island in sorted_islands:
        bounds = island.bounds
        island.move(Vec2(cursor - bounds.min_x, -bounds.min_y))
        cursor += bounds.width + spacing
    return True


def not_ready(name: str):
    warn("{} is scaffolded for the parity phase and is not implemented yet.".format(name))
    return False


ACTIONS = [
    Action("normalize", "Normalize", "Normalize selected UV shells into 0-1 space.", normalize, "normalize"),
    Action("align_left", "Align Left", "Align shells to the left bound.", lambda: align("MIN_X"), "align_left"),
    Action("align_right", "Align Right", "Align shells to the right bound.", lambda: align("MAX_X"), "align_right"),
    Action("align_top", "Align Top", "Align shells to the top bound.", lambda: align("MAX_Y"), "align_top"),
    Action("align_bottom", "Align Bottom", "Align shells to the bottom bound.", lambda: align("MIN_Y"), "align_bottom"),
    Action("align_center", "Align Center", "Align shells to the shared center.", lambda: align("CENTER"), "align_center"),
    Action("mirror_x", "Mirror X", "Mirror selected UV shells across U.", lambda: mirror("X"), "flip_x"),
    Action("mirror_y", "Mirror Y", "Mirror selected UV shells across V.", lambda: mirror("Y"), "flip_y"),
    Action("rotate_p90", "Rotate 90", "Rotate selected UV shells 90 degrees.", lambda: rotate(90), "p90"),
    Action("rotate_n90", "Rotate -90", "Rotate selected UV shells -90 degrees.", lambda: rotate(-90), "n90"),
    Action("rotate_180", "Rotate 180", "Rotate selected UV shells 180 degrees.", lambda: rotate(180), "p180"),
    Action("distribute_x", "Distribute X", "Distribute shells along U.", lambda: distribute("X"), "dist_x"),
    Action("distribute_y", "Distribute Y", "Distribute shells along V.", lambda: distribute("Y"), "dist_y"),
    Action("sort", "Sort", "Sort shells by 3D position.", sort_by_3d, "align_x"),
    Action("align_edges_x", "Edges X", "Align selected UV edge groups horizontally.", lambda: align_edges("X"), "edges_x"),
    Action("align_edges_y", "Edges Y", "Align selected UV edge groups vertically.", lambda: align_edges("Y"), "edges_y"),
    Action("orient_world", "Orient World", "Parity placeholder.", lambda: not_ready("Orient World"), "z"),
]
