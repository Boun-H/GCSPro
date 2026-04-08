import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from ui.peripheral_panel import PeripheralPanel


class PeripheralPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_panel_uses_larger_readable_layout(self):
        panel = PeripheralPanel()

        self.assertGreaterEqual(panel.minimumWidth(), 700)
        self.assertGreaterEqual(panel.minimumHeight(), 620)

    def test_set_values_updates_summary_and_recent_update(self):
        panel = PeripheralPanel()
        panel.set_values(
            {
                "joystick_enabled": True,
                "adsb_enabled": False,
                "video_stream_url": "rtsp://127.0.0.1/live",
                "camera_name": "FrontCam",
                "plugin_dirs": ["plugins/a"],
                "rtk_host": "192.168.10.2",
                "rtk_port": 2201,
            }
        )

        self.assertIn("Joystick", panel.summary_banner.text())
        self.assertIn("最近更新", panel.updated_at.text())
        self.assertIn("快捷操作", panel.quick_actions_summary.text())


if __name__ == "__main__":
    unittest.main()
