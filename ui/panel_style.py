from __future__ import annotations

from PyQt6.QtCore import QDateTime
from PyQt6.QtWidgets import QLabel, QPushButton, QWidget

STATUS_TONES = {
    "neutral": ("#142133", "#29425c", "#d9e6f8"),
    "ok": ("#103428", "#1f8b5f", "#c9f7df"),
    "warn": ("#3c2a11", "#c38b22", "#fde7a7"),
    "danger": ("#3d1d26", "#c25565", "#ffd5dc"),
    "info": ("#132c45", "#328ad8", "#d8edff"),
}


def build_panel_stylesheet(include_checks: bool = False) -> str:
    parts = [
        "QFrame { background:#121d2d; border:1px solid #2a4362; border-radius:10px; }",
        "QLabel { color:#d9e6f8; }",
        "QScrollArea { background:transparent; border:none; }",
        "QPushButton { min-height:32px; background:#1e3a5a; color:#d9e6f8; border:1px solid #35506b; border-radius:8px; padding:6px 12px; }",
        "QPushButton:hover { background:#264b73; }",
        "QPushButton[active='true'] { background:#1f6fb2; border:1px solid #58a6ff; color:#ffffff; }",
        "QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox, QListWidget { background:#0f1926; color:#d9e6f8; border:1px solid #27415f; border-radius:7px; padding:5px 8px; }",
        "QProgressBar { background:#101a28; border:1px solid #27415f; border-radius:7px; color:#d9e6f8; text-align:center; }",
        "QProgressBar::chunk { background:#1f8b5f; border-radius:6px; }",
        "QTabWidget::pane { border:1px solid #27415f; background:#0f1926; border-radius:8px; }",
        "QTabBar::tab { background:#162233; color:#d9e6f8; padding:6px 12px; margin-right:2px; border-top-left-radius:6px; border-top-right-radius:6px; }",
        "QTabBar::tab:selected { background:#1f6fb2; }",
    ]
    if include_checks:
        parts.append("QCheckBox { color:#d9e6f8; spacing:6px; }")
    return "".join(parts)


def apply_tone(widget: QWidget, tone: str = "neutral", padding: int = 8, radius: int = 8, font_size: int = 12):
    background, border, foreground = STATUS_TONES.get(tone, STATUS_TONES["neutral"])
    widget.setStyleSheet(
        "QLabel {"
        f"background:{background};"
        f"border:1px solid {border};"
        f"border-radius:{int(radius)}px;"
        f"color:{foreground};"
        f"padding:{int(padding)}px;"
        f"font-size:{int(font_size)}px;"
        "}"
    )


def style_panel_title(label: QLabel, size: int = 16):
    label.setStyleSheet(f"font-size:{int(size)}px; font-weight:700; color:#eef5ff;")


def style_panel_subtitle(label: QLabel, size: int = 11):
    label.setWordWrap(True)
    label.setStyleSheet(f"font-size:{int(size)}px; color:#8fa4bf;")


def style_timestamp_badge(label: QLabel):
    label.setAlignment(label.alignment())
    label.setMinimumWidth(108)
    label.setFixedHeight(24)
    apply_tone(label, "neutral", padding=2, radius=6, font_size=10)


def apply_banner_tone(widget: QWidget, tone: str = "neutral"):
    apply_tone(widget, tone, padding=6, radius=8, font_size=11)


def style_close_button(button: QPushButton):
    button.setFixedSize(24, 24)
    button.setStyleSheet(
        "QPushButton { min-height:24px; min-width:24px; padding:0px; background:#24364d; color:#d2dff1; border:1px solid #324b68; border-radius:6px; }"
        "QPushButton:hover { background:#2c4561; }"
    )


def style_action_button(button: QPushButton, tone: str = "info", compact: bool = False):
    background, border, foreground = STATUS_TONES.get(tone, STATUS_TONES["info"])
    min_height = 30 if compact else 34
    button.setStyleSheet(
        "QPushButton {"
        f"min-height:{min_height}px;"
        f"background:{background};"
        f"color:{foreground};"
        f"border:1px solid {border};"
        "border-radius:8px;"
        f"padding:{'4px 10px' if compact else '6px 12px'};"
        "font-weight:600;"
        "}"
        "QPushButton:hover {"
        f"background:{border};"
        "color:#ffffff;"
        "}"
    )


def recent_time_text(prefix: str = "最近更新") -> str:
    return f"{prefix}: {QDateTime.currentDateTime().toString('HH:mm:ss')}"
