import math
import time
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QFrame,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QComboBox,
    QStackedWidget,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QFileDialog,
    QScrollArea,
    QSplitter,
    QGroupBox,
    QFormLayout,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtCore import QPoint, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from ui.attitude_ball import AttitudeBall
import serial.tools.list_ports
import json

# 🔥 使用相对导入，解决模块路径依赖
from .map_bridge import MapBridge
from .map_controller import MapController
from .panel_manager import PanelManager
from .flight_control_panel import FlightControlPanel
from .link_manager_panel import LinkManagerPanel
from .link_settings_dialog import LinkSettingsDialog
from .mp_workbench_panel import MPWorkbenchPanel
from .vehicle_panel import VehiclePanel
from .waypoint_panel import WaypointPanel
from .param_panel import ParamPanel
from .setup_panel import VehicleSetupPanel
from .fly_view_panel import FlyViewPanel
from .analyze_panel import AnalyzePanel
from .peripheral_panel import PeripheralPanel
from .gcs_dialogs import gcs_confirm, gcs_warning, gcs_info, _DIALOG_STYLE

from core.alarm_system import AlarmSystem
from core.analyze_tools import discover_log_files, preview_log_file, summarize_log_files
from core.command_router import CommandRouter
from core.data_recorder import DataRecorder
from core.health_monitor import HealthMonitor
from core.link_manager import MultiLinkManager
from core.fact_panel_controller import FactPanelController
from core.firmware_plugin import resolve_plugins
from core.firmware_tools import build_firmware_upgrade_plan, build_parameter_validation_report, inspect_firmware_image
from core.mission import RouteConfig, build_upload_waypoints, split_downloaded_mission, validate_upload_waypoints
from core.parameter_manager import ParameterManager
from core.settings_manager import SettingsManager
from core.vehicle_manager import VehicleManager
from core.logger import UserActionLogger, get_app_logger
from core.constants import (
    BAUD_RATES,
    DEFAULT_BAUD,
    DEFAULT_LAT,
    DEFAULT_LON,
)

class ConnectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("连接飞控")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowCloseButtonHint)
        self.setFixedSize(440, 360)
        self._position_initialized = False
        self.init_ui()
        self.scan_ports()

    def init_ui(self):
        self.setStyleSheet("""
            QDialog { background-color: #0e1822; }
            QLabel  { color: #8aa5c0; font-size: 12px; }
            QComboBox {
                background-color: #162233; color: #d9e6f7;
                border: 1px solid #2d4a6a; border-radius: 6px;
                padding: 6px 10px; font-size: 12px;
            }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox QAbstractItemView {
                background: #162233; color: #d9e6f7;
                border: 1px solid #2d4a6a;
                selection-background-color: #1565c0;
            }
            QLineEdit {
                background-color: #162233; color: #d9e6f7;
                border: 1px solid #2d4a6a; border-radius: 6px;
                padding: 6px 10px; font-size: 12px;
            }
            QLineEdit:focus { border-color: #1f8cff; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(0)

        # ── Header ──────────────────────────────
        header = QHBoxLayout()
        icon_lbl = QLabel("📡")
        icon_lbl.setStyleSheet("font-size:26px; color:#d9e6f7;")
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        heading = QLabel("连接飞控设备")
        heading.setStyleSheet("font-size:15px; font-weight:700; color:#d9e6f7;")
        sub_lbl = QLabel("选择连接方式并配置参数后点击连接")
        sub_lbl.setStyleSheet("font-size:11px; color:#4a6a84;")
        title_col.addWidget(heading)
        title_col.addWidget(sub_lbl)
        header.addWidget(icon_lbl)
        header.addSpacing(10)
        header.addLayout(title_col)
        header.addStretch()
        layout.addLayout(header)
        layout.addSpacing(14)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet("background:#1d3048;")
        sep1.setFixedHeight(1)
        layout.addWidget(sep1)
        layout.addSpacing(14)

        # ── Connection-type tabs ─────────────────
        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        self.btn_serial_tab = QPushButton("   串口   ")
        self.btn_tcp_tab = QPushButton("   TCP   ")
        self.btn_udp_tab = QPushButton("   UDP   ")
        self.btn_serial_tab.setFixedHeight(30)
        self.btn_tcp_tab.setFixedHeight(30)
        self.btn_udp_tab.setFixedHeight(30)
        tab_row.addWidget(self.btn_serial_tab)
        tab_row.addWidget(self.btn_tcp_tab)
        tab_row.addWidget(self.btn_udp_tab)
        tab_row.addStretch()
        layout.addLayout(tab_row)
        layout.addSpacing(14)
        self._apply_tab_styles(0)

        # ── Stacked pages ────────────────────────
        self.stack = QStackedWidget()
        self.stack.setFixedHeight(88)

        # Serial page
        s_page = QWidget()
        sg = QGridLayout(s_page)
        sg.setContentsMargins(0, 0, 0, 0)
        sg.setSpacing(10)
        sg.setColumnMinimumWidth(0, 56)
        sg.setColumnStretch(1, 1)

        port_lbl = QLabel("串口号")
        port_row_w = QWidget()
        port_row = QHBoxLayout(port_row_w)
        port_row.setContentsMargins(0, 0, 0, 0)
        port_row.setSpacing(8)
        self.cmb_serial = QComboBox()
        self.cmb_serial.setFixedHeight(34)
        self.btn_refresh_ports = QPushButton("↻")
        self.btn_refresh_ports.setFixedSize(34, 34)
        self.btn_refresh_ports.setStyleSheet(
            "QPushButton { background:#162233; color:#8aa5c0; border:1px solid #2d4a6a;"
            " border-radius:6px; font-size:18px; font-weight:700; }"
            "QPushButton:hover { background:#243647; color:#d9e6f7; }"
        )
        port_row.addWidget(self.cmb_serial, 1)
        port_row.addWidget(self.btn_refresh_ports)

        baud_lbl = QLabel("波特率")
        self.cmb_baud = QComboBox()
        self.cmb_baud.addItems(BAUD_RATES)
        self.cmb_baud.setCurrentText(DEFAULT_BAUD)
        self.cmb_baud.setFixedHeight(34)

        sg.addWidget(port_lbl,   0, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        sg.addWidget(port_row_w, 0, 1)
        sg.addWidget(baud_lbl,   1, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        sg.addWidget(self.cmb_baud, 1, 1)
        self.stack.addWidget(s_page)

        # TCP page
        t_page = QWidget()
        tg = QGridLayout(t_page)
        tg.setContentsMargins(0, 0, 0, 0)
        tg.setSpacing(10)
        tg.setColumnMinimumWidth(0, 56)
        tg.setColumnStretch(1, 1)

        ip_lbl = QLabel("IP 地址")
        self.edit_ip = QLineEdit("127.0.0.1")
        self.edit_ip.setPlaceholderText("例如：127.0.0.1")
        self.edit_ip.setFixedHeight(34)

        pn_lbl = QLabel("端口")
        self.edit_port = QLineEdit("5760")
        self.edit_port.setPlaceholderText("例如：5760")
        self.edit_port.setFixedHeight(34)

        tg.addWidget(ip_lbl, 0, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        tg.addWidget(self.edit_ip, 0, 1)
        tg.addWidget(pn_lbl, 1, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        tg.addWidget(self.edit_port, 1, 1)
        self.stack.addWidget(t_page)

        # UDP page
        u_page = QWidget()
        ug = QGridLayout(u_page)
        ug.setContentsMargins(0, 0, 0, 0)
        ug.setSpacing(10)
        ug.setColumnMinimumWidth(0, 56)
        ug.setColumnStretch(1, 1)

        udp_host_lbl = QLabel("监听")
        self.edit_udp_host = QLineEdit("0.0.0.0")
        self.edit_udp_host.setPlaceholderText("例如：0.0.0.0")
        self.edit_udp_host.setFixedHeight(34)

        udp_port_lbl = QLabel("端口")
        self.edit_udp_port = QLineEdit("14550")
        self.edit_udp_port.setPlaceholderText("例如：14550")
        self.edit_udp_port.setFixedHeight(34)

        ug.addWidget(udp_host_lbl, 0, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        ug.addWidget(self.edit_udp_host, 0, 1)
        ug.addWidget(udp_port_lbl, 1, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        ug.addWidget(self.edit_udp_port, 1, 1)
        self.stack.addWidget(u_page)

        layout.addWidget(self.stack)
        layout.addSpacing(16)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("background:#1d3048;")
        sep2.setFixedHeight(1)
        layout.addWidget(sep2)
        layout.addSpacing(14)

        # ── Action buttons ───────────────────────
        act = QHBoxLayout()
        act.addStretch()
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.setStyleSheet(
            "QPushButton { background:#162233; color:#8aa5c0; border:1px solid #2d4a6a;"
            " border-radius:6px; padding:0 20px; font-size:13px; }"
            "QPushButton:hover { background:#243647; color:#d9e6f7; }"
        )
        self.btn_connect = QPushButton("连  接")
        self.btn_connect.setFixedHeight(36)
        self.btn_connect.setStyleSheet(
            "QPushButton { background:#1565c0; color:#ffffff; border:none;"
            " border-radius:6px; padding:0 28px; font-size:13px; font-weight:600; }"
            "QPushButton:hover { background:#1976d2; }"
        )
        act.addWidget(self.btn_cancel)
        act.addSpacing(8)
        act.addWidget(self.btn_connect)
        layout.addLayout(act)

        # Signals
        self.btn_serial_tab.clicked.connect(lambda: self._switch_type(0))
        self.btn_tcp_tab.clicked.connect(lambda: self._switch_type(1))
        self.btn_udp_tab.clicked.connect(lambda: self._switch_type(2))
        self.btn_connect.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_refresh_ports.clicked.connect(self.scan_ports)

    def _apply_tab_styles(self, active: int):
        buttons = [self.btn_serial_tab, self.btn_tcp_tab, self.btn_udp_tab]
        for index, button in enumerate(buttons):
            is_active = index == active
            left_radius = "6px" if index == 0 else "0px"
            right_radius = "6px" if index == len(buttons) - 1 else "0px"
            button.setStyleSheet(
                f"QPushButton {{ background:{'#1565c0' if is_active else '#162233'};"
                f" color:{'#ffffff' if is_active else '#8aa5c0'};"
                f" {'font-weight:600;' if is_active else ''}"
                f" border:1px solid {'#1565c0' if is_active else '#2d4a6a'};"
                f" {'border-left:none;' if index > 0 else ''}"
                f" border-top-left-radius:{left_radius}; border-bottom-left-radius:{left_radius};"
                f" border-top-right-radius:{right_radius}; border-bottom-right-radius:{right_radius};"
                f" padding:0 18px; font-size:13px; }}"
                f"QPushButton:hover {{ background:{'#1976d2' if is_active else '#243647'};"
                f" color:{'#ffffff' if is_active else '#d9e6f7'}; }}"
            )

    def _switch_type(self, index: int):
        self.stack.setCurrentIndex(index)
        self._apply_tab_styles(index)

    def showEvent(self, event):
        super().showEvent(event)
        self.scan_ports()
        if not self._position_initialized:
            self.center_dialog()
            self._position_initialized = True

    def center_dialog(self):
        parent = self.parentWidget()
        if parent is not None:
            center = parent.geometry().center()
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)
        else:
            screen = QApplication.primaryScreen().availableGeometry()
            self.move(screen.center().x() - self.width() // 2, screen.center().y() - self.height() // 2)

    def scan_ports(self):
        previous_port = self.cmb_serial.currentData()
        self.cmb_serial.clear()

        try:
            # 使用 pyserial 提供的设备名 + 描述，便于识别真实串口。
            ports = sorted(
                serial.tools.list_ports.comports(),
                key=lambda p: (str(getattr(p, "device", "") or "").upper(), str(getattr(p, "description", "") or "")),
            )
        except Exception:
            ports = []

        if not ports:
            self.cmb_serial.addItem("未检测到串口，请检查驱动/线缆后点击刷新", None)
            self.cmb_serial.setEnabled(False)
            self.btn_connect.setEnabled(False)
            return

        self.cmb_serial.setEnabled(True)
        self.btn_connect.setEnabled(True)
        restore_index = -1

        for idx, port in enumerate(ports):
            device = str(getattr(port, "device", "") or "")
            description = str(getattr(port, "description", "") or "")
            hwid = str(getattr(port, "hwid", "") or "")
            text = f"{device} - {description}" if description and description != "n/a" else device
            if hwid and hwid != "n/a":
                text = f"{text} [{hwid}]"
            self.cmb_serial.addItem(text, device)
            if previous_port and str(previous_port).upper() == device.upper():
                restore_index = idx

        self.cmb_serial.setCurrentIndex(restore_index if restore_index >= 0 else 0)

class MapNoticeOverlay(QWidget):
    """地图左上角滚动消息提示覆盖层：支持多条消息堆叠，每条 3 秒后自动消失"""
    _LEVEL_COLORS = {
        "info":   ("#3290d8", "#90caf9"),
        "ok":     ("#1a7f64", "#86efac"),
        "warn":   ("#c47a1b", "#fde68a"),
        "danger": ("#c25565", "#fecdd3"),
    }
    _LEVEL_ICONS = {"ok": "✔ ", "warn": "⚠ ", "danger": "✖ ", "info": "ℹ "}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFixedWidth(320)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 0, 0)
        lay.setSpacing(5)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._items: list = []
        self.hide()

    def add_notice(self, title: str, message: str, level: str = "info"):
        border_c, _ = self._LEVEL_COLORS.get(level, self._LEVEL_COLORS["info"])
        icon = self._LEVEL_ICONS.get(level, "ℹ ")

        item = QFrame(self)
        item.setStyleSheet(
            f"QFrame {{ background: rgba(9,22,38,0.93); border-left: 3px solid {border_c};"
            " border-radius: 0px 6px 6px 0px; }"
            "QLabel { background: transparent; border: none; color: #ffffff; font-size: 12px; }"
        )
        row = QHBoxLayout(item)
        row.setContentsMargins(10, 7, 12, 7)
        row.setSpacing(6)
        lbl_icon = QLabel(icon)
        lbl_icon.setStyleSheet(
            f"color: {border_c}; font-weight: 800; background: transparent; border: none; font-size: 13px;"
        )
        lbl_icon.setFixedWidth(18)
        text = f"<b>{title}</b>  {message}" if title else message
        lbl_text = QLabel(text)
        lbl_text.setWordWrap(True)
        lbl_text.setMaximumWidth(265)
        lbl_text.setStyleSheet("color: #ffffff; background: transparent; border: none; font-size: 12px;")
        row.addWidget(lbl_icon)
        row.addWidget(lbl_text, 1)

        self.layout().addWidget(item)
        self._items.append(item)
        self.adjustSize()
        self.raise_()
        self.show()
        QTimer.singleShot(3000, lambda: self._remove_item(item))

    def _remove_item(self, item: QFrame):
        if item in self._items:
            self._items.remove(item)
            self.layout().removeWidget(item)
            item.deleteLater()
        self.adjustSize()
        if not self._items:
            self.hide()


class FloatingPanel(QFrame):
    position_changed = pyqtSignal(QPoint)

    def __init__(self, is_flight=False, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "QFrame {"
            "background-color: rgba(11, 20, 31, 0.96);"
            "border: 1px solid rgba(58, 85, 116, 0.92);"
            "border-radius: 14px;"
            "}"
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.is_flight = is_flight
        self.dragging = False

    def mousePressEvent(self, e):
        if self.is_flight or e.button() != Qt.MouseButton.LeftButton:
            return
        self.dragging = True
        self.drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self.is_flight or not self.dragging:
            return
        self.move(e.globalPosition().toPoint() - self.drag_pos)

    def mouseReleaseEvent(self, e):
        self.dragging = False
        self.position_changed.emit(self.pos())


class ConnectionStatusLabel(QLabel):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

class DroneGroundStation(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("无人机地面站 GCS_PRO")
        self.setGeometry(50, 50, 1700, 1000)
        self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)
        
        self.alarm = AlarmSystem()
        self.connection_manager = MultiLinkManager(self)
        self.recorder = DataRecorder()
        self.action_logger = UserActionLogger()
        metadata_xml = Path(__file__).resolve().parent.parent / "references" / "ardupilot" / "ParameterFactMetaData.xml"
        self.parameter_manager = ParameterManager(metadata_xml_path=str(metadata_xml))
        self.settings_manager = SettingsManager()
        self.vehicle_manager = VehicleManager(self)
        self._firmware_plugin, self._autopilot_plugin = resolve_plugins({}, None)
        self.fact_panel_controller = FactPanelController(
            fact_system=self.parameter_manager.fact_system,
            autopilot_plugin=self._autopilot_plugin,
            settings_manager=self.settings_manager,
            parent=self,
        )
        self.app_logger = get_app_logger("GCS.MainWindow", "ui/main_window.log")
        self.waypoints = []
        self._selected_waypoint_index = -1
        self.current_map = str(self.settings_manager.get("ui.map_source", "谷歌卫星") or "谷歌卫星")
        self._map_add_mode = False
        self.latest_status = {}
        self.home_position = None
        self.vehicle_position = None
        self._vehicle_centered_once = False
        self._notice_overlay = None
        self._pending_manual_success_notice = False
        self._is_shutting_down = False
        self._status_label_style_map = {
            "neutral": ("rgba(19, 38, 60, 0.92)", "#35506b", "#d9e6f7"),
            "ok": ("rgba(14, 65, 52, 0.94)", "#1a7f64", "#bbf7d0"),
            "warn": ("rgba(91, 54, 12, 0.94)", "#c47a1b", "#fde68a"),
            "danger": ("rgba(92, 28, 35, 0.94)", "#c25565", "#fecdd3"),
            "info": ("rgba(15, 76, 129, 0.94)", "#3290d8", "#dbeafe"),
        }
        self.panel_manager = PanelManager(self)

        self.waypoint_panel = FloatingPanel(parent=self)
        self.param_panel = FloatingPanel(parent=self)
        self.links_panel = FloatingPanel(parent=self)
        self.vehicle_panel = FloatingPanel(parent=self)
        self.mp_panel = FloatingPanel(parent=self)
        self.setup_panel = FloatingPanel(parent=self)
        self.fly_view_panel = FloatingPanel(parent=self)
        self.analyze_panel = FloatingPanel(parent=self)
        self.peripheral_panel = FloatingPanel(parent=self)
        self.flight_panel = FloatingPanel(is_flight=True, parent=self)
        self.connect_dialog = ConnectionDialog(self)
        self._mission_transfer_active = False
        self._flight_command_busy = False
        self._command_busy_vehicle_id = ""
        self._busy_vehicle_ids = set()
        self._last_waypoint_preview_ts = 0.0
        self._last_auto_route_preview_ts = 0.0
        self._last_link_label = ""
        self._current_active_link_key = ""
        self._params_by_link = {}
        self._mission_context_by_link = {}
        self._params_by_vehicle = {}
        self._mission_context_by_vehicle = {}
        self._mp_action_handlers = {}

        self.init_ui()
        self._load_saved_connection_settings()
        QTimer.singleShot(350, self._maybe_auto_connect_last_link)
        self.log_user_action("app_started", window_size=f"{self.width()}x{self.height()}")

    def log_user_action(self, action, **details):
        self.action_logger.log(action, **details)

    def _apply_status_chip_style(self, label: QLabel, tone: str = "neutral"):
        background, border, foreground = self._status_label_style_map.get(
            tone,
            self._status_label_style_map["neutral"],
        )
        label.setStyleSheet(
            "QLabel {"
            f"background:{background};"
            f"border:1px solid {border};"
            "border-radius:10px;"
            f"color:{foreground};"
            "font-size:12px;"
            "font-weight:600;"
            "padding:4px 10px;"
            "}"
        )

    def _reset_live_status_labels(self):
        self.flight_time.setText("飞行时间: 00:00:00")
        self.battery.setText("电池: 100%")
        self.altitude.setText("高度: 0.0m")
        self.speed.setText("速度: 0.0m/s")
        self.mode.setText("模式: UNKNOWN")
        self.gps.setText("GPS: 0 颗")
        self.volt.setText("电压: 0.00V")
        self.alert.setText("状态: 正常")
        for label in [self.flight_time, self.battery, self.altitude, self.speed, self.mode, self.gps, self.volt]:
            self._apply_status_chip_style(label, "neutral")
        self._apply_status_chip_style(self.alert, "ok")

    def _update_telemetry_chip_styles(self, data: dict):
        battery_remaining = int(data.get("battery_remaining", 100) or 0)
        gps_count = int(data.get("gps", 0) or 0)
        voltage = float(data.get("volt", 0.0) or 0.0)

        battery_tone = "danger" if battery_remaining < 25 else "warn" if battery_remaining < 45 else "ok"
        gps_tone = "danger" if gps_count < 6 else "warn" if gps_count < 10 else "ok"
        voltage_tone = "danger" if voltage < 10.5 else "warn" if voltage < 11.1 else "neutral"

        self._apply_status_chip_style(self.battery, battery_tone)
        self._apply_status_chip_style(self.gps, gps_tone)
        self._apply_status_chip_style(self.volt, voltage_tone)
        self._apply_status_chip_style(self.alert, "ok")

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0,0,0,0)

        top_bar = QFrame()
        top_bar.setFixedHeight(68)
        top_bar.setStyleSheet("background-color: rgba(15, 20, 28, 0.92); border-bottom: 1px solid #293747;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 8, 10, 8)
        top_layout.setSpacing(10)

        # Left side - Status information
        self.connection_status = ConnectionStatusLabel("🔴 未连接")
        self.flight_time = QLabel("飞行时间: 00:00:00")
        self.battery = QLabel("电池: 100%")
        self.altitude = QLabel("高度: 0m")
        self.speed = QLabel("速度: 0m/s")
        self.mode = QLabel("模式: UNKNOWN")
        self.gps = QLabel("GPS: 0 颗")
        self.volt = QLabel("电压: 0.00V")
        self.alert = QLabel("状态: 正常")

        for status_label in [
            self.connection_status,
            self.flight_time,
            self.battery,
            self.altitude,
            self.speed,
            self.mode,
            self.gps,
            self.volt,
            self.alert,
        ]:
            self._apply_status_chip_style(status_label)
        self.connection_status.setCursor(Qt.CursorShape.PointingHandCursor)
        self.connection_status.setToolTip("点击连接或断开")
        self._apply_status_chip_style(self.connection_status, "danger")
        self._apply_status_chip_style(self.alert, "ok")

        self._status_labels = [
            self.connection_status,
            self.flight_time,
            self.battery,
            self.altitude,
            self.speed,
            self.mode,
            self.gps,
            self.volt,
            self.alert,
        ]
        for status_label in self._status_labels:
            status_label.setMinimumWidth(104)

        status_row = QWidget()
        status_row_layout = QHBoxLayout(status_row)
        status_row_layout.setContentsMargins(0, 0, 0, 0)
        status_row_layout.setSpacing(8)
        for status_label in self._status_labels:
            status_row_layout.addWidget(status_label)
        status_row_layout.addStretch()

        status_scroll = QScrollArea()
        status_scroll.setWidgetResizable(True)
        status_scroll.setFrameShape(QFrame.Shape.NoFrame)
        status_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        status_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        status_scroll.setWidget(status_row)
        status_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        top_layout.addWidget(status_scroll, 1)

        # Right side - Map source
        right_controls = QWidget()
        right_controls_layout = QHBoxLayout(right_controls)
        right_controls_layout.setContentsMargins(0, 0, 0, 0)
        right_controls_layout.setSpacing(8)
        map_label = QLabel("地图:")
        self._apply_status_chip_style(map_label, "info")
        map_label.setMinimumWidth(56)
        right_controls_layout.addWidget(map_label)
        self.cmb_map = QComboBox()
        self.cmb_map.addItems(["谷歌卫星", "ArcGIS卫星"])
        self.cmb_map.setCurrentText(self.current_map)
        self.cmb_map.setFixedWidth(120)
        self.cmb_map.setStyleSheet(
            "QComboBox { background:#13263c; color:#d9e6f7; border:1px solid #35506b; border-radius:6px; padding:4px 8px; }"
            "QComboBox QAbstractItemView { background:#13263c; color:#d9e6f7; border:1px solid #35506b; }"
        )
        right_controls_layout.addWidget(self.cmb_map)
        top_layout.addWidget(right_controls, 0)

        main_layout.addWidget(top_bar)

        left_bar = QFrame()
        left_bar.setFixedWidth(38)
        left_bar.setStyleSheet("background-color: rgba(12, 16, 24, 0.92); border-right: 1px solid #273444;")
        left_layout = QVBoxLayout(left_bar)
        left_layout.setContentsMargins(3,22,3,22)
        left_layout.setSpacing(11)
        
        self.btn_waypoint = QPushButton("📍")
        self.btn_waypoint.setToolTip("航点任务规划")
        self.btn_setup = QPushButton("🛠")
        self.btn_setup.setToolTip("Vehicle Setup")
        self.btn_flyview = QPushButton("🎮")
        self.btn_flyview.setToolTip("Fly View")
        self.btn_param = QPushButton("⚙")
        self.btn_param.setToolTip("参数面板")
        self.btn_analyze = QPushButton("📊")
        self.btn_analyze.setToolTip("Analyze / 日志 / 图表")
        self.btn_peripheral = QPushButton("🛰")
        self.btn_peripheral.setToolTip("外围能力")
        self.btn_vehicle = QPushButton("🚁")
        self.btn_vehicle.setToolTip("多机管理")
        self.btn_links = QPushButton("📶")
        self.btn_links.setToolTip("多链路面板")
        self.btn_link = QPushButton("🔗")
        self.btn_link.setToolTip("通信链路配置中心")
        self.btn_mp = QPushButton("🧰")
        self.btn_mp.setToolTip("MP核心工作台")

        for btn in [self.btn_waypoint, self.btn_setup, self.btn_flyview, self.btn_param, self.btn_analyze, self.btn_peripheral, self.btn_vehicle, self.btn_links, self.btn_link, self.btn_mp]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton {"
                "font-size:22px; min-width:34px; min-height:34px; padding:0px;"
                "border: 1px solid #35506b; border-radius: 10px;"
                "background: #13263c; color: #d9e6f7;"
                "}"
                "QPushButton:hover { background:#1a314a; border-color:#4a7398; }"
                "QPushButton:pressed { background:#0f2337; }"
            )
            left_layout.addWidget(btn)
        left_layout.addStretch()

        self.web_view = QWebEngineView()
        self.web_view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        dev_extras_attr = getattr(QWebEngineSettings.WebAttribute, "DeveloperExtrasEnabled", None)
        if dev_extras_attr is not None:
            self.web_view.page().settings().setAttribute(dev_extras_attr, True)
        self.map_bridge = MapBridge(self.web_view.page())
        self._map_channel = QWebChannel(self.web_view.page())
        self._map_channel.registerObject("mapBridge", self.map_bridge)
        self.web_view.page().setWebChannel(self._map_channel)
        self.map_controller = MapController(self.web_view, self.map_bridge, self)
        self.map_controller.initialize(self.current_map, [DEFAULT_LAT, DEFAULT_LON])

        # Create map container with flight control panel overlay
        map_container = QFrame()
        map_layout = QGridLayout(map_container)
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.addWidget(self.web_view, 0, 0)
        # 左上角消息提示覆盖层
        self._notice_overlay = MapNoticeOverlay(map_container)
        map_layout.addWidget(self._notice_overlay, 0, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        
        # Flight control panel - embedded in bottom right
        self.flight_content = FlightControlPanel()
        self.flight_panel = QFrame()
        self.flight_panel.setFixedSize(300, 270)
        self.flight_panel.setStyleSheet("""
            QFrame {
                background-color: rgba(11, 20, 31, 0.95);
                border: 1px solid rgba(58, 85, 116, 0.92);
                border-radius: 14px;
            }
        """)
        flight_layout = QVBoxLayout(self.flight_panel)
        flight_layout.setContentsMargins(8, 8, 8, 8)
        flight_layout.addWidget(self.flight_content)
        map_layout.addWidget(self.flight_panel, 0, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        # 姿态球浮窗（右上）
        self.attitude_ball = AttitudeBall()
        map_layout.addWidget(self.attitude_ball, 0, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_bar)
        splitter.addWidget(map_container)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setCollapsible(0, False)
        # 隐藏分割条句柄，保持左侧栏宽度固定不可拖
        splitter.setStyleSheet("QSplitter::handle { width: 0px; background: transparent; }")
        splitter.setHandleWidth(0)
        main_layout.addWidget(splitter)

        self.init_floating_panels()
        self.bind_all_signals()
        self._reset_live_status_labels()

    def init_floating_panels(self):
        self.waypoint_content = WaypointPanel()
        waypoint_layout = QVBoxLayout(self.waypoint_panel)
        waypoint_layout.setContentsMargins(6, 6, 6, 6)
        waypoint_layout.addWidget(self.waypoint_content)
        self.waypoint_panel.setMinimumSize(540, 820)
        self._resize_waypoint_panel()
        self.waypoint_panel.hide()
        self.waypoint_content.close_clicked.connect(lambda: self.hide_panel(self.waypoint_panel))
        self.waypoint_content.waypoints_updated.connect(self.on_waypoints_updated)
        self.waypoint_content.vehicle_tab_changed.connect(self._on_vehicle_selected)
        self.panel_manager.register("waypoint", self.waypoint_panel, anchor="top-left", margin=(70, 90))

        self.param_content = ParamPanel()
        self.param_content.set_fact_system(self.parameter_manager.fact_system)
        self.param_content.set_fact_controller(self.fact_panel_controller)
        param_layout = QVBoxLayout(self.param_panel)
        param_layout.setContentsMargins(6, 6, 6, 6)
        param_layout.addWidget(self.param_content)
        self.param_panel.setMinimumSize(700, 760)
        self._resize_param_panel()
        self.param_panel.hide()
        self.param_content.close_clicked.connect(lambda: self.hide_panel(self.param_panel))
        self.param_content.vehicle_tab_changed.connect(self._on_vehicle_selected)
        self.panel_manager.register("param", self.param_panel, anchor="top-left", margin=(90, 90))

        self.links_content = LinkManagerPanel()
        links_layout = QVBoxLayout(self.links_panel)
        links_layout.setContentsMargins(6, 6, 6, 6)
        links_layout.addWidget(self.links_content)
        self.links_panel.setMinimumSize(440, 640)
        self.links_panel.hide()
        self.links_content.close_clicked.connect(lambda: self.hide_panel(self.links_panel))
        self.links_content.activate_requested.connect(self._on_link_selected)
        self.links_content.disconnect_requested.connect(self._disconnect_link_from_panel)
        self.links_content.settings_requested.connect(self._open_link_settings)
        self.panel_manager.register("links", self.links_panel, anchor="top-left", margin=(96, 90))

        self.vehicle_content = VehiclePanel()
        vehicle_layout = QVBoxLayout(self.vehicle_panel)
        vehicle_layout.setContentsMargins(6, 6, 6, 6)
        vehicle_layout.addWidget(self.vehicle_content)
        self.vehicle_panel.setMinimumSize(420, 640)
        self.vehicle_panel.hide()
        self.vehicle_content.close_clicked.connect(lambda: self.hide_panel(self.vehicle_panel))
        self.vehicle_content.vehicle_selected.connect(self._on_vehicle_selected)
        self.vehicle_content.open_params_requested.connect(self._open_vehicle_params_page)
        self.vehicle_content.open_mission_requested.connect(self._open_vehicle_mission_page)
        self.vehicle_content.command_requested.connect(self._handle_vehicle_command_request)
        self.vehicle_content.batch_command_requested.connect(self._handle_batch_vehicle_command_request)
        self.vehicle_content.clear_queue_requested.connect(self._clear_selected_vehicle_queues)
        self.panel_manager.register("vehicle", self.vehicle_panel, anchor="top-left", margin=(100, 90))

        self.mp_workbench_panel = MPWorkbenchPanel()
        mp_layout = QVBoxLayout(self.mp_panel)
        mp_layout.setContentsMargins(6, 6, 6, 6)
        mp_layout.addWidget(self.mp_workbench_panel)
        self.mp_panel.setMinimumSize(520, 720)
        self.mp_panel.hide()
        self.mp_workbench_panel.close_clicked.connect(lambda: self.hide_panel(self.mp_panel))
        self.mp_workbench_panel.action_requested.connect(self._handle_mp_action_requested)
        self.panel_manager.register("mp", self.mp_panel, anchor="top-left", margin=(110, 90))

        self.setup_content = VehicleSetupPanel()
        setup_layout = QVBoxLayout(self.setup_panel)
        setup_layout.setContentsMargins(6, 6, 6, 6)
        setup_layout.addWidget(self.setup_content)
        self.setup_panel.setMinimumSize(480, 520)
        self.setup_panel.hide()
        self.setup_content.close_clicked.connect(lambda: self.hide_panel(self.setup_panel))
        self.setup_content.param_focus_requested.connect(self._focus_param_group)
        self.setup_content.firmware_requested.connect(self._open_firmware_upgrade)
        self.panel_manager.register("setup", self.setup_panel, anchor="top-right", margin=(28, 100))

        self.fly_view_content = FlyViewPanel()
        fly_layout = QVBoxLayout(self.fly_view_panel)
        fly_layout.setContentsMargins(6, 6, 6, 6)
        fly_layout.addWidget(self.fly_view_content)
        self.fly_view_panel.setMinimumSize(520, 440)
        self.fly_view_panel.hide()
        self.fly_view_content.close_clicked.connect(lambda: self.hide_panel(self.fly_view_panel))
        self.fly_view_content.guided_action_requested.connect(self._handle_fly_guided_action)
        self.fly_view_content.camera_action_requested.connect(self._handle_camera_action)
        self.fly_view_content.video_open_requested.connect(self._open_video_stream)
        self.fly_view_content.set_video_url(self.settings_manager.video_settings().get("stream_url", ""))
        self.panel_manager.register("fly", self.fly_view_panel, anchor="top-right", margin=(24, 110))

        self.analyze_content = AnalyzePanel()
        analyze_layout = QVBoxLayout(self.analyze_panel)
        analyze_layout.setContentsMargins(6, 6, 6, 6)
        analyze_layout.addWidget(self.analyze_content)
        self.analyze_panel.setMinimumSize(560, 500)
        self.analyze_panel.hide()
        self.analyze_content.close_clicked.connect(lambda: self.hide_panel(self.analyze_panel))
        self.analyze_content.refresh_requested.connect(self._refresh_analyze_panel)
        self.analyze_content.download_logs_requested.connect(self._download_vehicle_logs)
        self.analyze_content.replay_requested.connect(self._replay_log_file)
        self.analyze_content.log_selected.connect(self._preview_log_file)
        self.panel_manager.register("analyze", self.analyze_panel, anchor="top-right", margin=(22, 110))

        self.peripheral_content = PeripheralPanel()
        peripheral_layout = QVBoxLayout(self.peripheral_panel)
        peripheral_layout.setContentsMargins(6, 6, 6, 6)
        peripheral_layout.addWidget(self.peripheral_content)
        self.peripheral_panel.setMinimumSize(520, 500)
        self.peripheral_panel.hide()
        self.peripheral_content.close_clicked.connect(lambda: self.hide_panel(self.peripheral_panel))
        self.peripheral_content.save_requested.connect(self._save_peripheral_config)
        self.peripheral_content.rtk_inject_requested.connect(self._inject_rtk_position)
        self.peripheral_content.firmware_requested.connect(self._open_firmware_upgrade)
        self.peripheral_content.set_values(self._current_peripheral_values())
        self.panel_manager.register("peripherals", self.peripheral_panel, anchor="top-right", margin=(20, 110))

        self._build_mp_action_handlers()
        self._refresh_mp_action_states()

        # Flight control panel is now embedded in main layout

    def _resize_waypoint_panel(self):
        panel_width = max(540, min(640, int(self.width() * 0.32)))
        panel_height = max(820, min(980, self.height() - 120))
        self.waypoint_panel.resize(panel_width, panel_height)

    def _resize_param_panel(self):
        panel_width = max(700, min(860, int(self.width() * 0.42)))
        panel_height = max(720, min(900, self.height() - 120))
        self.param_panel.resize(panel_width, panel_height)

    def refresh_map_waypoints(self, recenter=False):
        if recenter and self.waypoints:
            last_waypoint = self.waypoints[-1]
            self.map_controller.set_center(last_waypoint["lat"], last_waypoint["lon"])
        self.map_controller.set_home_position(self.home_position)
        self.map_controller.update_waypoints(self.waypoints)
        self.map_controller.update_auto_route(self.waypoint_content.get_auto_route_items())
        if 0 <= self._selected_waypoint_index < len(self.waypoints):
            self.map_controller.select_waypoint_on_map(self._selected_waypoint_index)

    def show_panel(self, panel):
        panel_name = getattr(panel, "panel_name", panel.__class__.__name__)
        self.panel_manager.show_panel(panel_name, panel)
        panel.raise_()
        panel.activateWindow()
        self.log_user_action("panel_shown", panel=panel_name, x=panel.x(), y=panel.y())

    def hide_panel(self, panel):
        panel_name = getattr(panel, "panel_name", panel.__class__.__name__)
        self.panel_manager.hide_panel(panel_name, panel)
        self.log_user_action("panel_hidden", panel=panel_name)

    def _load_saved_connection_settings(self):
        try:
            serial_cfg = self.settings_manager.serial_defaults()
            tcp_cfg = self.settings_manager.tcp_defaults()
            udp_cfg = self.settings_manager.udp_defaults()
            self.connection_manager.configure_reconnect(
                enabled=bool(self.settings_manager.get("connections.auto_reconnect", True))
            )
            if serial_cfg.get("baud"):
                self.connect_dialog.cmb_baud.setCurrentText(str(serial_cfg.get("baud")))
            if serial_cfg.get("port"):
                saved_port = str(serial_cfg.get("port"))
                idx = self.connect_dialog.cmb_serial.findData(saved_port)
                if idx >= 0:
                    self.connect_dialog.cmb_serial.setCurrentIndex(idx)
            self.connect_dialog.edit_ip.setText(str(tcp_cfg.get("host", "127.0.0.1") or "127.0.0.1"))
            self.connect_dialog.edit_port.setText(str(tcp_cfg.get("port", 5760) or 5760))
            self.connect_dialog.edit_udp_host.setText(str(udp_cfg.get("host", "0.0.0.0") or "0.0.0.0"))
            self.connect_dialog.edit_udp_port.setText(str(udp_cfg.get("port", 14550) or 14550))
        except Exception:
            self.app_logger.exception("failed to load saved connection settings")

    def _maybe_auto_connect_last_link(self):
        if self.connection_manager.state != "disconnected":
            return
        if not bool(self.settings_manager.get("connections.auto_connect", False)):
            return
        recent_links = self.settings_manager.recent_links()
        if not recent_links:
            return
        try:
            self._connect_recent_link(recent_links[0], show_notice=False)
        except Exception:
            self.app_logger.exception("auto connect last link failed")

    def _connect_recent_link(self, entry: dict, show_notice: bool = True):
        item = dict(entry or {})
        kind = str(item.get("kind", "")).strip().lower()
        payload = dict(item.get("payload", {}) or {})
        if kind == "serial":
            port = str(payload.get("port", "")).strip()
            baud = int(payload.get("baud", 115200) or 115200)
            self._last_link_label = f"串口 {port}@{baud}"
            self.connection_manager.connect_serial(port, baud)
        elif kind == "tcp":
            host = str(payload.get("host", "127.0.0.1") or "127.0.0.1").strip()
            port = int(payload.get("port", 5760) or 5760)
            self._last_link_label = f"TCP {host}:{port}"
            self.connection_manager.connect_tcp(host, port)
        elif kind == "udp":
            host = str(payload.get("host", "0.0.0.0") or "0.0.0.0").strip()
            port = int(payload.get("port", 14550) or 14550)
            self._last_link_label = f"UDP {host}:{port}"
            self.connection_manager.connect_udp(host, port)
        else:
            raise ValueError(f"不支持的历史链路类型: {kind}")
        if show_notice:
            self._show_auto_notice("提示", f"正在连接最近链路：{item.get('label', self._last_link_label)}")

    def _reconnect_last_link(self):
        recent_links = self.settings_manager.recent_links()
        if recent_links:
            self._connect_recent_link(recent_links[0], show_notice=True)
            return
        self.connection_manager.reconnect_last()

    def _open_link_settings(self):
        dialog = LinkSettingsDialog(self)
        dialog.set_values(
            self.settings_manager.serial_defaults(),
            self.settings_manager.tcp_defaults(),
            self.settings_manager.udp_defaults(),
            bool(self.settings_manager.get("connections.auto_reconnect", True)),
            bool(self.settings_manager.get("connections.auto_connect", False)),
            str(self.settings_manager.get("ui.map_source", self.current_map) or self.current_map),
            self.settings_manager.recent_links(),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        values = dialog.values()
        self.settings_manager.update_serial_defaults(values["serial"].get("port", ""), values["serial"].get("baud", 115200), persist=False)
        self.settings_manager.update_tcp_defaults(values["tcp"].get("host", "127.0.0.1"), values["tcp"].get("port", 5760), persist=False)
        self.settings_manager.update_udp_defaults(values["udp"].get("host", "0.0.0.0"), values["udp"].get("port", 14550), persist=False)
        self.settings_manager.set("connections.auto_reconnect", bool(values.get("auto_reconnect", True)), persist=False)
        self.settings_manager.set("connections.auto_connect", bool(values.get("auto_connect", False)), persist=False)
        self.settings_manager.set("ui.map_source", values.get("map_source", self.current_map), persist=False)
        self.settings_manager.save()
        self.current_map = str(values.get("map_source", self.current_map) or self.current_map)
        if hasattr(self, "cmb_map"):
            self.cmb_map.setCurrentText(self.current_map)
        self._load_saved_connection_settings()
        self._show_auto_notice("设置已保存", "通信链路默认值已更新")

    def _open_link_panel(self):
        self.links_content.set_link_summaries(
            self.connection_manager.link_summaries(),
            (self.connection_manager.active_link_summary() or {}).get("key", ""),
        )
        self.links_content.set_active_link(self.connection_manager.active_link_summary())
        self.show_panel(self.links_panel)

    def _on_link_selected(self, link_key: str):
        selected = self.connection_manager.set_active_link(link_key)
        if not selected:
            return
        self.links_content.set_active_link(selected)

    def _disconnect_link_from_panel(self, link_key: str):
        self.connection_manager.disconnect_link(link_key, manual=True)

    def on_link_summaries_changed(self, links: list):
        if hasattr(self, "links_content") and self.links_content is not None:
            active_key = (self.connection_manager.active_link_summary() or {}).get("key", "")
            self.links_content.set_link_summaries(links, active_key)
        self._refresh_mp_action_states()

    def on_active_link_changed(self, link: dict):
        if hasattr(self, "links_content") and self.links_content is not None:
            self.links_content.set_active_link(link)
        link = dict(link or {})
        link_key = str(link.get("key", "") or "")
        kind = str(link.get("kind", "")).strip().lower()
        label = str(link.get("label", "")).strip()
        kind_label = {"serial": "串口", "tcp": "TCP", "udp": "UDP"}.get(kind, kind.upper() or "链路")
        self._last_link_label = f"{kind_label} {label}".strip()
        if not link_key:
            self._current_active_link_key = ""
            return
        if self._current_active_link_key and self._current_active_link_key != link_key:
            self._cache_link_context(self._current_active_link_key, include_params=True, include_mission=True)
        if self._current_active_link_key != link_key:
            self._current_active_link_key = link_key
            self._restore_link_context(link)

    def _open_vehicle_panel(self):
        self.vehicle_content.set_vehicle_summaries(
            self.vehicle_manager.vehicle_summaries(),
            (self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", ""),
        )
        self.vehicle_content.set_active_vehicle(self.vehicle_manager.active_vehicle())
        self.show_panel(self.vehicle_panel)

    def _open_vehicle_params_page(self, vehicle_id: str):
        if vehicle_id:
            self._select_vehicle_context(vehicle_id)
        self._open_param_panel()

    def _open_vehicle_mission_page(self, vehicle_id: str):
        if vehicle_id:
            self._select_vehicle_context(vehicle_id)
        self.show_panel(self.waypoint_panel)
        self.refresh_map_waypoints(recenter=bool(self.waypoints))

    def _open_setup_panel(self, section: str = "summary"):
        self.setup_content.set_vehicle(self.vehicle_manager.active_vehicle())
        self.setup_content.open_section(section)
        self.show_panel(self.setup_panel)

    def _open_fly_view(self):
        active = self.vehicle_manager.active_vehicle() or {}
        self.fly_view_content.set_video_url(self.settings_manager.video_settings().get("stream_url", ""))
        self.fly_view_content.set_vehicle_summary(
            str(active.get("vehicle_id", "--") or "--"),
            str(active.get("mode", self.latest_status.get("mode", "UNKNOWN")) or "UNKNOWN"),
            f"任务点 {int(active.get('mission_count', len(self.waypoints) or 0) or 0)} 个",
            str(active.get("link_name", "") or ""),
        )
        self.fly_view_content.set_status_payload(self.latest_status)
        self.show_panel(self.fly_view_panel)

    def _current_peripheral_values(self) -> dict:
        video_cfg = self.settings_manager.video_settings()
        peripheral_cfg = self.settings_manager.peripheral_settings()
        return {
            "joystick_enabled": bool(peripheral_cfg.get("joystick_enabled", False)),
            "adsb_enabled": bool(peripheral_cfg.get("adsb_enabled", False)),
            "video_stream_url": str(video_cfg.get("stream_url", "") or ""),
            "camera_name": str(video_cfg.get("camera_name", "PayloadCam") or "PayloadCam"),
            "plugin_dirs": list(peripheral_cfg.get("plugin_dirs", []) or []),
            "rtk_host": str(peripheral_cfg.get("rtk_host", "127.0.0.1") or "127.0.0.1"),
            "rtk_port": int(peripheral_cfg.get("rtk_port", 2101) or 2101),
        }

    def _open_peripheral_panel(self):
        self.peripheral_content.set_values(self._current_peripheral_values())
        self.show_panel(self.peripheral_panel)

    def _open_analyze_panel(self):
        self._refresh_analyze_panel()
        self.show_panel(self.analyze_panel)

    def _focus_param_group(self, group_name: str = "全部", search_text: str = ""):
        self._open_param_panel()
        if hasattr(self.param_content, "group_combo"):
            index = self.param_content.group_combo.findText(str(group_name or "全部"))
            if index >= 0:
                self.param_content.group_combo.setCurrentIndex(index)
        if hasattr(self.param_content, "search_edit"):
            self.param_content.search_edit.setText(str(search_text or ""))
            self.param_content.search_edit.setFocus()

    def _open_firmware_upgrade(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择固件文件",
            str(self.settings_manager.get("firmware.last_image", "") or ""),
            "Firmware files (*.apj *.px4 *.bin)",
        )
        if not file_path:
            return

        try:
            image_info = inspect_firmware_image(file_path)
        except Exception as exc:
            self._show_auto_notice("固件校验失败", str(exc))
            return

        self.settings_manager.set("firmware.last_image", file_path, persist=False)
        self.settings_manager.save()

        active_link = self.connection_manager.active_link_summary() or {}
        active_vehicle_id = str((self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "") or "")
        backup_path = self._create_parameter_backup_snapshot(active_vehicle_id, reason="firmware_pre_upgrade")
        plan = build_firmware_upgrade_plan(active_link, image_info)
        message_lines = [
            f"文件: {image_info.file_name}",
            f"格式: {image_info.extension}",
            f"大小: {image_info.size_bytes} bytes",
            f"CRC32: {image_info.crc32}",
        ]
        if image_info.board_id is not None:
            message_lines.append(f"Board ID: {image_info.board_id}")
        if image_info.description:
            message_lines.append(f"描述: {image_info.description}")
        if plan.get("can_reconnect"):
            message_lines.append(f"重连串口: {plan.get('port')} @ {plan.get('baud')}")
        if backup_path is not None:
            message_lines.append(f"参数备份: {backup_path}")
        if plan.get("precheck_steps"):
            message_lines.append("")
            message_lines.append("升级前检查：")
            message_lines.extend(f"- {step}" for step in plan.get("precheck_steps", []))
        if plan.get("postcheck_steps"):
            message_lines.append("")
            message_lines.append("升级后校验：")
            message_lines.extend(f"- {step}" for step in plan.get("postcheck_steps", []))
        message_lines.append("")
        message_lines.append("确认请求飞控进入 bootloader，并开始固件升级流程？")

        if not gcs_confirm(
            self,
            "Firmware Upgrade",
            "\n".join(message_lines),
            yes_text="进入升级",
            no_text="取消",
        ):
            return

        active_vehicle_id = str((self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "") or "")
        thread = self._thread_for_vehicle(active_vehicle_id) if active_vehicle_id else self.connection_manager.thread
        if thread is None:
            self._show_auto_notice("未连接", "当前未连接飞控，将仅打开固件目录供离线刷写")
        elif not hasattr(thread, "reboot_to_bootloader"):
            self._show_auto_notice("未实现", "当前链路暂不支持 Bootloader 重启")
        else:
            try:
                thread.reboot_to_bootloader()
            except Exception as exc:
                self._show_auto_notice("升级入口失败", str(exc))
                return

        if active_link.get("key") and plan.get("can_reconnect"):
            self.connection_manager.disconnect_link(str(active_link.get("key")), manual=True)

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(file_path).resolve().parent)))
        backup_hint = f"，参数已备份到 {backup_path}" if backup_path is not None else ""
        self._show_auto_notice("升级准备完成", f"已校验 {image_info.file_name}，CRC32={image_info.crc32}{backup_hint}")
        self.log_user_action(
            "firmware_upgrade_requested",
            vehicle_id=active_vehicle_id or "CURRENT",
            file=image_info.file_name,
            crc32=image_info.crc32,
        )

        if plan.get("can_reconnect"):
            reconnect_now = gcs_confirm(
                self,
                "Firmware Upgrade",
                "外部刷写完成后，点击“立即重连”恢复 MAVLink 连接；若稍后再刷写，可取消后手动重连。",
                yes_text="立即重连",
                no_text="稍后手动重连",
            )
            if reconnect_now:
                self.connection_manager.connect_serial(str(plan.get("port", "")), int(plan.get("baud", 115200) or 115200))
                self._show_auto_notice("重连中", f"正在重连 {plan.get('port')}@{plan.get('baud')}")
                if backup_path is not None:
                    QTimer.singleShot(1800, lambda path=str(backup_path), vehicle=active_vehicle_id: self._validate_parameter_backup(path, vehicle))

    def _handle_fly_guided_action(self, action_key: str):
        action = str(action_key or "").strip().lower()
        if action in {"vtol_takeoff_30m", "vtol_qland", "vtol_qrtl"}:
            self.execute_flight_command(action)
            return

        thread = self._thread_for_vehicle(str((self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "") or ""))
        if thread is None:
            self._show_auto_notice("未连接", "请先建立连接")
            return
        if not hasattr(thread, "set_mode"):
            self._show_auto_notice("未实现", "当前链路不支持 Guided 模式切换")
            return

        target_mode = CommandRouter.guided_target_mode(action)
        if not target_mode:
            self._show_auto_notice("未实现", f"未知 Guided 动作: {action_key}")
            return
        try:
            thread.set_mode(target_mode)
            status_text = CommandRouter.guided_status_text(action)
            if status_text:
                self.fly_view_content.set_mission_status(status_text)
            self._show_auto_notice("执行完成", f"已发送模式切换：{target_mode}")
            self.log_user_action("fly_guided_action", action=action, target_mode=target_mode)
        except Exception as exc:
            self._show_auto_notice("Guided 动作失败", str(exc))

    def _open_video_stream(self, url: str):
        target = str(url or "").strip()
        if not target:
            self._show_auto_notice("提示", "请先输入视频流 URL")
            return
        current_camera = self.settings_manager.video_settings().get("camera_name", "PayloadCam")
        self.settings_manager.update_video_settings(target, current_camera)
        self.fly_view_content.set_video_url(target)
        opened = QDesktopServices.openUrl(QUrl.fromUserInput(target))
        if opened:
            self._show_auto_notice("视频已打开", target)
            self.log_user_action("video_stream_opened", url=target)
        else:
            self._show_auto_notice("打开失败", f"无法打开视频流：{target}")

    def _handle_camera_action(self, action_key: str):
        labels = {
            "snapshot": "已触发拍照命令",
            "record_start": "开始录像",
            "record_stop": "停止录像",
            "gimbal_center": "云台回中",
        }
        text = labels.get(str(action_key or "").strip(), f"相机动作: {action_key}")
        self.fly_view_content.set_camera_status(text)
        self._show_auto_notice("相机", text)
        self.log_user_action("camera_action_requested", action=action_key)

    def _discover_log_files(self) -> list[str]:
        logs_root = Path(__file__).resolve().parent.parent / "logs"
        return [str(item.path) for item in discover_log_files(logs_root, limit=100)]

    def _preview_log_file(self, file_path: str):
        if hasattr(self, "analyze_content") and self.analyze_content is not None:
            self.analyze_content.set_log_preview(preview_log_file(file_path))

    def _refresh_analyze_panel(self):
        if hasattr(self, "analyze_content") and self.analyze_content is not None:
            self.analyze_content.set_status_payload(self.latest_status)
            entries = discover_log_files(Path(__file__).resolve().parent.parent / "logs", limit=100)
            summary = summarize_log_files(entries)
            summary_text = f"共发现 {summary['total_files']} 个日志/回放文件 | 总大小 {summary['total_bytes'] / 1024.0:.1f} KB"
            if summary.get("latest_file"):
                summary_text += f" | 最新: {summary['latest_file']}"
            self.analyze_content.set_log_files([str(item.path) for item in entries], summary_text=summary_text)
            if entries:
                self.analyze_content.set_log_preview(preview_log_file(entries[0].path))

    def _download_vehicle_logs(self):
        self._refresh_analyze_panel()
        logs_root = Path(__file__).resolve().parent.parent / "logs"
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(logs_root)))
        self._show_auto_notice("日志目录", f"已打开 {logs_root}")
        self.log_user_action("logs_directory_opened", path=str(logs_root))

    def _replay_log_file(self, file_path: str):
        path = Path(str(file_path or "").strip())
        if not path.exists():
            self._show_auto_notice("回放失败", f"文件不存在：{path}")
            return
        self._preview_log_file(str(path))
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        self._show_auto_notice("回放/查看", f"已打开日志文件：{path.name}")
        self.log_user_action("log_replay_opened", file=str(path))

    def _save_peripheral_config(self, values: dict):
        payload = dict(values or {})
        self.settings_manager.update_video_settings(payload.get("video_stream_url", ""), payload.get("camera_name", "PayloadCam"), persist=False)
        self.settings_manager.update_peripheral_settings(payload, persist=False)
        self.settings_manager.save()
        self.fly_view_content.set_video_url(payload.get("video_stream_url", ""))
        self.peripheral_content.set_values(self._current_peripheral_values())
        self._show_auto_notice("设置已保存", "外围能力配置已更新")
        self.log_user_action("peripheral_settings_saved", values=json.dumps(payload, ensure_ascii=False))

    def _inject_rtk_position(self, payload: dict):
        values = dict(payload or {})
        self.settings_manager.update_peripheral_settings(
            {
                "rtk_host": values.get("host", "127.0.0.1"),
                "rtk_port": values.get("port", 2101),
            },
            persist=False,
        )
        self.settings_manager.save()
        thread = self._thread_for_vehicle(str((self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "") or ""))
        if thread is not None and hasattr(thread, "set_home_position"):
            try:
                thread.set_home_position(float(values.get("lat", 0.0) or 0.0), float(values.get("lon", 0.0) or 0.0), float(values.get("alt", 0.0) or 0.0))
            except Exception as exc:
                self._show_auto_notice("RTK/GPS 注入失败", str(exc))
                return
        self._show_auto_notice("RTK/GPS", f"已写入目标坐标 {float(values.get('lat', 0.0) or 0.0):.6f}, {float(values.get('lon', 0.0) or 0.0):.6f}")
        self.log_user_action("rtk_injection_requested", values=json.dumps(values, ensure_ascii=False))

    def _handle_vehicle_command_request(self, vehicle_id: str, command_name: str):
        if vehicle_id:
            self._select_vehicle_context(vehicle_id)
        self.execute_flight_command(command_name, vehicle_id=vehicle_id)

    def _on_vehicle_selected(self, vehicle_id: str):
        selected = self._select_vehicle_context(vehicle_id)
        if not selected:
            return
        lat = selected.get("lat")
        lon = selected.get("lon")
        if lat is not None and lon is not None:
            self.map_controller.set_center(float(lat), float(lon))

    def on_vehicle_summaries_changed(self, vehicles: list):
        active_id = (self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "")
        if hasattr(self, "vehicle_content") and self.vehicle_content is not None:
            self.vehicle_content.set_vehicle_summaries(vehicles, active_id)
        if hasattr(self, "param_content") and self.param_content is not None:
            self.param_content.set_vehicle_tabs(vehicles, active_id)
        if hasattr(self, "waypoint_content") and self.waypoint_content is not None:
            self.waypoint_content.set_vehicle_tabs(vehicles, active_id)
        self._refresh_mp_action_states()

    def on_active_vehicle_changed(self, vehicle: dict):
        if hasattr(self, "vehicle_content") and self.vehicle_content is not None:
            self.vehicle_content.set_active_vehicle(vehicle)
        item = dict(vehicle or {})
        vehicle_id = str(item.get("vehicle_id", "") or "")
        if vehicle_id:
            if hasattr(self, "param_content") and self.param_content is not None:
                self.param_content.activate_vehicle_tab(vehicle_id, emit_signal=False)
            if hasattr(self, "waypoint_content") and self.waypoint_content is not None:
                self.waypoint_content.activate_vehicle_tab(vehicle_id, emit_signal=False)
        if hasattr(self, "flight_content") and self.flight_content is not None:
            self.flight_content.set_vehicle_identity(str(item.get("vehicle_id", "--") or "--"), str(item.get("link_name", "") or ""))
        if hasattr(self, "setup_content") and self.setup_content is not None:
            self.setup_content.set_vehicle(item)
        if hasattr(self, "fly_view_content") and self.fly_view_content is not None:
            self.fly_view_content.set_vehicle_summary(
                str(item.get("vehicle_id", "--") or "--"),
                str(item.get("mode", self.latest_status.get("mode", "UNKNOWN")) or "UNKNOWN"),
                f"任务点 {int(item.get('mission_count', len(self.waypoints) or 0) or 0)} 个",
                str(item.get("link_name", "") or ""),
            )

    def on_link_status_updated(self, data: dict):
        try:
            plugin_bundle = resolve_plugins(data, None)
            self.vehicle_manager.update_from_status(
                data,
                link_name=str(data.get("link_label", self._last_link_label) or self._last_link_label),
                plugin_bundle=plugin_bundle,
                link_key=str(data.get("link_key", "") or ""),
            )
        except Exception:
            self.app_logger.exception("link status update failed")

    def _handle_mp_action_requested(self, action_key: str):
        handler = self._mp_action_handlers.get(str(action_key or "").strip())
        if handler is None:
            self._show_auto_notice("未实现", f"未注册的动作: {action_key}")
            return
        try:
            handler()
        except Exception as exc:
            self.app_logger.exception("MP action failed: %s", action_key)
            self._show_auto_notice("执行失败", str(exc))

    def start_connection(self):
        if self.connection_manager.state in {"connecting", "disconnecting"}:
            self._show_auto_notice("提示", "连接状态切换中，请稍后再试")
            return

        self.log_user_action("connection_dialog_opened")
        if self.connect_dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                mode_index = self.connect_dialog.stack.currentIndex()
                if mode_index == 0:
                    port = self.connect_dialog.cmb_serial.currentData()
                    if not port:
                        port = self.connect_dialog.cmb_serial.currentText().split(" - ")[0].strip()
                    if not port or "未检测到串口" in str(port):
                        self._pending_manual_success_notice = False
                        self.log_user_action("connection_failed", error="未检测到可用串口")
                        self._show_auto_notice("未检测到串口", "请检查驱动/线缆，并点击串口刷新按钮后重试")
                        return
                    baud = int(self.connect_dialog.cmb_baud.currentText())
                    self.settings_manager.update_serial_defaults(port, baud)
                    self.settings_manager.add_recent_link("serial", f"{port}@{baud}", {"port": port, "baud": baud})
                    self._last_link_label = f"串口 {port}@{baud}"
                    self._pending_manual_success_notice = True
                    self.log_user_action("connection_requested", connection_type="serial", port=port, baud=baud)
                    self.connection_manager.connect_serial(port, baud)
                elif mode_index == 1:
                    ip = self.connect_dialog.edit_ip.text().strip()
                    port = int(self.connect_dialog.edit_port.text())
                    self.settings_manager.update_tcp_defaults(ip, port)
                    self.settings_manager.add_recent_link("tcp", f"TCP {ip}:{port}", {"host": ip, "port": port})
                    self._last_link_label = f"TCP {ip}:{port}"
                    self._pending_manual_success_notice = True
                    self.log_user_action("connection_requested", connection_type="tcp", ip=ip, port=port)
                    self.connection_manager.connect_tcp(ip, port)
                else:
                    host = self.connect_dialog.edit_udp_host.text().strip() or "0.0.0.0"
                    port = int(self.connect_dialog.edit_udp_port.text())
                    self.settings_manager.update_udp_defaults(host, port)
                    self.settings_manager.add_recent_link("udp", f"UDP {host}:{port}", {"host": host, "port": port})
                    self._last_link_label = f"UDP {host}:{port}"
                    self._pending_manual_success_notice = True
                    self.log_user_action("connection_requested", connection_type="udp", host=host, port=port)
                    self.connection_manager.connect_udp(host, port)
            except Exception as e:
                self._pending_manual_success_notice = False
                self.log_user_action("connection_failed", error=str(e))
                self._show_auto_notice("连接失败", str(e))
        else:
            self._pending_manual_success_notice = False
            self.log_user_action("connection_dialog_cancelled")

    def on_connection_status_clicked(self):
        state = self.connection_manager.state
        if state == "connected":
            if not gcs_confirm(
                self,
                "断开连接",
                "确定断开与飞控的连接吗？",
                yes_text="断开",
                no_text="取消",
                danger=True,
            ):
                return
            self.connection_manager.disconnect(manual=True)
            self._show_auto_notice("提示", "已断开连接")
            self.log_user_action("connection_disconnected_from_status")
            return
        if state in {"connecting", "disconnecting"}:
            self._show_auto_notice("提示", "连接状态切换中，请稍后再试")
            return
        self.start_connection()

    def execute_flight_command(self, command_name, vehicle_id: str | None = None):
        active_vehicle = self.vehicle_manager.active_vehicle() or {}
        target_vehicle_id = str(vehicle_id or active_vehicle.get("vehicle_id", "") or "CURRENT")
        detail = self.vehicle_manager.vehicle_detail(target_vehicle_id) or {}
        if detail.get("command_busy") or target_vehicle_id in self._busy_vehicle_ids:
            self._show_auto_notice("请稍候", f"载具 {target_vehicle_id} 的上一条指令仍在处理中")
            return
        thread = self._thread_for_vehicle(target_vehicle_id)
        if thread is None:
            self._show_auto_notice("未连接", "请先建立连接")
            return

        confirm_meta = CommandRouter.confirmation_for(command_name)
        if confirm_meta:
            if not gcs_confirm(
                self,
                str(confirm_meta.get("title", "确认执行")),
                str(confirm_meta.get("message", "是否继续执行当前动作？")),
                yes_text="确认执行",
                no_text="取消",
                danger=True,
            ):
                return

        self.log_user_action("flight_control_clicked", command=command_name, vehicle_id=target_vehicle_id)
        mode_requirement = CommandRouter.mode_requirement(command_name)
        if mode_requirement:
            if not self._ensure_vtol_mode(
                thread,
                str(mode_requirement.get("target_mode", "") or ""),
                fallback_modes=set(mode_requirement.get("fallback_modes", set()) or set()),
            ):
                return

        commands = {
            "arm": thread.arm,
            "disarm": thread.disarm,
            "vtol_takeoff_30m": lambda: thread.vtol_takeoff(30),
            "vtol_qland": thread.qland,
            "vtol_qrtl": thread.qrtl,
        }
        if command_name not in commands:
            self._show_auto_notice("未实现", f"不支持的飞控动作: {command_name}")
            return
        self._busy_vehicle_ids.add(target_vehicle_id)
        self._flight_command_busy = bool(self._busy_vehicle_ids)
        self._command_busy_vehicle_id = target_vehicle_id
        self.vehicle_manager.mark_command_state(target_vehicle_id, command_name, True)
        self.flight_content.set_command_busy(True, f"载具 {target_vehicle_id} 指令发送中，请稍候…")
        try:
            commands[command_name]()
        finally:
            QTimer.singleShot(900, lambda vehicle_key=target_vehicle_id: self._clear_flight_command_busy(vehicle_key))

    def _ensure_vtol_mode(self, thread, target_mode: str, fallback_modes: set[str] | None = None) -> bool:
        fallback_modes = set(fallback_modes or set())
        accepted = {str(target_mode).upper()} | {str(item).upper() for item in fallback_modes}
        current_mode = str(self.latest_status.get("mode", "UNKNOWN") or "UNKNOWN").upper()
        if current_mode in accepted:
            return True
        if not hasattr(thread, "set_mode"):
            self._show_auto_notice("功能不可用", "当前通信模块不支持模式切换")
            return False
        try:
            thread.set_mode(target_mode)
        except Exception as exc:
            self._show_auto_notice("模式切换失败", str(exc))
            return False

        deadline = time.time() + 3.0
        while time.time() < deadline:
            QApplication.processEvents()
            mode_now = str(self.latest_status.get("mode", "UNKNOWN") or "UNKNOWN").upper()
            if mode_now in accepted:
                return True
            time.sleep(0.05)

        self._show_auto_notice("模式未就绪", f"未能切换到 {target_mode}，当前模式: {self.latest_status.get('mode', 'UNKNOWN')}")
        return False

    def _clear_flight_command_busy(self, vehicle_id: str | None = None):
        target_vehicle_id = str(vehicle_id or self._command_busy_vehicle_id or "")
        if target_vehicle_id:
            last_command = (self.vehicle_manager.vehicle_detail(target_vehicle_id) or {}).get("last_command", "")
            self.vehicle_manager.mark_command_state(target_vehicle_id, str(last_command or ""), False)
            self._busy_vehicle_ids.discard(target_vehicle_id)
        self._flight_command_busy = bool(self._busy_vehicle_ids)
        self._command_busy_vehicle_id = ""
        if target_vehicle_id and self._process_next_vehicle_command(target_vehicle_id):
            return
        if self._busy_vehicle_ids:
            self.flight_content.set_command_busy(True, f"并发队列执行中：{len(self._busy_vehicle_ids)} 架载具")
        else:
            self.flight_content.set_command_busy(False)

    def _build_mp_action_handlers(self):
        self._mp_action_handlers = {
            "connection.open": self.start_connection,
            "connection.disconnect": lambda: self.connection_manager.disconnect(manual=True),
            "connection.reconnect": self._reconnect_last_link,
            "connection.panel": self._open_link_panel,
            "connection.settings": self._open_link_settings,
            "vehicle.panel": self._open_vehicle_panel,
            "setup.open": self._open_setup_panel,
            "setup.sensors": lambda: self._open_setup_panel("sensors"),
            "setup.power": lambda: self._open_setup_panel("power"),
            "setup.firmware": self._open_firmware_upgrade,
            "params.open": self._open_param_panel,
            "params.refresh": self.refresh_parameters_from_vehicle,
            "params.save": self.save_parameters_to_vehicle,
            "mission.toggle_add": self.enable_map_add_waypoint,
            "mission.fit_route": self.map_controller.fit_mission_route,
            "mission.batch_insert": self._mp_batch_insert_waypoints,
            "mission.batch_delete": self._mp_batch_delete_waypoints,
            "mission.reverse": self._mp_reverse_waypoints,
            "mission.clear": self.waypoint_content.clear_waypoints,
            "mission.uniform_alt": self.waypoint_content.set_uniform_height,
            "mission.set_home_vehicle": self._set_home_from_vehicle,
            "mission.set_home_map": self._start_home_map_pick_from_mp,
            "mission.download": self.download_waypoints_from_vehicle,
            "mission.upload": self.waypoint_content.request_upload,
            "map.toggle_measure": self.map_controller.toggle_measure_mode,
            "map.clear_measure": self.map_controller.clear_measure,
            "map.locate_aircraft": self.map_controller.locate_aircraft,
            "map.toggle_follow": self.map_controller.toggle_follow_aircraft,
            "flight.arm": lambda: self.execute_flight_command("arm"),
            "flight.disarm": lambda: self.execute_flight_command("disarm"),
            "flight.takeoff": lambda: self.execute_flight_command("vtol_takeoff_30m"),
            "flight.land": lambda: self.execute_flight_command("vtol_qland"),
            "flight.rtl": lambda: self.execute_flight_command("vtol_qrtl"),
            "fly.view": self._open_fly_view,
            "fly.guided_hold": lambda: self._handle_fly_guided_action("guided_hold"),
            "fly.guided_resume": lambda: self._handle_fly_guided_action("guided_resume"),
            "analyze.open": self._open_analyze_panel,
            "analyze.refresh": self._refresh_analyze_panel,
            "analyze.download_logs": self._download_vehicle_logs,
            "peripheral.open": self._open_peripheral_panel,
            "peripheral.save": lambda: self._save_peripheral_config(self.peripheral_content.values()),
            "peripheral.rtk": lambda: self._inject_rtk_position({
                "host": self.peripheral_content.rtk_host.text().strip(),
                "port": int(self.peripheral_content.rtk_port.value()),
                "lat": float(self.peripheral_content.inject_lat.value()),
                "lon": float(self.peripheral_content.inject_lon.value()),
                "alt": float(self.peripheral_content.inject_alt.value()),
            }),
        }

    def _mp_batch_insert_waypoints(self):
        self.show_panel(self.waypoint_panel)
        self.waypoint_content.batch_insert_after_selected()

    def _mp_batch_delete_waypoints(self):
        self.show_panel(self.waypoint_panel)
        self.waypoint_content.delete_selected_waypoints()

    def _mp_reverse_waypoints(self):
        self.show_panel(self.waypoint_panel)
        self.waypoint_content.reverse_waypoints()

    def _active_link_context(self) -> tuple[str, str]:
        active = self.connection_manager.active_link_summary() if hasattr(self.connection_manager, "active_link_summary") else None
        link_key = str((active or {}).get("key", "") or "")
        link_label = str((active or {}).get("label", self._last_link_label) or self._last_link_label or "当前链路")
        return link_key, link_label

    def _cache_vehicle_context(self, vehicle_id: str | None = None, include_params: bool = True, include_mission: bool = True):
        active = self.vehicle_manager.active_vehicle() or {}
        target_vehicle_id = str(vehicle_id or active.get("vehicle_id", "") or "").strip()
        if not target_vehicle_id:
            return
        if include_params:
            values = self.parameter_manager.fact_system.values_dict()
            if values:
                self._params_by_vehicle[target_vehicle_id] = dict(values)
        if include_mission:
            self._mission_context_by_vehicle[target_vehicle_id] = {
                "home_position": (dict(self.home_position) if isinstance(self.home_position, dict) else None),
                "waypoints": [dict(wp) for wp in (self.waypoints or [])],
                "auto_route_overrides": dict(getattr(self.waypoint_content, "_auto_route_overrides", {}) or {}),
                "plan_constraints": dict(getattr(self.waypoint_content, "_plan_constraints", {}) or {}),
            }

    def _cache_link_context(self, link_key: str | None = None, include_params: bool = True, include_mission: bool = True):
        self._cache_vehicle_context(include_params=include_params, include_mission=include_mission)
        target_key = str(link_key or self._active_link_context()[0]).strip()
        if not target_key:
            return
        if include_params:
            values = self.parameter_manager.fact_system.values_dict()
            if values:
                self._params_by_link[target_key] = dict(values)
        if include_mission:
            self._mission_context_by_link[target_key] = {
                "home_position": (dict(self.home_position) if isinstance(self.home_position, dict) else None),
                "waypoints": [dict(wp) for wp in (self.waypoints or [])],
                "auto_route_overrides": dict(getattr(self.waypoint_content, "_auto_route_overrides", {}) or {}),
                "plan_constraints": dict(getattr(self.waypoint_content, "_plan_constraints", {}) or {}),
            }

    def _restore_link_context(self, link: dict | None):
        item = dict(link or {})
        link_key = str(item.get("key", "") or "")
        if not link_key:
            return
        active_vehicle = self.vehicle_manager.active_vehicle() or {}
        active_vehicle_id = str(active_vehicle.get("vehicle_id", "") or "").strip()
        vehicle_link_key = self._find_link_key_for_vehicle(active_vehicle) if active_vehicle_id else ""

        params = None
        if active_vehicle_id and vehicle_link_key == link_key:
            params = self._params_by_vehicle.get(active_vehicle_id)
        if not params:
            params = self._params_by_link.get(link_key)
        if params:
            self.parameter_manager.fact_system.update_values(params)
            self.param_content.set_fact_system(self.parameter_manager.fact_system)
            self.param_content.set_parameters(params, vehicle_id=active_vehicle_id or None)
            self.param_content.mark_status(f"已切换到 {item.get('label', '当前链路')} 的参数缓存", vehicle_id=active_vehicle_id or None)

        mission = None
        if active_vehicle_id and vehicle_link_key == link_key:
            mission = self._mission_context_by_vehicle.get(active_vehicle_id)
        if mission is None:
            mission = self._mission_context_by_link.get(link_key)
        if mission is None:
            self._sync_active_vehicle_context_metrics(include_params=bool(params), include_mission=False)
            return
        self.home_position = dict(mission.get("home_position") or {}) if mission.get("home_position") else None
        self.waypoints = [dict(wp) for wp in (mission.get("waypoints") or [])]
        self.waypoint_content.set_home_waypoint(self.home_position, vehicle_id=active_vehicle_id or None)
        self.waypoint_content.set_auto_route_overrides(dict(mission.get("auto_route_overrides") or {}), vehicle_id=active_vehicle_id or None)
        self.waypoint_content.set_plan_constraints(dict(mission.get("plan_constraints") or {}), vehicle_id=active_vehicle_id or None)
        self.waypoint_content.set_waypoints(self.waypoints, vehicle_id=active_vehicle_id or None)
        self.refresh_map_waypoints(recenter=bool(self.waypoints))
        self._sync_active_vehicle_context_metrics(include_params=bool(params), include_mission=True)

    def _sync_active_vehicle_context_metrics(self, include_params: bool = True, include_mission: bool = True):
        active = self.vehicle_manager.active_vehicle() or {}
        vehicle_id = str(active.get("vehicle_id", "") or "")
        if not vehicle_id:
            return
        payload = {}
        if include_params:
            params = self.parameter_manager.fact_system.values_dict()
            payload["params_total"] = len(params)
            payload["params_modified"] = len(self.param_content.modified_parameters()) if hasattr(self, "param_content") else 0
        if include_mission:
            payload["mission_count"] = len(self.waypoints or [])
            payload["auto_route_count"] = len(self.waypoint_content.get_auto_route_items()) if hasattr(self, "waypoint_content") else 0
            payload["home_set"] = bool(self.home_position or getattr(self.waypoint_content, "_home_wp", None))
        if payload:
            self.vehicle_manager.update_vehicle_context(vehicle_id, **payload)

    def _find_link_key_for_vehicle(self, vehicle: dict | None) -> str:
        item = dict(vehicle or {})
        direct_key = str(item.get("link_key", "") or "").strip()
        if direct_key:
            return direct_key
        target = str(item.get("link_name", "") or "").strip()
        if not target or not hasattr(self.connection_manager, "link_summaries"):
            return ""
        for link in self.connection_manager.link_summaries():
            label = str(link.get("label", "") or "").strip()
            if label and (target == label or target.endswith(label)):
                return str(link.get("key", "") or "")
        return ""

    def _thread_for_vehicle(self, vehicle_id: str):
        detail = self.vehicle_manager.vehicle_detail(vehicle_id) or {}
        link_key = self._find_link_key_for_vehicle(detail)
        if link_key and hasattr(self.connection_manager, "thread_for_link"):
            thread = self.connection_manager.thread_for_link(link_key)
            if thread is not None:
                return thread
        if link_key:
            self.connection_manager.set_active_link(link_key)
        return self.connection_manager.thread

    @staticmethod
    def _command_display_name(command_name: str) -> str:
        return CommandRouter.display_name(command_name)

    def _enqueue_vehicle_command(self, vehicle_id: str, command_name: str) -> bool:
        payload = self.vehicle_manager.enqueue_command(vehicle_id, command_name)
        if payload is None:
            return False
        if not payload.get("command_busy"):
            self._process_next_vehicle_command(vehicle_id)
        return True

    def _process_next_vehicle_command(self, vehicle_id: str) -> bool:
        detail = self.vehicle_manager.vehicle_detail(vehicle_id) or {}
        if detail.get("command_busy"):
            return False
        next_command = self.vehicle_manager.pop_next_command(vehicle_id)
        if not next_command:
            return False
        self.execute_flight_command(next_command, vehicle_id=vehicle_id)
        return True

    def _handle_batch_vehicle_command_request(self, command_name: str, vehicle_ids: list[str]):
        targets = []
        for vehicle_id in vehicle_ids or []:
            key = str(vehicle_id or "").strip()
            if key and key not in targets:
                targets.append(key)
        if not targets:
            return
        queued = [vehicle_id for vehicle_id in targets if self._enqueue_vehicle_command(vehicle_id, command_name)]
        if queued:
            action_label = self._command_display_name(command_name)
            self._show_auto_notice("批量控制已加入队列", f"{len(queued)} 架载具等待执行 {action_label}")
            self.log_user_action("flight_batch_command_queued", command=command_name, vehicle_ids=",".join(queued), total=len(queued))

    def _clear_selected_vehicle_queues(self, vehicle_ids: list[str]):
        cleared = []
        for vehicle_id in vehicle_ids or []:
            key = str(vehicle_id or "").strip()
            if not key:
                continue
            if self.vehicle_manager.set_command_queue(key, []) is not None:
                cleared.append(key)
        if cleared:
            self._show_auto_notice("队列已清空", f"已清空 {len(cleared)} 架载具的待执行指令")

    def _select_vehicle_context(self, vehicle_id: str):
        selected = self.vehicle_manager.set_active_vehicle(vehicle_id)
        if not selected:
            return None
        if hasattr(self, "param_content") and self.param_content is not None:
            self.param_content.activate_vehicle_tab(vehicle_id, emit_signal=False)
        if hasattr(self, "waypoint_content") and self.waypoint_content is not None:
            self.waypoint_content.activate_vehicle_tab(vehicle_id, emit_signal=False)
        link_key = self._find_link_key_for_vehicle(selected)
        if link_key:
            self.connection_manager.set_active_link(link_key)
        return selected

    def _refresh_mp_action_states(self):
        workbench = getattr(self, "mp_workbench_panel", None)
        if workbench is None:
            return

        state = str(getattr(self.connection_manager, "state", "disconnected") or "disconnected")
        is_connected = state == "connected"

        if hasattr(workbench, "set_status"):
            status_text = {
                "connected": "飞控已连接",
                "connecting": "飞控连接中…",
                "disconnecting": "飞控断开中…",
                "disconnected": "飞控未连接",
            }.get(state, "飞控未连接")
            workbench.set_status(status_text)

        if not hasattr(workbench, "set_action_active"):
            return

        workbench.set_action_active("connection.open", state in {"connecting", "disconnected"})
        workbench.set_action_active("connection.disconnect", state in {"connected", "disconnecting"})
        workbench.set_action_active("connection.reconnect", bool(self.settings_manager.recent_links()))
        workbench.set_action_active("connection.panel", len(self.connection_manager.link_summaries()) > 0)
        has_vehicle = len(self.vehicle_manager.vehicle_summaries()) > 0
        workbench.set_action_active("connection.settings", True)
        workbench.set_action_active("vehicle.panel", has_vehicle)
        workbench.set_action_active("setup.open", has_vehicle)
        workbench.set_action_active("setup.sensors", has_vehicle)
        workbench.set_action_active("setup.power", has_vehicle)
        workbench.set_action_active("setup.firmware", is_connected)
        workbench.set_action_active("mission.toggle_add", self._map_add_mode)
        workbench.set_action_active("mission.upload", self._mission_transfer_active and is_connected)
        workbench.set_action_active("mission.download", self._mission_transfer_active and is_connected)
        workbench.set_action_active("map.toggle_measure", bool(getattr(self.map_controller, "measure_mode", False)))
        workbench.set_action_active("map.toggle_follow", bool(getattr(self.map_controller, "follow_aircraft", False)))
        workbench.set_action_active("fly.view", has_vehicle)
        workbench.set_action_active("fly.guided_hold", is_connected)
        workbench.set_action_active("fly.guided_resume", is_connected)
        workbench.set_action_active("analyze.open", True)
        workbench.set_action_active("analyze.refresh", True)
        workbench.set_action_active("analyze.download_logs", bool(self._discover_log_files()) or is_connected)
        workbench.set_action_active("peripheral.open", True)
        workbench.set_action_active("peripheral.save", True)
        workbench.set_action_active("peripheral.rtk", is_connected)

    def _open_param_panel(self):
        self.show_panel(self.param_panel)
        self.param_content.set_fact_system(self.parameter_manager.fact_system)
        active_vehicle_id = str((self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "") or "")
        if active_vehicle_id:
            self.param_content.activate_vehicle_tab(active_vehicle_id, emit_signal=False)
        cached = self.parameter_manager.fact_system.values_dict()
        if cached:
            self.param_content.set_parameters(cached, vehicle_id=active_vehicle_id or None)
        if self.connection_manager.is_connected():
            self.refresh_parameters_from_vehicle()
        else:
            self.param_content.mark_status("未连接飞控，可导入JSON或查看缓存", vehicle_id=active_vehicle_id or None)

    def refresh_parameters_from_vehicle(self):
        active_vehicle_id = str((self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "") or "")
        thread = self._thread_for_vehicle(active_vehicle_id) if active_vehicle_id else self.connection_manager.thread
        link_key, link_label = self._active_link_context()
        if thread is None or not self.connection_manager.is_connected():
            self._show_auto_notice("未连接", "请先建立飞控连接")
            return
        self.connection_manager.suppress_watchdog(True)
        try:
            self.param_content.mark_status(f"正在从 {link_label} 读取参数…", vehicle_id=active_vehicle_id or None)
            QApplication.processEvents()
            params = self.parameter_manager.load_from_vehicle(thread, timeout=8.0)
            self.param_content.set_fact_system(self.parameter_manager.fact_system)
            self.param_content.set_parameters(params, vehicle_id=active_vehicle_id or None)
            self._cache_link_context(link_key, include_params=True, include_mission=False)
            self._sync_active_vehicle_context_metrics(include_params=True, include_mission=False)
            self._show_auto_notice("读取成功", f"[{link_label}] 已读取 {len(params)} 项参数")
            self.log_user_action("params_loaded_from_vehicle", total=len(params), link=link_label, link_key=link_key)
        except Exception as exc:
            self.param_content.mark_status(f"读取失败：{exc}", vehicle_id=active_vehicle_id or None)
            self._show_auto_notice("参数读取失败", str(exc))
            self.app_logger.exception("parameter refresh failed")
        finally:
            self.connection_manager.suppress_watchdog(False)

    def save_parameters_to_vehicle(self):
        active_vehicle_id = str((self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "") or "")
        thread = self._thread_for_vehicle(active_vehicle_id) if active_vehicle_id else self.connection_manager.thread
        link_key, link_label = self._active_link_context()
        if thread is None or not self.connection_manager.is_connected():
            self._show_auto_notice("未连接", "请先建立飞控连接")
            return
        modified = self.param_content.modified_parameters(vehicle_id=active_vehicle_id or None)
        if not modified:
            self._show_auto_notice("提示", "没有已修改的参数")
            return
        self.connection_manager.suppress_watchdog(True)
        try:
            self.param_content.mark_status(f"正在通过 {link_label} 写入 {len(modified)} 项参数…", vehicle_id=active_vehicle_id or None)
            QApplication.processEvents()
            applied = self.parameter_manager.apply_to_vehicle(thread, modified, timeout_per_param=1.5)
            self.param_content.apply_param_values(applied, vehicle_id=active_vehicle_id or None)
            self._cache_link_context(link_key, include_params=True, include_mission=False)
            self._sync_active_vehicle_context_metrics(include_params=True, include_mission=False)
            self._show_auto_notice("写入成功", f"[{link_label}] 已写入 {len(applied)} 项参数")
            self.log_user_action("params_written_to_vehicle", total=len(applied), link=link_label, link_key=link_key)
        except Exception as exc:
            self.param_content.mark_status(f"写入失败：{exc}", vehicle_id=active_vehicle_id or None)
            self._show_auto_notice("参数写入失败", str(exc))
            self.app_logger.exception("parameter save failed")
        finally:
            self.connection_manager.suppress_watchdog(False)

    def import_parameters_from_file(self):
        active_vehicle_id = str((self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "") or "")
        file_path, _ = QFileDialog.getOpenFileName(self, "导入参数", "", "JSON files (*.json)")
        if not file_path:
            return
        try:
            values = self.parameter_manager.import_from_file(file_path)
            self.param_content.set_fact_system(self.parameter_manager.fact_system)
            self.param_content.set_parameters(self.parameter_manager.fact_system.values_dict(), vehicle_id=active_vehicle_id or None)
            self._cache_link_context(include_params=True, include_mission=False)
            self._sync_active_vehicle_context_metrics(include_params=True, include_mission=False)
            self._show_auto_notice("导入成功", f"已导入 {len(values)} 项参数")
            self.log_user_action("params_imported_from_file", total=len(values), file=file_path)
        except Exception as exc:
            self._show_auto_notice("参数导入失败", str(exc))
            self.app_logger.exception("parameter import failed")

    def export_parameters_to_file(self):
        active_vehicle_id = str((self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "") or "")
        file_path, _ = QFileDialog.getSaveFileName(self, "导出参数快照", "params_snapshot.json", "JSON files (*.json)")
        if not file_path:
            return
        try:
            payload = self.param_content.snapshot_payload(vehicle_id=active_vehicle_id or None) if hasattr(self, "param_content") else None
            self.parameter_manager.export_to_file(file_path, payload=payload)
            self._show_auto_notice("导出成功", f"参数快照已导出到 {file_path}")
            self.log_user_action("params_exported_to_file", file=file_path, vehicle_id=active_vehicle_id or "GLOBAL")
        except Exception as exc:
            self._show_auto_notice("参数导出失败", str(exc))
            self.app_logger.exception("parameter export failed")

    def _create_parameter_backup_snapshot(self, vehicle_id: str = "", reason: str = "manual"):
        try:
            payload = self.param_content.snapshot_payload(vehicle_id=vehicle_id or None) if hasattr(self, "param_content") else {}
            values = dict((payload or {}).get("values") or self.parameter_manager.fact_system.values_dict() or {})
            if not values:
                return None
            backup_dir = Path(__file__).resolve().parent.parent / "logs" / "data" / "records" / "param_backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            safe_vehicle = str(vehicle_id or "current").replace(":", "_")
            file_path = backup_dir / f"{safe_vehicle}_{reason}_{stamp}.json"
            snapshot = dict(payload or {})
            snapshot.setdefault("vehicle_id", vehicle_id or "CURRENT")
            snapshot["reason"] = reason
            snapshot["values"] = values
            self.parameter_manager.export_to_file(str(file_path), payload=snapshot)
            return file_path
        except Exception:
            self.app_logger.exception("parameter backup snapshot failed")
            return None

    def _validate_parameter_backup(self, backup_path, vehicle_id: str = ""):
        path = Path(str(backup_path or ""))
        if not path.exists():
            return
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
            before_values = dict(snapshot.get("values") or {})
            if self.connection_manager.is_connected():
                self.refresh_parameters_from_vehicle()
            after_values = self.parameter_manager.fact_system.values_dict()
            report = build_parameter_validation_report(before_values, after_values, tolerance=1e-3)
            if hasattr(self, "param_content") and self.param_content is not None:
                self.param_content.mark_status(report.get("summary", "升级后参数校验完成"), vehicle_id=vehicle_id or None)
            self._show_auto_notice("升级后参数校验", report.get("summary", "升级后参数校验完成"))
            self.log_user_action(
                "firmware_param_validation",
                vehicle_id=vehicle_id or "CURRENT",
                backup=str(path),
                changed=report.get("changed_count", 0),
            )
        except Exception as exc:
            self._show_auto_notice("参数校验失败", str(exc))
            self.app_logger.exception("firmware parameter validation failed")

    def _show_auto_notice(self, title: str, message: str, duration_ms: int = 3000):
        _ok     = ("成功", "完成", "连接成功", "下载成功", "上传成功")
        _danger = ("失败", "错误", "崩溃", "超时", "无效")
        _warn   = ("未连接", "未实现", "功能不可用", "请稍候", "未检测到")
        text = f"{title}{message}"
        if any(k in text for k in _ok):
            level = "ok"
        elif any(k in text for k in _danger):
            level = "danger"
        elif any(k in text for k in _warn):
            level = "warn"
        else:
            level = "info"
        if self._notice_overlay is not None:
            self._notice_overlay.add_notice(title, message, level)
            return
        # 兜底：若覆盖层尚未初始化，至少保证状态栏文案可见，不让异常中断流程。
        if hasattr(self, "connection_status") and self.connection_status is not None:
            self.connection_status.setText(f"提示: {title} {message}")

    def on_connection_state_changed(self, state: str):
        try:
            state = str(state or "disconnected")

            labels = {
                "connected": "🟢 已连接",
                "connecting": "🟡 连接中",
                "disconnecting": "🟠 断开中",
                "disconnected": "🔴 未连接",
            }
            tones = {
                "connected": "ok",
                "connecting": "warn",
                "disconnecting": "warn",
                "disconnected": "danger",
            }
            flight_labels = {
                "connected": "已连接",
                "connecting": "连接中",
                "disconnecting": "断开中",
                "disconnected": "未连接",
            }

            self.connection_status.setText(labels.get(state, "🔴 未连接"))
            self._apply_status_chip_style(self.connection_status, tones.get(state, "danger"))
            self.connection_status.setToolTip("点击断开连接" if state == "connected" else "点击打开连接对话框")

            self.flight_content.set_connection_state(flight_labels.get(state, "未连接"))
            if hasattr(self, "fly_view_content") and self.fly_view_content is not None:
                self.fly_view_content.set_connection_state(flight_labels.get(state, "未连接"))
                if state != "connected":
                    self.fly_view_content.set_mission_status("等待连接")
            self._refresh_mp_action_states()

            if state == "connected":
                self.recorder.start_recording()
                self._vehicle_centered_once = False
                thread = self.connection_manager.thread
                if thread is not None:
                    try:
                        thread.request_home_position(timeout=1.5)
                    except Exception:
                        pass
                if self._pending_manual_success_notice:
                    self._show_auto_notice("成功", "设备连接成功！")
                    self.log_user_action("connection_succeeded")
                    self._pending_manual_success_notice = False
                return

            connected_links = []
            if hasattr(self.connection_manager, "link_summaries"):
                connected_links = [item for item in self.connection_manager.link_summaries() if item.get("connected")]
            if connected_links:
                return
            active_vehicle_id = str((self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "") or "")
            self.recorder.stop_recording()
            self.vehicle_manager.mark_all_disconnected()
            self._vehicle_centered_once = False
            self.home_position = None
            self.vehicle_position = None
            self.map_controller.set_home_position(None)
            self.waypoint_content.set_home_waypoint(None, vehicle_id=active_vehicle_id or None)
            self.map_controller.clear_vehicle_position()
            self._reset_live_status_labels()
        except Exception as exc:
            self.app_logger.exception("on_connection_state_changed crashed: %s", exc)

    def on_connection_error(self, message):
        try:
            self.log_user_action("connection_failed", error=message)
            if hasattr(self, "fly_view_content") and self.fly_view_content is not None:
                self.fly_view_content.set_alert_text(str(message or "连接异常"))
            if "自动重连" in message or "连接中断" in message:
                self._show_auto_notice("连接状态", message)
            else:
                self._show_auto_notice("连接失败", message)
        except Exception as exc:
            self.app_logger.exception("on_connection_error crashed: %s", exc)

    def update_drone_status(self, data):
        self.latest_status = data.copy()
        plugin_bundle = resolve_plugins(data, self.connection_manager.thread)
        self._firmware_plugin, self._autopilot_plugin = plugin_bundle
        self.fact_panel_controller.set_autopilot_plugin(self._autopilot_plugin)
        vehicle_summary = self.vehicle_manager.update_from_status(
            data,
            link_name=str(data.get("link_label", self._last_link_label or self.connection_status.text()) or self.connection_status.text()),
            plugin_bundle=plugin_bundle,
        )
        if hasattr(self, "mp_workbench_panel") and self.mp_workbench_panel is not None:
            self.mp_workbench_panel.set_status(
                f"{vehicle_summary.get('vehicle_id', '--')} | {vehicle_summary.get('mode', 'UNKNOWN')} | 电池 {vehicle_summary.get('battery_remaining', 0)}%"
            )
        if hasattr(self, "setup_content") and self.setup_content is not None:
            self.setup_content.set_vehicle(vehicle_summary)
        if hasattr(self, "fly_view_content") and self.fly_view_content is not None:
            mission_count = int(vehicle_summary.get('mission_count', len(self.waypoints) or 0) or 0)
            mission_text = HealthMonitor.build_mission_text(data, mission_count=mission_count)
            self.fly_view_content.set_vehicle_summary(
                str(vehicle_summary.get("vehicle_id", "--") or "--"),
                str(vehicle_summary.get("mode", "UNKNOWN") or "UNKNOWN"),
                mission_text,
                str(vehicle_summary.get("link_name", "") or ""),
            )
            self.fly_view_content.set_status_payload(data)
            self.fly_view_content.set_connection_state("已连接")
            self.fly_view_content.set_mission_status(mission_text)
            self.fly_view_content.set_alert_text("正常")
        if hasattr(self, "analyze_content") and self.analyze_content is not None:
            self.analyze_content.set_status_payload(data)
        self._sync_home_position_from_status(self.latest_status)
        self.alarm.refresh_heartbeat()
        self.alarm.check_status(data)
        self.recorder.write_data(data)
        self.battery.setText(f"电池: {data.get('battery_remaining', 100)}%")
        self.altitude.setText(f"高度: {data.get('alt', 0):.1f}m")
        self.speed.setText(f"速度: {data.get('vel', 0):.1f}m/s")
        self.mode.setText(f"模式: {data.get('mode', 'UNKNOWN')}")
        self.gps.setText(f"GPS: {data.get('gps', 0)} 颗")
        self.volt.setText(f"电压: {data.get('volt', 0):.2f}V")
        self.alert.setText("状态: 正常")
        self._update_telemetry_chip_styles(data)
        self.flight_content.set_flight_mode(data.get('mode', 'UNKNOWN'))

        roll = data.get('roll', 0.0)
        pitch = data.get('pitch', 0.0)
        yaw = data.get('yaw', data.get('heading', 0.0))
        if hasattr(self, 'attitude_ball'):
            self.attitude_ball.set_flight_data(
                roll,
                pitch,
                yaw,
                altitude=data.get('alt', 0.0),
                speed=data.get('vel', 0.0),
                mode=data.get('mode', 'UNKNOWN'),
                battery=data.get('battery_remaining', 100),
            )
        lat = float(data.get('lat', 0.0) or 0.0)
        lon = float(data.get('lon', 0.0) or 0.0)
        if lat and lon:
            self.vehicle_position = {
                "lat": lat,
                "lon": lon,
                "altitude": float(data.get('alt', 0.0) or 0.0),
                "heading": float(data.get('heading', data.get('yaw', 0.0)) or 0.0),
            }
            if self.connection_manager.state == "connected" and not self._vehicle_centered_once:
                self.map_controller.set_center(lat, lon)
                self._vehicle_centered_once = True
            self.map_controller.set_vehicle_position(
                lat,
                lon,
                float(data.get('alt', 0.0) or 0.0),
                float(data.get('heading', data.get('yaw', 0.0)) or 0.0),
            )
        self._refresh_mp_action_states()

    def show_alert(self, title, msg):
        self.log_user_action("alert_shown", title=title, message=msg)
        self.alert.setText(f"状态: {title}")
        self._apply_status_chip_style(self.alert, "danger")
        if hasattr(self, "fly_view_content") and self.fly_view_content is not None:
            self.fly_view_content.set_alert_text(str(title or "异常"))
        self._show_auto_notice(title, msg)

    def add_waypoint(self, lat, lon):
        self.app_logger.info(f"add_waypoint called: lat={lat}, lon={lon}")
        try:
            lat = float(lat)
            lon = float(lon)
        except Exception:
            self.app_logger.warning(f"Invalid coordinates type: lat={lat}, lon={lon}")
            return
        if not (math.isfinite(lat) and math.isfinite(lon) and -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            self.app_logger.warning(f"Invalid coordinates range: lat={lat}, lon={lon}")
            return
        terrain_alt = self._terrain_alt_for_coordinate(lat, lon)
        wp = self._build_waypoint_from_map_click(lat, lon, terrain_alt=terrain_alt)
        active_vehicle_id = str((self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "") or "")
        insert_at = self._selected_waypoint_index + 1 if self._selected_waypoint_index >= 0 else len(self.waypoints)
        insert_at = max(0, min(insert_at, len(self.waypoints)))
        self.waypoints.insert(insert_at, wp)
        self._selected_waypoint_index = insert_at
        self.waypoint_content.set_waypoints(self.waypoints, vehicle_id=active_vehicle_id or None)
        self.waypoint_content.select_waypoint_row(insert_at)
        self.map_controller.select_waypoint_on_map(insert_at)
        self.log_user_action("map_waypoint_added", lat=lat, lon=lon, total=len(self.waypoints))
        self.refresh_map_waypoints(recenter=True)

    def add_waypoint_from_map_click(self, payload: dict):
        self.app_logger.info(f"add_waypoint_from_map_click called: payload={payload}")
        lat = float(payload.get("lat", 0.0) or 0.0)
        lon = float(payload.get("lon", 0.0) or 0.0)
        px = float(payload.get("x", 0.0) or 0.0)
        py = float(payload.get("y", 0.0) or 0.0)
        terrain_alt = float(payload.get("alt", 0.0) or 0.0)
        if not (math.isfinite(lat) and math.isfinite(lon) and -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            self.app_logger.warning(f"Invalid coordinates: lat={lat}, lon={lon}")
            return

        wp = self._build_waypoint_from_map_click(lat, lon, terrain_alt=terrain_alt)
        active_vehicle_id = str((self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "") or "")
        insert_at = self._selected_waypoint_index + 1 if self._selected_waypoint_index >= 0 else len(self.waypoints)
        insert_at = max(0, min(insert_at, len(self.waypoints)))
        self.waypoints.insert(insert_at, wp)
        self._selected_waypoint_index = insert_at
        self.waypoint_content.set_waypoints(self.waypoints, vehicle_id=active_vehicle_id or None)
        self.waypoint_content.select_waypoint_row(insert_at)
        self.map_controller.select_waypoint_on_map(insert_at)
        self.log_user_action(
            "map_waypoint_added",
            lat=lat,
            lon=lon,
            pixel_x=px,
            pixel_y=py,
            alt=int(round(wp["alt"])),
            terrain_alt=terrain_alt,
            insert_at=insert_at,
            total=len(self.waypoints),
        )
        self.refresh_map_waypoints(recenter=True)

    def add_mission_item_from_map_click(self, lat: float, lon: float, alt: float = 300.0) -> dict:
        """MP等价映射：点击地图后创建一个标准 NAV_WAYPOINT 任务项。"""
        return {
            "type": "WAYPOINT",
            "action": "NAV_WAYPOINT",
            "command": 16,
            "param1": 0.0,
            "param2": 0.0,
            "param3": 0.0,
            "param4": 0.0,
            "speed": float(RouteConfig.DEFAULT_SPEED),
            "hold_time": float(RouteConfig.DEFAULT_HOLD_TIME),
            "holdTime": float(RouteConfig.DEFAULT_HOLD_TIME),
            "lat": float(lat),
            "lon": float(lon),
            "alt": float(int(round(alt))),
            "current": 0,
            "autocontinue": 1,
        }

    def _terrain_alt_for_coordinate(self, lat: float, lon: float) -> float:
        try:
            zoom = int(getattr(self.map_controller, "current_zoom", 15) or 15)
            elev = self.map_bridge.getDemElevation(lat, lon, zoom)
            value = float(elev)
            return value if math.isfinite(value) else 0.0
        except Exception:
            return 0.0

    def _build_waypoint_from_map_click(
        self,
        lat: float,
        lon: float,
        alt_hint: float = 0.0,
        terrain_alt: float | None = None,
    ) -> dict:
        if alt_hint > 0:
            relative_alt = float(int(round(alt_hint)))
        elif self._selected_waypoint_index >= 0 and self._selected_waypoint_index < len(self.waypoints):
            relative_alt = float(int(round(self.waypoints[self._selected_waypoint_index].get("alt", 300.0) or 300.0)))
        elif self.waypoints:
            relative_alt = float(int(round(self.waypoints[-1].get("alt", 300.0) or 300.0)))
        else:
            relative_alt = 300.0
        mission_item = self.add_mission_item_from_map_click(lat, lon, relative_alt)
        terrain_value = float(terrain_alt or 0.0) if isinstance(terrain_alt, (int, float)) and math.isfinite(float(terrain_alt or 0.0)) else 0.0
        # 保留当前GCS增强字段（MP基础项 + UI扩展）
        mission_item.update({
            "action": "NAVIGATE",
            "loiter": False,
            "loiter_radius": 60.0,
            "loiter_time": 30.0,
            "source": "map_click",
            "terrain_alt": terrain_value,
        })
        return mission_item

    def enable_map_add_waypoint(self):
        next_state = not self._map_add_mode
        self.app_logger.info(f"enable_map_add_waypoint: toggling to {next_state}")
        self.set_map_add_mode(next_state)
        self.show_panel(self.waypoint_panel)
        self.log_user_action("waypoint_add_mode_toggled", enabled=next_state)

    def set_map_add_mode(self, enabled: bool):
        self.app_logger.info(f"set_map_add_mode: enabled={enabled}")
        self._map_add_mode = enabled
        self.map_controller.set_add_mode(enabled)
        self.waypoint_content.set_add_mode_active(enabled)
        self._refresh_mp_action_states()

    def move_waypoint(self, index, lat, lon):
        index = int(index)
        if not (0 <= index < len(self.waypoints)):
            return
        self._selected_waypoint_index = index
        self.waypoints[index]["lat"] = lat
        self.waypoints[index]["lon"] = lon
        # 仅更新受影响的表格单元格和模型，避免触发完整表格重建 + JS 全量重渲染
        self.waypoint_content.commit_drag_position(index, lat, lon)
        self.map_controller.move_waypoint(index, self.waypoints[index])
        self.log_user_action("map_waypoint_moved", index=index, lat=lat, lon=lon)

    def move_waypoint_realtime(self, index, lat, lon):
        index = int(index)
        if not (0 <= index < len(self.waypoints)):
            return
        self._selected_waypoint_index = index
        self.waypoints[index]["lat"] = lat
        self.waypoints[index]["lon"] = lon
        # 拖拽过程中不回写模型，避免触发整表刷新导致 marker 被重建、表现为“拖不动”。

    def on_map_waypoint_selected(self, index: int):
        row = int(index)
        if not (0 <= row < len(self.waypoints)):
            return
        self._selected_waypoint_index = row
        self.show_panel(self.waypoint_panel)
        self.waypoint_content.select_waypoint_row(row)
        self.map_controller.select_waypoint_on_map(row)
        self.log_user_action("map_waypoint_selected", index=row)

    def on_map_insert_waypoint_after(self, index: int):
        row = int(index)
        if not (0 <= row < len(self.waypoints)):
            return
        self._selected_waypoint_index = row
        base = self.waypoints[row]
        base_lat = float(base.get("lat", 0.0) or 0.0)
        base_lon = float(base.get("lon", 0.0) or 0.0)
        base_alt = float(base.get("alt", 0.0) or 0.0)

        insert_lat = base_lat
        insert_lon = base_lon
        insert_alt = base_alt
        if row + 1 < len(self.waypoints):
            next_wp = self.waypoints[row + 1]
            next_lat = float(next_wp.get("lat", base_lat) or base_lat)
            next_lon = float(next_wp.get("lon", base_lon) or base_lon)
            next_alt = float(next_wp.get("alt", base_alt) or base_alt)
            insert_lat = (base_lat + next_lat) / 2.0
            insert_lon = (base_lon + next_lon) / 2.0
            insert_alt = (base_alt + next_alt) / 2.0

        terrain_alt = self._terrain_alt_for_coordinate(insert_lat, insert_lon)
        wp = self._build_waypoint_from_map_click(
            insert_lat,
            insert_lon,
            alt_hint=insert_alt,
            terrain_alt=terrain_alt,
        )
        active_vehicle_id = str((self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "") or "")
        insert_at = row + 1
        self.waypoints.insert(insert_at, wp)
        self._selected_waypoint_index = insert_at
        self.waypoint_content.set_waypoints(self.waypoints, vehicle_id=active_vehicle_id or None)
        self.waypoint_content.select_waypoint_row(insert_at)
        self.map_controller.select_waypoint_on_map(insert_at)
        self.refresh_map_waypoints()
        self.log_user_action("map_waypoint_inserted_after", index=row, insert_at=insert_at)

    def on_map_fly_to_waypoint(self, index: int):
        row = int(index)
        if not (0 <= row < len(self.waypoints)):
            return

        active_vehicle = self.vehicle_manager.active_vehicle() or {}
        target_vehicle_id = str(active_vehicle.get("vehicle_id", "") or "CURRENT")
        detail = self.vehicle_manager.vehicle_detail(target_vehicle_id) or {}
        if detail.get("command_busy") or target_vehicle_id in self._busy_vehicle_ids:
            self._show_auto_notice("请稍候", f"载具 {target_vehicle_id} 的上一条飞控指令仍在处理中")
            return

        thread = self._thread_for_vehicle(target_vehicle_id)
        if thread is None:
            self._show_auto_notice("未连接", "请先建立连接")
            return
        if not hasattr(thread, "fly_to_waypoint"):
            self._show_auto_notice("功能不可用", "当前通信模块不支持飞向航点")
            return

        wp = self.waypoints[row]
        lat = float(wp.get("lat", 0.0) or 0.0)
        lon = float(wp.get("lon", 0.0) or 0.0)
        alt = float(wp.get("alt", 0.0) or 0.0)
        self._selected_waypoint_index = row
        self.waypoint_content.select_waypoint_row(row)
        self.map_controller.select_waypoint_on_map(row)

        self.log_user_action("map_waypoint_fly_to", index=row, lat=lat, lon=lon, alt=alt, vehicle_id=target_vehicle_id)
        if not self._ensure_vtol_mode(thread, "GUIDED", fallback_modes={"QGUIDED"}):
            return
        self._busy_vehicle_ids.add(target_vehicle_id)
        self._flight_command_busy = bool(self._busy_vehicle_ids)
        self._command_busy_vehicle_id = target_vehicle_id
        self.vehicle_manager.mark_command_state(target_vehicle_id, f"fly_to_wp_{row}", True)
        self.flight_content.set_command_busy(True, f"载具 {target_vehicle_id} 正在飞向航点 {row}…")
        try:
            thread.fly_to_waypoint(lat, lon, alt)
        finally:
            QTimer.singleShot(900, lambda vehicle_key=target_vehicle_id: self._clear_flight_command_busy(vehicle_key))

    def on_map_delete_waypoint(self, index: int):
        row = int(index)
        if not (0 <= row < len(self.waypoints)):
            return
        self.waypoint_content.model.delete_rows([row])
        if not self.waypoints:
            self._selected_waypoint_index = -1
            return
        next_row = max(0, min(row, len(self.waypoints) - 1))
        self._selected_waypoint_index = next_row
        self.waypoint_content.select_waypoint_row(next_row)
        self.map_controller.select_waypoint_on_map(next_row)

    def on_map_upload_waypoint(self, index: int):
        """Upload selected waypoint without altering other mission items."""
        link_key, link_label = self._active_link_context()
        row = int(index)
        if not (0 <= row < len(self.waypoints)):
            self._show_auto_notice("错误", "航点索引无效")
            return
        wp = self.waypoints[row]
        self._selected_waypoint_index = row
        self.waypoint_content.select_waypoint_row(row)
        self.map_controller.select_waypoint_on_map(row)
        self.log_user_action("map_waypoint_upload", index=row)

        thread = self.connection_manager.thread
        if thread is None or not self.connection_manager.is_connected():
            self._show_auto_notice("未连接", "请先建立飞控连接")
            return

        self._mission_transfer_active = True
        self.connection_manager.suppress_watchdog(True)
        try:
            if hasattr(thread, "upload_single_mission_item"):
                self.waypoint_content.set_transfer_progress('upload', 0, 1, 0, f'准备通过 {link_label} 上传单航点', True)
                QApplication.processEvents()
                thread.upload_single_mission_item(row, wp)
                self._cache_link_context(link_key, include_params=False, include_mission=True)
                self._sync_active_vehicle_context_metrics(include_params=False, include_mission=True)
                self.waypoint_content.set_transfer_progress('upload', 1, 1, 100, f'{link_label} 单航点上传完成', False)
                self._show_auto_notice("上传成功", f"[{link_label}] 已更新飞控任务中的第 {row} 号航点（其他航点保持不变）")
            else:
                # Backward-compatible fallback: full upload with unchanged waypoints.
                self.upload_waypoints_to_vehicle(self.waypoint_content.get_waypoints())
                self._show_auto_notice("提示", "当前通信模块不支持单航点增量写入，已执行全任务同步上传")
        except Exception as exc:
            self.waypoint_content.clear_transfer_progress("单航点上传失败")
            self.log_user_action("map_waypoint_upload_failed", index=row, error=str(exc))
            self._show_auto_notice("上传失败", str(exc))
        finally:
            self._mission_transfer_active = False
            self.connection_manager.suppress_watchdog(False)

    def on_home_point_updated(self, lat: float, lon: float, alt: float):
        active_vehicle_id = str((self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "") or "")
        thread = self._thread_for_vehicle(active_vehicle_id) if active_vehicle_id else self.connection_manager.thread
        connected = self.connection_manager.is_connected() and thread is not None
        if connected:
            try:
                thread.set_home_position(lat, lon, alt)
                home_ack = thread.request_home_position(timeout=2.0)
                if isinstance(home_ack, dict):
                    lat = float(home_ack.get('lat', lat) or lat)
                    lon = float(home_ack.get('lon', lon) or lon)
                    alt = float(home_ack.get('alt', alt) or alt)
            except Exception as exc:
                self.app_logger.warning("set real home failed, fallback to local display: %s", exc)

        active_vehicle_id = str((self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "") or "")
        self.home_position = {
            "type": "HOME",
            "lat": float(lat),
            "lon": float(lon),
            "alt": float(alt),
            "source": "fc_home" if connected else "local_pending_home",
        }
        self.map_controller.set_home_position(self.home_position)
        self.waypoint_content.set_home_waypoint(self.home_position, vehicle_id=active_vehicle_id or None)
        self._cache_link_context(include_params=False, include_mission=True)
        self._sync_active_vehicle_context_metrics(include_params=False, include_mission=True)
        self.log_user_action("home_point_updated", lat=lat, lon=lon, alt=alt)

    def _sync_home_position_from_status(self, status: dict | None = None):
        source = status if isinstance(status, dict) else self.latest_status
        try:
            home_lat = float(source.get("home_lat", 0.0) or 0.0)
            home_lon = float(source.get("home_lon", 0.0) or 0.0)
            home_alt = float(source.get("home_alt_abs", 0.0) or 0.0)
        except Exception:
            return

        if not (math.isfinite(home_lat) and math.isfinite(home_lon)):
            return
        if abs(home_lat) < 1e-9 and abs(home_lon) < 1e-9:
            return

        current = self.home_position or {}
        changed = (
            abs(float(current.get("lat", 0.0) or 0.0) - home_lat) > 1e-7
            or abs(float(current.get("lon", 0.0) or 0.0) - home_lon) > 1e-7
            or abs(float(current.get("alt", 0.0) or 0.0) - home_alt) > 0.1
        )
        if not changed:
            return

        active_vehicle_id = str((self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "") or "")
        self.home_position = {
            "type": "HOME",
            "lat": home_lat,
            "lon": home_lon,
            "alt": home_alt,
            "source": "fc_home",
        }
        self.map_controller.set_home_position(self.home_position)
        self.waypoint_content.set_home_waypoint(self.home_position, vehicle_id=active_vehicle_id or None)
        self._cache_link_context(include_params=False, include_mission=True)

    def on_home_button_clicked(self):
        msg = QMessageBox(self)
        msg.setWindowTitle("设置 H 点")
        msg.setText("如何设置起始/返航(H)点？")
        msg.setStyleSheet(_DIALOG_STYLE)
        btn_vehicle = msg.addButton("使用飞机当前位置", QMessageBox.ButtonRole.AcceptRole)
        btn_map = msg.addButton("在地图上点击选择", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked == btn_vehicle:
            self._set_home_from_vehicle()
        elif clicked == btn_map:
            self._start_home_map_pick()

    def _set_home_from_vehicle(self):
        vp = self.vehicle_position if hasattr(self, "vehicle_position") else None
        if vp is None:
            gcs_warning(self, "无飞机位置", "当前没有飞机 GPS 位置，无法用飞机位置设置 H 点。\n请先连接飞机或等待获取 GPS。")
            return
        lat = float(vp.get("lat", 0.0) or 0.0)
        lon = float(vp.get("lon", 0.0) or 0.0)
        alt = float(vp.get("altitude", 0.0) or 0.0)
        self.on_home_point_updated(lat, lon, alt)
        self.app_logger.info(f"H点设为飞机位置: lat={lat:.7f} lon={lon:.7f} alt={alt:.1f}")

    def _start_home_map_pick(self):
        if self._map_add_mode:
            self.set_map_add_mode(False)
        self.map_controller.set_home_pick_mode(True)
        self.waypoint_content.transfer_widget.show_status("请在地图上点击选择 H 点位置…", 0)

    def _start_home_map_pick_from_mp(self):
        self.show_panel(self.waypoint_panel)
        self._start_home_map_pick()

    def on_home_picked_from_map(self, lat: float, lon: float):
        zoom = int(self.map_controller.current_zoom)
        elev = self.map_bridge.getDemElevation(lat, lon, zoom)
        alt = float(elev) if (isinstance(elev, (int, float)) and elev == elev) else 0.0
        self.on_home_point_updated(lat, lon, alt)
        self.app_logger.info(f"H点从地图选取: lat={lat:.7f} lon={lon:.7f} alt={alt:.1f}")

    def on_waypoints_updated(self, waypoints):
        """Handle waypoints updates from waypoint panel"""
        self.waypoints = waypoints
        if not self.waypoints:
            self._selected_waypoint_index = -1
        elif self._selected_waypoint_index >= len(self.waypoints):
            self._selected_waypoint_index = len(self.waypoints) - 1
        self._cache_link_context(include_params=False, include_mission=True)
        self._sync_active_vehicle_context_metrics(include_params=False, include_mission=True)
        self.log_user_action("waypoints_updated", total=len(waypoints))
        self.refresh_map_waypoints()

    def on_auto_route_updated(self, route_items):
        """Handle auto-route (takeoff/landing) updates from waypoint panel."""
        if self.map_controller:
            self.map_controller.update_auto_route(route_items)
        self._cache_link_context(include_params=False, include_mission=True)
        self._sync_active_vehicle_context_metrics(include_params=False, include_mission=True)
        self.log_user_action("auto_route_updated", items_count=len(route_items))

    def on_auto_route_point_moved(self, point_name, lat, lon):
        """Handle auto-route point drag completion (non-real-time)."""
        self.waypoint_content.update_auto_route_point(point_name, lat, lon, emit_signal=True)
        self.log_user_action("auto_route_point_moved", point=point_name, lat=round(lat, 7), lon=round(lon, 7))

    def on_auto_route_point_moved_realtime(self, point_name, lat, lon):
        """Handle auto-route point dragging in real-time for preview."""
        now = time.time()
        # 节流更新自动航线参数，避免拖拽期间频繁触发表格重建。
        if (now - self._last_auto_route_preview_ts) >= 0.18:
            self._last_auto_route_preview_ts = now
            self.waypoint_content.update_auto_route_point(point_name, lat, lon, emit_signal=False)

    def on_map_changed(self, text):
        self.current_map = text
        self.settings_manager.set("ui.map_source", text)
        self.log_user_action("map_source_changed", map_source=text)
        self.map_controller.set_map_source(text)

    def _build_upload_waypoints(self, visible_waypoints: list[dict]) -> list[dict]:
        home_source = self.home_position or getattr(self.waypoint_content, "_home_wp", None)
        return build_upload_waypoints(
            visible_waypoints,
            self.waypoint_content.get_auto_route_items(),
            home_source,
        )

    def _restore_home_from_downloaded_mission(self, downloaded: list[dict]):
        if self.home_position:
            return
        for item in (downloaded or []):
            try:
                seq = int((item or {}).get("seq", -1) or -1)
                name = str((item or {}).get("name", "") or "").upper()
                wp_type = str((item or {}).get("type", "") or "").upper()
                if seq != 0 and name != "HOME" and wp_type != "HOME":
                    continue
                lat = float((item or {}).get("lat", 0.0) or 0.0)
                lon = float((item or {}).get("lon", 0.0) or 0.0)
                alt = float((item or {}).get("alt", 0.0) or 0.0)
            except Exception:
                continue
            if not (math.isfinite(lat) and math.isfinite(lon)):
                continue
            active_vehicle_id = str((self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "") or "")
            self.home_position = {
                "type": "HOME",
                "lat": lat,
                "lon": lon,
                "alt": alt,
                "source": "mission_wp0",
            }
            self.map_controller.set_home_position(self.home_position)
            self.waypoint_content.set_home_waypoint(self.home_position, vehicle_id=active_vehicle_id or None)
            return

    def _split_downloaded_mission(self, downloaded: list[dict]) -> tuple[dict[str, dict], list[dict]]:
        return split_downloaded_mission(
            [dict(wp) for wp in (downloaded or [])],
            self.home_position,
            self.waypoint_content.get_auto_route_items(),
        )

    @staticmethod
    def _validate_upload_waypoints(waypoints: list[dict]) -> tuple[bool, str]:
        return validate_upload_waypoints(waypoints)

    def upload_waypoints_to_vehicle(self, waypoints):
        active_vehicle_id = str((self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "") or "")
        thread = self._thread_for_vehicle(active_vehicle_id) if active_vehicle_id else self.connection_manager.thread
        link_key, link_label = self._active_link_context()
        if thread is None or not self.connection_manager.is_connected():
            self.app_logger.warning(
                "upload blocked: state=%s thread=%s waypoints=%s",
                self.connection_manager.state,
                bool(thread),
                len(waypoints or []),
            )
            self.waypoint_content.clear_transfer_progress()
            self._show_auto_notice("未连接", "请先建立飞控连接")
            return

        if self.waypoint_content._home_wp is None:
            self.waypoint_content.clear_transfer_progress("上传中止")
            self._show_auto_notice("上传中止", "请先设置H点，H点为飞控0号航点")
            self.log_user_action("mission_upload_blocked", reason="missing_home")
            return

        self._mission_transfer_active = True
        self.connection_manager.suppress_watchdog(True)
        try:
            mission_waypoints = self._build_upload_waypoints(waypoints)
            valid, message = self._validate_upload_waypoints(mission_waypoints)
            if not valid:
                self.waypoint_content.clear_transfer_progress("上传中止")
                self._show_auto_notice("上传中止", message)
                self.log_user_action("mission_upload_blocked", reason=message)
                return
            has_home_item = (mission_waypoints and str(mission_waypoints[0].get('name', '')) == 'HOME')
            display_count = len(mission_waypoints) - (1 if has_home_item else 0)
            self.app_logger.info(
                "mission upload start: visible=%s total=%s include_home=%s auto_route=%s state=%s",
                len(waypoints or []),
                len(mission_waypoints),
                has_home_item,
                max(0, display_count - len(waypoints or [])),
                self.connection_manager.state,
            )
            self.waypoint_content.set_transfer_progress('upload', 0, len(mission_waypoints), 0, f'准备通过 {link_label} 上传航线', True)
            QApplication.processEvents()
            thread.upload_mission(mission_waypoints)
            self._cache_link_context(link_key, include_params=False, include_mission=True)
            self._sync_active_vehicle_context_metrics(include_params=False, include_mission=True)
            self.waypoint_content.set_transfer_progress('upload', len(mission_waypoints), len(mission_waypoints), 100, f'{link_label} 航线上传完成', False)
            self.log_user_action(
                "mission_uploaded",
                total=len(mission_waypoints),
                visible=len(waypoints or []),
                link=link_label,
                link_key=link_key,
            )
            self._show_auto_notice(
                "上传成功",
                f"[{link_label}] 已向飞控上传 {display_count} 个任务点（WP0=Home 占位）"
            )
        except Exception as exc:
            self.app_logger.exception("mission upload failed")
            self.waypoint_content.clear_transfer_progress("上传失败")
            self.log_user_action("mission_upload_failed", error=str(exc))
            self._show_auto_notice("上传失败", str(exc))
        finally:
            self._mission_transfer_active = False
            self.connection_manager.suppress_watchdog(False)

    def download_waypoints_from_vehicle(self):
        active_vehicle_id = str((self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "") or "")
        thread = self._thread_for_vehicle(active_vehicle_id) if active_vehicle_id else self.connection_manager.thread
        link_key, link_label = self._active_link_context()
        if thread is None or not self.connection_manager.is_connected():
            self.app_logger.warning(
                "download blocked: state=%s thread=%s",
                self.connection_manager.state,
                bool(thread),
            )
            self.waypoint_content.clear_transfer_progress()
            self._show_auto_notice("未连接", "请先建立飞控连接")
            return

        self._mission_transfer_active = True
        self.connection_manager.suppress_watchdog(True)
        try:
            self.app_logger.info("mission download start: state=%s link=%s", self.connection_manager.state, link_label)
            self.waypoint_content.set_transfer_progress('download', 0, 0, 0, f'准备从 {link_label} 下载航线', True)
            QApplication.processEvents()
            downloaded = thread.download_mission()
            thread.request_home_position(timeout=2.0)
            self._sync_home_position_from_status()
            self._restore_home_from_downloaded_mission([dict(wp) for wp in (downloaded or [])])
            auto_route_overrides, waypoints = self._split_downloaded_mission([dict(wp) for wp in (downloaded or [])])
            self.waypoints = waypoints
            active_vehicle_id = str((self.vehicle_manager.active_vehicle() or {}).get("vehicle_id", "") or "")
            self.waypoint_content.set_auto_route_overrides(auto_route_overrides, vehicle_id=active_vehicle_id or None)
            self.waypoint_content.set_waypoints(waypoints, vehicle_id=active_vehicle_id or None)
            self._cache_link_context(link_key, include_params=False, include_mission=True)
            self._sync_active_vehicle_context_metrics(include_params=False, include_mission=True)
            total_downloaded = len(downloaded or [])
            self.waypoint_content.set_transfer_progress('download', total_downloaded, total_downloaded, 100, f'{link_label} 航线下载完成', False)
            self.refresh_map_waypoints(recenter=bool(waypoints))
            self.log_user_action("mission_downloaded", total=total_downloaded, visible=len(waypoints), home=1 if self.home_position else 0, link=link_label, link_key=link_key)
            self._show_auto_notice(
                "下载成功",
                f"[{link_label}] 已下载 {total_downloaded} 个航点，真实 Home 点已单独同步"
            )
        except Exception as exc:
            self.app_logger.exception("mission download failed")
            self.waypoint_content.clear_transfer_progress("下载失败")
            self.log_user_action("mission_download_failed", error=str(exc))
            self._show_auto_notice("下载失败", str(exc))
        finally:
            self._mission_transfer_active = False
            self.connection_manager.suppress_watchdog(False)

    def on_mission_progress(self, payload):
        message = str(payload.get('message', '') or '')
        link_label = str(payload.get('link_label', '') or '')
        if link_label and link_label not in message:
            message = f"[{link_label}] {message}"
        self.waypoint_content.set_transfer_progress(
            payload.get('operation', 'upload'),
            int(payload.get('current', 0) or 0),
            int(payload.get('total', 0) or 0),
            int(payload.get('percent', 0) or 0),
            message,
            bool(payload.get('active', False)),
        )
        QApplication.processEvents()

    def on_waypoint_table_changed(self, item):
        if not self.waypoint_content.route_table.hasFocus():
            return

        mission_index = self.waypoint_content.table_row_to_mission_index(item.row())
        if mission_index < 0:
            return

        headers = {2: "lat", 3: "lon", 4: "alt"}
        field = headers.get(item.column())
        if field is None:
            field = {5: "speed", 6: "hold_time"}.get(item.column())
        if not field:
            return
        self.log_user_action(
            "waypoint_cell_edited",
            row=mission_index,
            table_row=item.row(),
            field=field,
            value=item.text(),
        )

    def on_waypoint_panel_selection_changed(self):
        mission_index = self.waypoint_content.table_row_to_mission_index(self.waypoint_content._selected_row)
        if not (0 <= mission_index < len(self.waypoints)):
            self._selected_waypoint_index = -1
            return
        self._selected_waypoint_index = mission_index
        self.map_controller.select_waypoint_on_map(mission_index)

    def bind_all_signals(self):
        self.connection_manager.status_updated.connect(self.update_drone_status)
        self.connection_manager.connection_state_changed.connect(self.on_connection_state_changed)
        self.connection_manager.connection_error.connect(self.on_connection_error)
        self.connection_manager.mission_progress.connect(self.on_mission_progress)
        if hasattr(self.connection_manager, "links_changed"):
            self.connection_manager.links_changed.connect(self.on_link_summaries_changed)
        if hasattr(self.connection_manager, "active_link_changed"):
            self.connection_manager.active_link_changed.connect(self.on_active_link_changed)
        if hasattr(self.connection_manager, "link_status_updated"):
            self.connection_manager.link_status_updated.connect(self.on_link_status_updated)
        self.vehicle_manager.vehicles_changed.connect(self.on_vehicle_summaries_changed)
        self.vehicle_manager.active_vehicle_changed.connect(self.on_active_vehicle_changed)
        self.alarm.alert_signal.connect(self.show_alert)
        self.map_bridge.add_waypoint_signal.connect(self.add_waypoint)
        self.map_bridge.add_waypoint_detail_signal.connect(self.add_waypoint_from_map_click)
        self.map_bridge.move_waypoint_signal.connect(self.move_waypoint)
        self.map_bridge.move_waypoint_realtime_signal.connect(self.move_waypoint_realtime)
        self.map_bridge.select_waypoint_signal.connect(self.on_map_waypoint_selected)
        self.map_bridge.map_add_mode_signal.connect(self.set_map_add_mode)
        self.map_bridge.measure_mode_signal.connect(self.map_controller.set_measure_mode)
        self.map_bridge.follow_mode_signal.connect(self.map_controller.set_follow_aircraft)
        self.map_bridge.home_point_signal.connect(self.on_home_point_updated)
        self.map_bridge.home_pick_from_map_signal.connect(self.on_home_picked_from_map)
        self.map_bridge.insert_waypoint_after_signal.connect(self.on_map_insert_waypoint_after)
        self.map_bridge.delete_waypoint_signal.connect(self.on_map_delete_waypoint)
        self.map_bridge.fly_to_waypoint_signal.connect(self.on_map_fly_to_waypoint)
        self.map_bridge.upload_waypoint_signal.connect(self.on_map_upload_waypoint)

        self.waypoint_content.auto_route_updated.connect(self.on_auto_route_updated)
        self.map_bridge.move_auto_route_point_signal.connect(self.on_auto_route_point_moved)
        self.map_bridge.move_auto_route_point_realtime_signal.connect(self.on_auto_route_point_moved_realtime)

        self.cmb_map.currentTextChanged.connect(self.on_map_changed)
        self.connection_status.clicked.connect(self.on_connection_status_clicked)
        self.btn_waypoint.clicked.connect(lambda: self.show_panel(self.waypoint_panel))
        self.btn_setup.clicked.connect(self._open_setup_panel)
        self.btn_flyview.clicked.connect(self._open_fly_view)
        self.btn_param.clicked.connect(self._open_param_panel)
        self.btn_analyze.clicked.connect(self._open_analyze_panel)
        self.btn_peripheral.clicked.connect(self._open_peripheral_panel)
        self.btn_vehicle.clicked.connect(self._open_vehicle_panel)
        self.btn_links.clicked.connect(self._open_link_panel)
        self.btn_link.clicked.connect(self._open_link_settings)
        self.btn_mp.clicked.connect(lambda: self.show_panel(self.mp_panel))
        self.flight_content.arm_clicked.connect(lambda: self.execute_flight_command("arm"))
        self.flight_content.disarm_clicked.connect(lambda: self.execute_flight_command("disarm"))
        self.flight_content.takeoff_clicked.connect(lambda: self.execute_flight_command("vtol_takeoff_30m"))
        self.flight_content.land_clicked.connect(lambda: self.execute_flight_command("vtol_qland"))
        self.flight_content.return_clicked.connect(lambda: self.execute_flight_command("vtol_qrtl"))

        self.waypoint_content.close_btn.clicked.connect(lambda: self.log_user_action("panel_close_clicked", panel="waypoint"))

        self.waypoint_content.btn_add.clicked.connect(lambda: self.log_user_action("waypoint_action_clicked", action_name="map_add_mode"))
        self.waypoint_content.btn_delete.clicked.connect(lambda: self.log_user_action("waypoint_action_clicked", action_name="delete_selected"))
        self.waypoint_content.btn_clear.clicked.connect(lambda: self.log_user_action("waypoint_action_clicked", action_name="clear"))
        self.waypoint_content.btn_set_height.clicked.connect(lambda: self.log_user_action("waypoint_action_clicked", action_name="set_uniform_height"))
        self.waypoint_content.home_btn_clicked.connect(self.on_home_button_clicked)
        self.waypoint_content.btn_export_kml.clicked.connect(lambda: self.log_user_action("waypoint_action_clicked", action_name="export_kml"))
        self.waypoint_content.btn_import_kml.clicked.connect(lambda: self.log_user_action("waypoint_action_clicked", action_name="import_kml"))
        self.waypoint_content.btn_export_waypoints.clicked.connect(lambda: self.log_user_action("waypoint_action_clicked", action_name="export_waypoints"))
        self.waypoint_content.btn_import_waypoints.clicked.connect(lambda: self.log_user_action("waypoint_action_clicked", action_name="import_waypoints"))
        self.waypoint_content.btn_upload_mission.clicked.connect(lambda: self.log_user_action("waypoint_action_clicked", action_name="upload_mission"))
        self.waypoint_content.btn_download_mission.clicked.connect(lambda: self.log_user_action("waypoint_action_clicked", action_name="download_mission"))
        self.waypoint_content.route_table.itemChanged.connect(self.on_waypoint_table_changed)
        self.waypoint_content.route_table.itemSelectionChanged.connect(self.on_waypoint_panel_selection_changed)
        self.waypoint_content.upload_requested.connect(self.upload_waypoints_to_vehicle)
        self.waypoint_content.download_requested.connect(self.download_waypoints_from_vehicle)
        self.waypoint_content.add_mode_requested.connect(self.enable_map_add_waypoint)
        self.param_content.refresh_requested.connect(self.refresh_parameters_from_vehicle)
        self.param_content.save_requested.connect(self.save_parameters_to_vehicle)
        self.param_content.load_requested.connect(self.import_parameters_from_file)
        self.param_content.export_requested.connect(self.export_parameters_to_file)
        self.waypoint_panel.position_changed.connect(lambda _: self.panel_manager.remember_position("waypoint", self.waypoint_panel))
        # Flight control panel is embedded in right-bottom and always visible
        self.flight_panel.show()
        self.waypoint_content.set_waypoints(self.waypoints)

    def _extract_home_and_visible_waypoints(self, waypoints):
        if not waypoints:
            return None, []

        home_waypoint = waypoints[0]
        visible_waypoints = waypoints[1:]

        if visible_waypoints:
            visible_waypoints[0]['loiter'] = True
            visible_waypoints[0]['loiter_radius'] = 250.0
            visible_waypoints[0]['loiter_time'] = 60.0

        self.log_user_action(
            "home_point_extracted",
            lat=float(home_waypoint.get('lat', 0.0)),
            lon=float(home_waypoint.get('lon', 0.0)),
            hidden=len(waypoints) - len(visible_waypoints),
        )
        return home_waypoint, visible_waypoints

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "waypoint_panel") and self.waypoint_panel is not None:
            self._resize_waypoint_panel()
        if hasattr(self, "param_panel") and self.param_panel is not None:
            self._resize_param_panel()
        self.panel_manager.constrain_visible_panels()
        if hasattr(self, "_notice_overlay") and self._notice_overlay is not None:
            self._notice_overlay.raise_()

    def _shutdown_background_services(self):
        if self._is_shutting_down:
            return
        self._is_shutting_down = True

        if hasattr(self, "_notice_overlay") and self._notice_overlay is not None:
            self._notice_overlay.hide()

        self.set_map_add_mode(False)
        self._mission_transfer_active = False

        if self.connect_dialog is not None and self.connect_dialog.isVisible():
            self.connect_dialog.reject()

        # Prevent late queued callbacks during teardown.
        signal_pairs = [
            (self.connection_manager.status_updated, self.update_drone_status),
            (self.connection_manager.connection_state_changed, self.on_connection_state_changed),
            (self.connection_manager.connection_error, self.on_connection_error),
            (self.connection_manager.mission_progress, self.on_mission_progress),
            (self.alarm.alert_signal, self.show_alert),
            (self.map_bridge.add_waypoint_signal, self.add_waypoint),
            (self.map_bridge.move_waypoint_signal, self.move_waypoint),
            (self.map_bridge.move_waypoint_realtime_signal, self.move_waypoint_realtime),
            (self.connection_status.clicked, self.on_connection_status_clicked),
        ]
        for signal, slot in signal_pairs:
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass

        # Stop MAVLink thread and reconnect timers before tearing down map UI.
        self.connection_manager.shutdown()
        self.recorder.stop_recording()

        if self.web_view is not None:
            try:
                self.web_view.stop()
            except Exception:
                pass
            try:
                self.web_view.page().setWebChannel(None)
            except Exception:
                pass
            self._map_channel = None
            try:
                self.web_view.setHtml("")
            except Exception:
                pass

    def closeEvent(self, event):
        self._shutdown_background_services()

        # Close all floating panels when main window closes
        self.waypoint_panel.close()
        self.flight_panel.close()
        if hasattr(self, "_notice_overlay") and self._notice_overlay is not None:
            self._notice_overlay.close()
            self._notice_overlay = None

        self.log_user_action("app_closed")
        event.accept()








