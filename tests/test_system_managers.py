import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PyQt6.QtCore import QObject, pyqtSignal

from core.fact_panel_controller import FactPanelController
from core.firmware_plugin import ArduPilotAutoPilotPlugin, resolve_plugins
from core.link_manager import MultiLinkManager
from core.mp_core_registry import grouped_features
from core.settings_manager import SettingsManager
from core.vehicle_manager import VehicleManager


class FakeConnectionManager(QObject):
    status_updated = pyqtSignal(dict)
    connection_state_changed = pyqtSignal(str)
    connection_error = pyqtSignal(str)
    mission_progress = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = "disconnected"
        self._thread = object()
        self.reconnect_calls = 0

    @property
    def state(self):
        return self._state

    @property
    def thread(self):
        return self._thread if self._state == "connected" else None

    def is_connected(self):
        return self._state == "connected"

    def connect_serial(self, port: str, baud: int):
        self._state = "connected"
        self.connection_state_changed.emit("connected")
        self.status_updated.emit({"mode": "QGUIDED", "sysid": 1, "compid": 1})

    def connect_tcp(self, ip: str, port: int):
        self._state = "connected"
        self.connection_state_changed.emit("connected")
        self.status_updated.emit({"mode": "AUTO", "sysid": 2, "compid": 1})

    def connect_udp(self, host: str, port: int, mode: str = "udpin"):
        self._state = "connected"
        self.connection_state_changed.emit("connected")
        self.status_updated.emit({"mode": "MANUAL", "sysid": 3, "compid": 1})

    def reconnect_last(self):
        self.reconnect_calls += 1

    def suppress_watchdog(self, suppressed: bool):
        return None

    def disconnect(self, manual: bool = True):
        self._state = "disconnected"
        self.connection_state_changed.emit("disconnected")

    def shutdown(self):
        self.disconnect(manual=True)


