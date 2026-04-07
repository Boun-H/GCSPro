import unittest

from core.mission import MissionController, MissionItem, PlanMasterController


class PlanModelTests(unittest.TestCase):
    def test_mission_item_roundtrip(self):
        item = MissionItem.from_waypoint({
            "seq": 3,
            "command": 16,
            "frame": 3,
            "param1": 1,
            "param2": 2,
            "param3": 3,
            "param4": 4,
            "lat": 31.2,
            "lon": 121.5,
            "alt": 80,
            "type": "WAYPOINT",
            "name": "WP3",
        })
        json_obj = item.to_plan_json()
        restored = MissionItem.from_plan_json(json_obj)
        self.assertEqual(restored.command, 16)
        self.assertEqual(restored.sequence_number, 3)
        self.assertAlmostEqual(restored.params[4], 31.2, places=6)

    def test_mission_controller_exports_qgc_plan_json(self):
        controller = MissionController.from_waypoints([
            {"type": "HOME", "name": "HOME", "seq": 0, "lat": 31.0, "lon": 121.0, "alt": 15},
            {"seq": 1, "lat": 31.1, "lon": 121.1, "alt": 90, "command": 16},
        ])
        plan = controller.to_plan_json()
        self.assertEqual(plan["fileType"], "Plan")
        self.assertIn("mission", plan)
        self.assertEqual(plan["mission"]["plannedHomePosition"][0], 31.0)
        self.assertEqual(len(plan["mission"]["items"]), 1)
        self.assertEqual(plan["mission"]["items"][0]["type"], "SimpleItem")

    def test_import_qgc_plan_json_returns_home_and_items(self):
        plan = {
            "fileType": "Plan",
            "groundStation": "QGroundControl",
            "version": 1,
            "mission": {
                "version": 2,
                "firmwareType": 12,
                "vehicleType": 20,
                "cruiseSpeed": 15,
                "hoverSpeed": 5,
                "plannedHomePosition": [31.0, 121.0, 15.0],
                "items": [
                    {
                        "type": "SimpleItem",
                        "command": 16,
                        "frame": 3,
                        "autoContinue": True,
                        "doJumpId": 1,
                        "params": [0, 0, 0, 0, 31.1, 121.1, 90],
                    }
                ],
            },
            "geoFence": {"version": 2, "circles": [], "polygons": []},
            "rallyPoints": {"version": 2, "points": []},
        }
        imported = PlanMasterController.from_plan_json(plan).to_waypoints(include_home=True)
        self.assertEqual(len(imported), 2)
        self.assertEqual(imported[0]["seq"], 0)
        self.assertEqual(imported[1]["seq"], 1)

    def test_complex_item_extracts_generated_simple_items(self):
        plan = {
            "fileType": "Plan",
            "groundStation": "QGroundControl",
            "version": 1,
            "mission": {
                "version": 2,
                "plannedHomePosition": [31.0, 121.0, 15.0],
                "items": [
                    {
                        "type": "ComplexItem",
                        "complexItemType": "survey",
                        "TransectStyleComplexItem": {
                            "items": [
                                {
                                    "type": "SimpleItem",
                                    "command": 16,
                                    "frame": 3,
                                    "autoContinue": True,
                                    "doJumpId": 7,
                                    "params": [0, 0, 0, 0, 31.2, 121.2, 100],
                                },
                                {
                                    "type": "SimpleItem",
                                    "command": 16,
                                    "frame": 3,
                                    "autoContinue": True,
                                    "doJumpId": 8,
                                    "params": [0, 0, 0, 0, 31.3, 121.3, 110],
                                },
                            ]
                        },
                    }
                ],
            },
            "geoFence": {"version": 2, "circles": [], "polygons": []},
            "rallyPoints": {"version": 2, "points": []},
        }
        controller = MissionController.from_plan_json(plan)
        waypoints = controller.to_waypoints(include_home=True)
        self.assertEqual(len(waypoints), 3)
        self.assertEqual(waypoints[1]["seq"], 1)
        self.assertEqual(waypoints[2]["seq"], 2)
        self.assertAlmostEqual(waypoints[2]["lat"], 31.3, places=6)

    def test_plan_master_writes_plan_structure(self):
        data = PlanMasterController.from_waypoints([
            {"type": "HOME", "name": "HOME", "seq": 0, "lat": 31.0, "lon": 121.0, "alt": 15},
            {"seq": 1, "lat": 31.1, "lon": 121.1, "alt": 100, "command": 16},
        ]).to_plan_json()
        self.assertEqual(data["fileType"], "Plan")
        self.assertEqual(data["mission"]["items"][0]["type"], "SimpleItem")

    def test_plan_master_preserves_geo_fence_and_rally_points(self):
        plan = {
            "fileType": "Plan",
            "groundStation": "QGroundControl",
            "version": 1,
            "mission": {
                "version": 2,
                "plannedHomePosition": [31.0, 121.0, 20.0],
                "items": [],
            },
            "geoFence": {
                "version": 2,
                "circles": [{"center": [31.1, 121.1], "radius": 300.0, "inclusion": True}],
                "polygons": [{"polygon": [[31.2, 121.2], [31.25, 121.25], [31.21, 121.28]], "inclusion": False}],
            },
            "rallyPoints": {
                "version": 2,
                "points": [{"lat": 31.3, "lon": 121.3, "alt": 50.0}],
            },
        }
        controller = PlanMasterController.from_plan_json(plan)
        out = controller.to_plan_json()
        self.assertEqual(len(out["geoFence"]["circles"]), 1)
        self.assertEqual(len(out["geoFence"]["polygons"]), 1)
        self.assertEqual(len(out["rallyPoints"]["points"]), 1)
        self.assertAlmostEqual(out["rallyPoints"]["points"][0]["lat"], 31.3, places=6)

    def test_complex_metadata_waypoints_roundtrip_as_complex_item(self):
        waypoints = [
            {"type": "HOME", "name": "HOME", "seq": 0, "lat": 31.0, "lon": 121.0, "alt": 15},
            {"seq": 1, "lat": 31.11, "lon": 121.11, "alt": 90, "command": 16, "complex_group": 1, "complex_item_type": "survey"},
            {"seq": 2, "lat": 31.12, "lon": 121.12, "alt": 90, "command": 16, "complex_group": 1, "complex_item_type": "survey"},
            {"seq": 3, "lat": 31.2, "lon": 121.2, "alt": 120, "command": 16},
        ]
        controller = PlanMasterController.from_waypoints(waypoints)
        data = controller.to_plan_json()
        self.assertEqual(data["mission"]["items"][0]["type"], "ComplexItem")
        self.assertEqual(data["mission"]["items"][0]["complexItemType"], "survey")
        self.assertEqual(data["mission"]["items"][1]["type"], "SimpleItem")

    def test_plan_master_from_plan_json(self):
        plan = {
            "fileType": "Plan",
            "groundStation": "QGroundControl",
            "version": 1,
            "mission": {
                "version": 2,
                "plannedHomePosition": [31.0, 121.0, 20.0],
                "items": [],
            },
            "geoFence": {"version": 2, "circles": [], "polygons": []},
            "rallyPoints": {"version": 2, "points": []},
        }
        loaded = PlanMasterController.from_plan_json(plan)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.file_type, "Plan")


if __name__ == "__main__":
    unittest.main()
