import math
import unittest
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import patch

from mio3_uv_maya.core.mathutils import Bounds2D, Vec2, Vec3, polygon_area
from mio3_uv_maya.core.mesh import FaceRecord, MayaUVIsland, MayaUVIslandManager, MayaUVObject
from mio3_uv_maya.core.gridify import gridify_island, gridify_islands
from mio3_uv_maya.core.rectify import RectifyOptions, rectify_island, rectify_islands
from mio3_uv_maya.operators.base import Action
from mio3_uv_maya.operators.align import (
    _align_edge_groups,
    _align_selected_components,
    _align_shells,
    _has_edge_align_selection,
    _has_node_component_selection,
)
from mio3_uv_maya.operators.texel import _density_from_areas, _scale_islands_to_density
from mio3_uv_maya.operators import all_actions
import mio3_uv_maya.core.undo as undo_module
import mio3_uv_maya.core.mesh as mesh_module
import mio3_uv_maya.operators.arrange as arrange_module
import mio3_uv_maya.operators.base as base_module
import mio3_uv_maya.operators.unwrap as unwrap_module


class FakeUVObject:
    shape = "meshShape"

    def __init__(self, positions, faces=None):
        self.uv_positions = dict(positions)
        self.faces = faces or []
        self.vertex_positions = {}
        self.uv_to_faces = defaultdict(set)
        self.edge_to_faces = defaultdict(list)
        self.write_count = 0

    def set_uv_positions(self, updates):
        self.write_count += 1
        self.uv_positions.update(updates)


class FakeCmds:
    def __init__(self):
        self.calls = []
        self.undo_state = True

    def undoInfo(self, **kwargs):
        self.calls.append(("undoInfo", dict(kwargs)))
        if kwargs.get("query") and kwargs.get("state"):
            return self.undo_state
        if "stateWithoutFlush" in kwargs:
            self.undo_state = bool(kwargs["stateWithoutFlush"])
        return None

    def inViewMessage(self, **kwargs):
        self.calls.append(("inViewMessage", dict(kwargs)))


class FakeMeshFn:
    def __init__(self):
        self.set_uvs_calls = []
        self.set_uv_calls = []
        self.update_count = 0

    def setUVs(self, u_values, v_values, uv_set):
        self.set_uvs_calls.append((list(u_values), list(v_values), uv_set))

    def setUV(self, uv_id, u_value, v_value, uv_set):
        self.set_uv_calls.append((uv_id, u_value, v_value, uv_set))

    def updateSurface(self):
        self.update_count += 1


class FakeNativeCmds:
    def __init__(self, selection=None, conversions=None, history_connections=None):
        self.selection = selection or []
        self.conversions = conversions or {}
        self.history_connections = history_connections or {}
        self.calls = []

    def ls(self, *args, **kwargs):
        self.calls.append(("ls", tuple(args), dict(kwargs)))
        if args:
            return list(args[0])
        return list(self.selection)

    def polyListComponentConversion(self, components, **kwargs):
        self.calls.append(("polyListComponentConversion", (list(components),), dict(kwargs)))
        key = tuple(components), tuple(sorted(kwargs.items()))
        return list(self.conversions.get(key, components))

    def select(self, components, **kwargs):
        self.calls.append(("select", (list(components),), dict(kwargs)))
        self.selection = list(components)

    def polyMergeUV(self, *args, **kwargs):
        self.calls.append(("polyMergeUV", tuple(args), dict(kwargs)))

    def polyMapSewMove(self, *args, **kwargs):
        self.calls.append(("polyMapSewMove", tuple(args), dict(kwargs)))

    def polyEditUV(self, *args, **kwargs):
        self.calls.append(("polyEditUV", tuple(args), dict(kwargs)))

    def listConnections(self, attr, **kwargs):
        self.calls.append(("listConnections", (attr,), dict(kwargs)))
        return list(self.history_connections.get(attr, []))

    def listRelatives(self, *args, **kwargs):
        self.calls.append(("listRelatives", tuple(args), dict(kwargs)))
        return []


def rebuild_fake_topology(obj):
    obj.uv_to_faces = defaultdict(set)
    obj.edge_to_faces = defaultdict(list)
    for face in obj.faces:
        for uv_id in face.uv_ids:
            obj.uv_to_faces[uv_id].add(face.face_id)
        if len(face.vertex_ids) != len(face.uv_ids):
            continue
        for local_index, vertex_id in enumerate(face.vertex_ids):
            next_index = (local_index + 1) % len(face.vertex_ids)
            edge = tuple(sorted((vertex_id, face.vertex_ids[next_index])))
            obj.edge_to_faces[edge].append((face.face_id, local_index, next_index))
    return obj


def build_grid_object(columns, rows, uv_positions=None, vertex_positions=None):
    obj = FakeUVObject({})
    obj.vertex_positions = {}
    obj.faces = []

    for row in range(rows + 1):
        for column in range(columns + 1):
            vertex_id = row * (columns + 1) + column
            position = vertex_positions.get(vertex_id) if vertex_positions else None
            obj.vertex_positions[vertex_id] = position or Vec3(float(column), float(row), 0.0)
            obj.uv_positions[vertex_id] = (uv_positions or {}).get(vertex_id, Vec2(float(column), float(row)))

    for row in range(rows):
        for column in range(columns):
            face_id = row * columns + column
            bl = row * (columns + 1) + column
            br = bl + 1
            tl = bl + columns + 1
            tr = tl + 1
            face = FaceRecord(face_id, [bl, br, tr, tl], [bl, br, tr, tl])
            obj.faces.append(face)
    rebuild_fake_topology(obj)
    return obj


