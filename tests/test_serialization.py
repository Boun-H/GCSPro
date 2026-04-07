import tempfile
import unittest
from pathlib import Path

from core.mission import (
    MAV_CMD_NAV_RETURN_TO_LAUNCH,
    filter_valid_waypoints,
    import_from_kml,
    import_from_waypoints,
    preprocess_imported_waypoints,
    split_imported_route_points,
)
from core.mission.serialization import export_to_kml, export_to_waypoints


class SerializationTests(unittest.TestCase):
    def test_preprocess_converts_rtl_to_home_waypoint(self):
        home = {"lat": 31.2, "lon": 121.5, "alt": 15.0}
        raw = [{"command": MAV_CMD_NAV_RETURN_TO_LAUNCH, "type": "WAYPOINT"}]
        processed = preprocess_imported_waypoints(raw, home)
        self.assertEqual(len(processed), 1)
        self.assertEqual(processed[0]["name"], "RTL")
        self.assertAlmostEqual(processed[0]["lat"], home["lat"], places=6)

    def test_split_imported_route_points_extracts_home_and_overrides(self):
        imported = [
            {"name": "HOME", "type": "HOME", "seq": 0, "lat": 31.1, "lon": 121.1, "alt": 15},
            {"name": "T1", "type": "VTOL_TAKEOFF", "lat": 31.1, "lon": 121.1, "alt": 40},
            {"name": "T2", "type": "WAYPOINT", "lat": 31.2, "lon": 121.2, "alt": 90, "loiter_radius": 80, "loiter_time": 20},
            {"name": "M1", "type": "WAYPOINT", "lat": 31.3, "lon": 121.3, "alt": 100},
        ]
        home, overrides, mission = split_imported_route_points(imported)
        self.assertIsNotNone(home)
        self.assertEqual(len(mission), 1)
        self.assertIn("t1_alt", overrides)
        self.assertIn("t2_lat", overrides)

    def test_export_import_kml(self):
        waypoints = [
            {"name": "W1", "type": "WAYPOINT", "lat": 31.0, "lon": 121.0, "alt": 100},
            {"name": "W2", "type": "WAYPOINT", "lat": 31.1, "lon": 121.1, "alt": 120},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            kml_path = temp_path / "route.kml"

            export_to_kml(str(kml_path), waypoints)
            kml_result = import_from_kml(str(kml_path))

            self.assertEqual(len(kml_result), 2)

    def test_export_import_waypoints_format(self):
        waypoints = [
            {"name": "HOME", "type": "HOME", "seq": 0, "lat": 31.0, "lon": 121.0, "alt": 15},
            {"name": "W1", "type": "WAYPOINT", "seq": 1, "lat": 31.1, "lon": 121.1, "alt": 100, "hold_time": 6},
            {"name": "W2", "type": "WAYPOINT", "seq": 2, "lat": 31.2, "lon": 121.2, "alt": 120, "hold_time": 3},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            wpl_path = temp_path / "route.waypoints"
            export_to_waypoints(str(wpl_path), waypoints)
            result = import_from_waypoints(str(wpl_path))

        self.assertGreaterEqual(len(result), 2)
        self.assertAlmostEqual(result[1]["lat"], 31.1, places=6)
        self.assertAlmostEqual(float(result[1].get("hold_time", 0.0)), 6.0, places=3)

    def test_filter_valid_waypoints_counts_invalid_entries(self):
        mixed = [
            {"type": "WAYPOINT", "lat": 31.0, "lon": 121.0, "alt": 100},
            {"type": "WAYPOINT", "lat": 999.0, "lon": 121.0, "alt": 100},
        ]
        valid, invalid_count = filter_valid_waypoints(mixed)
        self.assertEqual(len(valid), 1)
        self.assertEqual(invalid_count, 1)


if __name__ == "__main__":
    unittest.main()
