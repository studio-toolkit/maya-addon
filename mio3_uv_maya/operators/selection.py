"""Selection and symmetry operators."""

from __future__ import annotations

from .base import Action, warn
from ..core.components import select_uvs
from ..core.mesh import MayaUVIslandManager
from ..core.mathutils import polygon_area


def _manager() -> MayaUVIslandManager | None:
    manager = MayaUVIslandManager.from_selection()
    if not manager.objects:
        warn("Select a mesh or UV components first.")
        return None
    return manager


def select_boundary():
    manager = _manager()
    if manager is None:
        return False
    selected = {}
    for island in manager.islands:
        boundary = set()
        for edge_records in island.obj.edge_to_faces.values():
            uv_pairs = []
            for face_id, a, b in edge_records:
                face = island.obj.faces[face_id]
                if face.uv_ids[a] in island.uv_ids and face.uv_ids[b] in island.uv_ids:
                    uv_pairs.append((face.uv_ids[a], face.uv_ids[b]))
            if len(uv_pairs) == 1:
                boundary.update(uv_pairs[0])
        selected.setdefault(island.obj.shape, set()).update(boundary)
    for shape, uv_ids in selected.items():
        select_uvs(shape, uv_ids)
    return True


def select_flipped():
    manager = _manager()
    if manager is None:
        return False
    selected = {}
    for obj in manager.objects:
        flipped = set()
        for face in obj.faces:
            points = [obj.uv_positions[uv_id] for uv_id in face.uv_ids if uv_id in obj.uv_positions]
            if polygon_area(points) < 0:
                flipped.update(face.uv_ids)
        selected[obj.shape] = flipped
    for shape, uv_ids in selected.items():
        select_uvs(shape, uv_ids)
    return True


def select_zero_area(threshold: float = 1e-8):
    manager = _manager()
    if manager is None:
        return False
    selected = {}
    for obj in manager.objects:
        zero = set()
        for face in obj.faces:
            points = [obj.uv_positions[uv_id] for uv_id in face.uv_ids if uv_id in obj.uv_positions]
            if abs(polygon_area(points)) <= threshold:
                zero.update(face.uv_ids)
        selected[obj.shape] = zero
    for shape, uv_ids in selected.items():
        select_uvs(shape, uv_ids)
    return True


def select_half(axis: str = "X", positive: bool = True):
    manager = _manager()
    if manager is None:
        return False
    selected = {}
    for obj in manager.objects:
        uv_ids = set()
        for uv_id, uv in obj.uv_positions.items():
            faces = obj.uv_to_faces.get(uv_id, set())
            vertices = []
            for face_id in faces:
                face = obj.faces[face_id]
                for vertex_id, face_uv_id in zip(face.vertex_ids, face.uv_ids):
                    if face_uv_id == uv_id:
                        vertices.append(obj.vertex_positions[vertex_id])
            if not vertices:
                continue
            value = sum(v.axis_value(axis) for v in vertices) / len(vertices)
            if (positive and value >= 0.0) or (not positive and value <= 0.0):
                uv_ids.add(uv_id)
        selected[obj.shape] = uv_ids
    for shape, uv_ids in selected.items():
        select_uvs(shape, uv_ids)
    return True


def not_ready(name: str):
    warn("{} is scaffolded for the parity phase and is not implemented yet.".format(name))
    return False


ACTIONS = [
    Action("select_half_negative_x", "-X", "Select UVs on negative X side in 3D.", lambda: select_half("X", False), "x_n"),
    Action("select_half_positive_x", "+X", "Select UVs on positive X side in 3D.", lambda: select_half("X", True), "x_p"),
    Action("select_boundary", "Boundary", "Select UV shell boundary.", select_boundary, "boundary"),
    Action("select_flipped", "Flipped", "Select flipped UV faces.", select_flipped, "similar"),
    Action("select_zero_area", "No Region", "Select zero-area UV faces.", select_zero_area, "highlight"),
    Action("select_similar", "Similar", "Parity placeholder.", lambda: not_ready("Similar"), "similar"),
    Action("select_mirror", "Mirror", "Parity placeholder.", lambda: not_ready("Mirror Selection"), "mirror_uv"),
    Action("symmetrize", "Symmetrize", "Parity placeholder.", lambda: not_ready("Symmetrize"), "symmetrize"),
    Action("symmetry_snap", "Snap", "Parity placeholder.", lambda: not_ready("Snap to Symmetry"), "snap"),
]

