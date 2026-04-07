"""
GCSPro 统一弹窗工具 — 深色主题，白色字体
使用方式：
    from .gcs_dialogs import gcs_confirm, gcs_warning, gcs_info, gcs_input_double
"""
from typing import Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

# ── 统一深色主题样式 ────────────────────────────────────────────────────────
_DIALOG_STYLE = """
    QDialog, QMessageBox {
        background-color: #0d1826;
    }
    QLabel {
        color: #ffffff;
        font-size: 13px;
        background: transparent;
    }
    QPushButton {
        background: #1a3452;
        color: #ffffff;
        border: 1px solid #3a6090;
        border-radius: 8px;
        min-width: 90px;
        min-height: 34px;
        padding: 4px 16px;
        font-size: 13px;
        font-weight: 600;
    }
    QPushButton:hover {
        background: #244165;
        border-color: #5588bb;
    }
    QPushButton:pressed {
        background: #11263d;
    }
    QPushButton[role="danger"] {
        background: #6b1f1f;
        border-color: #c0392b;
    }
    QPushButton[role="danger"]:hover {
        background: #8b2a2a;
    }
    QDoubleSpinBox, QSpinBox, QLineEdit {
        background: #162233;
        color: #ffffff;
        border: 1px solid #2d4a6a;
        border-radius: 6px;
        padding: 5px 8px;
        font-size: 13px;
        selection-background-color: #1565c0;
    }
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
        background: #1e3452;
        border: 1px solid #2d4a6a;
        border-radius: 3px;
        width: 18px;
    }
"""


def _make_msgbox(parent, title: str, text: str, icon) -> QMessageBox:
    """创建统一风格的 QMessageBox 实例"""
    msg = QMessageBox(parent)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setIcon(icon)
    msg.setStyleSheet(_DIALOG_STYLE)
    return msg


def gcs_confirm(
    parent,
    title: str,
    message: str,
    yes_text: str = "确认",
    no_text: str = "取消",
    danger: bool = False,
) -> bool:
    """深色主题确认弹窗，返回 True 表示用户点击了确认"""
    msg = _make_msgbox(parent, title, message, QMessageBox.Icon.Question)
    btn_yes = msg.addButton(yes_text, QMessageBox.ButtonRole.AcceptRole)
    btn_no = msg.addButton(no_text, QMessageBox.ButtonRole.RejectRole)
    if danger:
        btn_yes.setStyleSheet(
            "QPushButton { background:#8b2020; color:#fff; border:1px solid #c0392b;"
            "border-radius:8px; min-width:90px; min-height:34px; padding:4px 16px;"
            "font-size:13px; font-weight:600; }"
            "QPushButton:hover { background:#a52828; }"
            "QPushButton:pressed { background:#6b1414; }"
        )
    msg.setDefaultButton(btn_no)
    msg.exec()
    return msg.clickedButton() == btn_yes


def gcs_warning(parent, title: str, message: str):
    """深色主题警告弹窗"""
    msg = _make_msgbox(parent, title, message, QMessageBox.Icon.Warning)
    btn = msg.addButton("确定", QMessageBox.ButtonRole.AcceptRole)
    msg.setDefaultButton(btn)
    msg.exec()


def gcs_info(parent, title: str, message: str):
    """深色主题信息弹窗"""
    msg = _make_msgbox(parent, title, message, QMessageBox.Icon.Information)
    btn = msg.addButton("确定", QMessageBox.ButtonRole.AcceptRole)
    msg.setDefaultButton(btn)
    msg.exec()


class GcsInputDoubleDialog(QDialog):
    """深色主题浮点数输入弹窗（替代 QInputDialog.getDouble）"""

    def __init__(
        self,
        parent,
        title: str,
        label: str,
        default: float,
        min_val: float,
        max_val: float,
        decimals: int = 0,
        suffix: str = " m",
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setFixedWidth(340)
        self.setStyleSheet(_DIALOG_STYLE)
        self._value = default

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 18)
        layout.setSpacing(14)

        lbl = QLabel(label)
        lbl.setStyleSheet("color:#ffffff; font-size:13px; font-weight:600;")
        layout.addWidget(lbl)

        self._spinbox = QDoubleSpinBox()
        self._spinbox.setRange(min_val, max_val)
        self._spinbox.setValue(default)
        self._spinbox.setDecimals(decimals)
        self._spinbox.setSuffix(suffix)
        self._spinbox.setMinimumHeight(36)
        layout.addWidget(self._spinbox)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()
        btn_cancel = QPushButton("取消")
        btn_ok = QPushButton("确定")
        btn_cancel.setFixedHeight(36)
        btn_ok.setFixedHeight(36)
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._on_accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _on_accept(self):
        self._value = self._spinbox.value()
        self.accept()

    def get_value(self) -> Tuple[float, bool]:
        """显示对话框并返回 (value, accepted)"""
        ok = self.exec() == QDialog.DialogCode.Accepted
        return self._value, ok


def gcs_input_double(
    parent,
    title: str,
    label: str,
    default: float,
    min_val: float,
    max_val: float,
    decimals: int = 0,
    suffix: str = " m",
) -> Tuple[float, bool]:
    """深色主题浮点数输入，返回 (value, ok)"""
    dlg = GcsInputDoubleDialog(parent, title, label, default, min_val, max_val, decimals, suffix)
    return dlg.get_value()
