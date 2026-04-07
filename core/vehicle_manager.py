from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal

from .firmware_plugin import AutoPilotPlugin, FirmwarePlugin, resolve_plugins


@dataclass
class ManagedVehicle:
    vehicle_id: str
    system_id: int
    component_id: int
    link_key: str = ""
    link_name: str = ""
    firmware_name: str = "Generic Firmware"
    plugin_name: str = "Generic AutoPilot"
    mode: str = "UNKNOWN"
    battery_remaining: int = 100
    gps: int = 0
    lat: float | None = None
    lon: float | None = None
    altitude: float | None = None
    heading: float | None = None
    params_total: int = 0
    params_modified: int = 0
    mission_count: int = 0
    auto_route_count: int = 0
    home_set: bool = False
    command_busy: bool = False
    last_command: str = ""
    last_command_at: float | None = None
    pending_commands: list[str] = field(default_factory=list)
    queue_depth: int = 0
    connected: bool = False
    last_seen: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        return {
            "vehicle_id": self.vehicle_id,
            "system_id": self.system_id,
            "component_id": self.component_id,
            "link_key": self.link_key,
            "link_name": self.link_name,
            "firmware_name": self.firmware_name,
            "plugin_name": self.plugin_name,
            "mode": self.mode,
            "battery_remaining": self.battery_remaining,
            "gps": self.gps,
            "lat": self.lat,
            "lon": self.lon,
            "altitude": self.altitude,
            "heading": self.heading,
            "params_total": self.params_total,
            "params_modified": self.params_modified,
            "mission_count": self.mission_count,
            "auto_route_count": self.auto_route_count,
            "home_set": self.home_set,
            "command_busy": self.command_busy,
            "last_command": self.last_command,
            "last_command_at": self.last_command_at,
            "pending_commands": list(self.pending_commands or []),
            "queue_depth": self.queue_depth,
            "connected": self.connected,
            "last_seen": self.last_seen,
        }


