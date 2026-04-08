import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.setup_panel import VehicleSetupPanel


class VehicleSetupPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_open_section_switches_tab_and_nav_state(self):
        panel = VehicleSetupPanel()

        panel.open_section("power")

        self.assertEqual(panel.tabs.tabText(panel.tabs.currentIndex()), "Power")
        self.assertEqual(panel._nav_buttons["power"].property("active"), "true")

    def test_setup_panel_uses_large_readable_layout(self):
        panel = VehicleSetupPanel()

        self.assertGreaterEqual(panel.minimumWidth(), 720)
        self.assertTrue(panel.tabs.tabBar().isHidden())
        self.assertGreaterEqual(len(panel._nav_buttons), 8)

    def test_set_vehicle_updates_overview_and_section_text(self):
        panel = VehicleSetupPanel()

        panel.set_vehicle(
            {
                "vehicle_id": "7:1",
                "mode": "AUTO",
                "battery_remaining": 38,
                "gps": 11,
                "volt": 11.42,
                "firmware_name": "ArduPilot Firmware",
                "plugin_name": "ArduPilot AutoPilot",
                "link_name": "COM7@115200",
                "queue_depth": 2,
                "mission_count": 9,
                "params_total": 152,
                "home_set": True,
            }
        )

        self.assertIn("载具 7:1", panel.overview_banner.text())
        self.assertIn("38%", panel._overview_cards["battery"].text())
        self.assertIn("COM7@115200", panel._section_labels["summary"].text())
        self.assertIn("ArduPilot Firmware", panel._section_hints["firmware"].text())
        self.assertIn("最近更新", panel.updated_at.text())
        self.assertIn("快捷操作", panel.quick_actions_summary.text())
    def test_calibration_wizard_progress_updates_from_vehicle_state(self):
        panel = VehicleSetupPanel()

        panel.set_vehicle(
            {
                "vehicle_id": "9:1",
                "mode": "QGUIDED",
                "battery_remaining": 86,
                "gps": 14,
                "volt": 11.8,
                "firmware_name": "ArduPilot Firmware",
                "plugin_name": "ArduPilot AutoPilot",
                "link_name": "UDP 14550",
                "queue_depth": 0,
                "mission_count": 6,
                "params_total": 188,
                "home_set": True,
            }
        )
        panel.open_section("wizard")

        self.assertEqual(panel.tabs.tabText(panel.tabs.currentIndex()), "Calibration Wizard")
        self.assertGreaterEqual(panel.wizard_progress.value(), 60)
        self.assertIn("已完成", panel._wizard_steps["sensors"].text())
        self.assertIn("下一步", panel.wizard_summary.text())


if __name__ == "__main__":
    unittest.main()
