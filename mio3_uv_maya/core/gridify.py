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
    edge_key: tuple[int, int]


@dataclass
class GridifyResult:
    quad_islands: int = 0
    changed_islands: int = 0
    already_rectangular: int = 0
    skipped_islands: int = 0


class LoopGraph:
    """BMesh-like loop graph built from Maya face-vertex/UV assignments."""

    def __init__(self, obj, original_positions: dict[int, Vec2]):
        self.obj = obj
        self.original_positions = original_positions
        self.face_by_id = {face.face_id: face for face in obj.faces}
        self.loops: dict[tuple[int, int], LoopRef] = {}
        self.edge_loops: dict[tuple[int, int], list[LoopRef]] = defaultdict(list)
        self.uv_loop_index: dict[tuple[int, tuple[float, float]], list[LoopRef]] = defaultdict(list)

        for face in obj.faces:
            if len(face.vertex_ids) != len(face.uv_ids):
                continue
            for local_index, (vertex_id, uv_id) in enumerate(zip(face.vertex_ids, face.uv_ids)):
                loop = LoopRef(
                    face_id=face.face_id,
                    local_index=local_index,
                    vertex_id=vertex_id,
                    uv_id=uv_id,
                    edge_key=_edge_key(face, local_index),
                )
                self.loops[(face.face_id, local_index)] = loop
                self.edge_loops[loop.edge_key].append(loop)
                self.uv_loop_index[(vertex_id, _uv_key(original_positions[uv_id]))].append(loop)

    def face(self, face_id: int):
        return self.face_by_id[face_id]

    def face_loops(self, face) -> list[LoopRef]:
        return [self.loops[(face.face_id, index)] for index in range(len(face.vertex_ids))]

    def next_loop(self, loop: LoopRef, steps: int = 1) -> LoopRef:
        face = self.face(loop.face_id)
        index = (loop.local_index + steps) % len(face.vertex_ids)
        return self.loops[(loop.face_id, index)]

    def radial_next(self, loop: LoopRef) -> LoopRef:
        loops = self.edge_loops.get(loop.edge_key, [])
        if not loops:
            return loop
        index = loops.index(loop)
        return loops[(index + 1) % len(loops)]

    def is_quad_face(self, face_id: int) -> bool:
        face = self.face_by_id.get(face_id)
        return bool(face and len(face.vertex_ids) == 4 and len(face.uv_ids) == 4)

    def edge_is_boundary(self, edge_key: tuple[int, int]) -> bool:
        return len(self.edge_loops.get(edge_key, [])) <= 1

    def edge_is_manifold(self, edge_key: tuple[int, int]) -> bool:
        return len(self.edge_loops.get(edge_key, [])) == 2

    def edge_uv_continuous(self, loop: LoopRef, other_loop: LoopRef) -> bool:
        next_loop = self.next_loop(loop)
        other_next = self.next_loop(other_loop)

        a = self.original_positions[loop.uv_id]
        b = self.original_positions[next_loop.uv_id]
        c = self.original_positions[other_loop.uv_id]
        d = self.original_positions[other_next.uv_id]

        if loop.vertex_id == other_loop.vertex_id:
            return _same_uv(a, c) and _same_uv(b, d)
        return _same_uv(a, d) and _same_uv(b, c)

    def can_walk_between(self, loop: LoopRef, allowed_face_ids: set[int]) -> bool:
        if not self.edge_is_manifold(loop.edge_key):
            return False
        other_loop = self.radial_next(loop)
        return other_loop.face_id in allowed_face_ids and self.edge_uv_continuous(loop, other_loop)


def _uv_key(uv: Vec2) -> tuple[float, float]:
    return round(uv.x, 6), round(uv.y, 6)


def _same_uv(a: Vec2, b: Vec2) -> bool:
    dx = a.x - b.x
    dy = a.y - b.y
    return dx * dx + dy * dy <= 1e-12


def _edge_key(face, local_index: int) -> tuple[int, int]:
    return tuple(sorted((face.vertex_ids[local_index], face.vertex_ids[(local_index + 1) % len(face.vertex_ids)])))


