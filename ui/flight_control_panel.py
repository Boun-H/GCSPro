from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QFont

class FlightControlPanel(QFrame):
    arm_clicked = pyqtSignal()
    disarm_clicked = pyqtSignal()
    takeoff_clicked = pyqtSignal()
    land_clicked = pyqtSignal()
    return_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.connection_text = "未连接"
        self.mode_text = "UNKNOWN"
        self._command_busy = False
        self.setStyleSheet(
            "QFrame { background: transparent; border: none; }"
            "QLabel { color: #d9eaff; }"
        )
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        title = QLabel("VTOL 飞行控制")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        title.setStyleSheet("color: #d9eaff;")
        header_layout.addWidget(title)

        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(8)

        self.connection_badge = QLabel(self.connection_text)
        self.mode_badge = QLabel(self.mode_text)
        self.vehicle_badge = QLabel("Vehicle --")
        for badge in [self.connection_badge, self.mode_badge, self.vehicle_badge]:
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setMinimumHeight(26)
            badge.setStyleSheet(
                "background-color: rgba(18, 37, 58, 0.92);"
                "border: 1px solid rgba(53, 80, 107, 0.85);"
                "border-radius: 13px;"
                "padding: 2px 10px;"
                "color: #d9eaff;"
                "font-weight: 600;"
            )
        meta_row.addWidget(self.connection_badge)
        meta_row.addWidget(self.mode_badge)
        meta_row.addWidget(self.vehicle_badge)
        header_layout.addLayout(meta_row)
        main_layout.addWidget(header)

        self.summary = QLabel("当前面板为 VTOL 专用控制，连接后可直接执行。")
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("color: #8fb0d3; font-size: 12px;")
        main_layout.addWidget(self.summary)

        button_grid = QGridLayout()
        button_grid.setContentsMargins(0, 0, 0, 0)
        button_grid.setHorizontalSpacing(8)
        button_grid.setVerticalSpacing(8)

        self.btn_arm = QPushButton("解锁\nARM")
        self.btn_disarm = QPushButton("上锁\nDISARM")
        self.btn_takeoff = QPushButton("垂起\nVTOL")
        self.btn_land = QPushButton("垂降\nQLAND")
        self.btn_return = QPushButton("返航\nQRTL")

        self._style_button(self.btn_arm, "#1f9d68", "#16754d")
        self._style_button(self.btn_disarm, "#b85c38", "#924628")
        self._style_button(self.btn_takeoff, "#2072b8", "#165687")
        self._style_button(self.btn_land, "#4b647f", "#34475b")
        self._style_button(self.btn_return, "#0f766e", "#0c5b56")

        button_grid.addWidget(self.btn_arm, 0, 0)
        button_grid.addWidget(self.btn_disarm, 0, 1)
        button_grid.addWidget(self.btn_takeoff, 1, 0)
        button_grid.addWidget(self.btn_land, 1, 1)
        button_grid.addWidget(self.btn_return, 2, 0, 1, 2)
        main_layout.addLayout(button_grid)
        main_layout.addStretch()

        self.btn_arm.clicked.connect(self.arm_clicked.emit)
        self.btn_disarm.clicked.connect(self.disarm_clicked.emit)
        self.btn_takeoff.clicked.connect(self.takeoff_clicked.emit)
        self.btn_land.clicked.connect(self.land_clicked.emit)
        self.btn_return.clicked.connect(self.return_clicked.emit)
        self.set_controls_enabled(False)

    def _style_button(self, button, background, hover_background):
        button.setMinimumHeight(58)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFont(QFont("Microsoft YaHei", 10, QFont.Weight.Bold))
        button.setStyleSheet(
            "QPushButton {{"
            f"background-color: {background};"
            "color: white;"
            "border: none;"
            "border-radius: 10px;"
            "padding: 8px 10px;"
            "text-align: center;"
            "}}"
            "QPushButton:hover {{"
            f"background-color: {hover_background};"
            "}}"
            "QPushButton:pressed {{"
            "padding-top: 10px;"
            "padding-bottom: 6px;"
            "}}"
            "QPushButton:disabled {{"
            "background-color: #aab4bf;"
            "color: #edf1f5;"
            "}}"
        )

    def set_connection_state(self, state_text):
        self.connection_text = state_text
        self.connection_badge.setText(state_text)
        background = "rgba(14, 65, 52, 0.92)" if state_text == "已连接" else "rgba(91, 54, 12, 0.92)" if state_text == "连接中" else "rgba(92, 28, 35, 0.92)"
        border = "#1a7f64" if state_text == "已连接" else "#c47a1b" if state_text == "连接中" else "#c25565"
        self.connection_badge.setStyleSheet(
            "background-color: " + background + ";"
            "border: 1px solid " + border + ";"
            "border-radius: 13px; padding: 2px 10px; color: #d9eaff; font-weight: 600;"
        )
        self.set_controls_enabled(state_text == "已连接" and not self._command_busy)

    def set_flight_mode(self, mode_text):
        self.mode_text = mode_text
        self.mode_badge.setText(mode_text)

    def set_vehicle_identity(self, vehicle_id: str, link_name: str = ""):
        text = str(vehicle_id or "--")
        if link_name:
            text = f"{text} @ {link_name}"
        self.vehicle_badge.setText(text)

    def set_controls_enabled(self, enabled: bool):
        for button in [self.btn_arm, self.btn_disarm, self.btn_takeoff, self.btn_land, self.btn_return]:
            button.setEnabled(bool(enabled))
        if enabled:
            self.summary.setText("当前面板为 VTOL 专用控制，连接后可直接执行。")
        else:
            self.summary.setText("当前不可下发指令：请先连接飞控。")

    def set_command_busy(self, busy: bool, hint: str = ""):
        self._command_busy = bool(busy)
        if busy:
            self.set_controls_enabled(False)
            if hint:
                self.summary.setText(hint)
        else:
            self.set_controls_enabled(self.connection_text == "已连接")