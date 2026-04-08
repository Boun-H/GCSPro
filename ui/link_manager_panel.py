from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class LinkManagerPanel(QFrame):
    close_clicked = pyqtSignal()
    activate_requested = pyqtSignal(str)
    disconnect_requested = pyqtSignal(str)
    settings_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._active_key = ""
        self.setMinimumSize(520, 620)
        self.setStyleSheet(
            "QFrame { background:#121d2d; border:1px solid #2a4362; border-radius:10px; }"
            "QLabel { color:#d9e6f8; }"
            "QPushButton { background:#1e3a5a; color:#d9e6f8; border:1px solid #35506b; border-radius:8px; padding:6px 10px; }"
            "QPushButton:hover { background:#264b73; }"
            "QListWidget { background:#0f1926; color:#d9e6f8; border:1px solid #27415f; border-radius:8px; }"
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 10, 10, 6)
        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(2)
        title = QLabel("链路管理")
        title.setStyleSheet("font-size:16px; font-weight:700; color:#eef5ff;")
        subtitle = QLabel("并行连接的 Serial / TCP / UDP 链路")
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

        self.summary_label = QLabel("暂无活动链路")
        self.summary_label.setStyleSheet("color:#9fb4cf;")
        content.addWidget(self.summary_label)

        self.link_list = QListWidget()
        self.link_list.setMinimumHeight(220)
        content.addWidget(self.link_list)

        action_row = QHBoxLayout()
        self.btn_activate = QPushButton("设为当前")
        self.btn_disconnect = QPushButton("断开所选")
        self.btn_settings = QPushButton("链路设置")
        action_row.addWidget(self.btn_activate)
        action_row.addWidget(self.btn_disconnect)
        action_row.addStretch()
        action_row.addWidget(self.btn_settings)
        content.addLayout(action_row)

        details = QWidget()
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(8, 8, 8, 8)
        details_layout.setSpacing(6)
        details.setStyleSheet("QWidget { background:#0f1926; border:1px solid #27415f; border-radius:8px; }")
        self.detail_name = QLabel("链路: --")
        self.detail_state = QLabel("状态: --")
        self.detail_mode = QLabel("模式: --")
        self.detail_vehicle = QLabel("载具: --")
        self.detail_error = QLabel("错误: --")
        self.detail_error.setWordWrap(True)
        for label in [self.detail_name, self.detail_state, self.detail_mode, self.detail_vehicle, self.detail_error]:
            label.setStyleSheet("color:#d9e6f8; border:none; background:transparent;")
            details_layout.addWidget(label)
        content.addWidget(details)

        main_layout.addLayout(content)

        self.close_btn.clicked.connect(self.close_clicked.emit)
        self.btn_settings.clicked.connect(self.settings_requested.emit)
        self.btn_activate.clicked.connect(self._emit_activate)
        self.btn_disconnect.clicked.connect(self._emit_disconnect)
        self.link_list.itemSelectionChanged.connect(self._emit_activate)

    def _selected_key(self) -> str:
        item = self.link_list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole) or "").strip() if item is not None else ""

    def _emit_activate(self):
        key = self._selected_key()
        if key:
            self.activate_requested.emit(key)

    def _emit_disconnect(self):
        key = self._selected_key()
        if key:
            self.disconnect_requested.emit(key)

    def set_link_summaries(self, links: list[dict], active_key: str = ""):
        self._active_key = str(active_key or "")
        self.link_list.blockSignals(True)
        self.link_list.clear()
        for link in links or []:
            key = str(link.get("key", ""))
            state = str(link.get("state", "disconnected"))
            marker = "★ " if key == self._active_key else ""
            text = f"{marker}{link.get('kind', '--').upper()} | {link.get('label', '--')} | {state}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.link_list.addItem(item)
            if key == self._active_key:
                self.link_list.setCurrentItem(item)
        self.link_list.blockSignals(False)
        self.summary_label.setText(f"活动链路 {len(links or [])} 条")

    def set_active_link(self, link: dict | None):
        link = dict(link or {})
        self._active_key = str(link.get("key", "") or "")
        self.detail_name.setText(f"链路: {link.get('kind', '--').upper()} / {link.get('label', '--')}")
        self.detail_state.setText(f"状态: {link.get('state', 'disconnected')}")
        self.detail_mode.setText(f"模式: {link.get('mode', 'UNKNOWN')}")
        vehicle_id = "--"
        if link.get("sysid") is not None:
            vehicle_id = f"{link.get('sysid')}:{link.get('compid', 1)}"
        self.detail_vehicle.setText(f"载具: {vehicle_id}")
        self.detail_error.setText(f"错误: {link.get('last_error', '--') or '--'}")
