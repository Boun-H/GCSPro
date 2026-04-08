from __future__ import annotations

import json

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.health_monitor import HealthMonitor

from .panel_style import (
    apply_banner_tone,
    apply_tone,
    build_panel_stylesheet,
    recent_time_text,
    style_action_button,
    style_close_button,
    style_panel_subtitle,
    style_panel_title,
    style_timestamp_badge,
)


class FlyViewPanel(QFrame):
    close_clicked = pyqtSignal()
    guided_action_requested = pyqtSignal(str)
    camera_action_requested = pyqtSignal(str)
    video_open_requested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setStyleSheet(build_panel_stylesheet())
        self.setMinimumSize(760, 620)
        self._video_url = ""
        self._metric_cards: dict[str, QLabel] = {}
        self._last_connection_state = "未连接"
        self._last_payload: dict = {}
        self._manual_alert_text = ""

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 8, 10, 4)
        header_layout.setSpacing(8)
        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        title = QLabel("Fly View")
        style_panel_title(title, 16)
        subtitle = QLabel("飞行状态 / 任务控制 / 视频 / 相机 / 保护")
        style_panel_subtitle(subtitle, 11)
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header_layout.addLayout(title_col)
        header_layout.addStretch()
        self.updated_at = QLabel("最近更新: --:--:--")
        self.updated_at.setAlignment(Qt.AlignmentFlag.AlignCenter)
        style_timestamp_badge(self.updated_at)
        header_layout.addWidget(self.updated_at, 0, Qt.AlignmentFlag.AlignVCenter)
        self.close_btn = QPushButton("×")
        style_close_button(self.close_btn)
        header_layout.addWidget(self.close_btn)
        main_layout.addWidget(header)

        self.body_scroll = QScrollArea()
        self.body_scroll.setWidgetResizable(True)
        self.body_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.body_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        body_host = QWidget()
        body = QVBoxLayout(body_host)
        body.setContentsMargins(10, 0, 10, 10)
        body.setSpacing(10)

        self.status_summary = QLabel("载具: -- | 模式: UNKNOWN | 任务状态: 就绪")
        self.status_summary.setWordWrap(True)
        apply_banner_tone(self.status_summary, "info")
        body.addWidget(self.status_summary)

        top_split = QHBoxLayout()
        top_split.setSpacing(10)

        left_column = QWidget()
        left_layout = QVBoxLayout(left_column)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        metrics = QWidget()
        metrics_layout = QGridLayout(metrics)
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.setHorizontalSpacing(8)
        metrics_layout.setVerticalSpacing(8)
        for idx, key in enumerate(["battery", "gps", "flight", "position"]):
            label = QLabel("--")
            label.setMinimumHeight(68)
            label.setWordWrap(True)
            self._apply_card_style(label, "neutral")
            self._metric_cards[key] = label
            metrics_layout.addWidget(label, idx // 2, idx % 2)
        metrics_layout.setColumnStretch(0, 1)
        metrics_layout.setColumnStretch(1, 1)
        left_layout.addWidget(metrics)
        self._set_default_cards()

        self.connection_status = QLabel("连接状态: 未连接")
        self.mission_status = QLabel("任务执行状态: 未开始")
        self.camera_status = QLabel("相机状态: 待机")
        self.alert_status = QLabel("飞行告警: 正常")
        self.alert_status.setWordWrap(True)
        for label in [self.connection_status, self.mission_status, self.camera_status, self.alert_status]:
            label.setWordWrap(True)
            apply_banner_tone(label, "neutral")

        status_grid = QGridLayout()
        status_grid.setHorizontalSpacing(8)
        status_grid.setVerticalSpacing(8)
        status_grid.addWidget(self.connection_status, 0, 0)
        status_grid.addWidget(self.mission_status, 0, 1)
        status_grid.addWidget(self.camera_status, 1, 0)
        status_grid.addWidget(self.alert_status, 1, 1)
        status_grid.setColumnStretch(0, 1)
        status_grid.setColumnStretch(1, 1)
        left_layout.addLayout(status_grid)
        top_split.addWidget(left_column, 3)

        right_column = QWidget()
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        self.quick_actions_summary = QLabel("核心操作: 导航 / 返航 / 视频 / 相机")
        self.quick_actions_summary.setWordWrap(True)
        apply_banner_tone(self.quick_actions_summary, "neutral")
        right_layout.addWidget(self.quick_actions_summary)

        toolbar = QGridLayout()
        toolbar.setHorizontalSpacing(8)
        toolbar.setVerticalSpacing(8)
        self.btn_hold = QPushButton("Guided Hold")
        self.btn_resume = QPushButton("继续任务")
        self.btn_takeoff = QPushButton("VTOL 起飞")
        self.btn_land = QPushButton("QLAND")
        self.btn_rtl = QPushButton("QRTL")
        toolbar.addWidget(self.btn_hold, 0, 0)
        toolbar.addWidget(self.btn_resume, 0, 1)
        toolbar.addWidget(self.btn_takeoff, 1, 0)
        toolbar.addWidget(self.btn_land, 1, 1)
        toolbar.addWidget(self.btn_rtl, 2, 0, 1, 2)
        toolbar.setColumnStretch(0, 1)
        toolbar.setColumnStretch(1, 1)
        right_layout.addLayout(toolbar)

        self.media_widget = QWidget()
        media_grid = QGridLayout(self.media_widget)
        media_grid.setContentsMargins(0, 0, 0, 0)
        media_grid.setHorizontalSpacing(8)
        media_grid.setVerticalSpacing(8)
        self.video_url_edit = QLineEdit()
        self.video_url_edit.setPlaceholderText("输入 HTTP/RTSP 视频流地址")
        self.video_url_edit.setMinimumHeight(34)
        self.btn_open_video = QPushButton("打开视频")
        self.btn_copy_status = QPushButton("复制遥测")
        self.btn_snapshot = QPushButton("拍照")
        self.btn_record = QPushButton("开始录像")
        self.btn_stop_record = QPushButton("停止录像")
        self.btn_center_gimbal = QPushButton("云台回中")
        media_grid.addWidget(self.video_url_edit, 0, 0, 1, 2)
        media_grid.addWidget(self.btn_open_video, 0, 2)
        media_grid.addWidget(self.btn_copy_status, 0, 3)
        media_grid.addWidget(self.btn_snapshot, 1, 0)
        media_grid.addWidget(self.btn_record, 1, 1)
        media_grid.addWidget(self.btn_stop_record, 1, 2)
        media_grid.addWidget(self.btn_center_gimbal, 1, 3)
        for column in range(4):
            media_grid.setColumnStretch(column, 1)
        right_layout.addWidget(self.media_widget)
        top_split.addWidget(right_column, 2)

        body.addLayout(top_split)

        self.action_suggestions = QLabel("动作建议: 继续监控遥测与任务进度")
        self.action_suggestions.setWordWrap(True)
        apply_banner_tone(self.action_suggestions, "neutral")
        body.addWidget(self.action_suggestions)

        self.btn_toggle_json = QPushButton("展开遥测 JSON")
        style_action_button(self.btn_toggle_json, "info", compact=True)
        self.telemetry_json = QPlainTextEdit()
        self.telemetry_json.setReadOnly(True)
        self.telemetry_json.setPlaceholderText("这里显示当前遥测 JSON 快照")
        self.telemetry_json.hide()
        body.addWidget(self.btn_toggle_json)
        body.addWidget(self.telemetry_json)
        body.addStretch()

        self.body_scroll.setWidget(body_host)
        main_layout.addWidget(self.body_scroll, 1)

        self.close_btn.clicked.connect(self.close_clicked.emit)
        self.btn_hold.clicked.connect(lambda: self.guided_action_requested.emit("guided_hold"))
        self.btn_resume.clicked.connect(lambda: self.guided_action_requested.emit("guided_resume"))
        self.btn_takeoff.clicked.connect(lambda: self.guided_action_requested.emit("vtol_takeoff_30m"))
        self.btn_land.clicked.connect(lambda: self.guided_action_requested.emit("vtol_qland"))
        self.btn_rtl.clicked.connect(lambda: self.guided_action_requested.emit("vtol_qrtl"))
        self.btn_open_video.clicked.connect(lambda: self.video_open_requested.emit(self.video_url_edit.text().strip()))
        self.btn_copy_status.clicked.connect(self._copy_snapshot)
        self.btn_toggle_json.clicked.connect(self._toggle_json_visibility)
        self.btn_snapshot.clicked.connect(lambda: self.camera_action_requested.emit("snapshot"))
        self.btn_record.clicked.connect(lambda: self.camera_action_requested.emit("record_start"))
        self.btn_stop_record.clicked.connect(lambda: self.camera_action_requested.emit("record_stop"))
        self.btn_center_gimbal.clicked.connect(lambda: self.camera_action_requested.emit("gimbal_center"))

        for button, tone in [
            (self.btn_hold, "info"),
            (self.btn_resume, "ok"),
            (self.btn_takeoff, "info"),
            (self.btn_land, "warn"),
            (self.btn_rtl, "danger"),
            (self.btn_open_video, "info"),
            (self.btn_copy_status, "ok"),
            (self.btn_snapshot, "info"),
            (self.btn_record, "warn"),
            (self.btn_stop_record, "danger"),
            (self.btn_center_gimbal, "neutral"),
        ]:
            style_action_button(button, tone, compact=True)
            button.setMinimumHeight(max(button.minimumHeight(), 34))
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._refresh_interaction_state()

    def _apply_card_style(self, label: QLabel, tone: str = "neutral"):
        apply_tone(label, tone, padding=8, radius=8)

    def _set_card(self, key: str, title: str, value: str, tone: str = "neutral"):
        label = self._metric_cards.get(key)
        if label is None:
            return
        self._apply_card_style(label, tone)
        label.setText(f"<b>{title}</b><br>{value}")

    def _set_default_cards(self):
        self._set_card("battery", "电池 / 电压", "--", "neutral")
        self._set_card("gps", "GPS / 模式", "--", "neutral")
        self._set_card("flight", "高度 / 速度", "--", "neutral")
        self._set_card("position", "位置", "--", "neutral")

    def _copy_snapshot(self):
        text = self.telemetry_json.toPlainText().strip()
        if text:
            QApplication.clipboard().setText(text)
            self.set_alert_text("已复制遥测快照")

    def _toggle_json_visibility(self):
        visible = not self.telemetry_json.isVisible()
        self.telemetry_json.setVisible(visible)
        self.btn_toggle_json.setText("收起遥测 JSON" if visible else "展开遥测 JSON")

    def _refresh_interaction_state(self):
        is_connected = self._last_connection_state not in {"未连接", "disconnected"}
        show_secondary = is_connected
        self.media_widget.setVisible(show_secondary)
        self.btn_toggle_json.setVisible(show_secondary)
        if not show_secondary:
            self.telemetry_json.hide()
            self.btn_toggle_json.setText("展开遥测 JSON")
        self.quick_actions_summary.setText(
            "核心操作: 导航 / 返航 / 视频 / 相机" if is_connected else "核心操作: 连接后解锁视频 / 相机 / 遥测详情"
        )
        for button in [self.btn_hold, self.btn_resume, self.btn_takeoff, self.btn_land, self.btn_rtl]:
            button.setEnabled(is_connected)

    def _refresh_alert_guidance(self):
        report = HealthMonitor.evaluate(
            self._last_payload,
            connection_state=self._last_connection_state,
            manual_alert_text=self._manual_alert_text,
        )
        self.alert_status.setText(str(report.get("alert_text", "飞行告警: 正常")))
        self.action_suggestions.setText(str(report.get("action_text", "动作建议: 继续监控遥测与任务进度")))
        connection_tone = "ok" if "已连接" in self._last_connection_state else "warn" if "连接" in self._last_connection_state else "danger"
        suggestion_tone = str(report.get("suggestion_tone", "ok"))
        apply_banner_tone(self.connection_status, connection_tone)
        apply_banner_tone(self.mission_status, "info")
        apply_banner_tone(self.camera_status, "neutral")
        apply_banner_tone(self.alert_status, suggestion_tone)
        apply_banner_tone(self.action_suggestions, suggestion_tone)
        style_action_button(self.btn_rtl, "danger" if suggestion_tone == "danger" else "warn" if suggestion_tone == "warn" else "danger", compact=True)
        self.btn_rtl.setText("⚠ QRTL" if suggestion_tone == "danger" else "QRTL")
        self.btn_rtl.setMinimumHeight(max(self.btn_rtl.minimumHeight(), 34))
        self._refresh_interaction_state()

    def set_video_url(self, url: str):
        self._video_url = str(url or "")
        self.video_url_edit.setText(self._video_url)

    def set_vehicle_summary(self, vehicle_id: str, mode: str, mission_text: str, link_name: str = ""):
        link = f" @ {link_name}" if link_name else ""
        self.status_summary.setText(f"载具: {vehicle_id or '--'}{link} | 模式: {mode or 'UNKNOWN'} | {mission_text or '任务状态: 就绪'}")
        self.quick_actions_summary.setText("快捷操作: Guided Hold / QRTL / 打开视频 / 相机控制")

    def set_connection_state(self, text: str):
        self._last_connection_state = str(text or "未连接")
        self.connection_status.setText(f"连接状态: {self._last_connection_state}")
        self._refresh_interaction_state()
        self._refresh_alert_guidance()

    def set_mission_status(self, text: str):
        self.mission_status.setText(f"任务执行状态: {text}")

    def set_camera_status(self, text: str):
        self.camera_status.setText(f"相机状态: {text}")

    def set_alert_text(self, text: str):
        self._manual_alert_text = str(text or "").strip()
        self._refresh_alert_guidance()

    def set_status_payload(self, payload: dict | None):
        data = dict(payload or {})
        self._last_payload = dict(data)
        preview = HealthMonitor.telemetry_preview(data)
        report = HealthMonitor.evaluate(
            data,
            connection_state=self._last_connection_state,
            manual_alert_text=self._manual_alert_text,
        )

        battery = int(preview["battery"])
        gps = int(preview["gps"])
        alt = float(preview["alt"])
        vel = float(preview["vel"])
        volt = float(preview["volt"])
        mode = str(preview["mode"])
        lat = preview.get("lat")
        lon = preview.get("lon")

        self._set_card("battery", "电池 / 电压", f"{battery}%<br>{volt:.2f} V", str(report.get("battery_tone", "ok")))
        self._set_card("gps", "GPS / 模式", f"{gps} 颗<br>{mode}", str(report.get("gps_tone", "ok")))
        self._set_card("flight", "高度 / 速度", f"{alt:.1f} m<br>{vel:.1f} m/s", str(report.get("flight_tone", "neutral")))
        if lat is not None and lon is not None:
            self._set_card("position", "位置", f"{float(lat):.6f}<br>{float(lon):.6f}", "info")
        else:
            self._set_card("position", "位置", "--", "neutral")

        self.telemetry_json.setPlainText(json.dumps(preview, ensure_ascii=False, indent=2))
        self.updated_at.setText(recent_time_text())
        self._refresh_alert_guidance()


__all__ = ["FlyViewPanel"]