def _edge_length(obj, edge_key: tuple[int, int]) -> float:
    a = obj.vertex_positions.get(edge_key[0])
    b = obj.vertex_positions.get(edge_key[1])
    if a is None or b is None:
        return 0.0
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def _candidate_faces_for_island(island, selected_face_ids: set[int] | None = None) -> list[object]:
    face_ids = {face_id for uv_id in island.uv_ids for face_id in island.obj.uv_to_faces.get(uv_id, set())}
    if selected_face_ids:
        face_ids.intersection_update(selected_face_ids)

    faces = []
    for face_id in sorted(face_ids):
        if face_id < 0 or face_id >= len(island.obj.faces):
            continue
        face = island.obj.faces[face_id]
        if len(face.vertex_ids) != 4 or len(face.uv_ids) != 4:
            continue
        if all(uv_id in island.uv_ids for uv_id in face.uv_ids):
            faces.append(face)
    return faces


def _split_uv_continuous_face_groups(graph: LoopGraph, faces: list[object]) -> list[list[object]]:
    allowed_face_ids = {face.face_id for face in faces}
    face_by_id = {face.face_id: face for face in faces}
    visited = set()
    groups = []

    for seed in faces:
        if seed.face_id in visited:
            continue
        group = []
        queue = deque([seed])
        visited.add(seed.face_id)
        while queue:
            face = queue.popleft()
            group.append(face)
            for loop in graph.face_loops(face):
                if not graph.can_walk_between(loop, allowed_face_ids):
                    continue
                other_face = face_by_id[graph.radial_next(loop).face_id]
                if other_face.face_id in visited:
                    continue
                visited.add(other_face.face_id)
                queue.append(other_face)
        groups.append(group)
    return groups


def _angle_diff_for_face(face, positions: dict[int, Vec2]) -> float:
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


def get_base_face(_obj, faces: list[object], positions: dict[int, Vec2] | None = None):
    if not faces:
        return None
    positions = positions or _obj.uv_positions
    best_face = None
    best_score = float("inf")
    all_rect = True

    for face in faces:
        angle_diff = _angle_diff_for_face(face, positions)
        if angle_diff >= RECT_THRESHOLD:
            all_rect = False
        if angle_diff < best_score:
            best_score = angle_diff
            best_face = face

    if all_rect:
        return None
    return best_face


def _compute_aspect(obj, active_face, selected_faces: list[object], graph: LoopGraph) -> float:
    selected_by_id = {face.face_id: face for face in selected_faces}
    selected_face_ids = set(selected_by_id)
    edge_dir = {loop.edge_key: index % 2 for index, loop in enumerate(graph.face_loops(active_face))}

    visited = {active_face.face_id}
    queue = deque([active_face])
    while queue:
        face = queue.popleft()
        for loop in graph.face_loops(face):
            if loop.edge_key not in edge_dir or not graph.can_walk_between(loop, selected_face_ids):
                continue
            other_face = selected_by_id[graph.radial_next(loop).face_id]
            if other_face.face_id in visited:
                continue
            visited.add(other_face.face_id)
            queue.append(other_face)
            shared_dir = edge_dir[loop.edge_key]
            shared_verts = set(loop.edge_key)
            for other_loop in graph.face_loops(other_face):
                if other_loop.edge_key in edge_dir:
                    continue
                if shared_verts.intersection(other_loop.edge_key):
                    edge_dir[other_loop.edge_key] = 1 - shared_dir
                else:
                    edge_dir[other_loop.edge_key] = shared_dir

    dir0 = [_edge_length(obj, edge) for edge, direction in edge_dir.items() if direction == 0]
    dir1 = [_edge_length(obj, edge) for edge, direction in edge_dir.items() if direction == 1]
    avg0 = sum(dir0) / len(dir0) if dir0 else 1.0
    avg1 = sum(dir1) / len(dir1) if dir1 else 1.0
    return avg0 / avg1 if avg1 > EPSILON else 1.0


def align_rect(obj, active_face, selected_faces: list[object], positions: dict[int, Vec2], ratio_influence: float, graph: LoopGraph | None = None) -> None:
    graph = graph or LoopGraph(obj, positions)
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
        geo_aspect = _compute_aspect(obj, active_face, selected_faces, graph)
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


