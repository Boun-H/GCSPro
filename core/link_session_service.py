from __future__ import annotations


class LinkSessionService:
    KIND_LABELS = {
        "serial": "串口",
        "tcp": "TCP",
        "udp": "UDP",
    }

    @classmethod
    def build_link_label(cls, kind: str, payload: dict | None = None) -> str:
        item = dict(payload or {})
        kind_key = str(kind or "").strip().lower()
        if kind_key == "serial":
            return f"串口 {str(item.get('port', '')).strip()}@{int(item.get('baud', 115200) or 115200)}"
        if kind_key == "tcp":
            return f"TCP {str(item.get('host', '127.0.0.1') or '127.0.0.1').strip()}:{int(item.get('port', 5760) or 5760)}"
        if kind_key == "udp":
            return f"UDP {str(item.get('host', '0.0.0.0') or '0.0.0.0').strip()}:{int(item.get('port', 14550) or 14550)}"
        fallback = str(item.get("label", "") or "").strip()
        return fallback or f"{cls.KIND_LABELS.get(kind_key, kind_key.upper() or '链路')}"

    @classmethod
    def resolve_active_link_context(cls, active_link: dict | None, last_link_label: str = "") -> tuple[str, str]:
        active = dict(active_link or {})
        link_key = str(active.get("key", "") or "")
        link_label = str(active.get("label", last_link_label) or last_link_label or "当前链路")
        return link_key, link_label

    @classmethod
    def connect_recent_entry(cls, connection_manager, entry: dict) -> str:
        item = dict(entry or {})
        kind = str(item.get("kind", "")).strip().lower()
        payload = dict(item.get("payload", {}) or {})
        label = cls.build_link_label(kind, payload)
        if kind == "serial":
            connection_manager.connect_serial(str(payload.get("port", "")).strip(), int(payload.get("baud", 115200) or 115200))
        elif kind == "tcp":
            connection_manager.connect_tcp(str(payload.get("host", "127.0.0.1") or "127.0.0.1").strip(), int(payload.get("port", 5760) or 5760))
        elif kind == "udp":
            connection_manager.connect_udp(str(payload.get("host", "0.0.0.0") or "0.0.0.0").strip(), int(payload.get("port", 14550) or 14550))
        else:
            raise ValueError(f"不支持的历史链路类型: {kind}")
        return label

    @staticmethod
    def build_settings_payload(values: dict | None) -> dict:
        item = dict(values or {})
        return {
            "serial": dict(item.get("serial", {}) or {}),
            "tcp": dict(item.get("tcp", {}) or {}),
            "udp": dict(item.get("udp", {}) or {}),
            "auto_reconnect": bool(item.get("auto_reconnect", True)),
            "auto_connect": bool(item.get("auto_connect", False)),
            "map_source": str(item.get("map_source", "谷歌卫星") or "谷歌卫星"),
        }


__all__ = ["LinkSessionService"]
