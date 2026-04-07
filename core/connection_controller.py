from __future__ import annotations

from .link_session_service import LinkSessionService


class ConnectionController:
    def __init__(self, link_session_service: LinkSessionService | None = None):
        self.link_session_service = link_session_service or LinkSessionService()

    @staticmethod
    def build_saved_context(settings_manager, current_map: str) -> dict:
        return {
            "serial": dict(settings_manager.serial_defaults() or {}),
            "tcp": dict(settings_manager.tcp_defaults() or {}),
            "udp": dict(settings_manager.udp_defaults() or {}),
            "auto_reconnect": bool(settings_manager.get("connections.auto_reconnect", True)),
            "auto_connect": bool(settings_manager.get("connections.auto_connect", False)),
            "map_source": str(settings_manager.get("ui.map_source", current_map) or current_map),
            "recent_links": list(settings_manager.recent_links() or []),
        }

    @staticmethod
    def should_auto_connect(connection_state: str, auto_connect_enabled: bool, recent_links: list[dict] | None) -> bool:
        return str(connection_state or "disconnected") == "disconnected" and bool(auto_connect_enabled) and bool(recent_links)

    def plan_dialog_submission(self, mode_index: int, values: dict | None) -> dict:
        payload = dict(values or {})
        try:
            if int(mode_index) == 0:
                port = str(payload.get("port", "")).strip()
                if not port or "未检测到串口" in port:
                    return {
                        "ok": False,
                        "title": "未检测到串口",
                        "message": "请检查驱动/线缆，并点击串口刷新按钮后重试",
                        "error": "未检测到可用串口",
                    }
                baud = int(float(payload.get("baud", 115200) or 115200))
                label = self.link_session_service.build_link_label("serial", {"port": port, "baud": baud})
                return {
                    "ok": True,
                    "kind": "serial",
                    "payload": {"port": port, "baud": baud},
                    "label": label,
                    "recent_label": f"{port}@{baud}",
                    "log": {"connection_type": "serial", "port": port, "baud": baud},
                }

            if int(mode_index) == 1:
                host = str(payload.get("host", "127.0.0.1") or "127.0.0.1").strip()
                port = int(float(payload.get("port", 5760) or 5760))
                label = self.link_session_service.build_link_label("tcp", {"host": host, "port": port})
                return {
                    "ok": True,
                    "kind": "tcp",
                    "payload": {"host": host, "port": port},
                    "label": label,
                    "recent_label": f"TCP {host}:{port}",
                    "log": {"connection_type": "tcp", "ip": host, "port": port},
                }

            host = str(payload.get("host", "0.0.0.0") or "0.0.0.0").strip() or "0.0.0.0"
            port = int(float(payload.get("port", 14550) or 14550))
            label = self.link_session_service.build_link_label("udp", {"host": host, "port": port})
            return {
                "ok": True,
                "kind": "udp",
                "payload": {"host": host, "port": port},
                "label": label,
                "recent_label": f"UDP {host}:{port}",
                "log": {"connection_type": "udp", "host": host, "port": port},
            }
        except Exception as exc:
            return {
                "ok": False,
                "title": "连接失败",
                "message": str(exc),
                "error": str(exc),
            }

    def execute_connection_plan(self, connection_manager, settings_manager, plan: dict) -> str:
        item = dict(plan or {})
        kind = str(item.get("kind", "")).strip().lower()
        payload = dict(item.get("payload", {}) or {})
        label = str(item.get("label", "") or "")

        if kind == "serial":
            settings_manager.update_serial_defaults(payload.get("port", ""), payload.get("baud", 115200))
            settings_manager.add_recent_link("serial", str(item.get("recent_label", label) or label), payload)
            connection_manager.connect_serial(str(payload.get("port", "")).strip(), int(payload.get("baud", 115200) or 115200))
            return label
        if kind == "tcp":
            settings_manager.update_tcp_defaults(payload.get("host", "127.0.0.1"), payload.get("port", 5760))
            settings_manager.add_recent_link("tcp", str(item.get("recent_label", label) or label), payload)
            connection_manager.connect_tcp(str(payload.get("host", "127.0.0.1") or "127.0.0.1").strip(), int(payload.get("port", 5760) or 5760))
            return label
        if kind == "udp":
            settings_manager.update_udp_defaults(payload.get("host", "0.0.0.0"), payload.get("port", 14550))
            settings_manager.add_recent_link("udp", str(item.get("recent_label", label) or label), payload)
            connection_manager.connect_udp(str(payload.get("host", "0.0.0.0") or "0.0.0.0").strip(), int(payload.get("port", 14550) or 14550))
            return label
        raise ValueError(f"不支持的连接类型: {kind}")

    def save_link_settings(self, settings_manager, values: dict | None, current_map: str) -> dict:
        payload = self.link_session_service.build_settings_payload({**dict(values or {}), "map_source": dict(values or {}).get("map_source", current_map)})
        settings_manager.update_serial_defaults(payload["serial"].get("port", ""), payload["serial"].get("baud", 115200), persist=False)
        settings_manager.update_tcp_defaults(payload["tcp"].get("host", "127.0.0.1"), payload["tcp"].get("port", 5760), persist=False)
        settings_manager.update_udp_defaults(payload["udp"].get("host", "0.0.0.0"), payload["udp"].get("port", 14550), persist=False)
        settings_manager.set("connections.auto_reconnect", payload["auto_reconnect"], persist=False)
        settings_manager.set("connections.auto_connect", payload["auto_connect"], persist=False)
        settings_manager.set("ui.map_source", payload["map_source"], persist=False)
        settings_manager.save()
        return payload


__all__ = ["ConnectionController"]