def _walk_face(graph: LoopGraph, active_face, faces: list[object]):
    selected_by_id = {face.face_id: face for face in faces}
    selected_face_ids = set(selected_by_id)
    tagged = {active_face.face_id}
    faces_a = [active_face]
    faces_b = []

    while faces_a:
        for face in faces_a:
            for loop in graph.face_loops(face):
                if not graph.can_walk_between(loop, selected_face_ids):
                    continue
                other_loop = graph.radial_next(loop)
                other_face = selected_by_id[other_loop.face_id]
                if other_face.face_id in tagged:
                    continue
                yield face, loop, other_face
                tagged.add(other_face.face_id)
                faces_b.append(other_face)
        faces_a, faces_b = faces_b, faces_a
        faces_b.clear()


def _walk_edgeloop_all(graph: LoopGraph, start_edge: tuple[int, int], allowed_face_ids: set[int]):
    loop_stack = []
    edges_visited = {start_edge}

    yield start_edge

    def walk_impl(loop: LoopRef):
        if loop.face_id not in allowed_face_ids or not graph.is_quad_face(loop.face_id):
            return
        other_loop = graph.next_loop(loop, 2)
        other_edge = other_loop.edge_key
        if other_edge in edges_visited:
            return
        edges_visited.add(other_edge)
        yield other_edge
        if not graph.edge_is_boundary(other_edge):
            loop_stack.append(other_loop)

    for loop in graph.edge_loops.get(start_edge, []):
        yield from walk_impl(loop)

    while loop_stack:
        test_loop = loop_stack.pop()
        loop = test_loop
        while True:
            loop = graph.radial_next(loop)
            if loop == test_loop:
                break
            yield from walk_impl(loop)


def _edge_loop_average_lengths(obj, faces: list[object], graph: LoopGraph) -> dict[tuple[int, int], float]:
    allowed_face_ids = {face.face_id for face in faces}
    edge_lengths = {}
    for face in faces:
        loops = graph.face_loops(face)
        for init_loop in loops[:2]:
            init_edge = init_loop.edge_key
            if init_edge in edge_lengths:
                continue
            edges = list(_walk_edgeloop_all(graph, init_edge, allowed_face_ids))
            if not edges:
                continue
            average = sum(_edge_length(obj, edge) for edge in edges) / float(len(edges))
            for edge in edges:
                edge_lengths[edge] = average
    return edge_lengths


def _loop_uv(loop: LoopRef, positions: dict[int, Vec2]) -> Vec2:
    return positions[loop.uv_id]


def _set_loop_uv(loop: LoopRef, positions: dict[int, Vec2], uv: Vec2) -> None:
    positions[loop.uv_id] = uv


def _blend_length_average_factor(ratio: float, blend: float) -> float:
    return ratio + ((1.0 - ratio) * blend)


def _apply_uv_from_loop(graph: LoopGraph, prev_loop: LoopRef, positions: dict[int, Vec2], edge_lengths, shape_blend: float) -> None:
    l_a = [
        prev_loop,
        graph.next_loop(prev_loop, 1),
        graph.next_loop(prev_loop, 2),
        graph.next_loop(prev_loop, 3),
    ]

    next_loop = graph.radial_next(prev_loop)
    if next_loop.vertex_id != prev_loop.vertex_id:
        b1 = next_loop
        b0 = graph.next_loop(b1, 1)
        b3 = graph.next_loop(b0, 1)
        b2 = graph.next_loop(b3, 1)
        l_b = [b0, b1, b2, b3]
    else:
        l_b = [
            next_loop,
            graph.next_loop(next_loop, 1),
            graph.next_loop(next_loop, 2),
            graph.next_loop(next_loop, 3),
        ]

    if shape_blend < 1.0:
        d1 = edge_lengths.get(l_a[1].edge_key, _edge_length(graph.obj, l_a[1].edge_key))
        d2 = edge_lengths.get(l_b[2].edge_key, _edge_length(graph.obj, l_b[2].edge_key))
        fac = _blend_length_average_factor(d2 / d1, shape_blend) if d1 > EPSILON else 1.0
    else:
        fac = 1.0

    a0 = _loop_uv(l_a[0], positions)
    a1 = _loop_uv(l_a[1], positions)
    a2 = _loop_uv(l_a[2], positions)
    a3 = _loop_uv(l_a[3], positions)

    _set_loop_uv(l_b[0], positions, a0)
    _set_loop_uv(l_b[3], positions, a0 + (a0 - a3) * fac)
    _set_loop_uv(l_b[1], positions, a1)
    _set_loop_uv(l_b[2], positions, a1 + (a1 - a2) * fac)


