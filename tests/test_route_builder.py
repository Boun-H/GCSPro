import unittest

from core.mission import build_auto_route_items


class RouteBuilderTests(unittest.TestCase):
    def test_without_home_returns_empty_route(self):
        result = build_auto_route_items(None, [], {})
        self.assertEqual(result.route_items, [])
        self.assertIn("纯任务航点直连模式", result.summary)

    def test_with_home_keeps_direct_mode_no_auto_points(self):
        home = {"lat": 31.20001, "lon": 121.50002, "alt": 20.0}
        mission = [{"type": "WAYPOINT", "lat": 31.3, "lon": 121.6, "alt": 120.0}]
        result = build_auto_route_items(home, mission, {})
        self.assertEqual(result.route_items, [])
        self.assertIn("0(H点)、1~1", result.summary)

    def test_with_home_and_empty_mission_returns_guidance(self):
        home = {"lat": 30.0, "lon": 120.0, "alt": 10.0}
        result = build_auto_route_items(home, [], {"t1_alt": 120.0})
        self.assertEqual(result.route_items, [])
        self.assertIn("请先添加任务航点", result.summary)


if __name__ == "__main__":
    unittest.main()
