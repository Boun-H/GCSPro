import unittest

from core.analyze_service import AnalyzeService
from core.command_router import CommandRouter
from core.health_monitor import HealthMonitor
from core.setup_wizard_service import SetupWizardService


class CoreServiceTests(unittest.TestCase):
    def test_setup_wizard_service_reports_progress_and_next_step(self):
        report = SetupWizardService.evaluate(
            {
                "firmware_name": "ArduPilot Firmware",
                "gps": 12,
                "battery_remaining": 82,
                "volt": 11.7,
                "params_total": 180,
                "mission_count": 0,
                "home_set": False,
            }
        )

        self.assertEqual(report["completed"], 4)
        self.assertIn("Safety", report["next_step"])
        self.assertTrue(any(step["key"] == "sensors" and step["done"] for step in report["steps"]))
        self.assertIn("校准进度", report["summary_text"])

    def test_health_monitor_builds_alerts_and_mission_text(self):
        report = HealthMonitor.evaluate(
            {
                "mode": "AUTO",
                "battery_remaining": 18,
                "gps": 4,
                "vel": 15.3,
                "alt": 120.0,
            },
            connection_state="链路异常 / 高延迟",
            manual_alert_text="姿态波动",
            mission_count=7,
        )

        self.assertIn("低电", report["issues"])
        self.assertIn("链路异常", report["issues"])
        self.assertIn("QRTL", " ".join(report["suggestions"]))
        self.assertEqual(report["suggestion_tone"], "danger")
        self.assertIn("AUTO 执行中", report["mission_text"])
        self.assertIn("7 点", report["mission_text"])

    def test_analyze_service_tracks_history_and_exports_csv(self):
        service = AnalyzeService(history_limit=5)

        service.ingest_status({"mode": "AUTO", "battery_remaining": 91, "alt": 20.0, "vel": 8.5, "gps": 12, "volt": 11.6}, timestamp="10:00:00")
        report = service.ingest_status({"mode": "AUTO", "battery_remaining": 84, "alt": 36.0, "vel": 12.2, "gps": 13, "volt": 11.4}, timestamp="10:00:05")
        chart_text = service.build_chart_text(["alt", "vel", "gps"], 5)
        csv_text = service.export_csv_text()

        self.assertEqual(service.history()["battery"][-1], 84.0)
        self.assertIn("高度趋势", chart_text)
        self.assertIn("CSV 导出", chart_text)
        self.assertIn("timestamp,battery,alt,vel,gps", csv_text)
        self.assertIn("模式 AUTO", report["chart_summary"])

    def test_command_router_centralizes_flight_command_metadata(self):
        confirm = CommandRouter.confirmation_for("vtol_qrtl")
        requirement = CommandRouter.mode_requirement("vtol_takeoff_30m")

        self.assertEqual(CommandRouter.display_name("vtol_qrtl"), "QRTL")
        self.assertEqual(CommandRouter.guided_target_mode("guided_hold"), "QLOITER")
        self.assertIn("垂直返航", confirm["title"])
        self.assertEqual(requirement["target_mode"], "QGUIDED")
        self.assertIn("QLOITER", requirement["fallback_modes"])


if __name__ == "__main__":
    unittest.main()
