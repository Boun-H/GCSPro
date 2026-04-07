from __future__ import annotations

from .constants import (
    GPS_CRITICAL,
    GPS_WARN,
    LINK_WARNING_TOKENS,
    LOW_BATTERY_CRITICAL,
    LOW_BATTERY_WARN,
    MODE_AUTO,
    MODE_GUIDED,
    MODE_QGUIDED,
    MODE_QLOITER,
)


class HealthMonitor:
    @staticmethod
    def telemetry_preview(payload: dict | None) -> dict:
        data = dict(payload or {})
        return {
            "mode": str(data.get("mode", "UNKNOWN") or "UNKNOWN"),
            "battery": int(data.get("battery_remaining", data.get("battery", 0)) or 0),
            "gps": int(data.get("gps", 0) or 0),
            "alt": round(float(data.get("alt", 0.0) or 0.0), 2),
            "vel": round(float(data.get("vel", 0.0) or 0.0), 2),
            "lat": data.get("lat"),
            "lon": data.get("lon"),
            "volt": round(float(data.get("volt", 0.0) or 0.0), 2),
        }

    @staticmethod
    def build_mission_text(payload: dict | None, mission_count: int = 0) -> str:
        data = dict(payload or {})
        mode_text = str(data.get("mode", "UNKNOWN") or "UNKNOWN").upper()
        speed = float(data.get("vel", 0.0) or 0.0)
        altitude = float(data.get("alt", 0.0) or 0.0)
        count = max(0, int(mission_count or 0))

        if MODE_AUTO in mode_text:
            return f"AUTO 执行中 · {count} 点 · {speed:.1f}m/s"
        if MODE_GUIDED in mode_text or MODE_QGUIDED in mode_text:
            return f"Guided 控制中 · 高度 {altitude:.1f}m"
        if "RTL" in mode_text:
            return "返航执行中"
        return f"任务点 {count} 个"

    @classmethod
    def evaluate(
        cls,
        payload: dict | None,
        connection_state: str = "",
        manual_alert_text: str = "",
        mission_count: int = 0,
    ) -> dict:
        preview = cls.telemetry_preview(payload)
        battery = int(preview["battery"])
        gps = int(preview["gps"])
        alt = float(preview["alt"])
        vel = float(preview["vel"])

        issues: list[str] = []
        suggestions: list[str] = []
        manual_text = str(manual_alert_text or "").strip()
        if manual_text and manual_text not in {"正常", "--"}:
            issues.append(manual_text)
        if 0 < battery < LOW_BATTERY_CRITICAL:
            issues.append("低电")
            suggestions.append("建议立即执行 QRTL / QLAND 并返航")
        elif 0 < battery < LOW_BATTERY_WARN:
            issues.append("电量偏低")
            suggestions.append("建议缩短任务并准备返航")
        if 0 < gps < GPS_CRITICAL:
            issues.append("GPS 弱")
            suggestions.append("建议切换 QLOITER / Hold，等待 GPS 定位恢复")
        elif 0 < gps < GPS_WARN:
            issues.append("GPS 一般")
            suggestions.append("建议谨慎继续 AUTO")

        lowered = str(connection_state or "").lower()
        if any(token.lower() in lowered for token in LINK_WARNING_TOKENS):
            issues.append("链路异常")
            suggestions.append("建议检查数传/天线并保留 QRTL 备选")

        unique_issues = list(dict.fromkeys(issues))
        unique_suggestions = list(dict.fromkeys(suggestions))
        danger_issues = {"低电", "链路异常"}
        suggestion_tone = "danger" if any(item in danger_issues for item in unique_issues) else "warn" if unique_issues else "ok"

        return {
            "battery_tone": "danger" if battery < LOW_BATTERY_CRITICAL else "warn" if battery < LOW_BATTERY_WARN else "ok",
            "gps_tone": "danger" if gps < GPS_CRITICAL else "warn" if gps < GPS_WARN else "ok",
            "flight_tone": "info" if alt > 1.0 or vel > 1.0 else "neutral",
            "issues": unique_issues,
            "suggestions": unique_suggestions,
            "alert_text": f"飞行告警: {' / '.join(unique_issues)}" if unique_issues else "飞行告警: 正常",
            "action_text": f"动作建议: {'；'.join(unique_suggestions)}" if unique_suggestions else "动作建议: 继续监控遥测与任务进度",
            "suggestion_tone": suggestion_tone,
            "mission_text": cls.build_mission_text(payload, mission_count=mission_count),
        }


__all__ = ["HealthMonitor"]
