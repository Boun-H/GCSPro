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

        return {
            "mode": mode,
            "battery": battery,
            "alt": alt,
            "vel": vel,
            "gps": gps,
            "volt": volt,
            "chart_summary": f"趋势摘要: 模式 {mode} | 电池 {battery}% | 高度 {alt:.1f}m | 速度 {vel:.1f}m/s | GPS {gps} 颗",
            "banner_summary": f"分析概览: 模式 {mode} | 电池 {battery}% | GPS {gps} | 高度 {alt:.1f}m | 速度 {vel:.1f}m/s",
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