class VehicleManager(QObject):
    vehicles_changed = pyqtSignal(list)
    active_vehicle_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vehicles: Dict[str, ManagedVehicle] = {}
        self._active_vehicle_id: Optional[str] = None

    @staticmethod
    def _vehicle_key(system_id: int, component_id: int) -> str:
        return f"{int(system_id)}:{int(component_id)}"

    def update_from_status(
        self,
        status: Dict,
        link_name: str = "",
        plugin_bundle: Optional[Tuple[FirmwarePlugin, AutoPilotPlugin]] = None,
        link_key: str = "",
    ) -> Dict:
        status = dict(status or {})
        system_id = int(status.get("sysid", 1) or 1)
        component_id = int(status.get("compid", 1) or 1)
        vehicle_id = self._vehicle_key(system_id, component_id)
        firmware_plugin, autopilot_plugin = plugin_bundle or resolve_plugins(status, None)

        vehicle = self._vehicles.get(vehicle_id)
        if vehicle is None:
            vehicle = ManagedVehicle(vehicle_id=vehicle_id, system_id=system_id, component_id=component_id)
            self._vehicles[vehicle_id] = vehicle

        vehicle.link_key = str(link_key or vehicle.link_key or "")
        vehicle.link_name = str(link_name or vehicle.link_name or "未命名链路")
        vehicle.firmware_name = firmware_plugin.display_name
        vehicle.plugin_name = autopilot_plugin.display_name
        vehicle.mode = str(status.get("mode", vehicle.mode) or vehicle.mode)
        battery_remaining = status.get("battery_remaining", vehicle.battery_remaining)
        gps_count = status.get("gps", vehicle.gps)
        lat = status.get("lat", vehicle.lat)
        lon = status.get("lon", vehicle.lon)
        altitude = status.get("alt", vehicle.altitude)
        heading = status.get("heading", status.get("yaw", vehicle.heading))
        vehicle.battery_remaining = int(vehicle.battery_remaining if battery_remaining is None else battery_remaining)
        vehicle.gps = int(vehicle.gps if gps_count is None else gps_count)
        vehicle.lat = vehicle.lat if lat is None else float(lat)
        vehicle.lon = vehicle.lon if lon is None else float(lon)
        vehicle.altitude = vehicle.altitude if altitude is None else float(altitude)
        vehicle.heading = vehicle.heading if heading is None else float(heading)
        vehicle.connected = True
        vehicle.last_seen = time.time()

        if self._active_vehicle_id is None:
            self._active_vehicle_id = vehicle_id

        self.vehicles_changed.emit(self.vehicle_summaries())
        if vehicle_id == self._active_vehicle_id:
            self.active_vehicle_changed.emit(vehicle.to_dict())
        return vehicle.to_dict()

    def set_active_vehicle(self, vehicle_id: str) -> Optional[Dict]:
        key = str(vehicle_id or "").strip()
        if key not in self._vehicles:
            return None
        self._active_vehicle_id = key
        payload = self._vehicles[key].to_dict()
        self.active_vehicle_changed.emit(payload)
        return payload

    def vehicle_detail(self, vehicle_id: str) -> Optional[Dict]:
        key = str(vehicle_id or "").strip()
        if key not in self._vehicles:
            return None
        return self._vehicles[key].to_dict()

    def update_vehicle_context(
        self,
        vehicle_id: str,
        *,
        params_total: Optional[int] = None,
        params_modified: Optional[int] = None,
        mission_count: Optional[int] = None,
        auto_route_count: Optional[int] = None,
        home_set: Optional[bool] = None,
    ) -> Optional[Dict]:
        key = str(vehicle_id or "").strip()
        vehicle = self._vehicles.get(key)
        if vehicle is None:
            return None
        if params_total is not None:
            vehicle.params_total = max(0, int(params_total))
        if params_modified is not None:
            vehicle.params_modified = max(0, int(params_modified))
        if mission_count is not None:
            vehicle.mission_count = max(0, int(mission_count))
        if auto_route_count is not None:
            vehicle.auto_route_count = max(0, int(auto_route_count))
        if home_set is not None:
            vehicle.home_set = bool(home_set)
        payload = vehicle.to_dict()
        self.vehicles_changed.emit(self.vehicle_summaries())
        if key == self._active_vehicle_id:
            self.active_vehicle_changed.emit(payload)
        return payload

    def mark_command_state(self, vehicle_id: str, command_name: str, busy: bool) -> Optional[Dict]:
        key = str(vehicle_id or "").strip()
        vehicle = self._vehicles.get(key)
        if vehicle is None:
            return None
        vehicle.command_busy = bool(busy)
        vehicle.last_command = str(command_name or vehicle.last_command or "")
        vehicle.last_command_at = time.time()
        payload = vehicle.to_dict()
        self.vehicles_changed.emit(self.vehicle_summaries())
        if key == self._active_vehicle_id:
            self.active_vehicle_changed.emit(payload)
        return payload

    def set_command_queue(self, vehicle_id: str, commands: list[str]) -> Optional[Dict]:
        key = str(vehicle_id or "").strip()
        vehicle = self._vehicles.get(key)
        if vehicle is None:
            return None
        pending = [str(item or "").strip() for item in (commands or []) if str(item or "").strip()]
        vehicle.pending_commands = pending
        vehicle.queue_depth = len(pending)
        payload = vehicle.to_dict()
        self.vehicles_changed.emit(self.vehicle_summaries())
        if key == self._active_vehicle_id:
            self.active_vehicle_changed.emit(payload)
        return payload

    def enqueue_command(self, vehicle_id: str, command_name: str) -> Optional[Dict]:
        key = str(vehicle_id or "").strip()
        vehicle = self._vehicles.get(key)
        if vehicle is None:
            return None
        pending = list(vehicle.pending_commands or [])
        command_text = str(command_name or "").strip()
        if command_text:
            pending.append(command_text)
        return self.set_command_queue(key, pending)

    def pop_next_command(self, vehicle_id: str) -> Optional[str]:
        key = str(vehicle_id or "").strip()
        vehicle = self._vehicles.get(key)
        if vehicle is None:
            return None
        pending = list(vehicle.pending_commands or [])
        if not pending:
            self.set_command_queue(key, [])
            return None
        next_command = pending.pop(0)
        self.set_command_queue(key, pending)
        return next_command

    def active_vehicle(self) -> Optional[Dict]:
        if self._active_vehicle_id not in self._vehicles:
            return None
        return self._vehicles[self._active_vehicle_id].to_dict()

    def vehicle_summaries(self) -> list[Dict]:
        return [self._vehicles[key].to_dict() for key in sorted(self._vehicles.keys())]

    def mark_all_disconnected(self):
        for vehicle in self._vehicles.values():
            vehicle.connected = False
        self.vehicles_changed.emit(self.vehicle_summaries())
        active = self.active_vehicle()
        if active is not None:
            self.active_vehicle_changed.emit(active)

    def summary_text(self) -> str:
        total = len(self._vehicles)
        if total <= 0:
            return "载具: 0"
        active = self.active_vehicle() or {}
        return f"载具: {total} | 当前 {active.get('vehicle_id', '--')} {active.get('mode', 'UNKNOWN')}"