class SystemManagerTests(unittest.TestCase):
    def test_vehicle_manager_tracks_active_vehicle(self):
        manager = VehicleManager()
        plugin_bundle = resolve_plugins({"mode": "QGUIDED"}, None)

        summary = manager.update_from_status(
            {
                "sysid": 1,
                "compid": 1,
                "mode": "QGUIDED",
                "battery_remaining": 88,
                "gps": 12,
            },
            link_name="串口 COM6@115200",
            plugin_bundle=plugin_bundle,
        )

        self.assertEqual(summary["vehicle_id"], "1:1")
        self.assertEqual(summary["mode"], "QGUIDED")
        self.assertEqual(summary["plugin_name"], plugin_bundle[1].display_name)
        self.assertEqual(manager.active_vehicle()["vehicle_id"], "1:1")

    def test_vehicle_manager_can_switch_between_multiple_vehicles(self):
        manager = VehicleManager()
        ardupilot_bundle = resolve_plugins({"mode": "QGUIDED"}, None)
        generic_bundle = resolve_plugins({"mode": "MANUAL"}, None)

        manager.update_from_status(
            {"sysid": 1, "compid": 1, "mode": "QGUIDED", "battery_remaining": 88, "gps": 12},
            link_name="串口 COM6@115200",
            plugin_bundle=ardupilot_bundle,
        )
        manager.update_from_status(
            {"sysid": 2, "compid": 1, "mode": "MANUAL", "battery_remaining": 0, "gps": 0},
            link_name="TCP 127.0.0.1:5760",
            plugin_bundle=generic_bundle,
        )

        selected = manager.set_active_vehicle("2:1")
        self.assertEqual(len(manager.vehicle_summaries()), 2)
        self.assertEqual(selected["vehicle_id"], "2:1")
        self.assertEqual(selected["battery_remaining"], 0)
        self.assertEqual(selected["gps"], 0)

    def test_multi_link_manager_tracks_parallel_links(self):
        manager = MultiLinkManager(manager_factory=FakeConnectionManager)

        serial_key = manager.connect_serial("COM6", 115200)
        tcp_key = manager.connect_tcp("127.0.0.1", 5760)
        udp_key = manager.connect_udp("0.0.0.0", 14550)

        self.assertEqual(len(manager.link_summaries()), 3)
        self.assertEqual(manager.active_link_summary()["key"], udp_key)
        manager.set_active_link(serial_key)
        self.assertEqual(manager.active_link_summary()["kind"], "serial")
        manager.disconnect_link(tcp_key)
        self.assertEqual(len(manager.link_summaries()), 2)

    def test_multi_link_manager_emits_active_link_context(self):
        manager = MultiLinkManager(manager_factory=FakeConnectionManager)
        events = []
        manager.status_updated.connect(lambda payload: events.append(payload))

        manager.connect_serial("COM6", 115200)
        latest = manager.active_link_summary()

        self.assertEqual(latest["kind"], "serial")
        self.assertEqual(events[-1]["link_kind"], "serial")
        self.assertEqual(events[-1]["link_key"], latest["key"])

    def test_multi_link_manager_can_resolve_thread_for_specific_link(self):
        manager = MultiLinkManager(manager_factory=FakeConnectionManager)

        serial_key = manager.connect_serial("COM6", 115200)
        tcp_key = manager.connect_tcp("127.0.0.1", 5760)

        self.assertIsNotNone(manager.thread_for_link(serial_key))
        self.assertIsNotNone(manager.thread_for_link(tcp_key))

    def test_vehicle_manager_stores_independent_param_and_mission_context(self):
        manager = VehicleManager()
        plugin_bundle = resolve_plugins({"mode": "QGUIDED"}, None)
        manager.update_from_status(
            {"sysid": 1, "compid": 1, "mode": "QGUIDED", "battery_remaining": 88, "gps": 12},
            link_name="串口 COM6@115200",
            plugin_bundle=plugin_bundle,
        )
        manager.update_from_status(
            {"sysid": 2, "compid": 1, "mode": "AUTO", "battery_remaining": 76, "gps": 10},
            link_name="TCP 127.0.0.1:5760",
            plugin_bundle=plugin_bundle,
        )

        first = manager.update_vehicle_context(
            "1:1",
            params_total=128,
            params_modified=4,
            mission_count=9,
            auto_route_count=2,
            home_set=True,
        )
        second = manager.update_vehicle_context(
            "2:1",
            params_total=64,
            params_modified=1,
            mission_count=3,
            auto_route_count=0,
            home_set=False,
        )

        self.assertEqual(first["params_total"], 128)
        self.assertEqual(first["params_modified"], 4)
        self.assertEqual(first["mission_count"], 9)
        self.assertTrue(first["home_set"])
        self.assertEqual(second["params_total"], 64)
        self.assertEqual(second["mission_count"], 3)
        self.assertFalse(second["home_set"])

    def test_vehicle_manager_tracks_command_busy_per_vehicle(self):
        manager = VehicleManager()
        plugin_bundle = resolve_plugins({"mode": "QGUIDED"}, None)
        manager.update_from_status(
            {"sysid": 1, "compid": 1, "mode": "QGUIDED", "battery_remaining": 88, "gps": 12},
            link_name="串口 COM6@115200",
            plugin_bundle=plugin_bundle,
        )

        busy = manager.mark_command_state("1:1", "arm", True)
        idle = manager.mark_command_state("1:1", "arm", False)
        queued = manager.set_command_queue("1:1", ["vtol_takeoff_30m", "vtol_qrtl"])
        next_command = manager.pop_next_command("1:1")
        remaining = manager.vehicle_detail("1:1")

        self.assertTrue(busy["command_busy"])
        self.assertEqual(busy["last_command"], "arm")
        self.assertFalse(idle["command_busy"])
        self.assertEqual(queued["queue_depth"], 2)
        self.assertEqual(queued["pending_commands"], ["vtol_takeoff_30m", "vtol_qrtl"])
        self.assertEqual(next_command, "vtol_takeoff_30m")
        self.assertEqual(remaining["pending_commands"], ["vtol_qrtl"])
        self.assertEqual(remaining["queue_depth"], 1)

    def test_settings_manager_persists_recent_links(self):
        with TemporaryDirectory() as tmp_dir:
            settings_path = Path(tmp_dir) / "settings.json"
            manager = SettingsManager(str(settings_path))
            manager.update_serial_defaults("COM6", 115200)
            manager.update_tcp_defaults("127.0.0.1", 5760)
            manager.update_udp_defaults("0.0.0.0", 14550)
            manager.set("connections.auto_connect", True, persist=False)
            manager.add_recent_link("serial", "COM6@115200", {"port": "COM6", "baud": 115200})
            manager.save()

            reloaded = SettingsManager(str(settings_path))
            self.assertEqual(reloaded.serial_defaults()["port"], "COM6")
            self.assertEqual(reloaded.tcp_defaults()["host"], "127.0.0.1")
            self.assertEqual(reloaded.udp_defaults()["port"], 14550)
            self.assertTrue(reloaded.get("connections.auto_connect", False))
            self.assertGreaterEqual(len(reloaded.recent_links()), 1)

    def test_settings_manager_persists_video_and_peripheral_preferences(self):
        with TemporaryDirectory() as tmp_dir:
            settings_path = Path(tmp_dir) / "settings.json"
            manager = SettingsManager(str(settings_path))
            manager.update_video_settings("rtsp://127.0.0.1/live", "FrontCam", persist=False)
            manager.update_peripheral_settings(
                {
                    "joystick_enabled": True,
                    "adsb_enabled": True,
                    "rtk_host": "192.168.10.55",
                    "rtk_port": 2201,
                    "plugin_dirs": ["plugins/a", "plugins/b"],
                },
                persist=False,
            )
            manager.save()

            reloaded = SettingsManager(str(settings_path))
            self.assertEqual(reloaded.video_settings()["stream_url"], "rtsp://127.0.0.1/live")
            self.assertEqual(reloaded.video_settings()["camera_name"], "FrontCam")
            self.assertTrue(reloaded.peripheral_settings()["joystick_enabled"])
            self.assertTrue(reloaded.peripheral_settings()["adsb_enabled"])
            self.assertEqual(reloaded.peripheral_settings()["rtk_host"], "192.168.10.55")
            self.assertEqual(reloaded.peripheral_settings()["rtk_port"], 2201)
            self.assertEqual(reloaded.peripheral_settings()["plugin_dirs"], ["plugins/a", "plugins/b"])

    def test_mp_registry_exposes_phase_panels(self):
        groups = grouped_features()

        self.assertIn("Setup", groups)
        self.assertIn("Fly", groups)
        self.assertIn("Analyze", groups)
        self.assertIn("Peripheral", groups)
        self.assertTrue(any(feature.key == "setup.open" for feature in groups["Setup"]))
        self.assertTrue(any(feature.key == "fly.view" for feature in groups["Fly"]))
        self.assertTrue(any(feature.key == "analyze.open" for feature in groups["Analyze"]))
        self.assertTrue(any(feature.key == "peripheral.open" for feature in groups["Peripheral"]))

    def test_fact_panel_controller_groups_and_prioritizes_favorites(self):
        controller = FactPanelController(autopilot_plugin=ArduPilotAutoPilotPlugin())
        rows = controller.build_rows(
            {
                "PSC_ACCZ_P": 0.2,
                "WPNAV_SPEED": 500.0,
                "ARMING_CHECK": 1.0,
            },
            favorites={"WPNAV_SPEED"},
            search_text="",
            group_filter="全部",
        )

        self.assertEqual(rows[0]["name"], "WPNAV_SPEED")
        groups = controller.available_groups([row["name"] for row in rows])
        self.assertIn("WPNAV", groups)
        self.assertIn("PSC", groups)

    def test_fact_panel_controller_persists_favorites_into_settings(self):
        with TemporaryDirectory() as tmp_dir:
            settings_path = Path(tmp_dir) / "settings.json"
            settings = SettingsManager(str(settings_path))
            controller = FactPanelController(
                autopilot_plugin=ArduPilotAutoPilotPlugin(),
                settings_manager=settings,
            )

            controller.toggle_favorite("WPNAV_SPEED")
            reloaded = SettingsManager(str(settings_path))

            self.assertIn("WPNAV_SPEED", controller.favorites())
            self.assertIn("WPNAV_SPEED", reloaded.fact_favorites())

if __name__ == "__main__":
    unittest.main()
