from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class VehiclePanel(QFrame):
    close_clicked = pyqtSignal()
    vehicle_selected = pyqtSignal(str)
    open_params_requested = pyqtSignal(str)
    open_mission_requested = pyqtSignal(str)
    command_requested = pyqtSignal(str, str)
    batch_command_requested = pyqtSignal(str, list)
    clear_queue_requested = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self._active_vehicle_id = ""
        self.setMinimumSize(680, 700)
        self.setStyleSheet(
            "QFrame { background:#121d2d; border:1px solid #2a4362; border-radius:10px; }"
            "QLabel { color:#d9e6f8; }"
            "QPushButton { background:#1e3a5a; color:#d9e6f8; border:1px solid #35506b; border-radius:8px; padding:6px 10px; }"
            "QPushButton:hover { background:#264b73; }"
            "QListWidget { background:#0f1926; color:#d9e6f8; border:1px solid #27415f; border-radius:8px; }"
            "QTabWidget::pane { border:1px solid #27415f; background:#0f1926; border-radius:8px; }"
            "QTabBar::tab { background:#162233; color:#d9e6f8; padding:6px 12px; margin-right:2px; border-top-left-radius:6px; border-top-right-radius:6px; }"
            "QTabBar::tab:selected { background:#1f6fb2; }"
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 10, 10, 6)
        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(2)
        title = QLabel("Vehicle 视图")
        title.setStyleSheet("font-size:16px; font-weight:700; color:#eef5ff;")
        subtitle = QLabel("QGC 风格多机概览 / 参数页 / 任务页 / 控制")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size:12px; color:#9fb4cf;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        top_layout.addLayout(title_col)
        top_layout.addStretch()
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setStyleSheet("background:#24364d; color:#d2dff1; border:1px solid #324b68; border-radius:6px;")
        top_layout.addWidget(self.close_btn)
        main_layout.addWidget(top_bar)

        content = QVBoxLayout()
        content.setContentsMargins(10, 0, 10, 10)
        content.setSpacing(8)

        self.summary_label = QLabel("未发现载具")
        self.summary_label.setStyleSheet("color:#9fb4cf;")
        content.addWidget(self.summary_label)

        self.vehicle_list = QListWidget()
        self.vehicle_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.vehicle_list.setMinimumHeight(180)
        content.addWidget(self.vehicle_list)

        action_row = QHBoxLayout()
        self.btn_activate = QPushButton("设为当前")
        self.btn_open_params = QPushButton("参数页")
        self.btn_open_mission = QPushButton("任务页")
        action_row.addWidget(self.btn_activate)
        action_row.addWidget(self.btn_open_params)
        action_row.addWidget(self.btn_open_mission)
        action_row.addStretch()
        content.addLayout(action_row)

        self.tabs = QTabWidget()
        content.addWidget(self.tabs, 1)

        overview = QWidget()
        overview_layout = QVBoxLayout(overview)
        overview_layout.setContentsMargins(10, 10, 10, 10)
        overview_layout.setSpacing(6)
        self.detail_vehicle = QLabel("载具: --")
        self.detail_link = QLabel("链路: --")
        self.detail_plugin = QLabel("插件: --")
        self.detail_mode = QLabel("模式: --")
        self.detail_battery = QLabel("电池/GPS: --")
        self.detail_position = QLabel("位置: --")
        self.detail_position.setWordWrap(True)
        for label in [self.detail_vehicle, self.detail_link, self.detail_plugin, self.detail_mode, self.detail_battery, self.detail_position]:
            label.setStyleSheet("color:#d9e6f8; border:none; background:transparent;")
            overview_layout.addWidget(label)
        overview_layout.addStretch()
        self.tabs.addTab(overview, "概览")

        params_tab = QWidget()
        params_layout = QVBoxLayout(params_tab)
        params_layout.setContentsMargins(10, 10, 10, 10)
        params_layout.setSpacing(6)
        self.params_title = QLabel("参数页摘要")
        self.params_total = QLabel("参数总数: --")
        self.params_modified = QLabel("已修改: --")
        self.params_hint = QLabel("切换到该机可恢复独立参数缓存")
        self.params_hint.setWordWrap(True)
        for label in [self.params_title, self.params_total, self.params_modified, self.params_hint]:
            label.setStyleSheet("color:#d9e6f8; border:none; background:transparent;")
            params_layout.addWidget(label)
        params_layout.addStretch()
        self.tabs.addTab(params_tab, "参数页")

        mission_tab = QWidget()
        mission_layout = QVBoxLayout(mission_tab)
        mission_layout.setContentsMargins(10, 10, 10, 10)
        mission_layout.setSpacing(6)
        self.mission_title = QLabel("任务页摘要")
        self.mission_count = QLabel("任务航点: --")
        self.auto_route_count = QLabel("自动航线段: --")
        self.home_state = QLabel("H点: --")
        self.mission_hint = QLabel("切换到该机可恢复独立任务上下文")
        self.mission_hint.setWordWrap(True)
        for label in [self.mission_title, self.mission_count, self.auto_route_count, self.home_state, self.mission_hint]:
            label.setStyleSheet("color:#d9e6f8; border:none; background:transparent;")
            mission_layout.addWidget(label)
        mission_layout.addStretch()
        self.tabs.addTab(mission_tab, "任务页")

        control_tab = QWidget()
        control_layout = QVBoxLayout(control_tab)
        control_layout.setContentsMargins(10, 10, 10, 10)
        control_layout.setSpacing(8)
        self.control_hint = QLabel("当前选中载具的快捷控制入口")
        self.control_hint.setStyleSheet("color:#9fb4cf; border:none; background:transparent;")
        control_layout.addWidget(self.control_hint)

        self.batch_selection = QLabel("批量选择: 0 架")
        self.batch_selection.setStyleSheet("color:#9fb4cf; border:none; background:transparent;")
        control_layout.addWidget(self.batch_selection)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        self.btn_arm = QPushButton("ARM")
        self.btn_disarm = QPushButton("DISARM")
        self.btn_takeoff = QPushButton("VTOL 起飞")
        self.btn_rtl = QPushButton("QRTL")
        grid.addWidget(self.btn_arm, 0, 0)
        grid.addWidget(self.btn_disarm, 0, 1)
        grid.addWidget(self.btn_takeoff, 1, 0)
        grid.addWidget(self.btn_rtl, 1, 1)
        control_layout.addLayout(grid)

        batch_row = QHBoxLayout()
        self.btn_batch_arm = QPushButton("批量 ARM")
        self.btn_batch_disarm = QPushButton("批量 DISARM")
        self.btn_batch_takeoff = QPushButton("批量起飞")
        self.btn_batch_qland = QPushButton("批量 QLAND")
        self.btn_batch_rtl = QPushButton("批量 QRTL")
        self.btn_clear_queue = QPushButton("清空队列")
        batch_row.addWidget(self.btn_batch_arm)
        batch_row.addWidget(self.btn_batch_disarm)
        batch_row.addWidget(self.btn_batch_takeoff)
        batch_row.addWidget(self.btn_batch_qland)
        batch_row.addWidget(self.btn_batch_rtl)
        batch_row.addWidget(self.btn_clear_queue)
        control_layout.addLayout(batch_row)

        self.queue_state = QLabel("队列状态: 当前为空")
        self.queue_state.setWordWrap(True)
        self.queue_state.setStyleSheet("color:#c7d9ef; border:none; background:transparent;")
        control_layout.addWidget(self.queue_state)
        control_layout.addStretch()
        self.tabs.addTab(control_tab, "控制")

        main_layout.addLayout(content)

        self.close_btn.clicked.connect(self.close_clicked.emit)
        self.btn_activate.clicked.connect(self._emit_selected_vehicle)
        self.btn_open_params.clicked.connect(self._emit_open_params)
        self.btn_open_mission.clicked.connect(self._emit_open_mission)
        self.btn_arm.clicked.connect(lambda: self._emit_command("arm"))
        self.btn_disarm.clicked.connect(lambda: self._emit_command("disarm"))
        self.btn_takeoff.clicked.connect(lambda: self._emit_command("vtol_takeoff_30m"))
        self.btn_rtl.clicked.connect(lambda: self._emit_command("vtol_qrtl"))
        self.btn_batch_arm.clicked.connect(lambda: self._emit_batch_command("arm"))
        self.btn_batch_disarm.clicked.connect(lambda: self._emit_batch_command("disarm"))
        self.btn_batch_takeoff.clicked.connect(lambda: self._emit_batch_command("vtol_takeoff_30m"))
        self.btn_batch_qland.clicked.connect(lambda: self._emit_batch_command("vtol_qland"))
        self.btn_batch_rtl.clicked.connect(lambda: self._emit_batch_command("vtol_qrtl"))
        self.btn_clear_queue.clicked.connect(self._emit_clear_queue)
        self.vehicle_list.itemSelectionChanged.connect(self._emit_selected_vehicle)

    def _selected_vehicle_id(self) -> str:
        item = self.vehicle_list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole) or "").strip() if item is not None else ""

    def _selected_vehicle_ids(self) -> list[str]:
        vehicle_ids = []
        for item in self.vehicle_list.selectedItems():
            vehicle_id = str(item.data(Qt.ItemDataRole.UserRole) or "").strip()
            if vehicle_id:
                vehicle_ids.append(vehicle_id)
        return vehicle_ids

    def _emit_selected_vehicle(self):
        selected_ids = self._selected_vehicle_ids()
        self.batch_selection.setText(f"批量选择: {len(selected_ids)} 架")
        vehicle_id = self._selected_vehicle_id() or (selected_ids[0] if selected_ids else "")
        if vehicle_id:
            self.vehicle_selected.emit(vehicle_id)

    def _emit_open_params(self):
        vehicle_id = self._selected_vehicle_id() or self._active_vehicle_id
        if vehicle_id:
            self.open_params_requested.emit(vehicle_id)

    def _emit_open_mission(self):
        vehicle_id = self._selected_vehicle_id() or self._active_vehicle_id
        if vehicle_id:
            self.open_mission_requested.emit(vehicle_id)

    def _emit_command(self, command_name: str):
        vehicle_id = self._selected_vehicle_id() or self._active_vehicle_id
        if vehicle_id:
            self.command_requested.emit(vehicle_id, str(command_name or ""))

    def _emit_batch_command(self, command_name: str):
        vehicle_ids = self._selected_vehicle_ids()
        if vehicle_ids:
            self.batch_command_requested.emit(str(command_name or ""), vehicle_ids)

    def _emit_clear_queue(self):
        vehicle_ids = self._selected_vehicle_ids()
        if vehicle_ids:
            self.clear_queue_requested.emit(vehicle_ids)

    def set_vehicle_summaries(self, vehicles: list[dict], active_vehicle_id: str = ""):
        self._active_vehicle_id = str(active_vehicle_id or "")
        self.vehicle_list.blockSignals(True)
        self.vehicle_list.clear()
        for vehicle in vehicles or []:
            vehicle_id = str(vehicle.get("vehicle_id", "--"))
            marker = "★ " if vehicle_id == self._active_vehicle_id else ""
            connected = "在线" if vehicle.get("connected") else "离线"
            text = (
                f"{marker}{vehicle_id} | {vehicle.get('mode', 'UNKNOWN')} | "
                f"电池 {vehicle.get('battery_remaining', 0)}% | 参数 {vehicle.get('params_total', 0)} | 任务 {vehicle.get('mission_count', 0)} | {connected}"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, vehicle_id)
            self.vehicle_list.addItem(item)
            if vehicle_id == self._active_vehicle_id:
                item.setSelected(True)
                self.vehicle_list.setCurrentItem(item)

        total = len(vehicles or [])
        online = sum(1 for vehicle in (vehicles or []) if vehicle.get("connected"))
        queue_lines = []
        for vehicle in vehicles or []:
            pending = [str(item) for item in (vehicle.get("pending_commands") or []) if str(item or "").strip()]
            if pending:
                queue_lines.append(f"{vehicle.get('vehicle_id', '--')}: {' → '.join(pending)}")
        self.summary_label.setText(f"已发现 {total} 架载具 / 在线 {online} 架")
        self.queue_state.setText("队列状态: 当前为空" if not queue_lines else "队列状态:\n" + "\n".join(queue_lines))
        self.batch_selection.setText(f"批量选择: {len(self._selected_vehicle_ids())} 架")
        self.vehicle_list.blockSignals(False)

    def set_active_vehicle(self, vehicle: dict | None):
        vehicle = dict(vehicle or {})
        self._active_vehicle_id = str(vehicle.get("vehicle_id", "") or "")
        self.detail_vehicle.setText(f"载具: {vehicle.get('vehicle_id', '--')}")
        self.detail_link.setText(f"链路: {vehicle.get('link_name', '--')}")
        self.detail_plugin.setText(f"插件: {vehicle.get('firmware_name', '--')} / {vehicle.get('plugin_name', '--')}")
        self.detail_mode.setText(f"模式: {vehicle.get('mode', 'UNKNOWN')}")
        self.detail_battery.setText(f"电池/GPS: {vehicle.get('battery_remaining', 0)}% / {vehicle.get('gps', 0)}")
        lat = vehicle.get("lat")
        lon = vehicle.get("lon")
        alt = vehicle.get("altitude")
        if lat is None or lon is None:
            self.detail_position.setText("位置: --")
        else:
            self.detail_position.setText(f"位置: {float(lat):.6f}, {float(lon):.6f}, 高度 {float(alt or 0.0):.1f}m")

        self.params_total.setText(f"参数总数: {int(vehicle.get('params_total', 0) or 0)}")
        self.params_modified.setText(f"已修改: {int(vehicle.get('params_modified', 0) or 0)}")
        self.params_hint.setText(f"参数缓存链路: {vehicle.get('link_name', '--')}")

        self.mission_count.setText(f"任务航点: {int(vehicle.get('mission_count', 0) or 0)}")
        self.auto_route_count.setText(f"自动航线段: {int(vehicle.get('auto_route_count', 0) or 0)}")
        self.home_state.setText(f"H点: {'已设置' if vehicle.get('home_set') else '未设置'}")
        last_command = str(vehicle.get('last_command', '') or '--')
        command_busy = bool(vehicle.get('command_busy', False))
        queue_depth = int(vehicle.get('queue_depth', 0) or 0)
        self.control_hint.setText(f"最近指令: {last_command} | {'执行中' if command_busy else '空闲'} | 队列 {queue_depth}")

        has_vehicle = bool(self._active_vehicle_id)
        for button in [
            self.btn_activate,
            self.btn_open_params,
            self.btn_open_mission,
            self.btn_arm,
            self.btn_disarm,
            self.btn_takeoff,
            self.btn_rtl,
            self.btn_batch_arm,
            self.btn_batch_disarm,
            self.btn_batch_takeoff,
            self.btn_batch_qland,
            self.btn_batch_rtl,
            self.btn_clear_queue,
        ]:
            button.setEnabled(has_vehicle)

