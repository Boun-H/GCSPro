import unittest

from core.mission import build_upload_waypoints, split_downloaded_mission, validate_upload_waypoints


class MissionTransferTests(unittest.TestCase):
    def test_build_upload_waypoints_assigns_qgc_style_sequences(self):
        visible = [
            {"lat": 31.1001, "lon": 121.1001, "alt": 80, "seq": 99},
            {"lat": 31.1002, "lon": 121.1002, "alt": 90, "seq": 42},
        ]
        home = {"lat": 31.0, "lon": 121.0, "alt": 15.0}

        mission = build_upload_waypoints(visible, [], home)

        self.assertEqual(len(mission), 3)
        self.assertEqual(mission[0]["seq"], 0)
        self.assertEqual(mission[0]["name"], "HOME")
        self.assertEqual(mission[1]["seq"], 1)
        self.assertEqual(mission[2]["seq"], 2)

    def test_split_downloaded_mission_sorts_by_seq_and_strips_home(self):
        downloaded = [
            {"seq": 2, "lat": 31.2, "lon": 121.2, "alt": 100, "command": 16},
            {"seq": 0, "lat": 31.0, "lon": 121.0, "alt": 15, "command": 16, "name": "HOME"},
            {"seq": 1, "lat": 31.1, "lon": 121.1, "alt": 90, "command": 16},
        ]

        _, visible = split_downloaded_mission(downloaded, {"lat": 31.0, "lon": 121.0, "alt": 15}, [])

        self.assertEqual(len(visible), 2)
        self.assertEqual([wp["seq"] for wp in visible], [1, 2])
        self.assertAlmostEqual(visible[0]["lat"], 31.1, places=6)
        self.assertAlmostEqual(visible[1]["lat"], 31.2, places=6)

    def test_split_downloaded_mission_uses_home_coordinate_fallback(self):
        downloaded = [
            {"seq": 9, "lat": 31.0, "lon": 121.0, "alt": 15, "command": 16},
            {"seq": 10, "lat": 31.3, "lon": 121.3, "alt": 120, "command": 16},
        ]

        _, visible = split_downloaded_mission(downloaded, {"lat": 31.0, "lon": 121.0, "alt": 15}, [])

        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0]["seq"], 1)
        self.assertAlmostEqual(visible[0]["lat"], 31.3, places=6)

    def test_validate_upload_waypoints_requires_home_and_unique_seq(self):
        valid, message = validate_upload_waypoints([
            {"seq": 1, "lat": 31.1, "lon": 121.1, "alt": 80, "command": 16},
        ])
        self.assertFalse(valid)
        self.assertIn("HOME", message)

        valid, message = validate_upload_waypoints([
            {"seq": 0, "name": "HOME", "lat": 31.0, "lon": 121.0, "alt": 15, "command": 16},
            {"seq": 1, "lat": 31.1, "lon": 121.1, "alt": 80, "command": 16},
            {"seq": 1, "lat": 31.2, "lon": 121.2, "alt": 90, "command": 16},
        ])
        self.assertFalse(valid)
        self.assertIn("重复", message)

    def test_build_upload_waypoints_sanitizes_unsupported_command(self):
        visible = [
            {"lat": 31.1001, "lon": 121.1001, "alt": 80, "command": 5001, "type": "WAYPOINT"},
        ]
        home = {"lat": 31.0, "lon": 121.0, "alt": 15.0}

        mission = build_upload_waypoints(visible, [], home)
        valid, message = validate_upload_waypoints(mission)

        self.assertEqual(mission[1]["command"], 16)
        self.assertTrue(valid, message)


if __name__ == "__main__":
    unittest.main()
