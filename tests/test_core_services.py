import time
import unittest

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from core.analyze_service import AnalyzeService
from core.command_router import CommandRouter
from core.connection_controller import ConnectionController
from core.connection_manager import ConnectionManager
from core.health_monitor import HealthMonitor
from core.link_session_service import LinkSessionService
from core.mission_sync_service import MissionSyncService
from core.mission_transfer_controller import MissionTransferController
from core.notification_controller import NotificationController
from core.setup_wizard_service import SetupWizardService
from core.telemetry_status_controller import TelemetryStatusController
from core.vehicle_context_service import VehicleContextService


class _DummyLinkThread(QObject):
    status_updated = pyqtSignal(dict)
    mission_progress = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop_thread(self):
        self.stopped = True


class CoreServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])

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

        service.ingest_status({"mode": "QGUIDED", "battery_remaining": 91, "alt": 20.0, "vel": 8.5, "gps": 12, "volt": 11.6}, timestamp="10:00:00")
        report = service.ingest_status({"mode": "AUTO", "battery_remaining": 24, "alt": 36.0, "vel": 12.2, "gps": 5, "volt": 11.4}, timestamp="10:00:05")
        chart_text = service.build_chart_text(["alt", "vel", "gps"], 5)
        csv_text = service.export_csv_text()
        flight_report = service.build_flight_report()

        self.assertEqual(service.history()["battery"][-1], 24.0)
        self.assertIn("高度趋势", chart_text)
        self.assertIn("CSV 导出", chart_text)
        self.assertIn("timestamp,battery,alt,vel,gps", csv_text)
        self.assertIn("模式 AUTO", report["chart_summary"])
        self.assertIn("自动飞行报告", flight_report)
        self.assertIn("最大高度", flight_report)
        self.assertIn("模式切换", flight_report)

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
        verify_pass = MissionSyncService().verify_roundtrip(
            [{"lat": 39.1, "lon": 116.2, "alt": 100, "name": "WP1"}],
            [
                {"seq": 0, "name": "HOME", "lat": 39.0, "lon": 116.0, "alt": 35.0},
                {"seq": 1, "name": "WP1", "lat": 39.1, "lon": 116.2, "alt": 100.0},
            ],
            home_position={"lat": 39.0, "lon": 116.0, "alt": 35.0},
            auto_route_items=[],
        )
        verify_fail = MissionSyncService().verify_roundtrip(
            [{"lat": 39.1, "lon": 116.2, "alt": 100, "name": "WP1"}],
            [
                {"seq": 0, "name": "HOME", "lat": 39.0, "lon": 116.0, "alt": 35.0},
                {"seq": 1, "name": "WP1", "lat": 39.15, "lon": 116.2, "alt": 120.0},
            ],
            home_position={"lat": 39.0, "lon": 116.0, "alt": 35.0},
            auto_route_items=[],
        )

        self.assertTrue(valid, msg=message)
        self.assertEqual(mission_waypoints[0]["name"], "HOME")
        self.assertTrue(upload_summary["has_home_item"])
        self.assertEqual(upload_summary["display_count"], 1)
        self.assertEqual(download_summary["visible_count"], 1)
        self.assertEqual(download_summary["home_position"]["source"], "mission_wp0")
        self.assertTrue(verify_pass["matched"])
        self.assertIn("校验通过", verify_pass["summary"])
        self.assertFalse(verify_fail["matched"])
        self.assertGreaterEqual(verify_fail["mismatch_count"], 1)

    def test_connection_controller_plans_dialog_submission(self):
        controller = ConnectionController()

        serial_plan = controller.plan_dialog_submission(0, {"port": "COM6", "baud": "115200"})
        udp_plan = controller.plan_dialog_submission(2, {"host": "", "port": "14550"})
        blocked_plan = controller.plan_dialog_submission(0, {"port": "", "baud": "115200"})

        self.assertTrue(serial_plan["ok"])
        self.assertEqual(serial_plan["kind"], "serial")
        self.assertEqual(serial_plan["label"], "串口 COM6@115200")
        self.assertTrue(udp_plan["ok"])
        self.assertEqual(udp_plan["payload"]["host"], "0.0.0.0")
        self.assertFalse(blocked_plan["ok"])
        self.assertIn("未检测到串口", blocked_plan["title"])

    def test_mission_transfer_controller_manages_progress_state(self):
        controller = MissionTransferController()

        start = controller.begin("upload", "串口 COM6@115200", total=3)
        progress = controller.format_progress_event(
            {
                "operation": "upload",
                "current": 1,
                "total": 3,
                "percent": 33,
                "message": "正在发送航点",
                "link_label": "串口 COM6@115200",
                "active": True,
            }
        )
        success = controller.finish_success("download", "TCP 127.0.0.1:5760", current=2, total=2)
        failure = controller.finish_failure("upload")

        self.assertTrue(start["active"])
        self.assertIn("准备通过 串口 COM6@115200 上传航线", start["message"])
        self.assertIn("[串口 COM6@115200]", progress["message"])
        self.assertEqual(success["percent"], 100)
        self.assertFalse(success["active"])
        self.assertEqual(failure["status_text"], "上传失败")

    def test_notification_and_telemetry_controllers_build_ui_payloads(self):
        notice = NotificationController.build_notice("上传成功", "任务已同步")
        error_notice = NotificationController.connection_error_notice("连接中断，自动重连中")
        connection_view = TelemetryStatusController.connection_view("connected")
        chip_tones = TelemetryStatusController.chip_tones({"battery_remaining": 22, "gps": 5, "volt": 10.4})
        labels = TelemetryStatusController.telemetry_labels({"battery_remaining": 88, "alt": 120.5, "vel": 12.3, "mode": "AUTO", "gps": 13, "volt": 11.7})

        self.assertEqual(notice["level"], "ok")
        self.assertEqual(error_notice["title"], "连接状态")
        self.assertEqual(connection_view["tone"], "ok")
        self.assertEqual(chip_tones["battery"], "danger")
        self.assertIn("高度: 120.5m", labels["altitude"])
        self.assertIn("GPS: 13 颗", labels["gps"])

    def test_connection_manager_connect_returns_without_blocking_ui(self):
        manager = ConnectionManager()
        thread = _DummyLinkThread()

        started_at = time.perf_counter()
        manager._connect(lambda: (time.sleep(0.35), thread)[1])
        elapsed = time.perf_counter() - started_at

        deadline = time.time() + 1.0
        while manager.thread is None and time.time() < deadline:
            self.qt_app.processEvents()
            time.sleep(0.01)

        self.assertLess(elapsed, 0.2)
        self.assertIs(manager.thread, thread)
        self.assertEqual(manager.state, "connected")
        self.assertTrue(thread.started)


if __name__ == "__main__":
    unittest.main()
