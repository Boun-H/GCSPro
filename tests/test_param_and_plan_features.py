import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from core.firmware_tools import build_parameter_validation_report
from core.mission.planning_safety import analyze_plan_safety
from ui.param_panel import ParamPanel


class ParamAndPlanFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _find_value_item(self, panel: ParamPanel, name: str):
        for row in range(panel.table.rowCount()):
            item = panel.table.item(row, 0)
            if item is not None and str(item.data(256) or item.text().replace("★ ", "").strip()) == name:
                return panel.table.item(row, 1)
        self.fail(f"parameter row not found: {name}")

    def test_param_panel_can_compare_rollback_and_snapshot(self):
        panel = ParamPanel()
        panel.set_parameters({"BATT_LOW_VOLT": 10.5, "WPNAV_SPEED": 500.0})

        value_item = self._find_value_item(panel, "BATT_LOW_VOLT")
        value_item.setText("11.2")
        panel._on_item_changed(value_item)

        diffs = panel.parameter_diff_rows()
        snapshot = panel.snapshot_payload()

        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0]["name"], "BATT_LOW_VOLT")
        self.assertIn("1 项", panel.diff_summary.text())
        self.assertIn("modified", snapshot)
        self.assertIn("BATT_LOW_VOLT", snapshot["modified"])

        rolled_back = panel.rollback_changes()
        self.assertIn("BATT_LOW_VOLT", rolled_back)
        self.assertEqual(panel.modified_parameters(), {})

    def test_plan_safety_report_detects_terrain_and_no_fly_risks(self):
        report = analyze_plan_safety(
            home={"lat": 39.0, "lon": 116.0, "alt": 35.0},
            waypoints=[
                {"lat": 39.0001, "lon": 116.0001, "alt": 20.0, "terrain_alt": 5.0},
                {"lat": 39.0002, "lon": 116.0002, "alt": 18.0, "terrain_alt": 12.0},
                {"lat": 39.00015, "lon": 116.00015, "alt": 18.0, "terrain_alt": 16.0},
            ],
            geofence={
                "polygons": [
                    {
                        "inclusion": False,
                        "polygon": [
                            {"lat": 39.00005, "lon": 116.00005},
                            {"lat": 39.00025, "lon": 116.00005},
                            {"lat": 39.00025, "lon": 116.00025},
                            {"lat": 39.00005, "lon": 116.00025},
                        ],
                    }
                ]
            },
            min_clearance_m=15.0,
        )

        self.assertLess(report["score"], 100)
        self.assertGreaterEqual(report["issue_count"], 2)
        self.assertIn("禁飞区", report["summary"])
        self.assertIn("地形", "\n".join(report["messages"]))

    def test_firmware_parameter_validation_report_flags_drift(self):
        report = build_parameter_validation_report(
            {"BATT_LOW_VOLT": 10.5, "WPNAV_SPEED": 500.0},
            {"BATT_LOW_VOLT": 11.0, "WPNAV_SPEED": 500.0, "NEW_PARAM": 1.0},
        )

        self.assertEqual(report["changed_count"], 2)
        self.assertIn("BATT_LOW_VOLT", report["changed"])
        self.assertIn("NEW_PARAM", report["changed"])


if __name__ == "__main__":
    unittest.main()
