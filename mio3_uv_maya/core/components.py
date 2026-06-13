"""Maya component parsing helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .maya_api import cmds

_COMP_RE = re.compile(r"^(?P<node>.+)\.(?P<kind>map|e|f|vtx)\[(?P<index>\d+)\]$")


@dataclass
class ComponentSelection:
    objects: set[str] = field(default_factory=set)
    uvs_by_node: dict[str, set[int]] = field(default_factory=dict)
    edges_by_node: dict[str, set[int]] = field(default_factory=dict)
    faces_by_node: dict[str, set[int]] = field(default_factory=dict)
    vertices_by_node: dict[str, set[int]] = field(default_factory=dict)

    @property
    def has_components(self) -> bool:
        return any((self.uvs_by_node, self.edges_by_node, self.faces_by_node, self.vertices_by_node))


def parse_component(component: str) -> tuple[str, str, int] | None:
    match = _COMP_RE.match(component)
    if not match:
        return None
    return match.group("node"), match.group("kind"), int(match.group("index"))


def current_selection(flatten: bool = True) -> ComponentSelection:
    maya_cmds = cmds()
    raw = maya_cmds.ls(sl=True, fl=flatten) or []
    result = ComponentSelection()
    for item in raw:
        parsed = parse_component(item)
        if parsed is None:
            result.objects.add(item)
            continue
        node, kind, index = parsed
        if kind == "map":
            result.uvs_by_node.setdefault(node, set()).add(index)
        elif kind == "e":
            result.edges_by_node.setdefault(node, set()).add(index)
        elif kind == "f":
            result.faces_by_node.setdefault(node, set()).add(index)
        elif kind == "vtx":
            result.vertices_by_node.setdefault(node, set()).add(index)
    return result


def mesh_shapes_from_selection(selection: ComponentSelection | None = None) -> list[str]:
    maya_cmds = cmds()
    selection = selection or current_selection()
    candidates = set(selection.objects)
    candidates.update(selection.uvs_by_node)
    candidates.update(selection.edges_by_node)
    candidates.update(selection.faces_by_node)
    candidates.update(selection.vertices_by_node)

    shapes = []
    for candidate in candidates:
        if maya_cmds.objectType(candidate, isType="mesh"):
            shapes.append(candidate)
            continue
        relatives = maya_cmds.listRelatives(candidate, shapes=True, noIntermediate=True, fullPath=True) or []
        for shape in relatives:
            if maya_cmds.objectType(shape, isType="mesh"):
                shapes.append(shape)
    return sorted(set(shapes))


def select_uvs(shape: str, uv_ids: set[int] | list[int]) -> None:
    maya_cmds = cmds()
    components = ["{}.map[{}]".format(shape, uv_id) for uv_id in sorted(uv_ids)]
    if components:
        maya_cmds.select(components, r=True)

