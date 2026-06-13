"""Maya mesh UV object and island model."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import defaultdict, deque

from .components import ComponentSelection, current_selection, mesh_shapes_from_selection
from .mathutils import Bounds2D, Vec2, Vec3
from .maya_api import cmds, om2


@dataclass
class FaceRecord:
    face_id: int
    vertex_ids: list[int]
    uv_ids: list[int]


@dataclass
class MayaUVObject:
    shape: str
    uv_set: str | None = None
    dag_path: object | None = None
    mesh_fn: object | None = None
    faces: list[FaceRecord] = field(default_factory=list)
    uv_positions: dict[int, Vec2] = field(default_factory=dict)
    vertex_positions: dict[int, Vec3] = field(default_factory=dict)
    uv_to_faces: dict[int, set[int]] = field(default_factory=dict)
    edge_to_faces: dict[tuple[int, int], list[tuple[int, int, int]]] = field(default_factory=dict)

    def __post_init__(self):
        self.refresh()

    def refresh(self) -> None:
        maya_cmds = cmds()
        om = om2()
        selection = om.MSelectionList()
        selection.add(self.shape)
        self.dag_path = selection.getDagPath(0)
        self.mesh_fn = om.MFnMesh(self.dag_path)
        self.uv_set = self.uv_set or self.mesh_fn.currentUVSetName()

        u_values, v_values = self.mesh_fn.getUVs(self.uv_set)
        self.uv_positions = {
            index: Vec2(float(u_values[index]), float(v_values[index]))
            for index in range(len(u_values))
        }

        counts, vertex_ids = self.mesh_fn.getVertices()
        uv_counts, uv_ids = self.mesh_fn.getAssignedUVs(self.uv_set)
        self.faces = []
        self.uv_to_faces = defaultdict(set)
        self.edge_to_faces = defaultdict(list)

        vert_cursor = 0
        uv_cursor = 0
        for face_id, count in enumerate(counts):
            vertices = [int(vertex_ids[vert_cursor + i]) for i in range(count)]
            vert_cursor += count
            face_uv_count = int(uv_counts[face_id]) if face_id < len(uv_counts) else 0
            if face_uv_count:
                face_uv_ids = [int(uv_ids[uv_cursor + i]) for i in range(face_uv_count)]
                uv_cursor += face_uv_count
            else:
                face_uv_ids = []
            record = FaceRecord(face_id, vertices, face_uv_ids)
            self.faces.append(record)
            for uv_id in face_uv_ids:
                self.uv_to_faces.setdefault(uv_id, set()).add(face_id)
            if len(vertices) == len(face_uv_ids):
                for local_index, vertex_id in enumerate(vertices):
                    next_index = (local_index + 1) % len(vertices)
                    next_vertex_id = vertices[next_index]
                    edge_key = tuple(sorted((vertex_id, next_vertex_id)))
                    self.edge_to_faces[edge_key].append((face_id, local_index, next_index))

        points = self.mesh_fn.getPoints(om.MSpace.kWorld)
        self.vertex_positions = {
            index: Vec3(float(point.x), float(point.y), float(point.z))
            for index, point in enumerate(points)
        }

        # Ensure Maya has flushed pending component edits before later queries.
        maya_cmds.refresh(currentView=True, force=False)

    @property
    def name(self) -> str:
        return self.shape

    def component_aliases(self) -> set[str]:
        maya_cmds = cmds()
        aliases = {self.shape, self.shape.split("|")[-1]}
        parents = maya_cmds.listRelatives(self.shape, parent=True, fullPath=True) or []
        for parent in parents:
            aliases.add(parent)
            aliases.add(parent.split("|")[-1])
        return aliases

    def component_node(self) -> str:
        parents = cmds().listRelatives(self.shape, parent=True, fullPath=True) or []
        return parents[0] if parents else self.shape

    def all_uv_ids(self) -> set[int]:
        return set(self.uv_positions.keys())

    def set_uv_positions(self, updates: dict[int, Vec2]) -> None:
        if not updates:
            return

        normalized = {
            int(uv_id): Vec2(float(uv.x), float(uv.y))
            for uv_id, uv in updates.items()
            if int(uv_id) in self.uv_positions
        }
        if not normalized:
            return

        batch_written = False
        if hasattr(self.mesh_fn, "setUVs"):
            u_values = [self.uv_positions[index].x for index in range(len(self.uv_positions))]
            v_values = [self.uv_positions[index].y for index in range(len(self.uv_positions))]
            for uv_id, uv in normalized.items():
                u_values[uv_id] = uv.x
                v_values[uv_id] = uv.y
            try:
                self.mesh_fn.setUVs(u_values, v_values, self.uv_set)
                batch_written = True
            except TypeError:
                try:
                    self.mesh_fn.setUVs(u_values, v_values)
                    batch_written = True
                except Exception:
                    batch_written = False
            except Exception:
                batch_written = False

        if not batch_written:
            for uv_id, uv in normalized.items():
                self.mesh_fn.setUV(int(uv_id), float(uv.x), float(uv.y), self.uv_set)

        self.uv_positions.update(normalized)
        self.mesh_fn.updateSurface()

    def connected_uv_shells(self) -> list[set[int]]:
        adjacency = {uv_id: set() for uv_id in self.uv_positions}
        for face in self.faces:
            if len(face.uv_ids) < 2:
                continue
            for index, uv_id in enumerate(face.uv_ids):
                next_uv_id = face.uv_ids[(index + 1) % len(face.uv_ids)]
                if uv_id == next_uv_id:
                    continue
                adjacency.setdefault(uv_id, set()).add(next_uv_id)
                adjacency.setdefault(next_uv_id, set()).add(uv_id)

        visited = set()
        shells = []
        for uv_id in adjacency:
            if uv_id in visited:
                continue
            shell = set()
            queue = deque([uv_id])
            visited.add(uv_id)
            while queue:
                current = queue.popleft()
                shell.add(current)
                for neighbor in adjacency[current]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            shells.append(shell)
        return shells

    def uv_ids_from_faces(self, face_ids: set[int]) -> set[int]:
        result = set()
        for face_id in face_ids:
            if 0 <= face_id < len(self.faces):
                result.update(self.faces[face_id].uv_ids)
        return result

    def uv_ids_from_vertices(self, vertex_ids: set[int]) -> set[int]:
        result = set()
        for face in self.faces:
            for vertex_id, uv_id in zip(face.vertex_ids, face.uv_ids):
                if vertex_id in vertex_ids:
                    result.add(uv_id)
        return result

    def uv_ids_from_edges(self, edge_ids: set[int]) -> set[int]:
        # Edge-id to UV-id conversion is delegated to Maya component conversion;
        # this keeps the mapping correct for Maya's internal edge indexing.
        maya_cmds = cmds()
        if not edge_ids:
            return set()
        node = self.component_node()
        edge_components = ["{}.e[{}]".format(node, edge_id) for edge_id in edge_ids]
        uv_components = maya_cmds.polyListComponentConversion(edge_components, tuv=True) or []
        uv_components = maya_cmds.ls(uv_components, fl=True) or []
        from .components import parse_component

        result = set()
        for component in uv_components:
            parsed = parse_component(component)
            if parsed and parsed[1] == "map":
                result.add(parsed[2])
        return result


@dataclass
class MayaUVIsland:
    obj: MayaUVObject
    uv_ids: set[int]

    @property
    def points(self) -> list[Vec2]:
        return [self.obj.uv_positions[uv_id] for uv_id in self.uv_ids if uv_id in self.obj.uv_positions]

    @property
    def bounds(self) -> Bounds2D:
        bounds = Bounds2D()
        bounds.include_many(self.points)
        return bounds

    @property
    def center(self) -> Vec2:
        return self.bounds.center

    @property
    def median_center(self) -> Vec2:
        points = self.points
        if not points:
            return Vec2()
        return Vec2(sum(p.x for p in points) / len(points), sum(p.y for p in points) / len(points))

    @property
    def center_3d(self) -> Vec3:
        vertex_ids = set()
        for uv_id in self.uv_ids:
            for face_id in self.obj.uv_to_faces.get(uv_id, set()):
                face = self.obj.faces[face_id]
                for vertex_id, face_uv_id in zip(face.vertex_ids, face.uv_ids):
                    if face_uv_id == uv_id:
                        vertex_ids.add(vertex_id)
        if not vertex_ids:
            return Vec3()
        total = Vec3()
        for vertex_id in vertex_ids:
            total = total + self.obj.vertex_positions.get(vertex_id, Vec3())
        return total / float(len(vertex_ids))

    def move(self, offset: Vec2) -> None:
        updates = {
            uv_id: self.obj.uv_positions[uv_id] + offset
            for uv_id in self.uv_ids
            if uv_id in self.obj.uv_positions
        }
        self.obj.set_uv_positions(updates)

    def transform(self, scale: Vec2 | None = None, offset: Vec2 | None = None, origin: Vec2 | None = None, angle: float = 0.0) -> None:
        scale = scale or Vec2(1.0, 1.0)
        offset = offset or Vec2()
        origin = origin or self.center
        updates = {}
        for uv_id in self.uv_ids:
            uv = self.obj.uv_positions[uv_id]
            local = Vec2((uv.x - origin.x) * scale.x, (uv.y - origin.y) * scale.y)
            transformed = Vec2(local.x + origin.x, local.y + origin.y)
            if angle:
                transformed = transformed.rotated(angle, origin)
            updates[uv_id] = transformed + offset
        self.obj.set_uv_positions(updates)


@dataclass
class MayaUVIslandManager:
    objects: list[MayaUVObject]
    selected_uvs_by_shape: dict[str, set[int]] = field(default_factory=dict)
    selection_kinds_by_shape: dict[str, set[str]] = field(default_factory=dict)
    islands: list[MayaUVIsland] = field(default_factory=list)

    @classmethod
    def from_selection(cls, include_all_if_no_components: bool = True) -> "MayaUVIslandManager":
        selection = current_selection()
        objects = [MayaUVObject(shape) for shape in mesh_shapes_from_selection(selection)]
        selected_by_shape = {}
        kinds_by_shape = {}
        for obj in objects:
            aliases = obj.component_aliases()
            selected = set()
            face_ids = set()
            vertex_ids = set()
            edge_ids = set()
            kinds = set()
            for alias in aliases:
                alias_uvs = selection.uvs_by_node.get(alias, set())
                alias_faces = selection.faces_by_node.get(alias, set())
                alias_vertices = selection.vertices_by_node.get(alias, set())
                alias_edges = selection.edges_by_node.get(alias, set())
                selected.update(alias_uvs)
                face_ids.update(alias_faces)
                vertex_ids.update(alias_vertices)
                edge_ids.update(alias_edges)
                if alias_uvs:
                    kinds.add("uv")
                if alias_edges:
                    kinds.add("edge")
                if alias_vertices:
                    kinds.add("vertex")
                if alias_faces:
                    kinds.add("face")
            selected.update(obj.uv_ids_from_faces(face_ids))
            selected.update(obj.uv_ids_from_vertices(vertex_ids))
            selected.update(obj.uv_ids_from_edges(edge_ids))
            if not selected and include_all_if_no_components:
                selected = obj.all_uv_ids()
            selected_by_shape[obj.shape] = selected
            kinds_by_shape[obj.shape] = kinds
        manager = cls(objects=objects, selected_uvs_by_shape=selected_by_shape, selection_kinds_by_shape=kinds_by_shape)
        manager.find_islands()
        return manager

    def find_islands(self) -> None:
        self.islands = []
        for obj in self.objects:
            selected = self.selected_uvs_by_shape.get(obj.shape, set())
            for shell in obj.connected_uv_shells():
                if selected and not shell.intersection(selected):
                    continue
                self.islands.append(MayaUVIsland(obj, set(shell)))

    def all_uv_ids_by_shape(self) -> dict[str, set[int]]:
        result = defaultdict(set)
        for island in self.islands:
            result[island.obj.shape].update(island.uv_ids)
        return dict(result)

    def bounds(self) -> Bounds2D:
        bounds = Bounds2D()
        for island in self.islands:
            bounds.include_many(island.points)
        return bounds

    def refresh(self) -> None:
        for obj in self.objects:
            obj.refresh()
        self.find_islands()
