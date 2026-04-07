from typing import Callable, Dict, List, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import QComboBox, QHeaderView, QTableWidget, QTableWidgetItem

from pymavlink import mavutil

from core.mission import FRAME_LABELS


class WaypointTableWidget(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(7)
        self.setHorizontalHeaderLabels(["序号", "动作", "纬度", "经度", "高度(m)", "速度(m/s)", "停留(s)"])
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.setColumnWidth(1, 147)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.EditKeyPressed)
        self.setShowGrid(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(28)
        self.setMinimumHeight(360)
        self.setStyleSheet(
            """
            QTableWidget {
                background: #0f1926;
                alternate-background-color: #142133;
                border: 1px solid #27415f;
                border-radius: 8px;
                gridline-color: transparent;
                selection-background-color: #33588f;
                selection-color: #f3f8ff;
                color: #d9e6f8;
            }
            QHeaderView::section {
                background-color: #1c2b40;
                color: #dfe9f6;
                padding: 4px 6px;
                border: none;
                border-bottom: 1px solid #2f4f71;
                font-weight: 700;
            }
            QTableWidget::item {
                padding: 2px 4px;
            }
            """
        )
        self._mav_cmd_options: List[Tuple[int, str]] = self._build_mav_cmd_options()

    @staticmethod
    def _build_mav_cmd_options() -> List[Tuple[int, str]]:
        options: List[Tuple[int, str]] = []
        try:
            cmd_enum = mavutil.mavlink.enums.get("MAV_CMD", {})
            for value, entry in cmd_enum.items():
                name = str(getattr(entry, "name", "") or "")
                if not name:
                    continue
                options.append((int(value), name))
        except Exception:
            options = []

        if not options:
            options = [(16, "MAV_CMD_NAV_WAYPOINT")]

        category_order = {"NAV": 0, "DO": 1, "CONDITION": 2, "OTHER": 3}

        def category_of(name: str) -> str:
            if name.startswith("MAV_CMD_NAV_"):
                return "NAV"
            if name.startswith("MAV_CMD_DO_"):
                return "DO"
            if name.startswith("MAV_CMD_CONDITION_"):
                return "CONDITION"
            return "OTHER"

        options.sort(key=lambda item: (category_order.get(category_of(item[1]), 99), item[0]))
        return options

    def render_rows(self, waypoints: List[Dict], action_changed_callback: Callable[[int, int], None]):
        for row in range(self.rowCount()):
            widget = self.cellWidget(row, 1)
            if widget:
                self.removeCellWidget(row, 1)
                widget.deleteLater()

        self.setRowCount(0)
        self.setRowCount(len(waypoints))
        for row, waypoint in enumerate(waypoints):
            self._populate_row(row, waypoint, action_changed_callback)

    def _populate_row(self, row: int, waypoint: Dict, action_changed_callback: Callable[[int, int], None]):
        # H点只读行（seq=0，is_home=True）
        if waypoint.get("is_home", False):
            _HOME_CLR = QColor("#6a9fcb")
            _RO_FLAGS = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            h_seq = QTableWidgetItem("H")
            h_seq.setFlags(_RO_FLAGS)
            h_seq.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            h_seq.setForeground(QBrush(_HOME_CLR))
            self.setItem(row, 0, h_seq)

            h_action = QTableWidgetItem(str(int(waypoint.get("command", 16) or 16)))
            h_action.setFlags(_RO_FLAGS)
            h_action.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            h_action.setForeground(QBrush(_HOME_CLR))
            self.setItem(row, 1, h_action)

            for col, fmt, val in [
                (2, "{:.7f}", float(waypoint.get("lat", 0.0))),
                (3, "{:.7f}", float(waypoint.get("lon", 0.0))),
                (4, "{}",    int(round(float(waypoint.get("alt", 0.0))))),
                (5, "{:.1f}", float(waypoint.get("speed", 0.0) or 0.0)),
                (6, "{:.1f}", float(waypoint.get("hold_time", waypoint.get("holdTime", 0.0)) or 0.0)),
            ]:
                cell = QTableWidgetItem(fmt.format(val))
                cell.setFlags(_RO_FLAGS)
                cell.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                cell.setForeground(QBrush(_HOME_CLR))
                self.setItem(row, col, cell)
            return

        # 普通任务行：序号取 waypoint["seq"] (1-based)
        seq_item = QTableWidgetItem(str(waypoint.get("seq", row + 1)))
        seq_item.setFlags(seq_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        seq_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setItem(row, 0, seq_item)

        action_combo = QComboBox()
        action_combo.setMinimumHeight(28)
        action_combo.setMaximumWidth(160)
        action_combo.setStyleSheet("padding: 2px 6px; background: #0f1926; color: #d9e6f8; border-radius: 4px;")

        category_titles = {
            "NAV": "── NAV ──",
            "DO": "── DO ──",
            "CONDITION": "── CONDITION ──",
            "OTHER": "── OTHER ──",
        }

        def category_of(name: str) -> str:
            if name.startswith("MAV_CMD_NAV_"):
                return "NAV"
            if name.startswith("MAV_CMD_DO_"):
                return "DO"
            if name.startswith("MAV_CMD_CONDITION_"):
                return "CONDITION"
            return "OTHER"

        def short_name(name: str, category: str) -> str:
            prefix = f"MAV_CMD_{category}_"
            if name.startswith(prefix):
                return name[len(prefix):]
            return name.replace("MAV_CMD_", "")

        combo_model = action_combo.model()
        current_category = ""
        for command, name in self._mav_cmd_options:
            category = category_of(name)
            if category != current_category:
                current_category = category
                action_combo.addItem(category_titles.get(category, "-- OTHER --"), None)
                header_item = combo_model.item(action_combo.count() - 1)
                if header_item is not None:
                    header_item.setEnabled(False)
                    header_item.setForeground(QBrush(QColor("#ffc653")))
                    header_item.setBackground(QBrush(QColor("#1a3050")))
                    _hdr_font = QFont()
                    _hdr_font.setBold(True)
                    header_item.setFont(_hdr_font)
            action_combo.addItem(f"{command} {short_name(name, category)}", command)
            action_combo.setItemData(action_combo.count() - 1, name, Qt.ItemDataRole.ToolTipRole)

        current_command = int(waypoint.get("command", 16) or 16)
        current_index = action_combo.findData(current_command)
        action_combo.setCurrentIndex(current_index if current_index >= 0 else 0)

        def on_action_index_changed(_idx: int, row_value=row, combo=action_combo):
            data = combo.currentData()
            if data is None:
                return
            action_changed_callback(row_value, int(data))

        action_combo.currentIndexChanged[int].connect(on_action_index_changed)
        self.setCellWidget(row, 1, action_combo)

        lat_item = QTableWidgetItem(f"{waypoint['lat']:.7f}")
        lat_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setItem(row, 2, lat_item)

        lon_item = QTableWidgetItem(f"{waypoint['lon']:.7f}")
        lon_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setItem(row, 3, lon_item)

        alt_item = QTableWidgetItem(f"{int(round(float(waypoint['alt'])))}")
        raw_alt = float(waypoint.get("source_alt", waypoint["alt"]))
        source_frame = int(waypoint.get("source_frame", waypoint.get("frame", 6)))
        frame_label = FRAME_LABELS.get(source_frame, f"FRAME_{source_frame}")
        alt_item.setToolTip(f"高度基准: {frame_label}\n载入高度: {waypoint['alt']:.2f} m\n原始高度: {raw_alt:.2f} m")
        alt_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setItem(row, 4, alt_item)

        speed_item = QTableWidgetItem(f"{float(waypoint.get('speed', 0.0) or 0.0):.1f}")
        speed_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setItem(row, 5, speed_item)

        hold_time = float(waypoint.get("hold_time", waypoint.get("holdTime", 0.0)) or 0.0)
        hold_item = QTableWidgetItem(f"{hold_time:.1f}")
        hold_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setItem(row, 6, hold_item)