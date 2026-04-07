from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.analyze_service import AnalyzeService

from .panel_style import apply_tone, build_panel_stylesheet, recent_time_text, style_action_button, style_close_button


class TimeSeriesChartWidget(QWidget):
    _COLORS = {
        "battery": "#4ade80",
        "alt": "#60a5fa",
        "vel": "#f59e0b",
        "gps": "#f472b6",
    }
    _LABELS = {
        "battery": "电池",
        "alt": "高度",
        "vel": "速度",
        "gps": "GPS",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._history: dict[str, list[float]] = {}
        self._visible_keys: list[str] = ["battery", "alt", "vel", "gps"]
        self.max_points = 20
        self.setMinimumHeight(200)

    def set_chart_data(self, history: dict[str, list[float]], visible_keys: list[str], max_points: int):
        self._history = {key: [float(value) for value in values] for key, values in (history or {}).items()}
        self._visible_keys = [str(key) for key in (visible_keys or [])]
        self.max_points = max(1, int(max_points or 20))
        self.update()

    def visible_series_names(self) -> list[str]:
        return list(self._visible_keys)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#0f1926"))

        left, top, right, bottom = 36, 14, 12, 24
        chart_rect = self.rect().adjusted(left, top, -right, -bottom)
        painter.setPen(QPen(QColor("#29425c"), 1))
        painter.drawRoundedRect(chart_rect, 6, 6)

        values: list[float] = []
        visible_series: list[tuple[str, list[float]]] = []
        for key in self._visible_keys:
            points = list(self._history.get(key, []))[-self.max_points :]
            if points:
                visible_series.append((key, points))
                values.extend(points)

        if not visible_series:
            painter.setPen(QColor("#9fb4cf"))
            painter.drawText(chart_rect, Qt.AlignmentFlag.AlignCenter, "请选择字段或等待遥测数据")
            return

        low = min(values)
        high = max(values)
        if abs(high - low) < 1e-9:
            high = low + 1.0

        for step in range(1, 5):
            y = chart_rect.top() + step * chart_rect.height() / 5.0
            painter.setPen(QPen(QColor("#1b3148"), 1, Qt.PenStyle.DashLine))
            painter.drawLine(int(chart_rect.left()), int(y), int(chart_rect.right()), int(y))

        for legend_index, (key, points) in enumerate(visible_series):
            color = QColor(self._COLORS.get(key, "#d9e6f8"))
            painter.setPen(QPen(color, 2))
            if len(points) == 1:
                ratio = (points[0] - low) / (high - low)
                y = chart_rect.bottom() - ratio * chart_rect.height()
                painter.drawEllipse(int(chart_rect.center().x()), int(y), 4, 4)
            else:
                for index in range(1, len(points)):
                    prev_ratio = (points[index - 1] - low) / (high - low)
                    curr_ratio = (points[index] - low) / (high - low)
                    x1 = chart_rect.left() + (index - 1) * chart_rect.width() / max(1, len(points) - 1)
                    x2 = chart_rect.left() + index * chart_rect.width() / max(1, len(points) - 1)
                    y1 = chart_rect.bottom() - prev_ratio * chart_rect.height()
                    y2 = chart_rect.bottom() - curr_ratio * chart_rect.height()
                    painter.drawLine(int(x1), int(y1), int(x2), int(y2))
            legend_x = chart_rect.left() + legend_index * 92
            painter.fillRect(int(legend_x), int(chart_rect.top() - 10), 12, 4, color)
            painter.setPen(QColor("#d9e6f8"))
            painter.drawText(int(legend_x + 16), int(chart_rect.top() - 4), self._LABELS.get(key, key))

        painter.setPen(QColor("#8fb1d6"))
        painter.drawText(6, chart_rect.top() + 12, f"{high:.1f}")
        painter.drawText(6, chart_rect.bottom(), f"{low:.1f}")


class AnalyzePanel(QFrame):
    close_clicked = pyqtSignal()
    refresh_requested = pyqtSignal()
    download_logs_requested = pyqtSignal()
    replay_requested = pyqtSignal(str)
    log_selected = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._chart_cards: dict[str, QLabel] = {}
        self._service = AnalyzeService(history_limit=120)
        self.field_checks: dict[str, QCheckBox] = {}
        self.setStyleSheet(build_panel_stylesheet(include_checks=True))

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 10, 10, 6)
        title_col = QVBoxLayout()
        title = QLabel("Analyze")
        title.setStyleSheet("font-size:16px; font-weight:700; color:#eef5ff;")
        subtitle = QLabel("MAVLink Inspector / 日志下载 / 回放 / 图表 / CSV")
        subtitle.setStyleSheet("font-size:12px; color:#9fb4cf;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header_layout.addLayout(title_col)
        header_layout.addStretch()
        self.updated_at = QLabel("最近更新: --:--:--")
        self.updated_at.setStyleSheet("font-size:12px; color:#9fb4cf;")
        header_layout.addWidget(self.updated_at)
        self.close_btn = QPushButton("×")
        style_close_button(self.close_btn)
        header_layout.addWidget(self.close_btn)
        main_layout.addWidget(header)

        self.summary_banner = QLabel("分析概览: 等待遥测 / 日志数据")
        self.summary_banner.setWordWrap(True)
        apply_tone(self.summary_banner, "info", padding=8, radius=8)
        main_layout.addWidget(self.summary_banner)

        self.quick_actions_summary = QLabel("快捷操作: 刷新日志 / 下载日志 / 回放 / CSV 导出 / 自动飞行报告")
        self.quick_actions_summary.setWordWrap(True)
        apply_tone(self.quick_actions_summary, "neutral", padding=7, radius=8)
        main_layout.addWidget(self.quick_actions_summary)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, 1)

        inspector = QWidget()
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.setContentsMargins(10, 10, 10, 10)
        self.inspector_summary = QLabel("优先展示关键指标卡片。JSON 详情默认折叠，可按需展开。")
        self.inspector_summary.setWordWrap(True)
        apply_tone(self.inspector_summary, "neutral", padding=7, radius=8)
        inspector_layout.addWidget(self.inspector_summary)
        self.btn_toggle_inspector = QPushButton("展开 JSON 详情")
        style_action_button(self.btn_toggle_inspector, "info", compact=True)
        inspector_layout.addWidget(self.btn_toggle_inspector)
        self.inspector_text = QPlainTextEdit()
        self.inspector_text.setReadOnly(True)
        self.inspector_text.setPlaceholderText("连接后将显示最新 MAVLink 遥测快照")
        self.inspector_text.hide()
        inspector_layout.addWidget(self.inspector_text)
        self.tabs.addTab(inspector, "Inspector")

        logs_page = QWidget()
        logs_layout = QVBoxLayout(logs_page)
        logs_layout.setContentsMargins(10, 10, 10, 10)
        self.log_list = QListWidget()
        self.log_summary = QLabel("尚未扫描日志")
        self.log_preview = QPlainTextEdit()
        self.log_preview.setReadOnly(True)
        self.log_preview.setPlaceholderText("选择日志后将在这里显示文本/二进制预览")
        btn_row = QHBoxLayout()
        self.btn_refresh = QPushButton("刷新日志")
        self.btn_download = QPushButton("下载飞控日志")
        self.btn_replay = QPushButton("回放选中日志")
        btn_row.addWidget(self.btn_refresh)
        btn_row.addWidget(self.btn_download)
        btn_row.addWidget(self.btn_replay)
        logs_layout.addWidget(self.log_summary)
        logs_layout.addWidget(self.log_list, 1)
        logs_layout.addWidget(self.log_preview, 1)
        logs_layout.addLayout(btn_row)
        self.tabs.addTab(logs_page, "日志")

        charts_page = QWidget()
        charts_layout = QVBoxLayout(charts_page)
        charts_layout.setContentsMargins(10, 10, 10, 10)

        controls = QHBoxLayout()
        for key, text in [("battery", "电池"), ("alt", "高度"), ("vel", "速度"), ("gps", "GPS")]:
            checkbox = QCheckBox(text)
            checkbox.setChecked(True)
            checkbox.toggled.connect(self._refresh_chart_view)
            self.field_checks[key] = checkbox
            controls.addWidget(checkbox)
        controls.addStretch()
        controls.addWidget(QLabel("时间轴"))
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["全部", "最近 5 条", "最近 10 条", "最近 20 条", "最近 50 条"])
        self.zoom_combo.setCurrentText("最近 20 条")
        self.zoom_combo.currentTextChanged.connect(self._refresh_chart_view)
        controls.addWidget(self.zoom_combo)
        self.btn_export_csv = QPushButton("导出 CSV")
        self.btn_export_csv.clicked.connect(self._export_csv_dialog)
        controls.addWidget(self.btn_export_csv)
        charts_layout.addLayout(controls)

        cards = QWidget()
        cards_layout = QGridLayout(cards)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setHorizontalSpacing(8)
        cards_layout.setVerticalSpacing(8)
        for idx, key in enumerate(["battery", "alt", "vel", "gps"]):
            label = QLabel("--")
            label.setMinimumHeight(54)
            label.setWordWrap(True)
            self._apply_card_style(label, "neutral")
            self._chart_cards[key] = label
            cards_layout.addWidget(label, idx // 2, idx % 2)
        charts_layout.addWidget(cards)

        self.chart_summary = QLabel("趋势摘要: 等待遥测数据")
        self.chart_summary.setWordWrap(True)
        self.chart_summary.setStyleSheet("background:#142133; color:#cfe3fb; border-radius:8px; padding:8px;")
        charts_layout.addWidget(self.chart_summary)

        self.chart_widget = TimeSeriesChartWidget()
        charts_layout.addWidget(self.chart_widget)

        self.chart_text = QPlainTextEdit()
        self.chart_text.setReadOnly(True)
        self.chart_text.setPlaceholderText("这里显示电池/高度/速度/GPS 的趋势摘要和导出提示")
        charts_layout.addWidget(self.chart_text)
        self.tabs.addTab(charts_page, "图表")

        report_page = QWidget()
        report_layout = QVBoxLayout(report_page)
        report_layout.setContentsMargins(10, 10, 10, 10)
        self.report_summary = QLabel("自动飞行报告: 等待遥测数据")
        self.report_summary.setWordWrap(True)
        apply_tone(self.report_summary, "info", padding=8, radius=8)
        report_layout.addWidget(self.report_summary)
        report_actions = QHBoxLayout()
        self.btn_copy_report = QPushButton("复制报告")
        style_action_button(self.btn_copy_report, "info", compact=True)
        report_actions.addWidget(self.btn_copy_report)
        report_actions.addStretch()
        report_layout.addLayout(report_actions)
        self.flight_report_text = QPlainTextEdit()
        self.flight_report_text.setReadOnly(True)
        self.flight_report_text.setPlaceholderText("连接后将自动生成飞行报告摘要")
        report_layout.addWidget(self.flight_report_text, 1)
        self.tabs.addTab(report_page, "报告")

        self.close_btn.clicked.connect(self.close_clicked.emit)
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)
        self.btn_download.clicked.connect(self.download_logs_requested.emit)
        self.btn_replay.clicked.connect(self._emit_replay)
        self.btn_toggle_inspector.clicked.connect(self._toggle_inspector)
        self.btn_copy_report.clicked.connect(self._copy_report)
        self.log_list.currentItemChanged.connect(self._emit_selected_log)
        style_action_button(self.btn_refresh, "info", compact=True)
        style_action_button(self.btn_download, "warn", compact=True)
        style_action_button(self.btn_replay, "ok", compact=True)
        style_action_button(self.btn_export_csv, "info", compact=True)
        self._refresh_chart_view()

    def _apply_card_style(self, label: QLabel, tone: str = "neutral"):
        apply_tone(label, tone, padding=8, radius=8)

    def _set_chart_card(self, key: str, title: str, value: str, tone: str = "neutral"):
        label = self._chart_cards.get(key)
        if label is None:
            return
        self._apply_card_style(label, tone)
        label.setText(f"<b>{title}</b><br>{value}")

    def _append_history(self, key: str, value: float):
        self._service._append_history(key, value)

    def _append_timestamp(self):
        self._service._append_timestamp()

    def _sparkline(self, values: list[float]) -> str:
        return self._service.sparkline(values)

    def _zoom_limit(self) -> int:
        return self._service.zoom_limit(self.zoom_combo.currentText())

    def _visible_chart_keys(self) -> list[str]:
        return [key for key, checkbox in self.field_checks.items() if checkbox.isChecked()]

    def _refresh_chart_view(self):
        visible_keys = self._visible_chart_keys()
        limit = self._zoom_limit()
        self.chart_widget.set_chart_data(self._service.history(), visible_keys, limit)
        self.chart_text.setPlainText(self._service.build_chart_text(visible_keys, limit))

    def _toggle_inspector(self):
        visible = not self.inspector_text.isVisible()
        self.inspector_text.setVisible(visible)
        self.btn_toggle_inspector.setText("收起 JSON 详情" if visible else "展开 JSON 详情")

    def _copy_report(self):
        text = self.flight_report_text.toPlainText().strip()
        if text:
            QApplication.clipboard().setText(text)
            self.report_summary.setText("自动飞行报告: 已复制到剪贴板")

    def export_chart_csv(self, file_path: str | None = None) -> str:
        return self._service.export_csv_text(file_path)

    def _export_csv_dialog(self):
        default_path = str(Path.cwd() / "analyze_export.csv")
        file_path, _ = QFileDialog.getSaveFileName(self, "导出遥测 CSV", default_path, "CSV files (*.csv)")
        if not file_path:
            return
        self.export_chart_csv(file_path)
        self.chart_summary.setText(f"趋势摘要: CSV 已导出到 {file_path}")

    def _emit_selected_log(self, *_args):
        item = self.log_list.currentItem()
        if item is not None:
            self.log_selected.emit(str(item.data(256) or item.text()))

    def _emit_replay(self):
        item = self.log_list.currentItem()
        if item is not None:
            self.replay_requested.emit(str(item.data(256) or item.text()))

    def set_status_payload(self, payload: dict | None):
        data = dict(payload or {})
        self.inspector_text.setPlainText(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))

        report = self._service.ingest_status(data)
        battery = int(report.get("battery", 0) or 0)
        alt = float(report.get("alt", 0.0) or 0.0)
        vel = float(report.get("vel", 0.0) or 0.0)
        gps = int(report.get("gps", 0) or 0)
        volt = float(report.get("volt", 0.0) or 0.0)
        mode = str(report.get("mode", "UNKNOWN") or "UNKNOWN")

        self._set_chart_card("battery", "电池", f"{battery}%\n{volt:.2f} V", "danger" if battery < 25 else "warn" if battery < 45 else "ok")
        self._set_chart_card("alt", "高度", f"{alt:.1f} m", "info" if alt > 1.0 else "neutral")
        self._set_chart_card("vel", "速度", f"{vel:.1f} m/s", "info" if vel > 1.0 else "neutral")
        self._set_chart_card("gps", "GPS", f"{gps} 颗\n{mode}", "danger" if gps < 6 else "warn" if gps < 10 else "ok")

        self.chart_summary.setText(str(report.get("chart_summary", "趋势摘要: 等待遥测数据")))
        self.summary_banner.setText(str(report.get("banner_summary", "分析概览: 等待遥测 / 日志数据")))
        self.report_summary.setText(str(report.get("report_summary", "自动飞行报告: 等待遥测数据")))
        self.flight_report_text.setPlainText(str(report.get("flight_report", "自动飞行报告\n等待遥测数据进入后自动生成。")))
        self.updated_at.setText(recent_time_text())
        self.inspector_summary.setText("优先展示关键指标卡片。JSON 详情默认折叠，可按需展开。")
        self._refresh_chart_view()

    def set_log_files(self, file_paths: list[str], summary_text: str = ""):
        self.log_list.clear()
        files = [Path(path) for path in (file_paths or [])]
        for path in files:
            label = path.name
            try:
                size_kb = path.stat().st_size / 1024.0
                label = f"{path.name}  ({size_kb:.1f} KB)"
            except Exception:
                pass
            self.log_list.addItem(label)
            self.log_list.item(self.log_list.count() - 1).setData(256, str(path))
        self.log_summary.setText(summary_text or f"共发现 {len(files)} 个日志/回放文件")
        if files and self.log_list.currentRow() < 0:
            self.log_list.setCurrentRow(0)

    def set_log_preview(self, text: str):
        self.log_preview.setPlainText(str(text or ""))


__all__ = ["AnalyzePanel", "TimeSeriesChartWidget"]
