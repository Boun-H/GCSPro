# ===================== 模块导入 =====================
import logging
from typing import List, Dict, Tuple, Optional
from PyQt6.QtWidgets import (
    QApplication,
    QFrame, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QMessageBox, QInputDialog, QTableWidgetItem, QTabBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from core.mission import (
    RouteConfig,
    WaypointModel,
    build_auto_route_items,
    calculate_horizontal_distance,
    export_mission_bundle,
    file_dialog_meta,
    import_mission_bundle,
    normalize_waypoint,
    validate_waypoint,
)
from .gcs_dialogs import gcs_confirm, gcs_input_double
from .waypoint_panel_parts import (
    AutoRouteDetailWidget,
    TransferStatusWidget,
    WaypointIOWidget,
    WaypointPanelController,
    WaypointTableWidget,
)

# ===================== 日志配置 =====================
logger = logging.getLogger("WaypointPanel")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.FileHandler("waypoint.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(handler)

# ===================== 核心航点面板（全量修复+序号严格对齐） =====================
class WaypointPanel(QFrame):
    # 对外信号
    close_clicked = pyqtSignal()
    add_mode_requested = pyqtSignal()
    home_btn_clicked = pyqtSignal()
    upload_requested = pyqtSignal(list)
    download_requested = pyqtSignal()
    waypoint_selected = pyqtSignal(int, dict)  # 选中航点信号（序号，航点数据）
    waypoints_updated = pyqtSignal(list)
    auto_route_updated = pyqtSignal(list)
    vehicle_tab_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # 核心状态变量
        self.model = WaypointModel(self)
        self._home_wp: Optional[Dict] = None  # H点，对应飞控0号航点
        self._auto_route_overrides: Dict = {}
        self._routes_by_name: Dict = {}
        self._updating_table: bool = False
        self._selected_row: int = -1
        self._home_display_offset: int = 0
        self._active_vehicle_id: str = ""
        self._vehicle_contexts: Dict[str, Dict] = {}
        self._tab_vehicle_ids: List[str] = []
        self._controller = WaypointPanelController()

        # UI初始化
        self._init_ui()
        self._init_timers()
        self.connect_signals()

        # 初始状态更新
        self.update_table()

    def _init_ui(self):
        """初始化UI界面，修复所有布局问题"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # 标题栏
        title_layout = QHBoxLayout()
        self.mission_title = QLabel("航点任务管理 | VTOL垂直起降专用")
        self.mission_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #f3f8ff;")
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setStyleSheet("QPushButton { border: none; border-radius: 12px; background: #c9302c; color: white; font-weight: 700; } QPushButton:hover { background: #d9534f; }")
        title_layout.addWidget(self.mission_title)
        title_layout.addStretch()
        title_layout.addWidget(self.close_btn)
        main_layout.addLayout(title_layout)

        self.vehicle_tabs = QTabBar()
        self.vehicle_tabs.setDocumentMode(True)
        self.vehicle_tabs.setDrawBase(False)
        self.vehicle_tabs.setExpanding(False)
        self.vehicle_tabs.hide()
        main_layout.addWidget(self.vehicle_tabs)

        self.vehicle_context_label = QLabel("当前任务页: 全局")
        self.vehicle_context_label.setStyleSheet("color: #9fb4cf; font-size: 12px; padding: 0 4px;")
        main_layout.addWidget(self.vehicle_context_label)

        # 内容布局
        content_layout = QVBoxLayout()
        content_layout.setSpacing(6)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # 1. 核心操作按钮区
        button_layout = QHBoxLayout()
        button_layout.setSpacing(4)
        self.btn_add = QPushButton("地图点选航点")
        self.btn_delete = QPushButton("删除选中")
        self.btn_clear = QPushButton("清空航点")
        self.btn_set_height = QPushButton("统一高度")
        self.btn_home = QPushButton("🏠 设置H点")

        # 按钮样式统一封装
        self._style_action_button(self.btn_add, "#1f9d68")
        self._style_action_button(self.btn_delete, "#8b5a1d")
        self._style_action_button(self.btn_clear, "#3b5a85")
        self._style_action_button(self.btn_set_height, "#0f766e")
        self._style_action_button(self.btn_home, "#1a4a6a")

        for btn in [
            self.btn_add,
            self.btn_delete,
            self.btn_clear,
            self.btn_set_height,
            self.btn_home,
        ]:
            button_layout.addWidget(btn)
        content_layout.addLayout(button_layout)

        # 2. 导入导出组件
        self.io_widget = WaypointIOWidget(self)
        self.btn_export_kml = self.io_widget.btn_export_kml
        self.btn_import_kml = self.io_widget.btn_import_kml
        self.btn_export_waypoints = self.io_widget.btn_export_waypoints
        self.btn_import_waypoints = self.io_widget.btn_import_waypoints
        content_layout.addWidget(self.io_widget)

        # 3. 航线上传下载区
        mission_layout = QHBoxLayout()
        mission_layout.setSpacing(4)
        self.btn_upload_mission = QPushButton("上传航线")
        self.btn_download_mission = QPushButton("下载航线")
        self._style_primary_button(self.btn_upload_mission, "#1f6fb2")
        self._style_primary_button(self.btn_download_mission, "#0f766e")
        mission_layout.addWidget(self.btn_upload_mission)
        mission_layout.addWidget(self.btn_download_mission)
        content_layout.addLayout(mission_layout)

        # 4. 航线执行摘要
        self.summary_label = QLabel("纯任务航点直连模式：设置 H 点后上传 HOME+任务航点。")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("color: #c8d8ee; font-size: 12px; padding: 4px 8px; background: #142133; border-radius: 4px;")
        content_layout.addWidget(self.summary_label)

        # H点详情
        self.home_detail_label = QLabel("H点详情：未设置")
        self.home_detail_label.setWordWrap(True)
        self.home_detail_label.setStyleSheet("color: #9fc1e6; font-size: 12px; padding: 4px 8px; background: #0f1a2a; border-radius: 4px;")
        content_layout.addWidget(self.home_detail_label)

        # 5. 航点表格主区【核心】UI序号与飞控序号1:1对齐
        self.route_table = WaypointTableWidget(self)
        content_layout.addWidget(self.route_table, 3)

        # 6. 自动航线配置区
        self.auto_route_group = AutoRouteDetailWidget(self)
        self.auto_route_group.setVisible(False)

        # 7. 传输状态反馈区
        self.transfer_widget = TransferStatusWidget(self)
        content_layout.addWidget(self.transfer_widget)

        main_layout.addLayout(content_layout)

        # 全局样式
        self.setStyleSheet("""
            QFrame { 
                background: #121d2d; 
                border: 1px solid #2a4362; 
                border-radius: 10px; 
            }
        """)

    def _style_action_button(self, btn: QPushButton, bg_color: str):
        """按钮样式封装，解决opacity不兼容问题"""
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg_color};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background: {bg_color}dd;
            }}
            QPushButton:pressed {{
                background: {bg_color}bb;
            }}
            QPushButton:disabled {{
                background: #3a3a3a;
                color: #888888;
            }}
        """)

    def _style_primary_button(self, btn: QPushButton, bg_color: str):
        """主按钮样式封装"""
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {bg_color};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: 700;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {bg_color}dd;
            }}
            QPushButton:pressed {{
                background: {bg_color}bb;
            }}
            QPushButton:disabled {{
                background: #3a3a3a;
                color: #888888;
            }}
        """)

    def _init_timers(self):
        """定时器生命周期管理"""
        # 提示信息自动关闭定时器
        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.setInterval(3000)
        self._notice_timer.timeout.connect(self._clear_notice)

    def connect_signals(self):
        """统一信号槽绑定，补全所有交互事件"""
        # 基础按钮信号
        self.close_btn.clicked.connect(self.close_clicked.emit)
        self.btn_add.clicked.connect(self.add_mode_requested.emit)
        self.btn_delete.clicked.connect(self.delete_selected_waypoints)
        self.btn_clear.clicked.connect(self.clear_waypoints)
        self.btn_set_height.clicked.connect(self.set_uniform_height)
        self.btn_home.clicked.connect(self.home_btn_clicked.emit)

        # 导入导出信号
        self.io_widget.export_requested.connect(self.export_waypoints)
        self.io_widget.import_requested.connect(self.import_waypoints)

        # 航线传输信号
        self.btn_upload_mission.clicked.connect(self.request_upload)
        self.btn_download_mission.clicked.connect(self.download_requested.emit)

        # 表格交互信号
        self.route_table.itemChanged.connect(self.on_table_item_changed)
        self.route_table.itemSelectionChanged.connect(self.on_table_selection_changed)
        self.route_table.cellClicked.connect(self.on_table_cell_clicked)
        self.route_table.currentItemChanged.connect(self._on_table_focus_changed)

        # 自动航线配置信号
        self.auto_route_group.route_field_changed.connect(self.on_auto_route_field_changed)
        self.vehicle_tabs.currentChanged.connect(self._on_vehicle_tab_changed)

        # 模型数据变更信号
        self.model.waypoints_changed.connect(self.update_table)

    def _blank_vehicle_context(self) -> Dict:
        return {
            "waypoints": [],
            "home_wp": None,
            "auto_route_overrides": {},
            "selected_row": -1,
        }

    def _capture_current_vehicle_context(self):
        vehicle_id = str(self._active_vehicle_id or "").strip()
        if not vehicle_id:
            return
        self._vehicle_contexts[vehicle_id] = {
            "waypoints": [dict(wp) for wp in self.model.waypoints()],
            "home_wp": (dict(self._home_wp) if isinstance(self._home_wp, dict) else None),
            "auto_route_overrides": dict(self._auto_route_overrides or {}),
            "selected_row": int(self._selected_row),
        }

    def set_vehicle_tabs(self, vehicles: List[Dict] | List[str], active_vehicle_id: str = ""):
        self._capture_current_vehicle_context()
        tab_ids: List[str] = []
        self.vehicle_tabs.blockSignals(True)
        while self.vehicle_tabs.count() > 0:
            self.vehicle_tabs.removeTab(0)
        for vehicle in vehicles or []:
            if isinstance(vehicle, dict):
                vehicle_id = str(vehicle.get("vehicle_id", "") or "").strip()
            else:
                vehicle_id = str(vehicle or "").strip()
            if not vehicle_id:
                continue
            tab_ids.append(vehicle_id)
            self.vehicle_tabs.addTab(vehicle_id)
            self._vehicle_contexts.setdefault(vehicle_id, self._blank_vehicle_context())
        self._tab_vehicle_ids = tab_ids
        self.vehicle_tabs.setVisible(bool(tab_ids))
        self.vehicle_tabs.blockSignals(False)

        target_id = str(active_vehicle_id or self._active_vehicle_id or "").strip()
        if not target_id and tab_ids:
            target_id = tab_ids[0]
        if target_id:
            self.activate_vehicle_tab(target_id, emit_signal=False)
        else:
            self._active_vehicle_id = ""
            self.vehicle_context_label.setText("当前任务页: 全局")

    def activate_vehicle_tab(self, vehicle_id: str, emit_signal: bool = False):
        target_id = str(vehicle_id or "").strip()
        if not target_id:
            return
        same_target = target_id == self._active_vehicle_id
        if not same_target:
            self._capture_current_vehicle_context()
        ctx = self._vehicle_contexts.setdefault(target_id, self._blank_vehicle_context())
        self._active_vehicle_id = target_id
        if target_id in self._tab_vehicle_ids:
            index = self._tab_vehicle_ids.index(target_id)
            self.vehicle_tabs.blockSignals(True)
            self.vehicle_tabs.setCurrentIndex(index)
            self.vehicle_tabs.blockSignals(False)
        self.vehicle_context_label.setText(f"当前任务页: {target_id}")
        if same_target:
            if emit_signal:
                self.vehicle_tab_changed.emit(target_id)
            return
        self._home_wp = dict(ctx.get("home_wp") or {}) if ctx.get("home_wp") else None
        self._auto_route_overrides = dict(ctx.get("auto_route_overrides") or {})
        self._selected_row = int(ctx.get("selected_row", -1) or -1)
        self.model.set_waypoints([dict(wp) for wp in (ctx.get("waypoints") or [])], track_undo=False)
        if emit_signal:
            self.vehicle_tab_changed.emit(target_id)

    def _on_vehicle_tab_changed(self, index: int):
        if not (0 <= index < len(self._tab_vehicle_ids)):
            return
        self.activate_vehicle_tab(self._tab_vehicle_ids[index], emit_signal=True)

    def set_waypoints(self, waypoints: List[Dict], track_undo: bool = False, vehicle_id: Optional[str] = None):
        target_id = str(vehicle_id or self._active_vehicle_id or "").strip()
        payload = [dict(wp) for wp in (waypoints or [])]
        if target_id:
            ctx = self._vehicle_contexts.setdefault(target_id, self._blank_vehicle_context())
            ctx["waypoints"] = payload
            if target_id != self._active_vehicle_id and self._active_vehicle_id:
                return
            self._active_vehicle_id = target_id
            self.vehicle_context_label.setText(f"当前任务页: {target_id}")
        self.model.set_waypoints(payload, track_undo=track_undo)

    def get_waypoints(self) -> List[Dict]:
        return self.model.waypoints()

    def mission_row_offset(self) -> int:
        return int(self._home_display_offset)

    def mission_index_to_table_row(self, mission_index: int) -> int:
        mission_index = int(mission_index)
        if not (0 <= mission_index < len(self.model.waypoints())):
            return -1
        return self.mission_row_offset() + mission_index

    def table_row_to_mission_index(self, table_row: int) -> int:
        table_row = int(table_row)
        mission_start_row = self.mission_row_offset()
        mission_end_row = mission_start_row + len(self.model.waypoints())
        if mission_start_row <= table_row < mission_end_row:
            return table_row - mission_start_row
        return -1

    def select_waypoint_row(self, mission_index: int):
        row = self.mission_index_to_table_row(mission_index)
        if 0 <= row < self.route_table.rowCount():
            self.route_table.selectRow(row)
            self._selected_row = row

    def set_add_mode_active(self, enabled: bool):
        self.btn_add.setChecked(False)
        self.btn_add.setText("退出点选" if enabled else "地图点选航点")

    def preview_waypoint_position(self, index: int, lat: float, lon: float):
        waypoints = self.model.waypoints()
        if 0 <= index < len(waypoints):
            updated = normalize_waypoint(waypoints[index])
            updated["lat"] = float(lat)
            updated["lon"] = float(lon)
            waypoints[index] = updated
            self.model.set_waypoints(waypoints, track_undo=False)

    def commit_drag_position(self, index: int, lat: float, lon: float):
        waypoints = self.model.waypoints()
        if 0 <= index < len(waypoints):
            updated = normalize_waypoint(waypoints[index])
            updated["lat"] = float(lat)
            updated["lon"] = float(lon)
            waypoints[index] = updated
            self.model.set_waypoints(waypoints, track_undo=True)

    def set_transfer_progress(self, transfer_type: str, current: int, total: int, percent: int, message: str, busy: bool):
        self._show_transfer_status(message, int(percent))
        self._set_transfer_buttons_enabled(not busy)
        QApplication.processEvents()

    def clear_transfer_progress(self, message: str = ""):
        if message:
            self._show_transfer_status(message, 0)
        else:
            self._clear_notice()
        self._set_transfer_buttons_enabled(True)
        QApplication.processEvents()

    def set_auto_route_overrides(self, overrides: Dict, vehicle_id: Optional[str] = None):
        target_id = str(vehicle_id or self._active_vehicle_id or "").strip()
        payload = dict(overrides or {})
        if target_id:
            ctx = self._vehicle_contexts.setdefault(target_id, self._blank_vehicle_context())
            ctx["auto_route_overrides"] = payload
            if target_id != self._active_vehicle_id and self._active_vehicle_id:
                return
        self._auto_route_overrides = payload
        self.update_table()

    def update_auto_route_point(self, point_name: str, lat: float, lon: float, emit_signal: bool = True):
        point_name = str(point_name or "")
        if point_name == "T1" and self._home_wp is not None:
            self._home_wp["lat"] = float(lat)
            self._home_wp["lon"] = float(lon)
        else:
            self._auto_route_overrides[f"{point_name.lower()}_lat"] = float(lat)
            self._auto_route_overrides[f"{point_name.lower()}_lon"] = float(lon)
        self.update_table()
        if emit_signal:
            self.auto_route_updated.emit([dict(route) for route in self.get_auto_route_items()])

    def batch_insert_after_selected(self):
        row = self._selected_row
        mission_count = len(self.model.waypoints())
        mission_row = self.table_row_to_mission_index(row)
        insert_at = mission_count if mission_row < 0 else max(0, min(mission_count, mission_row + 1))
        waypoints = self.model.waypoints()
        base_wp = dict(waypoints[insert_at - 1]) if insert_at > 0 and waypoints else {
            "type": "WAYPOINT",
            "lat": float(self._home_wp.get("lat", 0.0) if self._home_wp else 0.0),
            "lon": float(self._home_wp.get("lon", 0.0) if self._home_wp else 0.0),
            "alt": RouteConfig.DEFAULT_AUTO_ROUTE_ALT,
            "loiter": False,
        }
        waypoints.insert(insert_at, normalize_waypoint(base_wp))
        self.model.set_waypoints(waypoints, track_undo=True)
        self.select_waypoint_row(insert_at)

    def reverse_waypoints(self):
        waypoints = list(reversed(self.model.waypoints()))
        self.model.set_waypoints(waypoints, track_undo=True)

    # ===================== H点管理核心逻辑（对应飞控0号航点） =====================
    def set_home_waypoint(self, wp: Dict, vehicle_id: Optional[str] = None):
        """设置H点（起降基准点，飞控0号航点），自动刷新航线"""
        target_id = str(vehicle_id or self._active_vehicle_id or "").strip()
        if target_id:
            ctx = self._vehicle_contexts.setdefault(target_id, self._blank_vehicle_context())
            ctx["home_wp"] = dict(wp) if isinstance(wp, dict) else None
            if wp is None:
                ctx["auto_route_overrides"] = {}
            if target_id != self._active_vehicle_id and self._active_vehicle_id:
                return
        if wp is None:
            self._home_wp = None
            self._auto_route_overrides.clear()
            self.update_table()
            return
        if not validate_waypoint(wp):
            self._show_auto_notice("错误", "H点坐标非法，设置失败")
            return
        # 标准化H点，设置为HOME类型，对应飞控0号航点
        self._home_wp = normalize_waypoint({
            **wp,
            "name": "H点",
            "type": "HOME",
            "seq": 0,  # H点固定为飞控0号航点
            "description": "HOME基准点，飞控任务0号航点"
        })
        self._auto_route_overrides.clear()
        self.update_table()
        self._show_auto_notice("成功", "H点已设置，固定为飞控0号航点")

    # ===================== 自动航线生成核心逻辑【严格序号对齐】 =====================
    def get_auto_route_items(self) -> List[Dict]:
        """获取自动生成的起降航线，严格按序号规则生成"""
        route_items, _ = self._build_auto_route_items(self.model.waypoints())
        return route_items

    def _build_auto_route_items(self, waypoints: List[Dict]) -> Tuple[List[Dict], str]:
        result = build_auto_route_items(self._home_wp, waypoints, self._auto_route_overrides)
        for title, message in result.notices:
            self._show_auto_notice(title, message)
        return result.route_items, result.summary



    # ===================== 表格数据管理【列表序号1-based显示】 =====================
    def update_table(self):
        """全量刷新表格，列表序号从1开始显示"""
        self._updating_table = True
        auto_route_items, summary = self._build_auto_route_items(self.model.waypoints())
        mission_waypoints = self.model.waypoints()

        # 飞控任务序号保持 1..N（0 号固定给 H 点）
        current_seq = 1
        for wp in mission_waypoints:
            wp["seq"] = current_seq
            current_seq += 1

        # H点作为0号行显示（只读），不纳入 model.waypoints()
        if self._home_wp:
            home_display = {**self._home_wp, "seq": 0, "is_home": True}
            ui_display_route = [home_display] + mission_waypoints
            self._home_display_offset = 1
        else:
            ui_display_route = mission_waypoints
            self._home_display_offset = 0

        # 更新摘要与路由映射
        total_distance_m = 0.0
        travel_points = []
        if self._home_wp is not None:
            travel_points.append(self._home_wp)
        travel_points.extend(mission_waypoints)
        for prev, curr in zip(travel_points, travel_points[1:]):
            try:
                total_distance_m += calculate_horizontal_distance(
                    float(prev.get("lat", 0.0) or 0.0),
                    float(prev.get("lon", 0.0) or 0.0),
                    float(curr.get("lat", 0.0) or 0.0),
                    float(curr.get("lon", 0.0) or 0.0),
                )
            except Exception:
                continue
        avg_speed = sum(float(wp.get("speed", RouteConfig.DEFAULT_SPEED) or RouteConfig.DEFAULT_SPEED) for wp in mission_waypoints) / max(1, len(mission_waypoints))
        hold_seconds = sum(float(wp.get("hold_time", 0.0) or 0.0) for wp in mission_waypoints)
        eta_seconds = hold_seconds + (total_distance_m / max(0.1, avg_speed))
        metrics_text = f"任务 {len(mission_waypoints)} 点 | 航程 {total_distance_m / 1000.0:.2f} km | 预计 {eta_seconds / 60.0:.1f} min"
        self.summary_label.setText(f"{summary}\n{metrics_text}")
        if self._home_wp:
            frame = int(self._home_wp.get("source_frame", self._home_wp.get("frame", 0)) or 0)
            self.home_detail_label.setText(
                "H点详情："
                f"纬度 {float(self._home_wp.get('lat', 0.0)):.7f}，"
                f"经度 {float(self._home_wp.get('lon', 0.0)):.7f}，"
                f"高度 {float(self._home_wp.get('alt', 0.0)):.1f}m，"
                f"FRAME {frame}"
            )
        else:
            self.home_detail_label.setText("H点详情：未设置")
        self._routes_by_name = {str(route.get('name', '')): dict(route) for route in ui_display_route}

        self.waypoints_updated.emit([dict(wp) for wp in mission_waypoints])
        self.auto_route_updated.emit([dict(route) for route in auto_route_items])

        self.route_table.render_rows(ui_display_route, self.on_action_changed)
        self._capture_current_vehicle_context()

        self._updating_table = False

    def on_action_changed(self, row: int, command: int):
        """动作列变更：写回 MAV_CMD 并标准化该航点"""
        if self._updating_table:
            return
        # H点行（row < offset）不可编辑
        if self._home_display_offset > 0 and int(row) < self._home_display_offset:
            return

        model_row = int(row) - self._home_display_offset
        waypoints = self.model.waypoints()
        if not (0 <= model_row < len(waypoints)):
            return

        updated = normalize_waypoint({**waypoints[model_row], "command": int(command)})
        waypoints[model_row] = updated
        self.model.set_waypoints(waypoints, track_undo=True)

    def on_table_item_changed(self, item: QTableWidgetItem):
        """表格单元格内容变更回调（由 controller 处理规则）"""
        if self._updating_table:
            return
        # H点行不可编辑
        if self._home_display_offset > 0 and item.row() < self._home_display_offset:
            return

        model_row = item.row() - self._home_display_offset
        model_total = self.route_table.rowCount() - self._home_display_offset
        updated_waypoints, error = self._controller.handle_table_item_changed(
            model_row,
            item.column(),
            item.text(),
            model_total,
            self.model.waypoints(),
        )
        if error:
            title = "输入错误" if "数字" in error or "必须" in error or "不能" in error else "提示"
            self._show_auto_notice(title, error)
            self.update_table()
            return
        if updated_waypoints is None:
            return

        self.model.set_waypoints(updated_waypoints, track_undo=True)

    def _on_table_focus_changed(self, current: QTableWidgetItem, previous: QTableWidgetItem):
        """表格焦点离开时提交修改，避免数据丢失"""
        if previous is not None:
            self.on_table_item_changed(previous)

    def on_table_selection_changed(self):
        """表格选中行变更回调"""
        selected_rows = sorted(set(index.row() for index in self.route_table.selectedIndexes()))
        if not selected_rows:
            self._selected_row = -1
            return
        self._selected_row = selected_rows[0]

        # H点行不发射 waypoint_selected 信号
        model_row = self._selected_row - self._home_display_offset
        full_route = self.model.waypoints()
        if 0 <= model_row < len(full_route):
            self.waypoint_selected.emit(full_route[model_row]["seq"], full_route[model_row])

    def on_table_cell_clicked(self, row: int, col: int):
        """单元格点击回调"""
        self._selected_row = row

    # ===================== 核心业务功能 =====================
    def clear_waypoints(self):
        """清空所有航点，带二次确认"""
        if not self.model.waypoints():
            self._show_auto_notice("提示", "当前没有航点")
            return
        if self._ask_confirm("确认清空", "确定要清空所有任务航点吗？"):
            self.model.clear()

    def delete_selected_waypoints(self):
        """删除选中航点，倒序删除避免索引越界"""
        selected_rows = sorted(set(index.row() for index in self.route_table.selectedIndexes()))
        if not selected_rows:
            self._show_auto_notice("提示", "请先选择要删除的航点")
            return

        # 排除H点行，转换为模型索引
        has_home_selected = self._home_display_offset > 0 and any(r < self._home_display_offset for r in selected_rows)
        model_selected = [r - self._home_display_offset for r in selected_rows if r >= self._home_display_offset]
        model_total = self.route_table.rowCount() - self._home_display_offset

        mission_rows, forbidden = self._controller.handle_delete_selected(model_selected, model_total)

        if forbidden or has_home_selected:
            self._show_auto_notice("提示", "H点不可删除" if has_home_selected else "存在不可删除的行")
        if not mission_rows:
            return

        if self._ask_confirm("确认删除", f"确定要删除选中的{len(mission_rows)}个任务航点吗？"):
            self.model.delete_rows(mission_rows)

    def set_uniform_height(self):
        """批量设置统一高度，带校验"""
        current_waypoints = self.model.waypoints()
        if not current_waypoints:
            self._show_auto_notice("提示", "请先添加航点")
            return

        current_height = self._controller.default_uniform_height(current_waypoints)
        height, ok = self._ask_uniform_height(current_height)
        if ok and self._controller.validate_uniform_height(height):
            self.model.set_uniform_height(height)
            self._show_auto_notice("成功", f"已将所有任务航点高度统一设置为{int(height)}米")

    def on_auto_route_field_changed(self, params: Dict):
        """直连模式下保留接口，不启用自动航线参数"""
        _ = params

    # ===================== 航线传输核心逻辑【严格序号对齐】 =====================
    def request_upload(self):
        """航线上传流程编排（controller 负责确认文案）"""
        # H点校验
        if self._home_wp is None:
            self._show_auto_notice("上传失败", "请先设置H点，H点为飞控0号航点，必须先设置才能上传航线")
            return

        mission_waypoints = self.model.waypoints()
        confirm_msg = self._controller.build_upload_confirm_message(len(mission_waypoints))
        if not self._ask_confirm("确认上传", confirm_msg):
            return

        # 仅发射任务航点，main_window._build_upload_waypoints 负责添加 H 点占位
        self.upload_requested.emit(mission_waypoints)
        self._show_transfer_status("正在向飞控上传航线...", 0)

    def on_upload_finished(self, success: bool, message: str = ""):
        """上传完成回调"""
        self._set_transfer_buttons_enabled(True)
        if success:
            self._show_transfer_status("上传成功", 100)
            self._notice_timer.start()
        else:
            self._show_transfer_status(f"上传失败：{message}", 0)
            logger.error(f"航线上传失败：{message}")

    def on_download_progress(self, current: int, total: int):
        """下载进度回调"""
        progress = int((current / total) * 100) if total > 0 else 0
        self._show_transfer_status(f"正在下载航点...{current}/{total}", progress)
        self._set_transfer_buttons_enabled(False)

    def on_download_finished(self, success: bool, waypoints: List[Dict] = None, message: str = ""):
        """下载完成回调（controller 负责结果拆分）"""
        self._set_transfer_buttons_enabled(True)
        home_wp, mission_waypoints, error = self._controller.handle_download_result(success, waypoints, message)
        if error:
            self._show_transfer_status(f"下载失败：{error}", 0)
            logger.error(f"航线下载失败：{error}")
            return

        if home_wp:
            self.set_home_waypoint(home_wp)
        self.model.set_waypoints(mission_waypoints)
        self._show_transfer_status(f"下载成功，共{len(waypoints or [])}个航点", 100)
        self._notice_timer.start()

    def _show_transfer_status(self, message: str, progress: int):
        self.transfer_widget.show_status(message, progress)
        self.transfer_widget.repaint()

    def _clear_notice(self):
        self.transfer_widget.clear_status()

    def _set_transfer_buttons_enabled(self, enabled: bool):
        """设置传输按钮可用性"""
        self.btn_upload_mission.setEnabled(enabled)
        self.btn_download_mission.setEnabled(enabled)

    # ===================== 导入导出功能 =====================
    def export_waypoints(self, format_type: str):
        """导出航点，带备份机制"""
        current_waypoints = self.model.waypoints()
        full_route = ([self._home_wp] if self._home_wp else []) + current_waypoints

        if not full_route:
            self._show_auto_notice("提示", "没有航点可导出")
            return

        meta = file_dialog_meta(format_type)
        file_filter = meta.get("save_filter", "QGC WPL files (*.waypoints)")
        default_name = meta.get("default_name", "vtol_waypoints.waypoints")
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出航点", default_name, file_filter
        )
        if not file_path:
            return

        try:
            export_mission_bundle(file_path, format_type, full_route)
            self._show_auto_notice("成功", f"航点已导出到 {file_path}")
            logger.info(f"航点导出成功：{file_path}，共{len(full_route)}个航点")
        except Exception as e:
            logger.exception("导出航点失败：%s", file_path)
            self._show_auto_notice("导出失败", f"导出失败：{str(e)}")

    def import_waypoints(self, format_type: str):
        """导入航点（controller 负责确认与处理规则）"""
        meta = file_dialog_meta(format_type)
        file_filter = meta.get("open_filter", "QGC WPL files (*.waypoints)")
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入航点", "", file_filter
        )
        if not file_path:
            return

        try:
            waypoints = import_mission_bundle(file_path, format_type)

            if not waypoints:
                self._show_auto_notice("导入失败", "文件中没有找到有效的航点数据")
                return

            valid_waypoints, total, _invalid_count, msg = self._controller.build_import_preview(waypoints)
            if not self._ask_confirm("导入预览", msg):
                return

            if not valid_waypoints:
                self._show_auto_notice("导入失败", "没有有效航点可导入")
                return

            imported_home, _auto_route_overrides, mission_waypoints, processed_total = self._controller.handle_imported_waypoints(valid_waypoints, self._home_wp)
            if imported_home is not None:
                self.set_home_waypoint(imported_home)
            self.model.set_waypoints(mission_waypoints, track_undo=True)
            self._show_auto_notice("成功", self._controller.build_import_success_message(len(mission_waypoints), False, imported_home is not None))
            logger.info(
                "航点导入成功：%s，总计=%s，任务=%s，起降识别=%s，H点=%s",
                file_path,
                processed_total,
                len(mission_waypoints),
                False,
                imported_home is not None,
            )

        except Exception as e:
            error_text = f"导入失败 ({format_type}) 文件 {file_path}：{str(e)}"
            logger.exception(error_text)
            self._show_auto_notice("导入失败", f"导入失败：{str(e)}\n已记录到 waypoint.log")


    # ===================== 弹窗辅助函数 =====================
    def _ask_confirm(self, title: str, message: str) -> bool:
        """二次确认弹窗（深色主题，白色字体）"""
        return gcs_confirm(self, title, message, yes_text="确认", no_text="取消")

    def _show_auto_notice(self, title: str, message: str):
        """非阻塞状态提示，3秒后自动消失"""
        self._show_transfer_status(f"{title}：{message}", 0)
        self._notice_timer.start()

    def _ask_uniform_height(self, default_height: float) -> Tuple[float, bool]:
        """统一高度输入弹窗（深色主题）"""
        return gcs_input_double(
            self, "设置统一高度", "请输入航点统一高度（米）：",
            default_height, RouteConfig.MIN_ALT, RouteConfig.MAX_ALT, 0
        )

    # ===================== 生命周期管理 =====================
    def closeEvent(self, event):
        """面板关闭时清理资源，避免内存泄漏"""
        # 停止所有定时器
        if self._notice_timer.isActive():
            self._notice_timer.stop()
        # 断开所有信号槽
        try:
            self.model.waypoints_changed.disconnect(self.update_table)
        except TypeError:
            pass
        # 清理表格控件
        for row in range(self.route_table.rowCount()):
            for col in range(self.route_table.columnCount()):
                widget = self.route_table.cellWidget(row, col)
                if widget:
                    self.route_table.removeCellWidget(row, col)
                    widget.deleteLater()
        # 接受关闭事件
        event.accept()

# ===================== 测试入口 =====================
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = WaypointPanel()
    window.setWindowTitle("VTOL无人机航点任务管理面板 | 序号对齐版")
    window.resize(1200, 850)
    window.show()
    sys.exit(app.exec())