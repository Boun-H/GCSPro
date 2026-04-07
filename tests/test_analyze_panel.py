import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.analyze_panel import AnalyzePanel


class AnalyzePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_chart_cards_and_trend_text_update(self):
        panel = AnalyzePanel()

        self.assertTrue(panel.inspector_text.isHidden())
        self.assertIn("展开", panel.btn_toggle_inspector.text())

        panel.set_status_payload({"mode": "AUTO", "battery_remaining": 91, "alt": 20.0, "vel": 8.5, "gps": 12, "volt": 11.6})
        panel.set_status_payload({"mode": "AUTO", "battery_remaining": 84, "alt": 36.0, "vel": 12.2, "gps": 13, "volt": 11.4})

        panel.field_checks["battery"].setChecked(False)
        panel.zoom_combo.setCurrentText("最近 5 条")
        csv_text = panel.export_chart_csv()

        self.assertIn("84%", panel._chart_cards["battery"].text())
        self.assertIn("趋势", panel.chart_summary.text())
        self.assertIn("电池", panel.chart_text.toPlainText())
        self.assertTrue(any(ch in panel.chart_text.toPlainText() for ch in "▁▂▃▄▅▆▇█"))
        self.assertIn("timestamp,battery,alt,vel,gps", csv_text)
        self.assertEqual(panel.chart_widget.max_points, 5)
        self.assertNotIn("battery", panel.chart_widget.visible_series_names())
        self.assertIn("最近更新", panel.updated_at.text())
        self.assertIn("自动飞行报告", panel.flight_report_text.toPlainText())
        self.assertIn("最大高度", panel.flight_report_text.toPlainText())

if __name__ == "__main__":
    unittest.main()
