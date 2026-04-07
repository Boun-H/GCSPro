from PyQt6.QtWidgets import QFrame
from PyQt6.QtGui import QPainter, QPen, QColor, QPolygonF, QPainterPath, QFont
from PyQt6.QtCore import Qt, QPointF, QRectF
import math


class AttitudeBall(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.roll = 0.0
        self.pitch = 0.0
        self.yaw = 0.0
        self.altitude = 0.0
        self.speed = 0.0
        self.mode = "UNKNOWN"
        self.battery = 100
        self.setFixedSize(340, 340)
        self.setStyleSheet("background-color: rgba(8, 20, 36, 0.92); border: 1px solid rgba(120, 220, 255, 0.30); border-radius: 12px;")

    def set_attitude(self, roll, pitch, yaw):
        self.roll = roll
        self.pitch = pitch
        self.yaw = yaw
        self.update()

    def set_flight_data(self, roll, pitch, yaw, altitude=0.0, speed=0.0, mode="UNKNOWN", battery=100):
        self.roll = roll
        self.pitch = pitch
        self.yaw = yaw
        self.altitude = altitude
        self.speed = speed
        self.mode = mode
        self.battery = battery
        self.update()

    def paintEvent(self, event):
        width = self.width()
        height = self.height()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        shell_rect = QRectF(0, 0, width, height)
        heading_rect = QRectF(16, 22, width - 32, 30)
        horizon_rect = QRectF(76, 102, width - 152, 176)
        left_card = QRectF(14, 132, 52, 118)
        right_card = QRectF(width - 66, 132, 52, 118)
        bottom_strip = QRectF(10, height - 36, width - 20, 24)
        center_x = horizon_rect.center().x()
        center_y = horizon_rect.center().y() + 2

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(7, 18, 34, 232))
        painter.drawRoundedRect(shell_rect, 12, 12)
        painter.setPen(QPen(QColor(100, 214, 255, 120), 1.2))
        painter.drawRoundedRect(shell_rect.adjusted(1, 1, -1, -1), 12, 12)

        self._draw_heading_band(painter, heading_rect)
        self._draw_horizon_block(painter, horizon_rect, center_x, center_y)
        self._draw_metric_card(painter, left_card, "SPD", f"{self.speed:04.1f}", "m/s", QColor(104, 201, 255))
        self._draw_metric_card(painter, right_card, "ALT", f"{self.altitude:04.1f}", "m", QColor(118, 255, 176))
        self._draw_center_symbol(painter, center_x, center_y)
        self._draw_bottom_strip(painter, bottom_strip)
        painter.end()

    def _draw_heading_band(self, painter, rect):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(10, 20, 32, 220))
        painter.drawRoundedRect(rect, 6, 6)

        center_x = rect.center().x()
        baseline_y = rect.bottom() - 7
        current_heading = self.yaw % 360

        painter.setPen(QPen(QColor(104, 201, 255, 160), 1.2))
        painter.drawLine(int(rect.left() + 10), int(baseline_y), int(rect.right() - 10), int(baseline_y))
        painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        for step in (-20, -10, 0, 10, 20):
            x = center_x + step * 2.2
            tick_height = 9 if step in (-20, 0, 20) else 5
            painter.drawLine(int(x), int(baseline_y - tick_height), int(x), int(baseline_y))
            if step in (-20, 0, 20):
                value = int((current_heading + step + 360) % 360)
                painter.drawText(int(x - 12), int(rect.top() + 14), 24, 12, Qt.AlignmentFlag.AlignCenter, f"{value:03d}")

        heading_box = QRectF(center_x - 24, rect.top() + 3, 48, 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(16, 30, 46, 235))
        painter.drawRoundedRect(heading_box, 4, 4)
        painter.setPen(QPen(QColor(255, 202, 110), 1.3))
        painter.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        painter.drawText(heading_box, Qt.AlignmentFlag.AlignCenter, f"{int(current_heading):03d}")

    def _draw_horizon_block(self, painter, rect, center_x, center_y):
        painter.setPen(QPen(QColor(104, 201, 255, 150), 1.1))
        painter.setBrush(QColor(10, 18, 28, 208))
        painter.drawRoundedRect(rect, 10, 10)

        roll_rect = QRectF(rect.left() + 24, rect.top() - 28, rect.width() - 48, 26)
        self._draw_roll_arc(painter, roll_rect)

        clip_path = QPainterPath()
        clip_path.addRoundedRect(rect.adjusted(1, 1, -1, -1), 10, 10)
        painter.save()
        painter.setClipPath(clip_path)
        painter.translate(center_x, center_y)
        painter.rotate(-self.roll)

        pitch_scale = rect.height() / 60.0
        pitch_offset = self.pitch * pitch_scale
        painter.fillRect(QRectF(-rect.width(), -rect.height() + pitch_offset, rect.width() * 2, rect.height()), QColor(48, 122, 204))
        painter.fillRect(QRectF(-rect.width(), pitch_offset, rect.width() * 2, rect.height()), QColor(120, 82, 48))
        painter.setPen(QPen(QColor(240, 244, 248, 210), 1.8))
        painter.drawLine(QPointF(-rect.width(), pitch_offset), QPointF(rect.width(), pitch_offset))

        ladder_pen = QPen(QColor(232, 241, 250, 190), 1.2)
        painter.setPen(ladder_pen)
        painter.setFont(QFont("Microsoft YaHei", 9, QFont.Weight.Bold))
        for pitch_mark in range(-30, 31, 5):
            if pitch_mark == 0:
                continue
            y = pitch_offset - pitch_mark * pitch_scale
            line_half = rect.width() * (0.24 if pitch_mark % 10 == 0 else 0.14)
            painter.drawLine(QPointF(-line_half, y), QPointF(line_half, y))
            if pitch_mark % 10 == 0:
                self._draw_pitch_label(painter, -line_half - 26, y, str(abs(pitch_mark)))
                self._draw_pitch_label(painter, line_half + 4, y, str(abs(pitch_mark)))

        painter.restore()

    def _draw_roll_arc(self, painter, rect):
        center_x = rect.center().x()
        center_y = rect.bottom() + 34
        radius = rect.width() / 2 - 8
        painter.setPen(QPen(QColor(255, 206, 120, 160), 1.3))
        for angle in range(-45, 46, 15):
            radians = math.radians(angle)
            outer_x = center_x + math.sin(radians) * radius
            outer_y = center_y - math.cos(radians) * radius
            inner_radius = radius - (9 if angle % 30 == 0 else 5)
            inner_x = center_x + math.sin(radians) * inner_radius
            inner_y = center_y - math.cos(radians) * inner_radius
            painter.drawLine(QPointF(inner_x, inner_y), QPointF(outer_x, outer_y))

        painter.setBrush(QColor(255, 116, 88))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(QPolygonF([
            QPointF(center_x, rect.top() + 2),
            QPointF(center_x - 5, rect.top() + 12),
            QPointF(center_x + 5, rect.top() + 12),
        ]))

    def _draw_pitch_label(self, painter, x, y, text):
        label_rect = QRectF(x, y - 9, 22, 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(10, 18, 28, 170))
        painter.drawRoundedRect(label_rect, 4, 4)
        painter.setPen(QPen(QColor(242, 248, 255), 1.0))
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.setPen(QPen(QColor(232, 241, 250, 190), 1.2))

    def _draw_metric_card(self, painter, rect, title, value, unit, color):
        painter.setPen(QPen(color, 1.1))
        painter.setBrush(QColor(8, 16, 26, 212))
        painter.drawRoundedRect(rect, 7, 7)
        painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        painter.drawText(QRectF(rect.left(), rect.top() + 8, rect.width(), 12), Qt.AlignmentFlag.AlignCenter, title)

        value_rect = QRectF(rect.left() + 6, rect.top() + 34, rect.width() - 12, 28)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(14, 30, 48, 235))
        painter.drawRoundedRect(value_rect, 4, 4)

        painter.setPen(QPen(color, 1.0))
        painter.setFont(QFont("Consolas", 13, QFont.Weight.Bold))
        painter.drawText(value_rect, Qt.AlignmentFlag.AlignCenter, value)
        painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        painter.drawText(QRectF(rect.left(), rect.top() + 74, rect.width(), 14), Qt.AlignmentFlag.AlignCenter, unit)

    def _draw_center_symbol(self, painter, center_x, center_y):
        painter.setPen(QPen(QColor(247, 241, 115), 2.2))
        painter.drawLine(int(center_x - 26), int(center_y), int(center_x - 8), int(center_y))
        painter.drawLine(int(center_x + 8), int(center_y), int(center_x + 26), int(center_y))
        painter.drawLine(int(center_x - 8), int(center_y), int(center_x + 8), int(center_y))
        painter.drawLine(int(center_x), int(center_y - 8), int(center_x), int(center_y + 18))
        painter.setPen(QPen(QColor(104, 201, 255, 100), 1.0, Qt.PenStyle.DashLine))
        painter.drawLine(int(center_x - 42), int(center_y), int(center_x + 42), int(center_y))

    def _draw_bottom_strip(self, painter, rect):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(4, 14, 25, 215))
        painter.drawRoundedRect(rect, 6, 6)

        items = [
            ("ROLL", f"{self.roll:.1f}°"),
            ("PITCH", f"{self.pitch:.1f}°"),
            ("HDG", f"{self.yaw % 360:.1f}°"),
            ("BAT", f"{self.battery}%"),
        ]
        section_width = rect.width() / 5
        painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        painter.setPen(QPen(QColor(185, 255, 185), 1.0))
        for index, (label, value) in enumerate(items):
            section = QRectF(rect.left() + section_width * index, rect.top(), section_width, rect.height())
            painter.drawText(section, Qt.AlignmentFlag.AlignCenter, f"{label} {value}")

        mode_rect = QRectF(rect.right() - section_width, rect.top(), section_width, rect.height())
        painter.setPen(QPen(QColor(255, 208, 120), 1.0))
        painter.drawText(mode_rect, Qt.AlignmentFlag.AlignCenter, self.mode)

