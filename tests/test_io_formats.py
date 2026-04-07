import tempfile
import unittest
from pathlib import Path

from core.mission import (
    detect_format_from_path,
    export_mission_bundle,
    import_mission_bundle,
    normalize_format,
)


class MissionIOFormatsTests(unittest.TestCase):
    def test_normalize_format_alias(self):
        self.assertEqual(normalize_format("waypoints"), "waypoints")
        self.assertEqual(normalize_format("kml"), "kml")
        self.assertEqual(normalize_format("unknown"), "waypoints")

    def test_detect_format_from_path(self):
        self.assertEqual(detect_format_from_path("demo.waypoints"), "waypoints")
        self.assertEqual(detect_format_from_path("demo.kml"), "kml")
        self.assertEqual(detect_format_from_path("demo.unknown"), "waypoints")

    def test_export_import_bundle_roundtrip_waypoints(self):
        waypoints = [
            {"name": "HOME", "type": "HOME", "seq": 0, "lat": 31.0, "lon": 121.0, "alt": 15},
            {"name": "W1", "type": "WAYPOINT", "seq": 1, "lat": 31.1, "lon": 121.1, "alt": 100},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "route.waypoints"
            export_mission_bundle(str(file_path), "waypoints", waypoints)
            imported = import_mission_bundle(str(file_path), "waypoints")

        self.assertGreaterEqual(len(imported), 2)

if __name__ == "__main__":
    unittest.main()
