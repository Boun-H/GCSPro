import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.fly_view_panel import FlyViewPanel


class FlyViewPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_panel_uses_larger_readable_layout(self):
        panel = FlyViewPanel()

        self.assertGreaterEqual(panel.minimumWidth(), 760)
        self.assertGreaterEqual(panel.minimumHeight(), 620)
        self.assertTrue(panel.body_scroll.widgetResizable())

    def test_set_status_payload_updates_metric_cards(self):
        panel = FlyViewPanel()

        self.assertTrue(panel.telemetry_json.isHidden())
        self.assertIn("展开", panel.btn_toggle_json.text())

        panel.set_status_payload(
            {
                "mode": "AUTO",
                "battery_remaining": 32,
                "gps": 10,
                "alt": 84.6,
                "vel": 17.2,
                "lat": 39.1234567,
                "lon": 116.1234567,
                "volt": 11.31,
            }
        )

        self.assertIn("32%", panel._metric_cards["battery"].text())
        self.assertIn("10", panel._metric_cards["gps"].text())
        self.assertIn("84.6", panel._metric_cards["flight"].text())
        self.assertIn("最近更新", panel.updated_at.text())

    def test_copy_snapshot_button_preserves_json_preview(self):
        panel = FlyViewPanel()
        panel.set_status_payload({"mode": "QGUIDED", "battery_remaining": 88, "gps": 12})

        text = panel.telemetry_json.toPlainText()

        self.assertIn('"mode": "QGUIDED"', text)
        self.assertIn('"battery": 88', text)

    def test_alert_suggestions_escalate_for_low_battery_gps_and_link(self):
        panel = FlyViewPanel()
        panel.set_connection_state("链路异常 / 高延迟")
        panel.set_status_payload({"mode": "AUTO", "battery_remaining": 16, "gps": 4, "alt": 120.0, "vel": 21.0})

        self.assertIn("低电", panel.alert_status.text())
        self.assertIn("QRTL", panel.action_suggestions.text())
        self.assertIn("GPS", panel.action_suggestions.text())


if __name__ == "__main__":
    unittest.main()
