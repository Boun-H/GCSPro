import unittest

from core.analyze_service import AnalyzeService
from core.command_router import CommandRouter
from core.health_monitor import HealthMonitor
from core.link_session_service import LinkSessionService
from core.mission_sync_service import MissionSyncService
from core.setup_wizard_service import SetupWizardService
from core.vehicle_context_service import VehicleContextService


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

    def test_vehicle_context_service_restores_vehicle_preferred_snapshot(self):
        service = VehicleContextService()
        service.cache_vehicle_context(
            "1:1",
            param_values={"WPNAV_SPEED": 500},
            home_position={"lat": 39.1, "lon": 116.2},
            waypoints=[{"lat": 39.2, "lon": 116.3, "alt": 100}],
            auto_route_overrides={"T1": {"lat": 39.0, "lon": 116.0}},
            plan_constraints={"min_clearance": 35},
        )
        service.cache_link_context(
            "serial:1",
            param_values={"WPNAV_SPEED": 400},
            home_position={"lat": 38.0, "lon": 115.0},
            waypoints=[{"lat": 38.1, "lon": 115.1, "alt": 80}],
            auto_route_overrides={},
            plan_constraints={},
        )

        restored = service.resolve_link_context("serial:1", active_vehicle_id="1:1", vehicle_link_key="serial:1")
        metrics = service.build_vehicle_metrics(
            "1:1",
            param_values={"A": 1, "B": 2},
            modified_count=1,
            waypoints=[{"lat": 1, "lon": 2}],
            auto_route_count=2,
            home_set=True,
        )

        self.assertEqual(restored["params"]["WPNAV_SPEED"], 500)
        self.assertEqual(restored["mission"]["waypoints"][0]["alt"], 100)
        self.assertEqual(metrics["vehicle_id"], "1:1")
        self.assertEqual(metrics["payload"]["mission_count"], 1)
        self.assertTrue(metrics["payload"]["home_set"])

    def test_link_session_service_builds_recent_link_labels_and_settings_payload(self):
        entry = {"kind": "tcp", "payload": {"host": "127.0.0.1", "port": 5760}, "label": "TCP 127.0.0.1:5760"}

        label = LinkSessionService.build_link_label("serial", {"port": "COM6", "baud": 115200})
        resolved = LinkSessionService.resolve_active_link_context({"key": "tcp:1", "label": "TCP 127.0.0.1:5760"}, "")
        settings_payload = LinkSessionService.build_settings_payload(
            {
                "serial": {"port": "COM7", "baud": 57600},
                "tcp": {"host": "192.168.1.10", "port": 5760},
                "udp": {"host": "0.0.0.0", "port": 14550},
                "auto_reconnect": True,
                "auto_connect": False,
                "map_source": "谷歌卫星",
            }
        )

        self.assertEqual(label, "串口 COM6@115200")
        self.assertEqual(resolved, ("tcp:1", "TCP 127.0.0.1:5760"))
        self.assertEqual(settings_payload["map_source"], "谷歌卫星")
        self.assertTrue(settings_payload["auto_reconnect"])
        self.assertEqual(entry["label"], "TCP 127.0.0.1:5760")

    def test_mission_sync_service_prepares_upload_and_download_summaries(self):
        mission_waypoints = MissionSyncService.build_upload_waypoints(
            [{"lat": 39.1, "lon": 116.2, "alt": 100, "name": "WP1"}],
            [],
            {"lat": 39.0, "lon": 116.0, "alt": 35.0},
        )
        valid, message = MissionSyncService.validate_upload_waypoints(mission_waypoints)
        upload_summary = MissionSyncService.describe_upload(mission_waypoints, visible_count=1)
        download_summary = MissionSyncService.describe_download([
            {"seq": 0, "name": "HOME", "lat": 39.0, "lon": 116.0, "alt": 35.0},
            {"seq": 1, "name": "WP1", "lat": 39.1, "lon": 116.2, "alt": 100.0},
        ])

        self.assertTrue(valid, msg=message)
        self.assertEqual(mission_waypoints[0]["name"], "HOME")
        self.assertTrue(upload_summary["has_home_item"])
        self.assertEqual(upload_summary["display_count"], 1)
        self.assertEqual(download_summary["visible_count"], 1)
        self.assertEqual(download_summary["home_position"]["source"], "mission_wp0")


if __name__ == "__main__":
    unittest.main()
