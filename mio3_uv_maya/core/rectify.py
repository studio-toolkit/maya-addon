# SPDX-FileCopyrightText: 2026 Mio3 UV Maya contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Modifications:
# - Ported from the Blender Mio3 UV Rectify operator flow.
# - Rewritten against MayaUVObject, FaceRecord, and UV-id based assignments.

"""Rectify selected UV island boundaries into a rectangle."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import heapq
import math

from .mathutils import Vec2


EPSILON = 1e-10


@dataclass(frozen=True)
class RectifyOptions:
    bbox_type: str = "AVERAGE"
    distribute: str = "GEOMETRY"
    unwrap_method: str = "ANGLE_BASED"
    unwrap: bool = True
    stretch: bool = False
    pin: bool = True


@dataclass
class RectifyResult:
    valid_islands: int = 0
    changed_islands: int = 0
    skipped_islands: int = 0


@dataclass(frozen=True)
class BoundaryEdge:
    a_uv: int
    b_uv: int
    a_vertex: int
    b_vertex: int


def _uv_key(uv: Vec2) -> tuple[float, float]:
    return round(uv.x, 6), round(uv.y, 6)


def _same_uv(a: Vec2, b: Vec2) -> bool:
    dx = a.x - b.x
    dy = a.y - b.y
    return dx * dx + dy * dy <= 1e-12


def _edge_key(face, local_index: int) -> tuple[int, int]:
    return tuple(sorted((face.vertex_ids[local_index], face.vertex_ids[(local_index + 1) % len(face.vertex_ids)])))


def _edge_uv_ids(face, local_index: int) -> tuple[int, int]:
    return face.uv_ids[local_index], face.uv_ids[(local_index + 1) % len(face.uv_ids)]


def _edge_vertex_ids(face, local_index: int) -> tuple[int, int]:
    return face.vertex_ids[local_index], face.vertex_ids[(local_index + 1) % len(face.vertex_ids)]


def _edge_length_3d(obj, a_vertex: int, b_vertex: int) -> float:
    a = obj.vertex_positions.get(a_vertex)
    b = obj.vertex_positions.get(b_vertex)
    if a is None or b is None:
        return 0.0
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def _group_selected_uvs(island, selected_uvs: set[int]) -> dict[tuple[float, float], list[int]]:
    groups = defaultdict(list)
    for uv_id in sorted(selected_uvs.intersection(island.uv_ids)):
        uv = island.obj.uv_positions.get(uv_id)
        if uv is None:
            continue
        groups[_uv_key(uv)].append(uv_id)
    return dict(groups)


def get_bbox_uvs(uvs: list[Vec2]) -> list[Vec2]:
    min_x = min(uv.x for uv in uvs)
    min_y = min(uv.y for uv in uvs)
    max_x = max(uv.x for uv in uvs)
    max_y = max(uv.y for uv in uvs)
    return [
        Vec2(min_x, max_y),
        Vec2(max_x, max_y),
        Vec2(max_x, min_y),
        Vec2(min_x, min_y),
    ]


def get_bbox_average(uvs: list[Vec2]) -> list[Vec2]:
    center_x = sum(uv.x for uv in uvs) / float(len(uvs))
    center_y = sum(uv.y for uv in uvs) / float(len(uvs))
    avg_distance_x = sum(abs(uv.x - center_x) for uv in uvs) / float(len(uvs))
    avg_distance_y = sum(abs(uv.y - center_y) for uv in uvs) / float(len(uvs))
    return [
        Vec2(center_x - avg_distance_x, center_y + avg_distance_y),
        Vec2(center_x + avg_distance_x, center_y + avg_distance_y),
        Vec2(center_x + avg_distance_x, center_y - avg_distance_y),
        Vec2(center_x - avg_distance_x, center_y - avg_distance_y),
    ]


def _closest_corner_groups(selected_uv_groups: dict[tuple[float, float], list[int]], bbox_uvs: list[Vec2]):
    corners = []
    for bbox_point in bbox_uvs:
        candidates = []
        for uv_key, uv_ids in selected_uv_groups.items():
            total_diff = abs(uv_key[0] - bbox_point.x) + abs(uv_key[1] - bbox_point.y)
            candidates.append((uv_key, uv_ids, total_diff))
        if candidates:
            closest_uv_key, uv_ids, _total_diff = min(candidates, key=lambda item: item[2])
            corners.append((list(uv_ids), Vec2(closest_uv_key[0], closest_uv_key[1])))
    return corners


def _edge_uv_continuous(positions: dict[int, Vec2], face, local_index: int, other_face, other_local_index: int) -> bool:
    a_uv, b_uv = _edge_uv_ids(face, local_index)
    c_uv, d_uv = _edge_uv_ids(other_face, other_local_index)
    a_vertex, b_vertex = _edge_vertex_ids(face, local_index)
    c_vertex, _d_vertex = _edge_vertex_ids(other_face, other_local_index)

    a = positions[a_uv]
    b = positions[b_uv]
    c = positions[c_uv]
    d = positions[d_uv]
    if a_vertex == c_vertex:
        return _same_uv(a, c) and _same_uv(b, d)
    return _same_uv(a, d) and _same_uv(b, c)


def _boundary_edges(island, positions: dict[int, Vec2]) -> list[BoundaryEdge]:
    obj = island.obj
    face_ids = {face_id for uv_id in island.uv_ids for face_id in obj.uv_to_faces.get(uv_id, set())}
    face_by_id = {face.face_id: face for face in obj.faces}
    edges = []

    for face_id in sorted(face_ids):
        face = face_by_id.get(face_id)
        if not face or len(face.vertex_ids) != len(face.uv_ids):
            continue
        for local_index in range(len(face.vertex_ids)):
            a_uv, b_uv = _edge_uv_ids(face, local_index)
            if a_uv not in island.uv_ids or b_uv not in island.uv_ids:
                continue
            edge_key = _edge_key(face, local_index)
            records = obj.edge_to_faces.get(edge_key, [])
            continuous_neighbor = False
            for other_face_id, other_local_index, _other_next_index in records:
                if other_face_id == face.face_id or other_face_id not in face_ids:
                    continue
                other_face = face_by_id.get(other_face_id)
                if other_face and _edge_uv_continuous(positions, face, local_index, other_face, other_local_index):
                    continuous_neighbor = True
                    break
            if not continuous_neighbor:
                a_vertex, b_vertex = _edge_vertex_ids(face, local_index)
                edges.append(BoundaryEdge(a_uv, b_uv, a_vertex, b_vertex))
    return edges


def _boundary_graph(island, positions: dict[int, Vec2]):
    adjacency = defaultdict(dict)
    for edge in _boundary_edges(island, positions):
        geo_length = _edge_length_3d(island.obj, edge.a_vertex, edge.b_vertex)
        uv_length = (positions[edge.b_uv] - positions[edge.a_uv]).length
        weight = max(uv_length, geo_length, 1.0)
        existing = adjacency[edge.a_uv].get(edge.b_uv)
        if existing is None or weight < existing["weight"]:
            data = {"weight": weight, "geo_length": geo_length, "uv_length": uv_length}
            adjacency[edge.a_uv][edge.b_uv] = data
            adjacency[edge.b_uv][edge.a_uv] = data
    return adjacency


def _shortest_path(adjacency, start_uvs: list[int], end_uvs: list[int]) -> list[int]:
    start_set = set(start_uvs)
    end_set = set(end_uvs)
    queue = []
    best = {}
    previous = {}
    for uv_id in start_set:
        best[uv_id] = 0.0
        heapq.heappush(queue, (0.0, uv_id))

    found = None
    while queue:
        cost, uv_id = heapq.heappop(queue)
        if cost > best.get(uv_id, float("inf")) + EPSILON:
            continue
        if uv_id in end_set:
            found = uv_id
            break
        for neighbor, data in adjacency.get(uv_id, {}).items():
            next_cost = cost + data["weight"]
            if next_cost + EPSILON < best.get(neighbor, float("inf")):
                best[neighbor] = next_cost
                previous[neighbor] = uv_id
                heapq.heappush(queue, (next_cost, neighbor))

    if found is None:
        return []

    path = [found]
    while path[-1] not in start_set:
        path.append(previous[path[-1]])
    path.reverse()
    return path


def _path_lengths(path: list[int], adjacency, positions: dict[int, Vec2], mode: str) -> list[float]:
    lengths = [0.0]
    total = 0.0
    for index in range(1, len(path)):
        a = path[index - 1]
        b = path[index]
        data = adjacency.get(a, {}).get(b, {})
        if mode == "GEOMETRY":
            segment = data.get("geo_length", 0.0)
        elif mode == "EVEN":
            segment = 1.0
        else:
            segment = data.get("uv_length", (positions[b] - positions[a]).length)
        if segment <= EPSILON:
            segment = 1.0 if mode == "EVEN" else (positions[b] - positions[a]).length
        total += max(segment, 0.0)
        lengths.append(total)
    if total <= EPSILON and len(path) > 1:
        return [float(index) for index in range(len(path))]
    return lengths


def _straighten_path(path: list[int], start_uv: Vec2, end_uv: Vec2, positions: dict[int, Vec2], adjacency, mode: str) -> set[int]:
    if len(path) <= 1:
        return set(path)

    lengths = _path_lengths(path, adjacency, positions, mode)
    total = lengths[-1]
    if total <= EPSILON:
        total = float(max(len(path) - 1, 1))
        lengths = [float(index) for index in range(len(path))]

    direction = end_uv - start_uv
    boundary = set()
    for index, uv_id in enumerate(path):
        factor = lengths[index] / total
        positions[uv_id] = start_uv + direction * factor
        boundary.add(uv_id)
    return boundary


def _remap_bbox(boundary_uv_ids: set[int], positions: dict[int, Vec2], bbox_uvs: list[Vec2], bbox_average: list[Vec2]) -> None:
    old_width = bbox_uvs[1].x - bbox_uvs[0].x
    old_height = bbox_uvs[0].y - bbox_uvs[3].y
    new_width = bbox_average[1].x - bbox_average[0].x
    new_height = bbox_average[0].y - bbox_average[3].y
    if abs(old_width) <= EPSILON or abs(old_height) <= EPSILON:
        return

    scale_x = new_width / old_width
    scale_y = new_height / old_height
    old_origin = bbox_uvs[0]
    new_origin = bbox_average[0]

    for uv_id in boundary_uv_ids:
        uv = positions[uv_id]
        positions[uv_id] = Vec2(
            (uv.x - old_origin.x) * scale_x + new_origin.x,
            (uv.y - old_origin.y) * scale_y + new_origin.y,
        )


def _uv_adjacency(island) -> dict[int, set[int]]:
    adjacency = {uv_id: set() for uv_id in island.uv_ids}
    for face in island.obj.faces:
        if not set(face.uv_ids).intersection(island.uv_ids):
            continue
        for index, uv_id in enumerate(face.uv_ids):
            next_uv = face.uv_ids[(index + 1) % len(face.uv_ids)]
            if uv_id in island.uv_ids and next_uv in island.uv_ids:
                adjacency.setdefault(uv_id, set()).add(next_uv)
                adjacency.setdefault(next_uv, set()).add(uv_id)
    return adjacency


def _solver_iterations(options: RectifyOptions) -> int:
    base = {
        "ANGLE_BASED": 80,
        "CONFORMAL": 60,
        "MINIMUM_STRETCH": 120,
    }.get(options.unwrap_method, 80)
    if options.stretch:
        base += 80
    return base


def _relax_interior(island, positions: dict[int, Vec2], fixed_uv_ids: set[int], options: RectifyOptions) -> None:
    adjacency = _uv_adjacency(island)
    interior = [uv_id for uv_id in island.uv_ids if uv_id not in fixed_uv_ids and adjacency.get(uv_id)]
    if not interior:
        return

    for _iteration in range(_solver_iterations(options)):
        updates = {}
        for uv_id in interior:
            neighbors = [neighbor for neighbor in adjacency.get(uv_id, set()) if neighbor in positions]
            if not neighbors:
                continue
            total = Vec2()
            for neighbor in neighbors:
                total = total + positions[neighbor]
            updates[uv_id] = total / float(len(neighbors))
        positions.update(updates)


def rectify_island(island, selected_uvs: set[int], options: RectifyOptions | None = None) -> str:
    options = options or RectifyOptions()
    original_positions = dict(island.obj.uv_positions)
    selected_uv_groups = _group_selected_uvs(island, selected_uvs)
    if len(selected_uv_groups) < 4:
        return "skipped"

    selected_vectors = [Vec2(uv_key[0], uv_key[1]) for uv_key in selected_uv_groups]
    bbox_uvs = get_bbox_uvs(selected_vectors)
    corners = _closest_corner_groups(selected_uv_groups, bbox_uvs)
    if len(corners) < 4:
        return "skipped"

    positions = dict(original_positions)
    adjacency = _boundary_graph(island, original_positions)
    boundary_uv_ids = set()

    for (uv_ids, _corner_uv), bbox_uv in zip(corners, bbox_uvs):
        for uv_id in uv_ids:
            positions[uv_id] = bbox_uv
            boundary_uv_ids.add(uv_id)

    for (current_uv_ids, _current_uv), (next_uv_ids, _next_uv), current_bbox_uv, next_bbox_uv in zip(
        corners,
        corners[1:] + [corners[0]],
        bbox_uvs,
        bbox_uvs[1:] + [bbox_uvs[0]],
    ):
        path = _shortest_path(adjacency, current_uv_ids, next_uv_ids)
        if path:
            boundary_uv_ids.update(_straighten_path(path, current_bbox_uv, next_bbox_uv, positions, adjacency, options.distribute))

    if options.bbox_type == "AVERAGE" and boundary_uv_ids:
        bbox_average = get_bbox_average([corner_uv for _uv_ids, corner_uv in corners])
        _remap_bbox(boundary_uv_ids, positions, bbox_uvs, bbox_average)

    fixed_uv_ids = set(boundary_uv_ids)
    if options.unwrap:
        _relax_interior(island, positions, fixed_uv_ids, options)

    updates = {
        uv_id: uv
        for uv_id, uv in positions.items()
        if uv_id in original_positions and uv != original_positions[uv_id]
    }
    if not updates:
        return "unchanged"
    island.obj.set_uv_positions(updates)
    return "changed"


def rectify_islands(islands, selected_uvs_by_shape: dict[str, set[int]], options: RectifyOptions | None = None) -> RectifyResult:
    result = RectifyResult()
    options = options or RectifyOptions()
    for island in islands:
        selected_uvs = set(selected_uvs_by_shape.get(island.obj.shape, set()))
        status = rectify_island(island, selected_uvs, options)
        if status == "changed":
            result.valid_islands += 1
            result.changed_islands += 1
        elif status == "unchanged":
            result.valid_islands += 1
        else:
            result.skipped_islands += 1
    return result
