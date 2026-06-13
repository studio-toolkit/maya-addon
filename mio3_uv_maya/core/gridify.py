# SPDX-FileCopyrightText: 2009-2023 Blender Authors
#
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Modifications:
# - Adapted from Blender's UV follow active quads logic for Mio3 UV Maya.
# - Rewritten against MayaUVObject, FaceRecord, and UV-id based assignments.

"""Gridify helpers for quad UV islands."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
import math

from .mathutils import Vec2


RECT_THRESHOLD = 1e-4
EPSILON = 1e-10


@dataclass(frozen=True)
class LoopRef:
    face_id: int
    local_index: int
    vertex_id: int
    uv_id: int


@dataclass
class GridifyResult:
    quad_islands: int = 0
    changed_islands: int = 0
    already_rectangular: int = 0
    skipped_islands: int = 0


def _edge_key(face, local_index: int) -> tuple[int, int]:
    return tuple(sorted((face.vertex_ids[local_index], face.vertex_ids[(local_index + 1) % len(face.vertex_ids)])))


def _edge_length(obj, edge_key: tuple[int, int]) -> float:
    a = obj.vertex_positions.get(edge_key[0])
    b = obj.vertex_positions.get(edge_key[1])
    if a is None or b is None:
        return 0.0
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def _quad_faces_for_island(island) -> list[object]:
    face_ids = sorted({face_id for uv_id in island.uv_ids for face_id in island.obj.uv_to_faces.get(uv_id, set())})
    faces = []
    for face_id in face_ids:
        if face_id < 0 or face_id >= len(island.obj.faces):
            continue
        face = island.obj.faces[face_id]
        if len(face.vertex_ids) != 4 or len(face.uv_ids) != 4:
            continue
        if all(uv_id in island.uv_ids for uv_id in face.uv_ids):
            faces.append(face)
    return faces


def _angle_diff_for_face(obj, face, positions: dict[int, Vec2]) -> float:
    max_angle_diff = 0.0
    for index, uv_id in enumerate(face.uv_ids):
        uv = positions[uv_id]
        prev_uv = positions[face.uv_ids[index - 1]]
        next_uv = positions[face.uv_ids[(index + 1) % 4]]
        v1 = uv - prev_uv
        v2 = next_uv - uv
        angle = math.atan2(v1.x * v2.y - v1.y * v2.x, v1.x * v2.x + v1.y * v2.y)
        max_angle_diff = max(max_angle_diff, abs(angle - math.pi / 2.0))
    return max_angle_diff


def get_base_face(obj, faces: list[object], positions: dict[int, Vec2] | None = None):
    positions = positions or obj.uv_positions
    best_face = None
    best_score = float("inf")
    all_rect = True

    for face in faces:
        angle_diff = _angle_diff_for_face(obj, face, positions)
        if angle_diff >= RECT_THRESHOLD:
            all_rect = False
        if angle_diff < best_score:
            best_score = angle_diff
            best_face = face

    if all_rect:
        return None
    return best_face


def _compute_aspect(obj, active_face, selected_faces: list[object]) -> float:
    selected_by_id = {face.face_id: face for face in selected_faces}
    edge_dir = {}
    for index in range(4):
        edge_dir[_edge_key(active_face, index)] = index % 2

    visited = {active_face.face_id}
    queue = deque([active_face])
    while queue:
        face = queue.popleft()
        for local_index in range(4):
            edge = _edge_key(face, local_index)
            edge_records = obj.edge_to_faces.get(edge, [])
            if len(edge_records) != 2 or edge not in edge_dir:
                continue
            other_record = next((record for record in edge_records if record[0] != face.face_id), None)
            if other_record is None:
                continue
            other_face = selected_by_id.get(other_record[0])
            if other_face is None or other_face.face_id in visited:
                continue

            visited.add(other_face.face_id)
            queue.append(other_face)
            shared_dir = edge_dir[edge]
            shared_verts = set(edge)
            for other_index in range(4):
                other_edge = _edge_key(other_face, other_index)
                if other_edge in edge_dir:
                    continue
                if shared_verts.intersection(other_edge):
                    edge_dir[other_edge] = 1 - shared_dir
                else:
                    edge_dir[other_edge] = shared_dir

    dir0 = [_edge_length(obj, edge) for edge, direction in edge_dir.items() if direction == 0]
    dir1 = [_edge_length(obj, edge) for edge, direction in edge_dir.items() if direction == 1]
    avg0 = sum(dir0) / len(dir0) if dir0 else 1.0
    avg1 = sum(dir1) / len(dir1) if dir1 else 1.0
    return avg0 / avg1 if avg1 > EPSILON else 1.0


def align_rect(obj, active_face, selected_faces: list[object], positions: dict[int, Vec2], ratio_influence: float) -> None:
    uv_coords = [positions[uv_id] for uv_id in active_face.uv_ids]
    min_x = min(uv.x for uv in uv_coords)
    min_y = min(uv.y for uv in uv_coords)
    max_x = max(uv.x for uv in uv_coords)
    max_y = max(uv.y for uv in uv_coords)
    center_uv = Vec2((min_x + max_x) * 0.5, (min_y + max_y) * 0.5)

    edge_uv = uv_coords[1] - uv_coords[0]
    current_angle = math.atan2(edge_uv.y, edge_uv.x)
    target_angle = round(current_angle / (math.pi / 2.0)) * (math.pi / 2.0)
    angle_diff = target_angle - current_angle
    rotated_uvs = [uv.rotated(angle_diff, center_uv) for uv in uv_coords]

    sorted_by_y = sorted(zip(rotated_uvs, range(4)), key=lambda pair: (pair[0].y, pair[0].x))
    bottom_pairs = sorted(sorted_by_y[:2], key=lambda pair: pair[0].x)
    top_pairs = sorted(sorted_by_y[2:], key=lambda pair: pair[0].x)
    corner_pairs = [bottom_pairs[0], bottom_pairs[1], top_pairs[1], top_pairs[0]]
    ordered_uvs = [uv for uv, _index in corner_pairs]

    w = max(((ordered_uvs[1] - ordered_uvs[0]).length + (ordered_uvs[2] - ordered_uvs[3]).length) * 0.5, 1e-8)
    h = max(((ordered_uvs[2] - ordered_uvs[1]).length + (ordered_uvs[3] - ordered_uvs[0]).length) * 0.5, 1e-8)

    if ratio_influence > 0.0:
        geo_aspect = _compute_aspect(obj, active_face, selected_faces)
        dir0_vec = rotated_uvs[1] - rotated_uvs[0]
        if abs(dir0_vec.x) < abs(dir0_vec.y):
            geo_aspect = 1.0 / geo_aspect if geo_aspect > EPSILON else 1.0
        uv_aspect = w / h
        target_aspect = math.exp(
            math.log(max(uv_aspect, EPSILON)) * (1.0 - ratio_influence)
            + math.log(max(geo_aspect, EPSILON)) * ratio_influence
        )
        scale = math.sqrt(target_aspect / uv_aspect)
        w *= scale
        h /= scale

    half_w = w * 0.5
    half_h = h * 0.5
    new_uvs = [
        Vec2(center_uv.x - half_w, center_uv.y - half_h),
        Vec2(center_uv.x + half_w, center_uv.y - half_h),
        Vec2(center_uv.x + half_w, center_uv.y + half_h),
        Vec2(center_uv.x - half_w, center_uv.y + half_h),
    ]

    for (_uv, local_index), new_uv in zip(corner_pairs, new_uvs):
        positions[active_face.uv_ids[local_index]] = new_uv


def _edge_loop_average_lengths(obj, faces: list[object]) -> dict[tuple[int, int], float]:
    adjacency = defaultdict(set)
    edges = set()
    for face in faces:
        face_edges = [_edge_key(face, index) for index in range(4)]
        edges.update(face_edges)
        for index, edge in enumerate(face_edges):
            opposite = face_edges[(index + 2) % 4]
            adjacency[edge].add(opposite)
            adjacency[opposite].add(edge)

    result = {}
    visited = set()
    for edge in edges:
        if edge in visited:
            continue
        component = set()
        queue = deque([edge])
        visited.add(edge)
        while queue:
            current = queue.popleft()
            component.add(current)
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        lengths = [_edge_length(obj, item) for item in component]
        avg = sum(lengths) / len(lengths) if lengths else 1.0
        for item in component:
            result[item] = avg
    return result


def _other_quad_face(obj, face, local_index: int, selected_by_id: dict[int, object]):
    edge = _edge_key(face, local_index)
    records = obj.edge_to_faces.get(edge, [])
    if len(records) != 2:
        return None
    for face_id, other_local_index, _next_index in records:
        if face_id != face.face_id and face_id in selected_by_id:
            return selected_by_id[face_id], other_local_index
    return None


def _uv(face, local_index: int, positions: dict[int, Vec2]) -> Vec2:
    return positions[face.uv_ids[local_index % 4]]


def _set_uv(face, local_index: int, positions: dict[int, Vec2], uv: Vec2) -> None:
    positions[face.uv_ids[local_index % 4]] = uv


def _blend_length_average_factor(ratio: float, blend: float) -> float:
    return ratio + ((1.0 - ratio) * blend)


def _apply_uv_from_edge(obj, prev_face, prev_index: int, next_face, next_index: int, positions: dict[int, Vec2], edge_lengths, shape_blend: float) -> None:
    a = [prev_index % 4, (prev_index + 1) % 4, (prev_index + 2) % 4, (prev_index + 3) % 4]

    if next_face.vertex_ids[next_index] != prev_face.vertex_ids[prev_index]:
        b = [(next_index + 1) % 4, next_index % 4, (next_index + 3) % 4, (next_index + 2) % 4]
    else:
        b = [next_index % 4, (next_index + 1) % 4, (next_index + 2) % 4, (next_index + 3) % 4]

    fac = 1.0
    if shape_blend < 1.0:
        d1 = edge_lengths.get(_edge_key(prev_face, a[1]), _edge_length(obj, _edge_key(prev_face, a[1])))
        d2 = edge_lengths.get(_edge_key(next_face, b[2]), _edge_length(obj, _edge_key(next_face, b[2])))
        fac = _blend_length_average_factor(d2 / d1, shape_blend) if d1 > EPSILON else 1.0

    a0 = _uv(prev_face, a[0], positions)
    a1 = _uv(prev_face, a[1], positions)
    a2 = _uv(prev_face, a[2], positions)
    a3 = _uv(prev_face, a[3], positions)

    _set_uv(next_face, b[0], positions, a0)
    _set_uv(next_face, b[3], positions, a0 + (a0 - a3) * fac)
    _set_uv(next_face, b[1], positions, a1)
    _set_uv(next_face, b[2], positions, a1 + (a1 - a2) * fac)


def _uv_follow(obj, faces: list[object], active_face, positions: dict[int, Vec2], shape_blend: float) -> None:
    selected_by_id = {face.face_id: face for face in faces}
    edge_lengths = _edge_loop_average_lengths(obj, faces) if shape_blend < 1.0 else {}
    visited = {active_face.face_id}
    queue = deque([active_face])

    while queue:
        face = queue.popleft()
        for local_index in range(4):
            other = _other_quad_face(obj, face, local_index, selected_by_id)
            if other is None:
                continue
            other_face, other_local_index = other
            if other_face.face_id in visited:
                continue
            _apply_uv_from_edge(obj, face, local_index, other_face, other_local_index, positions, edge_lengths, shape_blend)
            visited.add(other_face.face_id)
            queue.append(other_face)


def _uv_key(uv: Vec2) -> tuple[float, float]:
    return round(uv.x, 6), round(uv.y, 6)


def _shared_uv_loops(obj, selected_face_ids: set[int], source_faces: list[object], original_positions: dict[int, Vec2]):
    loop_index = defaultdict(list)
    for face in obj.faces:
        for local_index, (vertex_id, uv_id) in enumerate(zip(face.vertex_ids, face.uv_ids)):
            loop_index[(vertex_id, _uv_key(original_positions[uv_id]))].append(
                LoopRef(face.face_id, local_index, vertex_id, uv_id)
            )

    shared = {}
    for face in source_faces:
        for local_index, (vertex_id, uv_id) in enumerate(zip(face.vertex_ids, face.uv_ids)):
            key = (vertex_id, _uv_key(original_positions[uv_id]))
            if key in shared:
                continue
            loops = loop_index.get(key, [])
            if not any(loop.face_id not in selected_face_ids for loop in loops):
                continue
            shared[key] = (uv_id, loops)
    return shared


def _sync_shared_uv_loops(shared_uvs, positions: dict[int, Vec2]) -> None:
    for source_uv_id, loops in shared_uvs.values():
        source_uv = positions[source_uv_id]
        for loop in loops:
            positions[loop.uv_id] = source_uv


def gridify_island(island, ratio_influence: float = 0.5, shape_blend: float = 0.0) -> str:
    faces = _quad_faces_for_island(island)
    if not faces:
        return "skipped"

    original_positions = dict(island.obj.uv_positions)
    active_face = get_base_face(island.obj, faces, original_positions)
    if active_face is None:
        return "already_rectangular"

    ratio_influence = max(0.0, min(float(ratio_influence), 1.0))
    shape_blend = max(0.0, min(float(shape_blend), 1.0))
    positions = dict(original_positions)
    selected_face_ids = {face.face_id for face in faces}
    shared_uvs = _shared_uv_loops(island.obj, selected_face_ids, faces, original_positions)

    align_rect(island.obj, active_face, faces, positions, ratio_influence)
    _uv_follow(island.obj, faces, active_face, positions, shape_blend)
    _sync_shared_uv_loops(shared_uvs, positions)

    updates = {
        uv_id: uv
        for uv_id, uv in positions.items()
        if uv_id in original_positions and uv != original_positions[uv_id]
    }
    if not updates:
        return "unchanged"
    island.obj.set_uv_positions(updates)
    return "changed"


def gridify_islands(islands, ratio_influence: float = 0.5, shape_blend: float = 0.0) -> GridifyResult:
    result = GridifyResult()
    for island in islands:
        status = gridify_island(island, ratio_influence, shape_blend)
        if status == "changed":
            result.quad_islands += 1
            result.changed_islands += 1
        elif status == "already_rectangular":
            result.quad_islands += 1
            result.already_rectangular += 1
        elif status == "unchanged":
            result.quad_islands += 1
        else:
            result.skipped_islands += 1
    return result
