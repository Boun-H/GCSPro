from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .panel_style import apply_tone, build_panel_stylesheet, recent_time_text, style_action_button, style_close_button


class PeripheralPanel(QFrame):
    close_clicked = pyqtSignal()
    save_requested = pyqtSignal(dict)
    rtk_inject_requested = pyqtSignal(dict)
    firmware_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setStyleSheet(build_panel_stylesheet(include_checks=True))

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 10, 10, 6)
        title_col = QVBoxLayout()
        title = QLabel("外围能力")
        title.setStyleSheet("font-size:16px; font-weight:700; color:#eef5ff;")
        subtitle = QLabel("Joystick / ADS-B / RTK / Firmware Upgrade / 插件扩展")
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

        self.summary_banner = QLabel("外围摘要: Joystick 关 | ADS-B 关 | 视频流未配置 | RTK 127.0.0.1:2101")
        self.summary_banner.setWordWrap(True)
        apply_tone(self.summary_banner, "info", padding=8, radius=8)
        main_layout.addWidget(self.summary_banner)

        self.quick_actions_summary = QLabel("快捷操作: 保存配置 / RTK 注入 / Firmware Upgrade")
        self.quick_actions_summary.setWordWrap(True)
        apply_tone(self.quick_actions_summary, "neutral", padding=7, radius=8)
        main_layout.addWidget(self.quick_actions_summary)

        quick_row = QHBoxLayout()
        self.btn_quick_save = QPushButton("保存配置")
        self.btn_quick_rtk = QPushButton("RTK 注入")
        self.btn_quick_fw = QPushButton("Firmware")
        for button, tone in [(self.btn_quick_save, "ok"), (self.btn_quick_rtk, "info"), (self.btn_quick_fw, "warn")]:
            style_action_button(button, tone, compact=True)
            quick_row.addWidget(button)
        quick_row.addStretch()
        main_layout.addLayout(quick_row)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, 1)

        config_page = QWidget()
        config_form = QFormLayout(config_page)
        config_form.setContentsMargins(12, 12, 12, 12)
        self.chk_joystick = QCheckBox("启用 Joystick")
        self.chk_adsb = QCheckBox("启用 ADS-B")
        self.video_url = QLineEdit()
        self.video_url.setPlaceholderText("视频流 URL")
        self.camera_name = QLineEdit()
        self.camera_name.setPlaceholderText("相机名称")
        self.plugin_dirs = QLineEdit()
        self.plugin_dirs.setPlaceholderText("插件目录，多个路径用 ; 分隔")
        config_form.addRow(self.chk_joystick)
        config_form.addRow(self.chk_adsb)
        config_form.addRow("视频流", self.video_url)
        config_form.addRow("相机名称", self.camera_name)
        config_form.addRow("插件目录", self.plugin_dirs)
        self.tabs.addTab(config_page, "配置")

        rtk_page = QWidget()
        rtk_form = QFormLayout(rtk_page)
        rtk_form.setContentsMargins(12, 12, 12, 12)
        self.rtk_host = QLineEdit("127.0.0.1")
        self.rtk_port = QSpinBox()
        self.rtk_port.setRange(1, 65535)
        self.rtk_port.setValue(2101)
        self.inject_lat = QDoubleSpinBox()
        self.inject_lat.setDecimals(7)
        self.inject_lat.setRange(-90.0, 90.0)
        self.inject_lon = QDoubleSpinBox()
        self.inject_lon.setDecimals(7)
        self.inject_lon.setRange(-180.0, 180.0)
        self.inject_alt = QDoubleSpinBox()
        self.inject_alt.setRange(-500.0, 10000.0)
        self.inject_alt.setValue(20.0)
        self.btn_inject = QPushButton("注入 RTK/GPS")
        rtk_form.addRow("RTK Host", self.rtk_host)
        rtk_form.addRow("RTK Port", self.rtk_port)
        rtk_form.addRow("纬度", self.inject_lat)
        rtk_form.addRow("经度", self.inject_lon)
        rtk_form.addRow("高度", self.inject_alt)
        rtk_form.addRow(self.btn_inject)
        self.tabs.addTab(rtk_page, "RTK/GPS")

        firmware_page = QWidget()
        firmware_layout = QVBoxLayout(firmware_page)
        firmware_layout.setContentsMargins(12, 12, 12, 12)
        firmware_layout.setSpacing(8)
        self.firmware_hint = QLabel("支持选择固件包、请求飞控重启到 bootloader，并进入升级流程。")
        self.firmware_hint.setWordWrap(True)
        self.btn_firmware = QPushButton("打开 Firmware Upgrade")
        self.btn_save = QPushButton("保存外围配置")
        firmware_layout.addWidget(self.firmware_hint)
        firmware_layout.addWidget(self.btn_firmware)
        firmware_layout.addWidget(self.btn_save)
        firmware_layout.addStretch()
        self.tabs.addTab(firmware_page, "Upgrade")

        self.close_btn.clicked.connect(self.close_clicked.emit)
        self.btn_firmware.clicked.connect(self.firmware_requested.emit)
        self.btn_save.clicked.connect(lambda: self.save_requested.emit(self.values()))
        self.btn_quick_save.clicked.connect(lambda: self.save_requested.emit(self.values()))
        self.btn_quick_rtk.clicked.connect(lambda: self.btn_inject.click())
        self.btn_quick_fw.clicked.connect(self.firmware_requested.emit)
        self.btn_inject.clicked.connect(lambda: self.rtk_inject_requested.emit({
            "host": self.rtk_host.text().strip(),
            "port": int(self.rtk_port.value()),
            "lat": float(self.inject_lat.value()),
            "lon": float(self.inject_lon.value()),
            "alt": float(self.inject_alt.value()),
        }))

        for button, tone in [(self.btn_inject, "info"), (self.btn_firmware, "warn"), (self.btn_save, "ok")]:
            style_action_button(button, tone, compact=True)

        for widget_signal in [
            self.chk_joystick.toggled,
            self.chk_adsb.toggled,
            self.video_url.textChanged,
            self.camera_name.textChanged,
            self.plugin_dirs.textChanged,
            self.rtk_host.textChanged,
            self.rtk_port.valueChanged,
        ]:
            widget_signal.connect(lambda *_args: self._update_summary())

        self._update_summary()

    def _update_summary(self):
        data = self.values()
        joystick = "Joystick 开" if data.get("joystick_enabled") else "Joystick 关"
        adsb = "ADS-B 开" if data.get("adsb_enabled") else "ADS-B 关"
        video = data.get("video_stream_url") or "视频流未配置"
        self.summary_banner.setText(
            f"外围摘要: {joystick} | {adsb} | {video} | RTK {data.get('rtk_host', '127.0.0.1')}:{data.get('rtk_port', 2101)}"
        )
        self.quick_actions_summary.setText("快捷操作: 保存配置 / RTK 注入 / Firmware Upgrade")
        self.updated_at.setText(recent_time_text())

    def values(self) -> dict:
        return {
            "joystick_enabled": bool(self.chk_joystick.isChecked()),
            "adsb_enabled": bool(self.chk_adsb.isChecked()),
            "video_stream_url": self.video_url.text().strip(),
            "camera_name": self.camera_name.text().strip(),
            "plugin_dirs": [item.strip() for item in self.plugin_dirs.text().split(';') if item.strip()],
            "rtk_host": self.rtk_host.text().strip(),
            "rtk_port": int(self.rtk_port.value()),
        }

    def set_values(self, values: dict | None):
        data = dict(values or {})
        self.chk_joystick.setChecked(bool(data.get("joystick_enabled", False)))
        self.chk_adsb.setChecked(bool(data.get("adsb_enabled", False)))
        self.video_url.setText(str(data.get("video_stream_url", "") or ""))
        self.camera_name.setText(str(data.get("camera_name", "") or ""))
        self.plugin_dirs.setText("; ".join(data.get("plugin_dirs", []) or []))
        self.rtk_host.setText(str(data.get("rtk_host", "127.0.0.1") or "127.0.0.1"))
        self.rtk_port.setValue(int(data.get("rtk_port", 2101) or 2101))
        self._update_summary()
