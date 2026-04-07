from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.mp_core_registry import grouped_features


class MPWorkbenchPanel(QFrame):
    close_clicked = pyqtSignal()
    action_requested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._action_buttons = {}
        self.setStyleSheet(
            "QFrame { background:#121d2d; border:1px solid #2a4362; border-radius:10px; }"
            "QLabel { color:#d9e6f8; }"
            "QPushButton { background:#1e3a5a; color:#d9e6f8; border:1px solid #35506b; border-radius:8px; padding:6px 10px; }"
            "QPushButton:hover { background:#264b73; }"
            "QPushButton:pressed { background:#173958; }"
            "QPushButton[active='true'] { background:#0f766e; border:1px solid #2dd4bf; color:#dcfce7; }"
            "QPushButton[active='true']:hover { background:#0d9488; }"
            "QGroupBox { color:#d9e6f8; }"
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 10, 10, 6)
        title = QLabel("MP核心工作台")
        title.setStyleSheet("font-size:16px; font-weight:700; color:#eef5ff;")
        subtitle = QLabel("自动生成的核心功能入口")
        subtitle.setStyleSheet("font-size:12px; color:#9fb4cf;")
        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(2)
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        top_layout.addLayout(title_col)
        top_layout.addStretch()
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setStyleSheet("background:#24364d; color:#d2dff1; border:1px solid #324b68; border-radius:6px;")
        top_layout.addWidget(self.close_btn)
        main_layout.addWidget(top_bar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(10, 0, 10, 10)
        content_layout.setSpacing(8)

        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("font-size:12px; color:#9fb4cf;")
        content_layout.addWidget(self.status_label)

        groups = grouped_features()
        for group_name, features in groups.items():
            block = QWidget()
            block_layout = QVBoxLayout(block)
            block_layout.setContentsMargins(0, 0, 0, 0)
            block_layout.setSpacing(6)

            group_title = QLabel(group_name)
            group_title.setStyleSheet("font-size:13px; font-weight:700; color:#dbeafe;")
            block_layout.addWidget(group_title)

            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(6)
            grid.setVerticalSpacing(6)

            for idx, feature in enumerate(features):
                btn = QPushButton(feature.label)
                btn.setToolTip(feature.description)
                btn.clicked.connect(lambda _=False, key=feature.key: self.action_requested.emit(key))
                self._action_buttons[feature.key] = btn
                grid.addWidget(btn, idx // 3, idx % 3)

            block_layout.addLayout(grid)
            content_layout.addWidget(block)

        content_layout.addStretch()
        main_layout.addWidget(content)

        self.close_btn.clicked.connect(self.close_clicked.emit)

    def set_status(self, text: str):
        self.status_label.setText(text)

    def set_action_active(self, action_key: str, active: bool):
        button = self._action_buttons.get(action_key)
        if button is None:
            return
        button.setProperty("active", "true" if active else "false")
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()
