from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class LinkSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("通信链路配置中心")
        self.setModal(True)
        self.setFixedSize(520, 420)
        self.setStyleSheet(
            "QDialog { background:#0e1822; color:#d9e6f7; }"
            "QLabel { color:#d9e6f7; }"
            "QPushButton { background:#1565c0; color:white; border:none; border-radius:6px; padding:6px 14px; }"
            "QPushButton:hover { background:#1976d2; }"
            "QComboBox, QTextEdit { background:#162233; color:#d9e6f7; border:1px solid #2d4a6a; border-radius:6px; padding:6px; }"
            "QCheckBox { color:#d9e6f7; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("QGC 风格链路配置")
        title.setStyleSheet("font-size:16px; font-weight:700;")
        subtitle = QLabel("统一保存默认串口 / TCP / UDP 参数、自动重连选项与最近连接记录")
        subtitle.setStyleSheet("font-size:12px; color:#9fb4cf;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        form_host = QWidget()
        form = QFormLayout(form_host)
        form.setContentsMargins(0, 8, 0, 8)
        form.setSpacing(8)

        self.serial_port = QComboBox()
        self.serial_port.setEditable(True)
        self.serial_baud = QComboBox()
        self.serial_baud.setEditable(True)
        self.serial_baud.addItems(["57600", "115200", "230400", "460800", "921600"])
        self.tcp_host = QComboBox()
        self.tcp_host.setEditable(True)
        self.tcp_host.addItems(["127.0.0.1", "192.168.1.10", "10.0.0.2"])
        self.tcp_port = QComboBox()
        self.tcp_port.setEditable(True)
        self.tcp_port.addItems(["5760", "14550", "14551"])
        self.udp_host = QComboBox()
        self.udp_host.setEditable(True)
        self.udp_host.addItems(["0.0.0.0", "127.0.0.1", "192.168.1.2"])
        self.udp_port = QComboBox()
        self.udp_port.setEditable(True)
        self.udp_port.addItems(["14550", "14551", "14552"])
        self.map_source = QComboBox()
        self.map_source.addItems(["谷歌卫星", "ArcGIS卫星"])
        self.chk_auto_reconnect = QCheckBox("启用自动重连")
        self.chk_auto_connect = QCheckBox("启动后自动连接最近链路")

        form.addRow("默认串口", self.serial_port)
        form.addRow("默认波特率", self.serial_baud)
        form.addRow("默认 TCP 主机", self.tcp_host)
        form.addRow("默认 TCP 端口", self.tcp_port)
        form.addRow("默认 UDP 主机", self.udp_host)
        form.addRow("默认 UDP 端口", self.udp_port)
        form.addRow("默认地图源", self.map_source)
        form.addRow("", self.chk_auto_reconnect)
        form.addRow("", self.chk_auto_connect)
        layout.addWidget(form_host)

        recent_title = QLabel("最近链路")
        recent_title.setStyleSheet("font-size:13px; font-weight:700;")
        layout.addWidget(recent_title)
        self.recent_links = QTextEdit()
        self.recent_links.setReadOnly(True)
        self.recent_links.setPlaceholderText("暂无最近链路记录")
        layout.addWidget(self.recent_links, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("保存")
        btn_ok.clicked.connect(self.accept)
        actions.addWidget(btn_cancel)
        actions.addWidget(btn_ok)
        layout.addLayout(actions)

    def set_values(self, serial_config: dict, tcp_config: dict, udp_config: dict, auto_reconnect: bool, auto_connect: bool, map_source: str, recent_links: list[dict]):
        self.serial_port.setEditText(str((serial_config or {}).get("port", "") or ""))
        self.serial_baud.setCurrentText(str((serial_config or {}).get("baud", 115200) or 115200))
        self.tcp_host.setEditText(str((tcp_config or {}).get("host", "127.0.0.1") or "127.0.0.1"))
        self.tcp_port.setCurrentText(str((tcp_config or {}).get("port", 5760) or 5760))
        self.udp_host.setEditText(str((udp_config or {}).get("host", "0.0.0.0") or "0.0.0.0"))
        self.udp_port.setCurrentText(str((udp_config or {}).get("port", 14550) or 14550))
        self.map_source.setCurrentText(str(map_source or "谷歌卫星") or "谷歌卫星")
        self.chk_auto_reconnect.setChecked(bool(auto_reconnect))
        self.chk_auto_connect.setChecked(bool(auto_connect))
        lines = []
        for item in recent_links or []:
            kind = str(item.get("kind", "unknown"))
            label = str(item.get("label", "未命名链路"))
            lines.append(f"- [{kind}] {label}")
        self.recent_links.setPlainText("\n".join(lines) if lines else "暂无最近链路记录")

    def values(self) -> dict:
        return {
            "serial": {
                "port": self.serial_port.currentText().strip(),
                "baud": int(float(self.serial_baud.currentText().strip() or 115200)),
            },
            "tcp": {
                "host": self.tcp_host.currentText().strip() or "127.0.0.1",
                "port": int(float(self.tcp_port.currentText().strip() or 5760)),
            },
            "udp": {
                "host": self.udp_host.currentText().strip() or "0.0.0.0",
                "port": int(float(self.udp_port.currentText().strip() or 14550)),
            },
            "auto_reconnect": self.chk_auto_reconnect.isChecked(),
            "auto_connect": self.chk_auto_connect.isChecked(),
            "map_source": self.map_source.currentText().strip() or "谷歌卫星",
        }
