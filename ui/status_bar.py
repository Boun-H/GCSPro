from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel

class StatusBarWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10,5,10,5)

        self.connection_status = QLabel("🔴 未连接")
        self.flight_time = QLabel("飞行时间: 00:00:00")
        self.battery = QLabel("电池: 100%")
        self.altitude = QLabel("高度: 0m")
        self.speed = QLabel("速度: 0m/s")

        self.layout.addWidget(self.connection_status)
        self.layout.addStretch()
        self.layout.addWidget(self.flight_time)
        self.layout.addStretch()
        self.layout.addWidget(self.battery)
        self.layout.addStretch()
        self.layout.addWidget(self.altitude)
        self.layout.addStretch()
        self.layout.addWidget(self.speed)