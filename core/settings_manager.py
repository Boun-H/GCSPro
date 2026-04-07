from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional


_DEFAULT_SETTINGS: Dict[str, Any] = {
    "connections": {
        "serial": {"port": "", "baud": 115200},
        "tcp": {"host": "127.0.0.1", "port": 5760},
        "udp": {"host": "0.0.0.0", "port": 14550},
        "recent_links": [],
        "auto_reconnect": True,
        "auto_connect": False,
    },
    "ui": {
        "map_source": "谷歌卫星",
    },
    "params": {
        "favorites": [],
    },
    "video": {
        "stream_url": "",
        "camera_name": "PayloadCam",
    },
    "peripherals": {
        "joystick_enabled": False,
        "adsb_enabled": False,
        "rtk_host": "127.0.0.1",
        "rtk_port": 2101,
        "plugin_dirs": [],
    },
}


class SettingsManager:
    """轻量版 QGC SettingsManager：集中保存通信链路与 UI 偏好。"""

    def __init__(self, file_path: Optional[str] = None):
        default_path = Path(__file__).resolve().parent.parent / "logs" / "config" / "settings.json"
        self.file_path = Path(file_path or default_path)
        self._data: Dict[str, Any] = deepcopy(_DEFAULT_SETTINGS)
        self.load()

    @staticmethod
    def _merge_dict(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
        for key, value in (incoming or {}).items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                SettingsManager._merge_dict(base[key], value)
            else:
                base[key] = value
        return base

    def load(self) -> Dict[str, Any]:
        self._data = deepcopy(_DEFAULT_SETTINGS)
        if self.file_path.exists():
            try:
                payload = json.loads(self.file_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    self._merge_dict(self._data, payload)
            except Exception:
                pass
        return deepcopy(self._data)

    def save(self):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get(self, dotted_key: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in str(dotted_key or "").split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return deepcopy(node)

    def set(self, dotted_key: str, value: Any, persist: bool = True):
        parts = [part for part in str(dotted_key or "").split(".") if part]
        if not parts:
            return
        node = self._data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
        if persist:
            self.save()

    def serial_defaults(self) -> Dict[str, Any]:
        return dict(self.get("connections.serial", {}) or {})

    def tcp_defaults(self) -> Dict[str, Any]:
        return dict(self.get("connections.tcp", {}) or {})

    def udp_defaults(self) -> Dict[str, Any]:
        return dict(self.get("connections.udp", {}) or {})

    def recent_links(self) -> List[Dict[str, Any]]:
        items = self.get("connections.recent_links", []) or []
        return [dict(item) for item in items if isinstance(item, dict)]

    def update_serial_defaults(self, port: str, baud: int, persist: bool = True):
        self._data.setdefault("connections", {}).setdefault("serial", {})
        self._data["connections"]["serial"] = {
            "port": str(port or "").strip(),
            "baud": int(baud or 115200),
        }
        if persist:
            self.save()

    def update_tcp_defaults(self, host: str, port: int, persist: bool = True):
        self._data.setdefault("connections", {}).setdefault("tcp", {})
        self._data["connections"]["tcp"] = {
            "host": str(host or "127.0.0.1").strip() or "127.0.0.1",
            "port": int(port or 5760),
        }
        if persist:
            self.save()

    def update_udp_defaults(self, host: str, port: int, persist: bool = True):
        self._data.setdefault("connections", {}).setdefault("udp", {})
        self._data["connections"]["udp"] = {
            "host": str(host or "0.0.0.0").strip() or "0.0.0.0",
            "port": int(port or 14550),
        }
        if persist:
            self.save()

    def add_recent_link(self, kind: str, label: str, payload: Dict[str, Any], persist: bool = True):
        entry = {
            "kind": str(kind or "unknown"),
            "label": str(label or "未命名链路"),
            "payload": dict(payload or {}),
        }
        recent = [item for item in self.recent_links() if item.get("label") != entry["label"]]
        recent.insert(0, entry)
        self._data.setdefault("connections", {})["recent_links"] = recent[:10]
        if persist:
            self.save()

    def fact_favorites(self) -> List[str]:
        names = self.get("params.favorites", []) or []
        return [str(name).strip().upper() for name in names if str(name).strip()]

    def set_fact_favorites(self, names: List[str], persist: bool = True):
        cleaned = []
        seen = set()
        for name in names or []:
            key = str(name or "").strip().upper()
            if not key or key in seen:
                continue
            seen.add(key)
            cleaned.append(key)
        self._data.setdefault("params", {})["favorites"] = cleaned
        if persist:
            self.save()

    def video_settings(self) -> Dict[str, Any]:
        return dict(self.get("video", {}) or {})

    def update_video_settings(self, stream_url: str, camera_name: str = "PayloadCam", persist: bool = True):
        self._data["video"] = {
            "stream_url": str(stream_url or "").strip(),
            "camera_name": str(camera_name or "PayloadCam").strip() or "PayloadCam",
        }
        if persist:
            self.save()

    def peripheral_settings(self) -> Dict[str, Any]:
        payload = dict(self.get("peripherals", {}) or {})
        payload["plugin_dirs"] = [str(item).strip() for item in (payload.get("plugin_dirs", []) or []) if str(item).strip()]
        return payload

    def update_peripheral_settings(self, values: Dict[str, Any], persist: bool = True):
        incoming = dict(values or {})
        self._data.setdefault("peripherals", {})
        self._data["peripherals"].update(
            {
                "joystick_enabled": bool(incoming.get("joystick_enabled", self._data["peripherals"].get("joystick_enabled", False))),
                "adsb_enabled": bool(incoming.get("adsb_enabled", self._data["peripherals"].get("adsb_enabled", False))),
                "rtk_host": str(incoming.get("rtk_host", self._data["peripherals"].get("rtk_host", "127.0.0.1")) or "127.0.0.1").strip() or "127.0.0.1",
                "rtk_port": int(incoming.get("rtk_port", self._data["peripherals"].get("rtk_port", 2101)) or 2101),
                "plugin_dirs": [str(item).strip() for item in (incoming.get("plugin_dirs", self._data["peripherals"].get("plugin_dirs", [])) or []) if str(item).strip()],
            }
        )
        if persist:
            self.save()
