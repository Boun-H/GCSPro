from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QWidget


class WaypointIOWidget(QWidget):
    export_requested = pyqtSignal(str)
    import_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(0, 0, 0, 0)

        self.btn_export_waypoints = QPushButton("导出WPL")
        self.btn_import_waypoints = QPushButton("导入WPL")
        self.btn_export_kml = QPushButton("导出KML")
        self.btn_import_kml = QPushButton("导入KML")

        for btn in [
            self.btn_export_waypoints,
            self.btn_import_waypoints,
            self.btn_export_kml,
            self.btn_import_kml,
        ]:
            btn.setStyleSheet("padding: 6px 12px; border-radius: 4px; background: #1c2b40; color: #d9e6f8;")
            layout.addWidget(btn)

        self.btn_export_waypoints.clicked.connect(lambda: self.export_requested.emit("waypoints"))
        self.btn_import_waypoints.clicked.connect(lambda: self.import_requested.emit("waypoints"))
        self.btn_export_kml.clicked.connect(lambda: self.export_requested.emit("kml"))
        self.btn_import_kml.clicked.connect(lambda: self.import_requested.emit("kml"))