def assert_grid_lines(test_case, obj, columns, rows):
    for row in range(rows + 1):
        ids = [row * (columns + 1) + column for column in range(columns + 1)]
        row_y = obj.uv_positions[ids[0]].y
        for uv_id in ids[1:]:
            test_case.assertAlmostEqual(obj.uv_positions[uv_id].y, row_y, places=6)

    for column in range(columns + 1):
        ids = [row * (columns + 1) + column for row in range(rows + 1)]
        column_x = obj.uv_positions[ids[0]].x
        for uv_id in ids[1:]:
            test_case.assertAlmostEqual(obj.uv_positions[uv_id].x, column_x, places=6)


class TestMio3UVMayaCore(unittest.TestCase):
    def test_vec2_rotation(self):
        rotated = Vec2(1.0, 0.0).rotated(math.pi / 2.0)
        self.assertAlmostEqual(rotated.x, 0.0, places=6)
        self.assertAlmostEqual(rotated.y, 1.0, places=6)

    def test_bounds(self):
        bounds = Bounds2D()
        bounds.include_many([Vec2(-1.0, 2.0), Vec2(3.0, -2.0)])
        self.assertEqual(bounds.width, 4.0)
        self.assertEqual(bounds.height, 4.0)
        self.assertEqual(bounds.center, Vec2(1.0, 0.0))

    def test_polygon_area(self):
        self.assertAlmostEqual(polygon_area([Vec2(0, 0), Vec2(1, 0), Vec2(1, 1), Vec2(0, 1)]), 1.0)

    def test_action_registry_has_expected_scale(self):
        actions = all_actions()
        self.assertGreaterEqual(len(actions), 40)
        self.assertTrue(any(action.id == "normalize" for action in actions))
        self.assertTrue(any(action.id == "checker_map" for action in actions))
        self.assertTrue(any(action.id == "align_edges_x" for action in actions))
        self.assertTrue(any(action.id == "align_edges_y" for action in actions))
        self.assertEqual(next(action for action in actions if action.id == "merge").tooltip, "Merge selected UVs within a small distance.")
        self.assertEqual(next(action for action in actions if action.id == "texel_density_set").tooltip, "Scale selected UV shells to the stored texel density.")
        self.assertEqual(next(action for action in actions if action.id == "gridify").tooltip, "Align selected quad UV shells into a grid.")
        self.assertEqual(next(action for action in actions if action.id == "rectify").tooltip, "Unwrap selected UV boundaries into a rectangle.")

    def test_single_face_is_one_uv_shell(self):
        obj = MayaUVObject.__new__(MayaUVObject)
        obj.uv_positions = {
            0: Vec2(0.0, 0.0),
            1: Vec2(1.0, 0.0),
            2: Vec2(1.0, 1.0),
            3: Vec2(0.0, 1.0),
        }
        obj.faces = [FaceRecord(0, [0, 1, 2, 3], [0, 1, 2, 3])]
        obj.edge_to_faces = {}
        self.assertEqual(obj.connected_uv_shells(), [{0, 1, 2, 3}])

    def test_uv_position_updates_use_single_batch_write(self):
        mesh_fn = FakeMeshFn()
        obj = MayaUVObject.__new__(MayaUVObject)
        obj.shape = "meshShape"
        obj.mesh_fn = mesh_fn
        obj.uv_set = "map1"
        obj.uv_positions = {
            0: Vec2(0.0, 0.0),
            1: Vec2(1.0, 0.0),
            2: Vec2(1.0, 1.0),
        }

        obj.set_uv_positions({1: Vec2(2.0, 3.0), 2: Vec2(4.0, 5.0)})

        self.assertEqual(mesh_fn.set_uvs_calls, [([0.0, 2.0, 4.0], [0.0, 3.0, 5.0], "map1")])
        self.assertEqual(mesh_fn.set_uv_calls, [])
        self.assertEqual(mesh_fn.update_count, 1)
        self.assertEqual(obj.uv_positions[1], Vec2(2.0, 3.0))
        self.assertEqual(obj.uv_positions[2], Vec2(4.0, 5.0))

    def test_uv_position_updates_with_history_use_component_tweaks(self):
        mesh_fn = FakeMeshFn()
        obj = MayaUVObject.__new__(MayaUVObject)
        obj.shape = "meshShape"
        obj.mesh_fn = mesh_fn
        obj.uv_set = "map1"
        obj.uv_positions = {
            0: Vec2(0.0, 0.0),
            1: Vec2(1.0, 0.0),
            2: Vec2(1.0, 1.0),
        }
        fake_cmds = FakeNativeCmds(
            selection=["meshShape.map[0]"],
            history_connections={"meshShape.inMesh": ["polyTweak1.output"]},
        )

        with patch.object(mesh_module, "cmds", return_value=fake_cmds):
            obj.set_uv_positions({1: Vec2(2.0, 3.0), 2: Vec2(4.0, 5.0)})

        self.assertEqual(mesh_fn.set_uvs_calls, [])
        self.assertEqual(mesh_fn.set_uv_calls, [])
        self.assertEqual(mesh_fn.update_count, 1)
        self.assertIn(("listConnections", ("meshShape.inMesh",), {"source": True, "destination": False}), fake_cmds.calls)
        self.assertIn(("polyEditUV", ("meshShape.map[1]",), {"relative": False, "uValue": 2.0, "vValue": 3.0}), fake_cmds.calls)
        self.assertIn(("polyEditUV", ("meshShape.map[2]",), {"relative": False, "uValue": 4.0, "vValue": 5.0}), fake_cmds.calls)
        self.assertEqual(fake_cmds.calls[-1], ("select", (["meshShape.map[0]"],), {"r": True}))
        self.assertEqual(obj.uv_positions[1], Vec2(2.0, 3.0))
        self.assertEqual(obj.uv_positions[2], Vec2(4.0, 5.0))

    def test_component_align_top_only_changes_selected_axis(self):
        obj = FakeUVObject(
            {
                0: Vec2(0.0, 0.0),
                1: Vec2(1.0, 0.5),
                2: Vec2(2.0, 1.0),
            }
        )
        manager = SimpleNamespace(objects=[obj], selected_uvs_by_shape={"meshShape": {0, 1, 2}})
        self.assertTrue(_align_selected_components(manager, "MAX_Y"))
        self.assertEqual(obj.uv_positions[0], Vec2(0.0, 1.0))
        self.assertEqual(obj.uv_positions[1], Vec2(1.0, 1.0))
        self.assertEqual(obj.uv_positions[2], Vec2(2.0, 1.0))

    def test_shell_align_moves_whole_shell_without_collapsing_points(self):
        obj = FakeUVObject(
            {
                0: Vec2(0.0, 0.0),
                1: Vec2(1.0, 0.0),
                2: Vec2(1.0, 1.0),
                3: Vec2(0.0, 1.0),
                4: Vec2(2.0, 3.0),
                5: Vec2(3.0, 3.0),
                6: Vec2(3.0, 4.0),
                7: Vec2(2.0, 4.0),
            }
        )
        manager = MayaUVIslandManager(
            objects=[obj],
            islands=[
                MayaUVIsland(obj, {0, 1, 2, 3}),
                MayaUVIsland(obj, {4, 5, 6, 7}),
            ],
        )
        self.assertTrue(_align_shells(manager, "MAX_Y"))
        self.assertEqual(obj.uv_positions[0], Vec2(0.0, 3.0))
        self.assertEqual(obj.uv_positions[2], Vec2(1.0, 4.0))
        self.assertEqual(obj.uv_positions[4], Vec2(2.0, 3.0))
        self.assertEqual(obj.uv_positions[6], Vec2(3.0, 4.0))
        self.assertEqual(obj.write_count, 1)

    def test_node_component_selection_excludes_face_only_selection(self):
        face_manager = MayaUVIslandManager(
            objects=[],
            selection_kinds_by_shape={"meshShape": {"face"}},
        )
        edge_manager = MayaUVIslandManager(
            objects=[],
            selection_kinds_by_shape={"meshShape": {"edge"}},
        )
        self.assertFalse(_has_node_component_selection(face_manager))
        self.assertTrue(_has_node_component_selection(edge_manager))
        self.assertFalse(_has_edge_align_selection(face_manager))
        self.assertTrue(_has_edge_align_selection(edge_manager))

    def test_align_edge_groups_horizontal(self):
        obj = FakeUVObject(
            {
                0: Vec2(0.0, 0.0),
                1: Vec2(1.0, 0.5),
                2: Vec2(2.0, 1.0),
            },
            faces=[FaceRecord(0, [0, 1, 2], [0, 1, 2])],
        )
        manager = MayaUVIslandManager(objects=[obj], selected_uvs_by_shape={"meshShape": {0, 1, 2}})
        self.assertTrue(_align_edge_groups(manager, "X"))
        self.assertEqual(obj.uv_positions[0], Vec2(0.0, 0.5))
        self.assertEqual(obj.uv_positions[1], Vec2(1.0, 0.5))
        self.assertEqual(obj.uv_positions[2], Vec2(2.0, 0.5))
        self.assertEqual(obj.write_count, 1)

    def test_action_message_does_not_create_undo_step(self):
        fake_cmds = FakeCmds()
        markers = []

        def callback():
            markers.append("callback")
            return True

        with patch.object(undo_module, "cmds", return_value=fake_cmds), patch.object(base_module, "cmds", return_value=fake_cmds):
            Action("align_bottom", "Align Bottom", "Align bottom.", callback).run()

        self.assertEqual(markers, ["callback"])
        self.assertEqual(
            fake_cmds.calls,
            [
                ("undoInfo", {"openChunk": True, "chunkName": "Align Bottom"}),
                ("undoInfo", {"closeChunk": True}),
                ("undoInfo", {"query": True, "state": True}),
                ("undoInfo", {"stateWithoutFlush": False}),
                ("inViewMessage", {"amg": "Mio3 UV: Align Bottom", "pos": "midCenter", "fade": True}),
                ("undoInfo", {"stateWithoutFlush": True}),
            ],
        )

    def test_merge_uses_maya_native_poly_merge_uv(self):
        selection = ["meshShape.e[10]", "meshShape.e[11]"]
        converted = ["meshShape.map[0]", "meshShape.map[1]"]
        fake_cmds = FakeNativeCmds(
            selection,
            conversions={(tuple(selection), (("tuv", True),)): converted},
        )
        with patch.object(arrange_module, "cmds", return_value=fake_cmds):
            self.assertTrue(arrange_module.merge(0.0025))

        self.assertEqual(
            fake_cmds.calls,
            [
                ("ls", (), {"sl": True, "fl": True}),
                ("polyListComponentConversion", (selection,), {"tuv": True}),
                ("ls", (converted,), {"fl": True}),
                ("select", (converted,), {"r": True}),
                ("polyMergeUV", (converted,), {"distance": 0.0025, "constructionHistory": False}),
            ],
        )

    def test_stitch_uses_maya_native_poly_map_sew_move(self):
        selection = ["meshShape.vtx[370]", "meshShape.vtx[371]"]
        converted = ["meshShape.e[352]", "meshShape.e[712]"]
        fake_cmds = FakeNativeCmds(
            selection,
            conversions={(tuple(selection), (("te", True),)): converted},
        )
        with patch.object(arrange_module, "cmds", return_value=fake_cmds):
            self.assertTrue(arrange_module.stitch())

        self.assertEqual(
            fake_cmds.calls,
            [
                ("ls", (), {"sl": True, "fl": True}),
                ("polyListComponentConversion", (selection,), {"te": True}),
                ("ls", (converted,), {"fl": True}),
                ("select", (converted,), {"r": True}),
                ("polyMapSewMove", (converted,), {"constructionHistory": False}),
            ],
        )

    def test_texel_density_formula_uses_texture_area(self):
        self.assertAlmostEqual(_density_from_areas(1.0, 0.25, 1024.0, 2048.0), math.sqrt(0.25 * 1024.0 * 2048.0))

    def test_texel_density_set_scales_shell_around_center(self):
        obj = FakeUVObject(
            {
                0: Vec2(0.0, 0.0),
                1: Vec2(0.5, 0.0),
                2: Vec2(0.5, 0.5),
                3: Vec2(0.0, 0.5),
            },
            faces=[FaceRecord(0, [0, 1, 2, 3], [0, 1, 2, 3])],
        )
        obj.uv_to_faces = {0: {0}, 1: {0}, 2: {0}, 3: {0}}
        obj.vertex_positions = {
            0: Vec3(0.0, 0.0, 0.0),
            1: Vec3(1.0, 0.0, 0.0),
            2: Vec3(1.0, 1.0, 0.0),
            3: Vec3(0.0, 1.0, 0.0),
        }

        changed = _scale_islands_to_density([MayaUVIsland(obj, {0, 1, 2, 3})], 1024.0, 1024.0, 1024.0)

        self.assertEqual(changed, 1)
        self.assertEqual(obj.write_count, 1)
        self.assertEqual(obj.uv_positions[0], Vec2(-0.25, -0.25))
        self.assertEqual(obj.uv_positions[1], Vec2(0.75, -0.25))
        self.assertEqual(obj.uv_positions[2], Vec2(0.75, 0.75))
        self.assertEqual(obj.uv_positions[3], Vec2(-0.25, 0.75))

    def test_rectify_distorted_quad_becomes_bbox_rectangle(self):
        obj = build_grid_object(
            1,
            1,
            {
                0: Vec2(0.0, 0.0),
                1: Vec2(1.2, 0.2),
                2: Vec2(-0.1, 1.0),
                3: Vec2(1.1, 1.15),
            },
        )
        island = MayaUVIsland(obj, set(obj.uv_positions))
        options = RectifyOptions(bbox_type="BBOX", distribute="EVEN", unwrap=False)

        self.assertEqual(rectify_island(island, {0, 1, 2, 3}, options), "changed")

        self.assertAlmostEqual(obj.uv_positions[0].y, obj.uv_positions[1].y, places=6)
        self.assertAlmostEqual(obj.uv_positions[2].y, obj.uv_positions[3].y, places=6)
        self.assertAlmostEqual(obj.uv_positions[0].x, obj.uv_positions[2].x, places=6)
        self.assertAlmostEqual(obj.uv_positions[1].x, obj.uv_positions[3].x, places=6)
        self.assertEqual(obj.write_count, 1)

    def test_rectify_two_by_two_boundary_paths_are_straight(self):
        uv_positions = {}
        for row in range(3):
            for column in range(3):
                uv_id = row * 3 + column
                uv_positions[uv_id] = Vec2(column + row * 0.18, row + column * 0.12)
        obj = build_grid_object(2, 2, uv_positions)
        island = MayaUVIsland(obj, set(obj.uv_positions))
        interior_before = obj.uv_positions[4]
        options = RectifyOptions(bbox_type="BBOX", distribute="EVEN", unwrap=False)

        self.assertEqual(rectify_island(island, {0, 2, 6, 8}, options), "changed")

        for row_ids in ([0, 1, 2], [6, 7, 8]):
            row_y = obj.uv_positions[row_ids[0]].y
            for uv_id in row_ids[1:]:
                self.assertAlmostEqual(obj.uv_positions[uv_id].y, row_y, places=6)
        for column_ids in ([0, 3, 6], [2, 5, 8]):
            column_x = obj.uv_positions[column_ids[0]].x
            for uv_id in column_ids[1:]:
                self.assertAlmostEqual(obj.uv_positions[uv_id].x, column_x, places=6)
        self.assertEqual(obj.uv_positions[4], interior_before)

    def test_rectify_three_by_two_boundary_paths_are_straight(self):
        uv_positions = {}
        for row in range(3):
            for column in range(4):
                uv_id = row * 4 + column
                uv_positions[uv_id] = Vec2(column + math.sin(row + column) * 0.11, row + column * 0.09)
        obj = build_grid_object(3, 2, uv_positions)
        island = MayaUVIsland(obj, set(obj.uv_positions))
        options = RectifyOptions(bbox_type="BBOX", distribute="EVEN", unwrap=False)

        self.assertEqual(rectify_island(island, {0, 3, 8, 11}, options), "changed")

        for row_ids in ([0, 1, 2, 3], [8, 9, 10, 11]):
            row_y = obj.uv_positions[row_ids[0]].y
            for uv_id in row_ids[1:]:
                self.assertAlmostEqual(obj.uv_positions[uv_id].y, row_y, places=6)
        for column_ids in ([0, 4, 8], [3, 7, 11]):
            column_x = obj.uv_positions[column_ids[0]].x
            for uv_id in column_ids[1:]:
                self.assertAlmostEqual(obj.uv_positions[uv_id].x, column_x, places=6)

    def test_rectify_distribute_modes_change_boundary_spacing(self):
        vertex_positions = {
            0: Vec3(0.0, 0.0, 0.0),
            1: Vec3(1.0, 0.0, 0.0),
            2: Vec3(3.0, 0.0, 0.0),
            3: Vec3(0.0, 1.0, 0.0),
            4: Vec3(1.0, 1.0, 0.0),
            5: Vec3(3.0, 1.0, 0.0),
        }
        uv_positions = {
            0: Vec2(0.0, 0.0),
            1: Vec2(0.7, 0.15),
            2: Vec2(2.0, 0.0),
            3: Vec2(0.0, 1.0),
            4: Vec2(0.7, 1.15),
            5: Vec2(2.0, 1.0),
        }
        even_obj = build_grid_object(2, 1, uv_positions, vertex_positions)
        geo_obj = build_grid_object(2, 1, uv_positions, vertex_positions)
        none_obj = build_grid_object(2, 1, uv_positions, vertex_positions)
        selected = {0, 2, 3, 5}

        self.assertEqual(rectify_island(MayaUVIsland(even_obj, set(even_obj.uv_positions)), selected, RectifyOptions("BBOX", "EVEN", unwrap=False)), "changed")
        self.assertEqual(rectify_island(MayaUVIsland(geo_obj, set(geo_obj.uv_positions)), selected, RectifyOptions("BBOX", "GEOMETRY", unwrap=False)), "changed")
        self.assertEqual(rectify_island(MayaUVIsland(none_obj, set(none_obj.uv_positions)), selected, RectifyOptions("BBOX", "NONE", unwrap=False)), "changed")

        even_top_mid = even_obj.uv_positions[4].x - even_obj.uv_positions[3].x
        geo_top_mid = geo_obj.uv_positions[4].x - geo_obj.uv_positions[3].x
        none_top_mid = none_obj.uv_positions[4].x - none_obj.uv_positions[3].x
        self.assertLess(geo_top_mid, even_top_mid)
        self.assertLess(geo_top_mid, none_top_mid)
        self.assertLess(none_top_mid, even_top_mid)

    def test_rectify_average_bbox_remaps_boundary(self):
        obj = build_grid_object(
            1,
            1,
            {
                0: Vec2(0.0, 0.0),
                1: Vec2(4.0, 0.0),
                2: Vec2(0.0, 3.0),
                3: Vec2(4.0, 1.0),
            },
        )
        island = MayaUVIsland(obj, set(obj.uv_positions))

        self.assertEqual(rectify_island(island, {0, 1, 2, 3}, RectifyOptions(bbox_type="AVERAGE", distribute="EVEN", unwrap=False)), "changed")

        self.assertAlmostEqual(obj.uv_positions[2].y, 2.0, places=6)
        self.assertAlmostEqual(obj.uv_positions[3].y, 2.0, places=6)
        self.assertAlmostEqual(obj.uv_positions[0].y, 0.0, places=6)
        self.assertAlmostEqual(obj.uv_positions[1].y, 0.0, places=6)

    def test_rectify_unwrap_relaxes_interior_without_moving_boundary(self):
        uv_positions = {}
        for row in range(3):
            for column in range(3):
                uv_id = row * 3 + column
                uv_positions[uv_id] = Vec2(column + row * 0.12, row + column * 0.08)
        uv_positions[4] = Vec2(5.0, 5.0)
        obj = build_grid_object(2, 2, uv_positions)
        island = MayaUVIsland(obj, set(obj.uv_positions))

        self.assertEqual(rectify_island(island, {0, 2, 6, 8}, RectifyOptions(bbox_type="BBOX", distribute="EVEN", unwrap=True)), "changed")

        min_x = min(obj.uv_positions[uv_id].x for uv_id in (0, 2, 6, 8))
        max_x = max(obj.uv_positions[uv_id].x for uv_id in (0, 2, 6, 8))
        min_y = min(obj.uv_positions[uv_id].y for uv_id in (0, 2, 6, 8))
        max_y = max(obj.uv_positions[uv_id].y for uv_id in (0, 2, 6, 8))
        self.assertGreaterEqual(obj.uv_positions[4].x, min_x)
        self.assertLessEqual(obj.uv_positions[4].x, max_x)
        self.assertGreaterEqual(obj.uv_positions[4].y, min_y)
        self.assertLessEqual(obj.uv_positions[4].y, max_y)
        for row_ids in ([0, 1, 2], [6, 7, 8]):
            row_y = obj.uv_positions[row_ids[0]].y
            for uv_id in row_ids[1:]:
                self.assertAlmostEqual(obj.uv_positions[uv_id].y, row_y, places=6)

    def test_rectify_skips_when_less_than_four_reference_uvs(self):
        obj = build_grid_object(1, 1)
        island = MayaUVIsland(obj, set(obj.uv_positions))

        self.assertEqual(rectify_island(island, {0, 1, 2}, RectifyOptions()), "skipped")
        self.assertEqual(obj.write_count, 0)

    def test_rectify_multi_island_only_processes_valid_reference_islands(self):
        obj_a = build_grid_object(1, 1)
        obj_b = build_grid_object(1, 1, {0: Vec2(10.0, 10.0), 1: Vec2(11.0, 10.0), 2: Vec2(10.0, 11.0), 3: Vec2(11.0, 11.0)})
        obj_b.shape = "meshShapeB"

        result = rectify_islands(
            [MayaUVIsland(obj_a, set(obj_a.uv_positions)), MayaUVIsland(obj_b, set(obj_b.uv_positions))],
            {"meshShape": {0, 1, 2, 3}},
            RectifyOptions(bbox_type="BBOX", unwrap=False),
        )

        self.assertEqual(result.valid_islands, 1)
        self.assertEqual(result.skipped_islands, 1)
        self.assertEqual(obj_a.write_count, 0)
        self.assertEqual(obj_b.write_count, 0)

    def test_rectify_uv_split_boundary_does_not_move_other_shell(self):
        obj = FakeUVObject(
            {
                0: Vec2(0.0, 0.0),
                1: Vec2(1.2, 0.2),
                2: Vec2(-0.1, 1.0),
                3: Vec2(1.1, 1.15),
                4: Vec2(2.0, 0.0),
                5: Vec2(3.0, 0.0),
                6: Vec2(2.0, 1.0),
                7: Vec2(3.0, 1.0),
            },
            faces=[
                FaceRecord(0, [0, 1, 3, 2], [0, 1, 3, 2]),
                FaceRecord(1, [1, 4, 5, 3], [4, 5, 7, 6]),
            ],
        )
        obj.vertex_positions = {
            0: Vec3(0.0, 0.0, 0.0),
            1: Vec3(1.0, 0.0, 0.0),
            2: Vec3(0.0, 1.0, 0.0),
            3: Vec3(1.0, 1.0, 0.0),
            4: Vec3(2.0, 0.0, 0.0),
            5: Vec3(2.0, 1.0, 0.0),
        }
        rebuild_fake_topology(obj)
        island = MayaUVIsland(obj, set(obj.uv_positions))
        other_shell_before = {uv_id: obj.uv_positions[uv_id] for uv_id in (4, 5, 6, 7)}

        self.assertEqual(rectify_island(island, {0, 1, 2, 3}, RectifyOptions(bbox_type="BBOX", unwrap=False)), "changed")

        self.assertEqual({uv_id: obj.uv_positions[uv_id] for uv_id in (4, 5, 6, 7)}, other_shell_before)

    def test_gridify_single_distorted_quad_becomes_rectangle(self):
        obj = build_grid_object(
            1,
            1,
            {
                0: Vec2(0.0, 0.0),
                1: Vec2(1.2, 0.2),
                2: Vec2(-0.1, 1.0),
                3: Vec2(1.1, 1.15),
            },
        )
        island = MayaUVIsland(obj, set(obj.uv_positions))

        self.assertEqual(gridify_island(island, ratio_influence=0.0, shape_blend=1.0), "changed")

        face = obj.faces[0]
        points = [obj.uv_positions[uv_id] for uv_id in face.uv_ids]
        self.assertAlmostEqual(points[0].y, points[1].y, places=6)
        self.assertAlmostEqual(points[2].y, points[3].y, places=6)
        self.assertAlmostEqual(points[0].x, points[3].x, places=6)
        self.assertAlmostEqual(points[1].x, points[2].x, places=6)
        self.assertEqual(obj.write_count, 1)

    def test_gridify_two_quad_strip_propagates_grid(self):
        obj = build_grid_object(
            2,
            1,
            {
                0: Vec2(0.0, 0.0),
                1: Vec2(0.9, 0.1),
                2: Vec2(1.9, 0.35),
                3: Vec2(0.0, 1.0),
                4: Vec2(0.95, 1.05),
                5: Vec2(1.8, 1.25),
            },
        )
        island = MayaUVIsland(obj, set(obj.uv_positions))

        self.assertEqual(gridify_island(island, ratio_influence=0.0, shape_blend=1.0), "changed")

        assert_grid_lines(self, obj, 2, 1)
        self.assertLess(obj.uv_positions[0].x, obj.uv_positions[1].x)
        self.assertLess(obj.uv_positions[1].x, obj.uv_positions[2].x)

    def test_gridify_two_by_two_patch_propagates_grid(self):
        uv_positions = {}
        for row in range(3):
            for column in range(3):
                uv_id = row * 3 + column
                uv_positions[uv_id] = Vec2(column + row * 0.12, row + column * 0.08)
        obj = build_grid_object(2, 2, uv_positions)
        island = MayaUVIsland(obj, set(obj.uv_positions))

        self.assertEqual(gridify_island(island, ratio_influence=0.0, shape_blend=1.0), "changed")

        assert_grid_lines(self, obj, 2, 2)

    def test_gridify_three_by_two_patch_propagates_grid(self):
        uv_positions = {}
        for row in range(3):
            for column in range(4):
                uv_id = row * 4 + column
                uv_positions[uv_id] = Vec2(column + math.sin(row + column) * 0.12, row + column * 0.07)
        obj = build_grid_object(3, 2, uv_positions)
        island = MayaUVIsland(obj, set(obj.uv_positions))

        self.assertEqual(gridify_island(island, ratio_influence=0.0, shape_blend=1.0), "changed")

        assert_grid_lines(self, obj, 3, 2)

    def test_gridify_l_shaped_face_subset_stays_inside_patch(self):
        uv_positions = {}
        for row in range(3):
            for column in range(3):
                uv_id = row * 3 + column
                uv_positions[uv_id] = Vec2(column + row * 0.16, row + column * 0.11)
        obj = build_grid_object(2, 2, uv_positions)
        island = MayaUVIsland(obj, set(obj.uv_positions))
        untouched_corner = obj.uv_positions[8]

        self.assertEqual(gridify_island(island, ratio_influence=0.0, shape_blend=1.0, selected_face_ids={0, 1, 2}), "changed")

        self.assertEqual(obj.uv_positions[8], untouched_corner)
        for row_ids in ([0, 1, 2], [3, 4, 5], [6, 7]):
            row_y = obj.uv_positions[row_ids[0]].y
            for uv_id in row_ids[1:]:
                self.assertAlmostEqual(obj.uv_positions[uv_id].y, row_y, places=6)
        for column_ids in ([0, 3, 6], [1, 4, 7], [2, 5]):
            column_x = obj.uv_positions[column_ids[0]].x
            for uv_id in column_ids[1:]:
                self.assertAlmostEqual(obj.uv_positions[uv_id].x, column_x, places=6)

    def test_gridify_uv_split_boundary_does_not_propagate_across_cut(self):
        obj = FakeUVObject(
            {
                0: Vec2(0.0, 0.0),
                1: Vec2(1.2, 0.2),
                2: Vec2(-0.1, 1.0),
                3: Vec2(1.1, 1.15),
                4: Vec2(2.0, 0.0),
                5: Vec2(3.0, 0.0),
                6: Vec2(2.0, 1.0),
                7: Vec2(3.0, 1.0),
            },
            faces=[
                FaceRecord(0, [0, 1, 3, 2], [0, 1, 3, 2]),
                FaceRecord(1, [1, 4, 5, 3], [4, 5, 7, 6]),
            ],
        )
        obj.vertex_positions = {
            0: Vec3(0.0, 0.0, 0.0),
            1: Vec3(1.0, 0.0, 0.0),
            2: Vec3(0.0, 1.0, 0.0),
            3: Vec3(1.0, 1.0, 0.0),
            4: Vec3(2.0, 0.0, 0.0),
            5: Vec3(2.0, 1.0, 0.0),
        }
        rebuild_fake_topology(obj)
        island = MayaUVIsland(obj, set(obj.uv_positions))
        right_shell_before = {uv_id: obj.uv_positions[uv_id] for uv_id in (4, 5, 6, 7)}

        self.assertEqual(gridify_island(island, ratio_influence=0.0, shape_blend=1.0, selected_face_ids={0, 1}), "changed")

        self.assertEqual({uv_id: obj.uv_positions[uv_id] for uv_id in (4, 5, 6, 7)}, right_shell_before)

    def test_gridify_explicit_face_selection_does_not_process_whole_shell(self):
        uv_positions = {}
        for row in range(3):
            for column in range(3):
                uv_id = row * 3 + column
                uv_positions[uv_id] = Vec2(column + row * 0.15, row + column * 0.09)
        obj = build_grid_object(2, 2, uv_positions)
        island = MayaUVIsland(obj, set(obj.uv_positions))
        untouched = {uv_id: obj.uv_positions[uv_id] for uv_id in (2, 5, 6, 7, 8)}

        self.assertEqual(gridify_island(island, ratio_influence=0.0, shape_blend=1.0, selected_face_ids={0}), "changed")

        self.assertEqual({uv_id: obj.uv_positions[uv_id] for uv_id in untouched}, untouched)

    def test_gridify_reversed_neighbor_loop_order_is_matched(self):
        uv_positions = {
            0: Vec2(0.0, 0.0),
            1: Vec2(0.9, 0.1),
            2: Vec2(1.9, 0.35),
            3: Vec2(0.0, 1.0),
            4: Vec2(0.95, 1.05),
            5: Vec2(1.8, 1.25),
        }
        obj = FakeUVObject(
            uv_positions,
            faces=[
                FaceRecord(0, [0, 1, 4, 3], [0, 1, 4, 3]),
                FaceRecord(1, [2, 5, 4, 1], [2, 5, 4, 1]),
            ],
        )
        obj.vertex_positions = {
            0: Vec3(0.0, 0.0, 0.0),
            1: Vec3(1.0, 0.0, 0.0),
            2: Vec3(2.0, 0.0, 0.0),
            3: Vec3(0.0, 1.0, 0.0),
            4: Vec3(1.0, 1.0, 0.0),
            5: Vec3(2.0, 1.0, 0.0),
        }
        rebuild_fake_topology(obj)
        island = MayaUVIsland(obj, set(obj.uv_positions))

        self.assertEqual(gridify_island(island, ratio_influence=0.0, shape_blend=1.0), "changed")

        assert_grid_lines(self, obj, 2, 1)

    def test_gridify_syncs_matching_unselected_uv_copies(self):
        obj = FakeUVObject(
            {
                0: Vec2(0.0, 0.0),
                1: Vec2(1.2, 0.2),
                2: Vec2(-0.1, 1.0),
                3: Vec2(1.1, 1.15),
                4: Vec2(1.2, 0.2),
                5: Vec2(1.1, 1.15),
                6: Vec2(2.0, 0.0),
                7: Vec2(2.0, 1.0),
            },
            faces=[
                FaceRecord(0, [0, 1, 3, 2], [0, 1, 3, 2]),
                FaceRecord(1, [1, 4, 5, 3], [4, 6, 7, 5]),
            ],
        )
        obj.vertex_positions = {
            0: Vec3(0.0, 0.0, 0.0),
            1: Vec3(1.0, 0.0, 0.0),
            2: Vec3(0.0, 1.0, 0.0),
            3: Vec3(1.0, 1.0, 0.0),
            4: Vec3(2.0, 0.0, 0.0),
            5: Vec3(2.0, 1.0, 0.0),
        }
        rebuild_fake_topology(obj)
        island = MayaUVIsland(obj, set(obj.uv_positions))

        self.assertEqual(gridify_island(island, ratio_influence=0.0, shape_blend=1.0, selected_face_ids={0}), "changed")

        self.assertEqual(obj.uv_positions[4], obj.uv_positions[1])
        self.assertEqual(obj.uv_positions[5], obj.uv_positions[3])

    def test_gridify_geometry_ratio_can_force_square_aspect(self):
        obj = build_grid_object(
            1,
            1,
            {
                0: Vec2(0.0, 0.0),
                1: Vec2(2.2, 0.2),
                2: Vec2(-0.1, 1.0),
                3: Vec2(2.0, 1.1),
            },
        )
        island = MayaUVIsland(obj, set(obj.uv_positions))

        self.assertEqual(gridify_island(island, ratio_influence=1.0, shape_blend=1.0), "changed")

        bounds = MayaUVIsland(obj, set(obj.uv_positions)).bounds
        self.assertAlmostEqual(bounds.width, bounds.height, places=6)

    def test_gridify_evenness_changes_strip_spacing(self):
        vertex_positions = {
            0: Vec3(0.0, 0.0, 0.0),
            1: Vec3(1.0, 0.0, 0.0),
            2: Vec3(3.0, 0.0, 0.0),
            3: Vec3(0.0, 1.0, 0.0),
            4: Vec3(1.0, 1.0, 0.0),
            5: Vec3(3.0, 1.0, 0.0),
        }
        uv_positions = {
            0: Vec2(0.0, 0.0),
            1: Vec2(1.0, 0.1),
            2: Vec2(2.0, 0.3),
            3: Vec2(0.0, 1.0),
            4: Vec2(1.0, 1.05),
            5: Vec2(2.0, 1.2),
        }
        even_obj = build_grid_object(2, 1, uv_positions, vertex_positions)
        geometry_obj = build_grid_object(2, 1, uv_positions, vertex_positions)

        self.assertEqual(gridify_island(MayaUVIsland(even_obj, set(even_obj.uv_positions)), 0.0, 1.0), "changed")
        self.assertEqual(gridify_island(MayaUVIsland(geometry_obj, set(geometry_obj.uv_positions)), 0.0, 0.0), "changed")

        even_width = MayaUVIsland(even_obj, set(even_obj.uv_positions)).bounds.width
        geometry_width = MayaUVIsland(geometry_obj, set(geometry_obj.uv_positions)).bounds.width
        self.assertGreater(geometry_width, even_width)

    def test_gridify_skips_non_quad_faces(self):
        obj = FakeUVObject(
            {
                0: Vec2(0.0, 0.0),
                1: Vec2(1.0, 0.0),
                2: Vec2(0.0, 1.0),
            },
            faces=[FaceRecord(0, [0, 1, 2], [0, 1, 2])],
        )
        obj.uv_to_faces = {0: {0}, 1: {0}, 2: {0}}
        island = MayaUVIsland(obj, {0, 1, 2})

        self.assertEqual(gridify_island(island), "skipped")
        self.assertEqual(obj.write_count, 0)

    def test_gridify_operator_runs_normalize_when_enabled(self):
        settings = SimpleNamespace(
            gridify_ratio_influence=0.5,
            gridify_shape_blend=0.0,
            gridify_normalize=True,
            gridify_keep_aspect=True,
        )
        result = SimpleNamespace(quad_islands=1, changed_islands=1, already_rectangular=0)
        manager = SimpleNamespace(islands=[object()], selected_face_ids_by_shape={"meshShape": {0, 1}})

        with patch.object(unwrap_module.Settings, "load", return_value=settings), patch.object(
            unwrap_module.MayaUVIslandManager, "from_selection", return_value=manager
        ), patch.object(unwrap_module, "gridify_islands", return_value=result) as gridify_mock, patch.object(
            unwrap_module.align, "normalize", return_value=True
        ) as normalize:
            self.assertTrue(unwrap_module.gridify())

        self.assertEqual(gridify_mock.call_args.kwargs["selected_face_ids_by_shape"], {"meshShape": {0, 1}})
        normalize.assert_called_once_with(keep_aspect=True)

    def test_rectify_operator_passes_settings_to_core(self):
        settings = SimpleNamespace(
            rectify_bbox_type="BBOX",
            rectify_distribute="EVEN",
            rectify_unwrap_method="CONFORMAL",
            rectify_unwrap=False,
            rectify_stretch=True,
            rectify_pin=False,
        )
        result = SimpleNamespace(valid_islands=1, changed_islands=1, skipped_islands=0)
        manager = SimpleNamespace(islands=[object()], selected_uvs_by_shape={"meshShape": {0, 1, 2, 3}})

        with patch.object(unwrap_module.Settings, "load", return_value=settings), patch.object(
            unwrap_module.MayaUVIslandManager, "from_selection", return_value=manager
        ) as manager_mock, patch.object(unwrap_module, "rectify_islands", return_value=result) as rectify_mock:
            self.assertTrue(unwrap_module.rectify())

        manager_mock.assert_called_once_with(include_all_if_no_components=False)
        options = rectify_mock.call_args.args[2]
        self.assertEqual(rectify_mock.call_args.args[1], {"meshShape": {0, 1, 2, 3}})
        self.assertEqual(options.bbox_type, "BBOX")
        self.assertEqual(options.distribute, "EVEN")
        self.assertEqual(options.unwrap_method, "CONFORMAL")
        self.assertFalse(options.unwrap)
        self.assertTrue(options.stretch)
        self.assertFalse(options.pin)


if __name__ == "__main__":
    unittest.main()
