from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import QGridLayout, QLabel, QLineEdit, QWidget

from core.mission import RouteConfig


class AutoRouteDetailWidget(QWidget):
    route_field_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        layout = QGridLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        layout.addWidget(QLabel("起飞过渡高度T1(m)"), 0, 0)
        self.t1_alt_input = QLineEdit(str(RouteConfig.DEFAULT_T1_ALT))
        self.t1_alt_input.setValidator(QDoubleValidator(RouteConfig.MIN_ALT, RouteConfig.MAX_ALT, 0))
        layout.addWidget(self.t1_alt_input, 0, 1)

        layout.addWidget(QLabel("巡航等待高度T2(m)"), 0, 2)
        self.t2_alt_input = QLineEdit(str(RouteConfig.DEFAULT_T2_ALT))
        self.t2_alt_input.setValidator(QDoubleValidator(RouteConfig.MIN_ALT, RouteConfig.MAX_ALT, 0))
        layout.addWidget(self.t2_alt_input, 0, 3)

        layout.addWidget(QLabel("降落盘旋高度L1(m)"), 1, 0)
        self.l1_alt_input = QLineEdit(str(RouteConfig.DEFAULT_L1_ALT))
        self.l1_alt_input.setValidator(QDoubleValidator(RouteConfig.MIN_ALT, RouteConfig.MAX_ALT, 0))
        layout.addWidget(self.l1_alt_input, 1, 1)

        layout.addWidget(QLabel("进近终止高度L2(m)"), 1, 2)
        self.l2_alt_input = QLineEdit(str(RouteConfig.DEFAULT_L2_ALT))
        self.l2_alt_input.setValidator(QDoubleValidator(RouteConfig.MIN_ALT, RouteConfig.MAX_ALT, 0))
        layout.addWidget(self.l2_alt_input, 1, 3)

        layout.addWidget(QLabel("降落高度L3(m)"), 2, 0)
        self.l3_alt_input = QLineEdit(str(RouteConfig.DEFAULT_L3_ALT))
        self.l3_alt_input.setValidator(QDoubleValidator(RouteConfig.MIN_ALT, RouteConfig.MAX_ALT, 0))
        layout.addWidget(self.l3_alt_input, 2, 1)

        layout.addWidget(QLabel("L2-L3距离(m)"), 2, 2)
        self.l2_l3_distance_input = QLineEdit(str(RouteConfig.DEFAULT_L2_DISTANCE_M))
        self.l2_l3_distance_input.setValidator(QDoubleValidator(RouteConfig.MIN_L2_TO_L3_DISTANCE_M, 2000, 0))
        layout.addWidget(self.l2_l3_distance_input, 2, 3)

        for input_widget in [
            self.t1_alt_input,
            self.t2_alt_input,
            self.l1_alt_input,
            self.l2_alt_input,
            self.l3_alt_input,
            self.l2_l3_distance_input,
        ]:
            input_widget.textChanged.connect(self._on_field_changed)

        self.setStyleSheet("QLabel { color: #d9e6f8; font-size: 12px; } QLineEdit { padding: 4px 6px; border-radius: 4px; background: #0f1926; border: 1px solid #27415f; color: #d9e6f8; }")

    def _on_field_changed(self):
        try:
            params = {
                "t1_alt": float(self.t1_alt_input.text()),
                "t2_alt": float(self.t2_alt_input.text()),
                "l1_alt": float(self.l1_alt_input.text()),
                "l2_alt": float(self.l2_alt_input.text()),
                "l3_alt": float(self.l3_alt_input.text()),
                "l2_l3_distance": float(self.l2_l3_distance_input.text()),
            }
            self.route_field_changed.emit(params)
        except ValueError:
            pass