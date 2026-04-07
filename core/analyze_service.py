from __future__ import annotations

import csv
import io
from datetime import datetime
from pathlib import Path


class AnalyzeService:
    SERIES_LABELS = {
        "battery": "电池",
        "alt": "高度",
        "vel": "速度",
        "gps": "GPS",
    }

    def __init__(self, history_limit: int = 120):
        self.history_limit = max(1, int(history_limit or 120))
        self._history: dict[str, list[float]] = {key: [] for key in self.SERIES_LABELS}
        self._timeline: list[str] = []
        self._mode_history: list[str] = []
        self._events: list[str] = []

    def history(self) -> dict[str, list[float]]:
        return {key: list(values) for key, values in self._history.items()}

    def timeline(self) -> list[str]:
        return list(self._timeline)

    def _append_timestamp(self, timestamp: str | None = None):
        self._timeline.append(str(timestamp or datetime.now().strftime("%H:%M:%S")))
        if len(self._timeline) > self.history_limit:
            del self._timeline[:-self.history_limit]

    def _append_history(self, key: str, value: float):
        history = self._history.setdefault(str(key), [])
        history.append(float(value))
        if len(history) > self.history_limit:
            del history[:-self.history_limit]

    @staticmethod
    def sparkline(values: list[float]) -> str:
        if not values:
            return "-"
        if len(values) == 1:
            return "▅"
        chars = "▁▂▃▄▅▆▇█"
        low = min(values)
        high = max(values)
        if abs(high - low) < 1e-9:
            return chars[4] * len(values)
        result = []
        for value in values:
            ratio = (value - low) / (high - low)
            index = max(0, min(len(chars) - 1, int(round(ratio * (len(chars) - 1)))))
            result.append(chars[index])
        return "".join(result)

    def zoom_limit(self, label: str | None = None) -> int:
        text = str(label or "全部")
        digits = "".join(ch for ch in text if ch.isdigit())
        if digits:
            return max(1, int(digits))
        return max(1, max((len(values) for values in self._history.values()), default=1))

    def _record_event(self, text: str):
        event_text = str(text or "").strip()
        if not event_text:
            return
        if event_text in self._events:
            return
        self._events.append(event_text)
        if len(self._events) > self.history_limit:
            del self._events[:-self.history_limit]

    def build_flight_report(self) -> str:
        if not any(self._history.values()):
            return "自动飞行报告\n等待遥测数据进入后自动生成。"

        battery_values = list(self._history.get("battery", []))
        alt_values = list(self._history.get("alt", []))
        vel_values = list(self._history.get("vel", []))
        gps_values = list(self._history.get("gps", []))
        sample_count = max(len(self._timeline), *(len(values) for values in self._history.values())) if self._history else len(self._timeline)
        start_time = self._timeline[0] if self._timeline else "--:--:--"
        end_time = self._timeline[-1] if self._timeline else "--:--:--"
        avg_speed = sum(vel_values) / max(1, len(vel_values)) if vel_values else 0.0
        unique_modes = []
        for mode in self._mode_history:
            if mode and mode not in unique_modes:
                unique_modes.append(mode)
        risk_items = []
        if battery_values and min(battery_values) < 25:
            risk_items.append("低电量")
        if gps_values and min(gps_values) < 6:
            risk_items.append("GPS 弱")
        if not risk_items:
            risk_items.append("未发现明显异常")
        events = list(self._events[-5:])
        if not events:
            events = ["暂无关键异常事件"]

        lines = [
            "自动飞行报告",
            f"采样点数: {sample_count}",
            f"时间范围: {start_time} ~ {end_time}",
            f"模式切换: {' -> '.join(unique_modes) if unique_modes else '--'}",
            f"最大高度: {max(alt_values) if alt_values else 0.0:.1f} m",
            f"平均速度: {avg_speed:.1f} m/s",
            f"最低电量: {min(battery_values) if battery_values else 0.0:.0f}%",
            f"GPS 范围: {min(gps_values) if gps_values else 0:.0f} ~ {max(gps_values) if gps_values else 0:.0f} 颗",
            f"风险摘要: {' / '.join(risk_items)}",
            "关键事件:",
        ]
        lines.extend(f"- {event}" for event in events)
        return "\n".join(lines)

    def ingest_status(self, payload: dict | None, timestamp: str | None = None) -> dict:
        data = dict(payload or {})
        battery = int(data.get("battery_remaining", 0) or 0)
        alt = float(data.get("alt", 0.0) or 0.0)
        vel = float(data.get("vel", 0.0) or 0.0)
        gps = int(data.get("gps", 0) or 0)
        volt = float(data.get("volt", 0.0) or 0.0)
        mode = str(data.get("mode", "UNKNOWN") or "UNKNOWN")

        self._append_timestamp(timestamp)
        self._append_history("battery", battery)
        self._append_history("alt", alt)
        self._append_history("vel", vel)
        self._append_history("gps", gps)

        previous_mode = self._mode_history[-1] if self._mode_history else ""
        if not previous_mode or previous_mode != mode:
            self._record_event(f"{self._timeline[-1]} 模式切换: {previous_mode or 'INIT'} → {mode}")
        self._mode_history.append(mode)
        if len(self._mode_history) > self.history_limit:
            del self._mode_history[:-self.history_limit]
        if 0 < battery < 25:
            self._record_event(f"{self._timeline[-1]} 低电量告警: {battery}%")
        if 0 < gps < 6:
            self._record_event(f"{self._timeline[-1]} GPS 弱: {gps} 颗")

        flight_report = self.build_flight_report()
        return {
            "mode": mode,
            "battery": battery,
            "alt": alt,
            "vel": vel,
            "gps": gps,
            "volt": volt,
            "chart_summary": f"趋势摘要: 模式 {mode} | 电池 {battery}% | 高度 {alt:.1f}m | 速度 {vel:.1f}m/s | GPS {gps} 颗",
            "banner_summary": f"分析概览: 模式 {mode} | 电池 {battery}% | GPS {gps} | 高度 {alt:.1f}m | 速度 {vel:.1f}m/s",
            "flight_report": flight_report,
            "report_summary": f"自动飞行报告: 最大高度 {max(self._history.get('alt', [0.0])):.1f}m | 最低电量 {min(self._history.get('battery', [0.0])):.0f}% | 平均速度 {(sum(self._history.get('vel', [])) / max(1, len(self._history.get('vel', [])))) if self._history.get('vel') else 0.0:.1f}m/s",
        }

    def build_chart_text(self, visible_keys: list[str], limit: int) -> str:
        keys = [str(key) for key in (visible_keys or [])]
        if not keys:
            return "当前未选中任何字段，请勾选需要显示的遥测量。"

        lines: list[str] = []
        for key, title in self.SERIES_LABELS.items():
            if key not in keys:
                lines.append(f"{title}趋势: 已隐藏")
                continue
            values = list(self._history.get(key, []))[-max(1, int(limit or 1)) :]
            if not values:
                lines.append(f"{title}: 等待数据")
                continue
            lines.append(f"{title}趋势: {self.sparkline(values)}   最近值: {values[-1]:.1f}")
        lines.append("CSV 导出包含 timestamp,battery,alt,vel,gps 五列。")
        return "\n".join(lines)

    def export_csv_text(self, file_path: str | None = None) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["timestamp", "battery", "alt", "vel", "gps"])
        total = max(len(self._timeline), *(len(values) for values in self._history.values())) if self._history else len(self._timeline)
        for index in range(total):
            writer.writerow(
                [
                    self._timeline[index] if index < len(self._timeline) else "",
                    self._history.get("battery", [])[index] if index < len(self._history.get("battery", [])) else "",
                    self._history.get("alt", [])[index] if index < len(self._history.get("alt", [])) else "",
                    self._history.get("vel", [])[index] if index < len(self._history.get("vel", [])) else "",
                    self._history.get("gps", [])[index] if index < len(self._history.get("gps", [])) else "",
                ]
            )
        text = buffer.getvalue()
        if file_path:
            Path(file_path).write_text(text, encoding="utf-8")
        return text


__all__ = ["AnalyzeService"]
