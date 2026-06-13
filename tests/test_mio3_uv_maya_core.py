import math
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mio3_uv_maya.core.mathutils import Bounds2D, Vec2, Vec3, polygon_area
from mio3_uv_maya.core.mesh import FaceRecord, MayaUVIsland, MayaUVIslandManager, MayaUVObject
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
import mio3_uv_maya.operators.arrange as arrange_module
import mio3_uv_maya.operators.base as base_module


class FakeUVObject:
    shape = "meshShape"

    def __init__(self, positions, faces=None):
        self.uv_positions = dict(positions)
        self.faces = faces or []
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
    def __init__(self, selection=None):
        self.selection = selection or []
        self.calls = []

    def ls(self, **kwargs):
        self.calls.append(("ls", dict(kwargs)))
        return list(self.selection)

    def polyMergeUV(self, **kwargs):
        self.calls.append(("polyMergeUV", dict(kwargs)))

    def polyMapSewMove(self, **kwargs):
        self.calls.append(("polyMapSewMove", dict(kwargs)))


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
        fake_cmds = FakeNativeCmds(["meshShape.map[0]", "meshShape.map[1]"])
        with patch.object(arrange_module, "cmds", return_value=fake_cmds):
            self.assertTrue(arrange_module.merge(0.0025))

        self.assertEqual(
            fake_cmds.calls,
            [
                ("ls", {"sl": True, "fl": True}),
                ("polyMergeUV", {"distance": 0.0025, "constructionHistory": False}),
            ],
        )

    def test_stitch_uses_maya_native_poly_map_sew_move(self):
        fake_cmds = FakeNativeCmds(["meshShape.e[4]"])
        with patch.object(arrange_module, "cmds", return_value=fake_cmds):
            self.assertTrue(arrange_module.stitch())

        self.assertEqual(
            fake_cmds.calls,
            [
                ("ls", {"sl": True, "fl": True}),
                ("polyMapSewMove", {"constructionHistory": False}),
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


if __name__ == "__main__":
    unittest.main()
