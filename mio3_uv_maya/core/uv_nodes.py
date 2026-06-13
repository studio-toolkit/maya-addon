"""UV node graph model for Maya."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque

from .mathutils import Bounds2D, Vec2
from .mesh import MayaUVObject


@dataclass(eq=True, frozen=True)
class MayaUVNode:
    obj_shape: str
    uv_id: int


@dataclass
class MayaUVNodeGroup:
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

    def set_positions(self, updates: dict[int, Vec2]) -> None:
        self.obj.set_uv_positions({uv_id: updates[uv_id] for uv_id in updates if uv_id in self.uv_ids})


@dataclass
class MayaUVNodeManager:
    objects: list[MayaUVObject]
    selected_uvs_by_shape: dict[str, set[int]]
    groups: list[MayaUVNodeGroup] = field(default_factory=list)

    @classmethod
    def from_island_manager(cls, island_manager) -> "MayaUVNodeManager":
        selected = island_manager.all_uv_ids_by_shape()
        for shape, uv_ids in getattr(island_manager, "selected_uvs_by_shape", {}).items():
            selected.setdefault(shape, set()).update(uv_ids)
        manager = cls(island_manager.objects, selected)
        manager.find_groups()
        return manager

    def find_groups(self) -> None:
        self.groups = []
        for obj in self.objects:
            selected = set(self.selected_uvs_by_shape.get(obj.shape, set()))
            if not selected:
                continue
            adjacency = {uv_id: set() for uv_id in selected}
            for face in obj.faces:
                for index, uv_id in enumerate(face.uv_ids):
                    if uv_id not in selected:
                        continue
                    next_uv = face.uv_ids[(index + 1) % len(face.uv_ids)]
                    prev_uv = face.uv_ids[index - 1]
                    if next_uv in selected:
                        adjacency[uv_id].add(next_uv)
                        adjacency[next_uv].add(uv_id)
                    if prev_uv in selected:
                        adjacency[uv_id].add(prev_uv)
                        adjacency[prev_uv].add(uv_id)
            visited = set()
            for uv_id in selected:
                if uv_id in visited:
                    continue
                queue = deque([uv_id])
                visited.add(uv_id)
                group = set()
                while queue:
                    current = queue.popleft()
                    group.add(current)
                    for neighbor in adjacency.get(current, set()):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
                self.groups.append(MayaUVNodeGroup(obj, group))
