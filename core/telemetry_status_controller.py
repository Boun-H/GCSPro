from __future__ import annotations


class TelemetryStatusController:
    _CONNECTION_LABELS = {
        "connected": {"text": "🟢 已连接", "tone": "ok", "tooltip": "点击断开连接", "flight_label": "已连接"},
        "connecting": {"text": "🟡 连接中", "tone": "warn", "tooltip": "连接建立中", "flight_label": "连接中"},
        "disconnecting": {"text": "🟠 断开中", "tone": "warn", "tooltip": "断开处理中", "flight_label": "断开中"},
        "disconnected": {"text": "🔴 未连接", "tone": "danger", "tooltip": "点击打开连接对话框", "flight_label": "未连接"},
    }

    @classmethod
    def connection_view(cls, state: str) -> dict:
        return dict(cls._CONNECTION_LABELS.get(str(state or "disconnected"), cls._CONNECTION_LABELS["disconnected"]))

    @staticmethod
    def reset_labels() -> dict:
        return {
            "flight_time": "飞行时间: 00:00:00",
            "battery": "电池: 100%",
            "altitude": "高度: 0.0m",
            "speed": "速度: 0.0m/s",
            "mode": "模式: UNKNOWN",
            "gps": "GPS: 0 颗",
            "volt": "电压: 0.00V",
            "alert": "状态: 正常",
            "tones": {
                "flight_time": "neutral",
                "battery": "neutral",
                "altitude": "neutral",
                "speed": "neutral",
                "mode": "neutral",
                "gps": "neutral",
                "volt": "neutral",
                "alert": "ok",
            },
        }

    @staticmethod
    def chip_tones(data: dict | None) -> dict:
        item = dict(data or {})
        battery_remaining = int(item.get("battery_remaining", 100) or 0)
        gps_count = int(item.get("gps", 0) or 0)
        voltage = float(item.get("volt", 0.0) or 0.0)
        return {
            "battery": "danger" if battery_remaining < 25 else "warn" if battery_remaining < 45 else "ok",
            "gps": "danger" if gps_count < 6 else "warn" if gps_count < 10 else "ok",
            "volt": "danger" if voltage < 10.5 else "warn" if voltage < 11.1 else "neutral",
            "alert": "ok",
        }

    @staticmethod
    def telemetry_labels(data: dict | None) -> dict:
        item = dict(data or {})
        return {
            "battery": f"电池: {int(item.get('battery_remaining', 100) or 0)}%",
            "altitude": f"高度: {float(item.get('alt', 0.0) or 0.0):.1f}m",
            "speed": f"速度: {float(item.get('vel', 0.0) or 0.0):.1f}m/s",
            "mode": f"模式: {str(item.get('mode', 'UNKNOWN') or 'UNKNOWN')}",
            "gps": f"GPS: {int(item.get('gps', 0) or 0)} 颗",
            "volt": f"电压: {float(item.get('volt', 0.0) or 0.0):.2f}V",
            "alert": "状态: 正常",
        }

    @staticmethod
    def workbench_status(vehicle_summary: dict | None) -> str:
        item = dict(vehicle_summary or {})
        return f"{item.get('vehicle_id', '--')} | {item.get('mode', 'UNKNOWN')} | 电池 {item.get('battery_remaining', 0)}%"


__all__ = ["TelemetryStatusController"]