def _uv_follow(graph: LoopGraph, faces: list[object], active_face, positions: dict[int, Vec2], shape_blend: float) -> None:
    edge_lengths = _edge_loop_average_lengths(graph.obj, faces, graph) if shape_blend < 1.0 else {}
    for _prev_face, prev_loop, _next_face in _walk_face(graph, active_face, faces):
        _apply_uv_from_loop(graph, prev_loop, positions, edge_lengths, shape_blend)


def _shared_uv_loops(graph: LoopGraph, selected_face_ids: set[int], source_faces: list[object]):
    shared = {}
    for face in source_faces:
        for loop in graph.face_loops(face):
            key = (loop.vertex_id, _uv_key(graph.original_positions[loop.uv_id]))
            if key in shared:
                continue
            loops = graph.uv_loop_index.get(key, [])
            if not any(other_loop.face_id not in selected_face_ids for other_loop in loops):
                continue
            shared[key] = (loop.uv_id, loops)
    return shared


def _sync_shared_uv_loops(shared_uvs, positions: dict[int, Vec2]) -> None:
    for source_uv_id, loops in shared_uvs.values():
        source_uv = positions[source_uv_id]
        for loop in loops:
            positions[loop.uv_id] = source_uv


def _gridify_face_group(graph: LoopGraph, faces: list[object], positions: dict[int, Vec2], ratio_influence: float, shape_blend: float) -> str:
    active_face = get_base_face(graph.obj, faces, positions)
    if active_face is None:
        return "already_rectangular"

    selected_face_ids = {face.face_id for face in faces}
    shared_uvs = _shared_uv_loops(graph, selected_face_ids, faces)
    align_rect(graph.obj, active_face, faces, positions, ratio_influence, graph)
    _uv_follow(graph, faces, active_face, positions, shape_blend)
    _sync_shared_uv_loops(shared_uvs, positions)
    return "changed"


def gridify_island(island, ratio_influence: float = 0.5, shape_blend: float = 0.0, selected_face_ids: set[int] | None = None) -> str:
    original_positions = dict(island.obj.uv_positions)
    graph = LoopGraph(island.obj, original_positions)
    faces = _candidate_faces_for_island(island, selected_face_ids)
    if not faces:
        return "skipped"

    ratio_influence = max(0.0, min(float(ratio_influence), 1.0))
    shape_blend = max(0.0, min(float(shape_blend), 1.0))
    positions = dict(original_positions)
    groups = _split_uv_continuous_face_groups(graph, faces)
    changed_groups = 0
    rectangular_groups = 0

    for group in groups:
        status = _gridify_face_group(graph, group, positions, ratio_influence, shape_blend)
        if status == "changed":
            changed_groups += 1
        elif status == "already_rectangular":
            rectangular_groups += 1

    updates = {
        uv_id: uv
        for uv_id, uv in positions.items()
        if uv_id in original_positions and uv != original_positions[uv_id]
    }
    if updates:
        island.obj.set_uv_positions(updates)
        return "changed"
    if changed_groups:
        return "unchanged"
    if rectangular_groups:
        return "already_rectangular"
    return "skipped"


def gridify_islands(
    islands,
    ratio_influence: float = 0.5,
    shape_blend: float = 0.0,
    selected_face_ids_by_shape: dict[str, set[int]] | None = None,
) -> GridifyResult:
    result = GridifyResult()
    selected_face_ids_by_shape = selected_face_ids_by_shape or {}
    for island in islands:
        selected_face_ids = selected_face_ids_by_shape.get(island.obj.shape)
        status = gridify_island(island, ratio_influence, shape_blend, selected_face_ids)
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
