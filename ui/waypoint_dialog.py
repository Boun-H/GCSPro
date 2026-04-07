from PyQt6.QtWidgets import (
    QDialog, QFormLayout, QDoubleSpinBox,
    QComboBox, QDialogButtonBox
)
from core.constants import DEFAULT_WAYPOINT

_DIALOG_STYLE = """
    QDialog {
        background-color: #0d1826;
    }
    QLabel {
        color: #ffffff;
        font-size: 13px;
    }
    QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit {
        background: #162233;
        color: #ffffff;
        border: 1px solid #2d4a6a;
        border-radius: 6px;
        padding: 5px 8px;
        font-size: 13px;
    }
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
        background: #1e3452;
        border: 1px solid #2d4a6a;
        border-radius: 3px;
        width: 18px;
    }
    QComboBox::drop-down { border: none; width: 20px; }
    QComboBox QAbstractItemView {
        background: #162233;
        color: #ffffff;
        border: 1px solid #2d4a6a;
        selection-background-color: #1565c0;
    }
    QPushButton {
        background: #1a3452;
        color: #ffffff;
        border: 1px solid #3a6090;
        border-radius: 8px;
        min-width: 80px;
        min-height: 32px;
        padding: 4px 14px;
        font-size: 13px;
        font-weight: 600;
    }
    QPushButton:hover { background: #244165; border-color: #5588bb; }
    QPushButton:pressed { background: #11263d; }
"""

class WaypointDialog(QDialog):
    def __init__(self, wp=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("航点详细信息")
        self.setFixedSize(460, 340)
        self.setStyleSheet(_DIALOG_STYLE)
        self.wp = wp or DEFAULT_WAYPOINT.copy()
        self.setup_ui()

    def setup_ui(self):
        layout = QFormLayout(self)
        self.index = QDoubleSpinBox()
        self.index.setRange(1, 999)
        self.index.setValue(self.wp.get("index", 1))
        self.lat = QDoubleSpinBox()
        self.lon = QDoubleSpinBox()
        self.alt = QDoubleSpinBox()
        self.speed = QDoubleSpinBox()
        self.lat.setRange(-90, 90)
        self.lon.setRange(-180, 180)
        self.alt.setRange(0, 2000)
        self.speed.setRange(0, 30)
        self.lat.setValue(self.wp.get("lat", 0))
        self.lon.setValue(self.wp.get("lon", 0))
        self.alt.setValue(self.wp.get("alt", 50))
        self.speed.setValue(self.wp.get("speed", 5))
        self.action = QComboBox()
        self.action.addItems(["悬停", "拍照", "直线飞行"])
        self.action.setCurrentText(self.wp.get("action", "悬停"))
        self.turn_mode = QComboBox()
        self.turn_mode.addItems(["协调转弯", "直飞"])
        self.turn_mode.setCurrentText(self.wp.get("turn_mode", "协调转弯"))
        layout.addRow("航点序号", self.index)
        layout.addRow("纬度", self.lat)
        layout.addRow("经度", self.lon)
        layout.addRow("高度(m)", self.alt)
        layout.addRow("速度(m/s)", self.speed)
        layout.addRow("执行动作", self.action)
        layout.addRow("转弯模式", self.turn_mode)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addRow(btns)

    def get_data(self):
        return {
            "index": int(self.index.value()),
            "lat": self.lat.value(),
            "lon": self.lon.value(),
            "alt": self.alt.value(),
            "speed": self.speed.value(),
            "action": self.action.currentText(),
            "turn_mode": self.turn_mode.currentText()
        }