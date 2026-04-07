from PyQt6.QtWidgets import QFormLayout, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from PyQt6.QtCore import pyqtSignal

class StatusPanel(QFrame):
    close_clicked = pyqtSignal()
    def __init__(self):
        super().__init__()
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0,0,0,0)
        
        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(5,5,5,5)
        top_layout.addStretch()
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(20,20)
        top_layout.addWidget(self.close_btn)
        main_layout.addWidget(top_bar)

        layout = QFormLayout()
        self.mode = QLabel("UNKNOWN")
        self.gps = QLabel("0 颗")
        self.alt = QLabel("0 m")
        self.vel = QLabel("0 m/s")
        self.volt = QLabel("0 V")
        self.batt = QLabel("100 %")
        self.alert = QLabel("正常")
        self.alert.setStyleSheet("color:green;")
        layout.addRow("飞行模式：", self.mode)
        layout.addRow("GPS 卫星：", self.gps)
        layout.addRow("相对高度：", self.alt)
        layout.addRow("飞行速度：", self.vel)
        layout.addRow("电池电压：", self.volt)
        layout.addRow("剩余电量：", self.batt)
        layout.addRow("设备状态：", self.alert)
        main_layout.addLayout(layout)
        self.close_btn.clicked.connect(self.close_clicked.emit)

    def update_data(self, data: dict):
        self.mode.setText(data.get('mode', 'UNKNOWN'))
        self.gps.setText(f"{data.get('gps', 0)} 颗")
        self.alt.setText(f"{data.get('alt', 0):.1f} m")
        self.vel.setText(f"{data.get('vel', 0):.1f} m/s")
        self.volt.setText(f"{data.get('volt', 0):.2f} V")
        self.batt.setText(f"{data.get('battery_remaining', 100)} %")