from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.setup_wizard_service import SetupWizardService

from .panel_style import apply_tone, build_panel_stylesheet, recent_time_text, style_action_button, style_close_button


class VehicleSetupPanel(QFrame):
    close_clicked = pyqtSignal()
    param_focus_requested = pyqtSignal(str, str)
    firmware_requested = pyqtSignal()

    _SECTION_META = {
        "wizard": ("Calibration Wizard", "分步骤完成整机校准与飞前检查", "全部", "", "按照引导逐步完成基础配置、校准和飞前确认。"),
        "firmware": ("Firmware", "固件版本与升级入口", "全部", "", "核对镜像、校验 CRC，并请求进入 bootloader。"),
        "summary": ("Summary", "整机摘要与识别信息", "全部", "", "建议先完成 Airframe / Sensors / Safety 三项基础检查。"),
        "airframe": ("Airframe", "机型 / 机架 / VTOL 相关参数", "Q", "VTOL", "重点检查 VTOL、机架类型、推力与过渡参数。"),
        "sensors": ("Sensors", "GPS / 罗盘 / IMU / 校准相关", "GPS", "COMPASS", "优先完成 GPS、Compass、IMU 校准，并确认卫星质量。"),
        "radio": ("Radio", "RC / Servo / 通道映射", "SERVO", "RC", "检查通道反向、死区、输出限位与失控保护。"),
        "flight_modes": ("Flight Modes", "飞行模式与任务模式配置", "MIS", "MODE", "为 VTOL 配置 QLOITER / QRTL / AUTO 等常用模式。"),
        "power": ("Power", "电池、电源与电压监测", "BATT", "BATT", "核对电池容量、电压告警阈值和电流传感器。"),
        "safety": ("Safety", "解锁、围栏、失控保护", "ARMING", "FAILSAFE", "确认解锁检查、围栏高度、RC/数据链失控动作。"),
        "motors": ("Motors", "电机输出与舵机控制", "SERVO", "MOT", "检查电机输出顺序、舵机方向、PWM 范围。"),
        "tuning": ("Tuning", "位置控制、导航与调参", "PSC", "WPNAV", "围绕 PSC / WPNAV / Q 参数做位置与速度调优。"),
    }

    def __init__(self):
        super().__init__()
        self._section_labels: dict[str, QLabel] = {}
        self._section_hints: dict[str, QLabel] = {}
        self._overview_cards: dict[str, QLabel] = {}
        self._nav_buttons: dict[str, QPushButton] = {}
        self._tab_index_map: dict[str, int] = {}
        self._wizard_steps: dict[str, QLabel] = {}
        self.wizard_summary: QLabel | None = None
        self.wizard_progress: QProgressBar | None = None
        self.setStyleSheet(build_panel_stylesheet())

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 10, 10, 6)
        title_col = QVBoxLayout()
        title = QLabel("Vehicle Setup")
        title.setStyleSheet("font-size:16px; font-weight:700; color:#eef5ff;")
        subtitle = QLabel("Firmware / Airframe / Sensors / Radio / Safety / Tuning")
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

        overview_box = QWidget()
        overview_layout = QVBoxLayout(overview_box)
        overview_layout.setContentsMargins(10, 0, 10, 0)
        overview_layout.setSpacing(8)
        self.overview_banner = QLabel("当前未选择载具，请先连接并选择目标飞行器。")
        self.overview_banner.setWordWrap(True)
        apply_tone(self.overview_banner, "info", padding=8, radius=8)
        overview_layout.addWidget(self.overview_banner)

        self.quick_actions_summary = QLabel("快捷操作: 固件升级 / Sensors 校准 / Safety 检查 / 参数跳转")
        self.quick_actions_summary.setWordWrap(True)
        apply_tone(self.quick_actions_summary, "neutral", padding=7, radius=8)
        overview_layout.addWidget(self.quick_actions_summary)

        quick_row = QHBoxLayout()
        self.btn_quick_firmware = QPushButton("固件升级")
        self.btn_quick_sensors = QPushButton("Sensors")
        self.btn_quick_power = QPushButton("Power")
        self.btn_quick_safety = QPushButton("Safety")
        for button, tone in [
            (self.btn_quick_firmware, "info"),
            (self.btn_quick_sensors, "ok"),
            (self.btn_quick_power, "warn"),
            (self.btn_quick_safety, "danger"),
        ]:
            style_action_button(button, tone, compact=True)
            quick_row.addWidget(button)
        quick_row.addStretch()
        overview_layout.addLayout(quick_row)

        cards = QWidget()
        cards_layout = QGridLayout(cards)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setHorizontalSpacing(8)
        cards_layout.setVerticalSpacing(8)
        for idx, key in enumerate(["vehicle", "link", "battery", "sensors"]):
            label = QLabel()
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            label.setWordWrap(True)
            label.setMinimumHeight(54)
            self._apply_card_style(label, "neutral")
            self._overview_cards[key] = label
            cards_layout.addWidget(label, idx // 2, idx % 2)
        overview_layout.addWidget(cards)
        main_layout.addWidget(overview_box)

        nav_row = QWidget()
        nav_layout = QHBoxLayout(nav_row)
        nav_layout.setContentsMargins(10, 0, 10, 0)
        nav_layout.setSpacing(6)
        for key, (title_text, _, _, _, _) in self._SECTION_META.items():
            btn = QPushButton(title_text)
            btn.clicked.connect(lambda _=False, section=key: self.open_section(section))
            self._nav_buttons[key] = btn
            nav_layout.addWidget(btn)
        main_layout.addWidget(nav_row)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, 1)

        for index, (key, (title_text, description, group_name, search_text, tip_text)) in enumerate(self._SECTION_META.items()):
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(8)

            heading = QLabel(title_text)
            heading.setStyleSheet("font-size:15px; font-weight:700; color:#eef5ff;")
            summary = QLabel(description)
            summary.setWordWrap(True)
            summary.setStyleSheet("color:#c7d9ef; background:#142133; border-radius:6px; padding:8px;")
            tip = QLabel(f"建议：{tip_text}\n推荐参数分组：{group_name}{' / ' + search_text if search_text else ''}")
            tip.setWordWrap(True)
            tip.setStyleSheet("color:#8fb1d6; background:#101a28; border:1px solid #23384f; border-radius:6px; padding:8px;")
            self._section_labels[key] = summary
            self._section_hints[key] = tip

            layout.addWidget(heading)
            layout.addWidget(summary)
            layout.addWidget(tip)

            if key == "wizard":
                self.wizard_summary = QLabel("校准向导将在连接后根据当前载具状态给出下一步建议。")
                self.wizard_summary.setWordWrap(True)
                self.wizard_summary.setStyleSheet("background:#142133; color:#dbeafe; border-radius:8px; padding:8px;")
                layout.addWidget(self.wizard_summary)

                self.wizard_progress = QProgressBar()
                self.wizard_progress.setRange(0, 100)
                self.wizard_progress.setValue(0)
                self.wizard_progress.setFormat("校准进度 %p%")
                layout.addWidget(self.wizard_progress)

                step_box = QWidget()
                step_layout = QVBoxLayout(step_box)
                step_layout.setContentsMargins(0, 0, 0, 0)
                step_layout.setSpacing(6)
                for step_key, step_title in [
                    ("firmware", "Firmware / Airframe 检查"),
                    ("sensors", "Sensors 校准"),
                    ("radio", "Radio / Servo 检查"),
                    ("power", "Power 健康检查"),
                    ("safety", "Safety / Failsafe 检查"),
                    ("mission", "Mission / 飞前准备"),
                ]:
                    label = QLabel(f"• {step_title}: 待处理")
                    label.setWordWrap(True)
                    label.setStyleSheet("background:#101a28; border:1px solid #23384f; border-radius:6px; padding:6px 8px; color:#c7d9ef;")
                    self._wizard_steps[step_key] = label
                    step_layout.addWidget(label)
                layout.addWidget(step_box)

                quick_actions = QHBoxLayout()
                for label_text, group, search in [
                    ("校准 Sensors", "GPS", "COMPASS"),
                    ("检查 Radio", "SERVO", "RC"),
                    ("检查 Power", "BATT", "BATT"),
                    ("检查 Safety", "ARMING", "FAILSAFE"),
                ]:
                    button = QPushButton(label_text)
                    style_action_button(button, "info", compact=True)
                    button.clicked.connect(lambda _=False, g=group, s=search: self.param_focus_requested.emit(g, s))
                    quick_actions.addWidget(button)
                quick_actions.addStretch()
                layout.addLayout(quick_actions)
            else:
                actions = QHBoxLayout()
                btn_params = QPushButton(f"打开 {group_name} 参数")
                style_action_button(btn_params, "info", compact=True)
                btn_params.clicked.connect(lambda _=False, g=group_name, s=search_text: self.param_focus_requested.emit(g, s))
                actions.addWidget(btn_params)
                if key == "firmware":
                    btn_fw = QPushButton("固件升级")
                    style_action_button(btn_fw, "warn", compact=True)
                    btn_fw.clicked.connect(self.firmware_requested.emit)
                    actions.addWidget(btn_fw)
                actions.addStretch()
                layout.addLayout(actions)

            layout.addStretch()
            self.tabs.addTab(page, title_text)
            self._tab_index_map[key] = index

        self.tabs.currentChanged.connect(self._sync_nav_state_from_tabs)
        self.close_btn.clicked.connect(self.close_clicked.emit)
        self.btn_quick_firmware.clicked.connect(self.firmware_requested.emit)
        self.btn_quick_sensors.clicked.connect(lambda: self.param_focus_requested.emit("GPS", "COMPASS"))
        self.btn_quick_power.clicked.connect(lambda: self.param_focus_requested.emit("BATT", "BATT"))
        self.btn_quick_safety.clicked.connect(lambda: self.param_focus_requested.emit("ARMING", "FAILSAFE"))
        self._set_default_overview()
        self._refresh_wizard({})
        self.open_section("summary")

    def _apply_card_style(self, label: QLabel, tone: str = "neutral"):
        apply_tone(label, tone, padding=8, radius=8)

    def _set_card_text(self, key: str, title: str, value: str, tone: str = "neutral"):
        label = self._overview_cards.get(key)
        if label is None:
            return
        self._apply_card_style(label, tone)
        label.setText(f"<b>{title}</b><br>{value}")

    def _set_default_overview(self):
        self._set_card_text("vehicle", "载具", "--", "neutral")
        self._set_card_text("link", "链路 / 模式", "--", "neutral")
        self._set_card_text("battery", "电池 / 电压", "--", "neutral")
        self._set_card_text("sensors", "GPS / 安全", "--", "neutral")

    def _sync_nav_state(self, active_key: str):
        for key, button in self._nav_buttons.items():
            button.setProperty("active", "true" if key == active_key else "false")
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def _sync_nav_state_from_tabs(self, index: int):
        for key, tab_index in self._tab_index_map.items():
            if tab_index == index:
                self._sync_nav_state(key)
                break

    def _set_wizard_step(self, step_key: str, title: str, done: bool, detail: str):
        label = self._wizard_steps.get(step_key)
        if label is None:
            return
        state_text = "已完成" if done else "待处理"
        apply_tone(label, "ok" if done else "warn", padding=6, radius=6)
        label.setText(f"• {title}: {state_text}\n{detail}")

    def _refresh_wizard(self, vehicle: dict | None):
        report = SetupWizardService.evaluate(vehicle)
        for step in report.get("steps", []):
            self._set_wizard_step(
                str(step.get("key", "")),
                str(step.get("title", "")),
                bool(step.get("done", False)),
                str(step.get("detail", "")),
            )

        if self.wizard_progress is not None:
            self.wizard_progress.setValue(int(report.get("progress_value", 0) or 0))

        summary_text = str(report.get("summary_text", "校准向导将在连接后根据当前载具状态给出下一步建议。"))
        if self.wizard_summary is not None:
            self.wizard_summary.setText(summary_text)
        if "wizard" in self._section_labels:
            self._section_labels["wizard"].setText(summary_text)
        if "wizard" in self._section_hints:
            self._section_hints["wizard"].setText(str(report.get("hint_text", "建议：按顺序完成上述步骤。")))

    def open_section(self, section_key: str):
        key = str(section_key or "summary").strip().lower()
        index = self._tab_index_map.get(key)
        if index is not None:
            self.tabs.setCurrentIndex(index)
            self._sync_nav_state(key)

    def set_vehicle(self, vehicle: dict | None):
        item = dict(vehicle or {})
        info = SetupWizardService.describe_vehicle(item)
        vehicle_id = info["vehicle_id"]
        mode = info["mode"]
        battery = info["battery"]
        gps = info["gps"]
        volt = info["volt"]
        firmware = info["firmware"]
        plugin = info["plugin"]
        link_name = info["link_name"]
        queue_depth = info["queue_depth"]
        mission_count = info["mission_count"]
        params_total = info["params_total"]
        home_set = info["home_set"]
        safety_text = info["safety_text"]

        self.updated_at.setText(recent_time_text())
        self.overview_banner.setText(info["overview_banner"])
        self.quick_actions_summary.setText(info["quick_actions"])
        self._set_card_text("vehicle", "载具", f"{vehicle_id}<br>{firmware}", "info")
        self._set_card_text("link", "链路 / 模式", f"{link_name}<br>{mode}", info["mode_tone"])
        self._set_card_text("battery", "电池 / 电压", f"{battery}%<br>{volt:.2f} V", info["battery_tone"])
        self._set_card_text("sensors", "GPS / 安全", f"{gps} 颗<br>{safety_text}", info["gps_tone"])

        self._section_labels["firmware"].setText(
            f"载具 {vehicle_id}\n固件: {firmware}\n自动驾驶仪: {plugin}\n可在此执行镜像校验、进入 bootloader 与升级流程。"
        )
        self._section_labels["summary"].setText(
            f"载具: {vehicle_id}\n模式: {mode}\n电池: {battery}%\nGPS: {gps} 颗\n链路: {link_name}\n参数缓存: {params_total} 项\n任务点: {mission_count}"
        )
        self._section_labels["airframe"].setText(
            f"当前机型与 VTOL 相关参数可在 Q / VTOL 分组中管理。\n载具: {vehicle_id} | 模式: {mode}\n建议重点核对过渡参数、巡航速度与垂起配置。"
        )
        self._section_labels["sensors"].setText(
            f"传感器概览：GPS {gps} 颗，电压 {volt:.2f}V。\n若 GPS 数量偏低或方向异常，建议重新做 Compass / IMU 校准。"
        )
        self._section_labels["radio"].setText(
            f"RC / Servo / 通道映射通过参数分组集中管理。\n当前链路: {link_name}，建议检查 RC 映射与输出限幅。"
        )
        self._section_labels["flight_modes"].setText(
            f"当前模式：{mode}\n可跳转查看 MODE / MIS 参数与任务执行配置。\n建议保留 QLOITER、AUTO、QRTL 等常用模式。"
        )
        self._section_labels["power"].setText(
            f"电池剩余：{battery}%\n电压：{volt:.2f}V\n电压/电源阈值可在 BATT 分组中统一配置。"
        )
        self._section_labels["safety"].setText(
            f"安全项包含 ARMING、FAILSAFE、围栏与返航规则。\n当前状态：{safety_text}。"
        )
        self._section_labels["motors"].setText(
            "电机/舵机输出、PWM、通道反向等集中在 SERVO/MOT 分组。\n建议在解锁前完成输出方向检查。"
        )
        self._section_labels["tuning"].setText(
            "调参入口聚焦 PSC / WPNAV / Q 分组，适合位置控制与 VTOL 调优。\n建议结合 Analyze 面板查看高度/速度趋势。"
        )

        self._section_hints["summary"].setText(
            f"建议：先完成基础检查，再进入飞行测试。\nHome: {'已设置' if home_set else '未设置'} | 队列: {queue_depth} | 参数缓存: {params_total}"
        )
        self._section_hints["power"].setText(
            f"建议：低于 45% 进入重点关注，低于 25% 应停止测试。\n当前电池 {battery}% / {volt:.2f}V"
        )
        self._section_hints["sensors"].setText(
            f"建议：GPS ≥ 10 颗为较佳，6~9 颗需关注，<6 建议暂停执行任务。\n当前 GPS: {gps}"
        )
        self._section_hints["firmware"].setText(
            f"建议：升级前确认镜像与机型匹配，并备份关键参数。\n当前固件：{firmware} / {plugin}"
        )
        self._section_hints["safety"].setText(
            f"建议：核对 ARMING、围栏、失控保护。\n{('已设置返航 Home，可执行更完整安全检查。' if home_set else '尚未设置 Home，建议先下载/确认 Home 点。')}"
        )

        for key, label in self._section_hints.items():
            if key not in {"wizard", "summary", "power", "sensors", "firmware", "safety"}:
                base = self._SECTION_META[key][4]
                label.setText(f"建议：{base}\n推荐参数分组：{self._SECTION_META[key][2]}{' / ' + self._SECTION_META[key][3] if self._SECTION_META[key][3] else ''}")

        if vehicle_id == "--":
            self.overview_banner.setText("当前未选择载具，请先连接并在多机管理中选择目标飞行器。")
            self.quick_actions_summary.setText("快捷操作: 固件升级 / Sensors 校准 / Safety 检查 / 参数跳转")
            self._set_default_overview()
            self._refresh_wizard({})
        else:
            self._refresh_wizard(item)

        self._sync_nav_state_from_tabs(self.tabs.currentIndex())


__all__ = ["VehicleSetupPanel"]
