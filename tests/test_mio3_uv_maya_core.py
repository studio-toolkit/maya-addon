import math
import unittest
from types import SimpleNamespace

from mio3_uv_maya.core.mathutils import Bounds2D, Vec2, polygon_area
from mio3_uv_maya.core.mesh import FaceRecord, MayaUVIsland, MayaUVIslandManager, MayaUVObject
from mio3_uv_maya.operators.align import (
    _align_edge_groups,
    _align_selected_components,
    _align_shells,
    _has_node_component_selection,
)
from mio3_uv_maya.operators import all_actions


class FakeUVObject:
    shape = "meshShape"

    def __init__(self, positions, faces=None):
        self.uv_positions = dict(positions)
        self.faces = faces or []

    def set_uv_positions(self, updates):
        self.uv_positions.update(updates)


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


if __name__ == "__main__":
    unittest.main()

