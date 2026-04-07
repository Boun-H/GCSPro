from PyQt6.QtCore import QDateTime, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.fact_panel_controller import FactPanelController
from core.firmware_plugin import ArduPilotAutoPilotPlugin


class ParamPanel(QFrame):
    close_clicked = pyqtSignal()
    save_requested = pyqtSignal()
    load_requested = pyqtSignal()
    refresh_requested = pyqtSignal()
    export_requested = pyqtSignal()
    vehicle_tab_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._updating_table = False
        self._params = {}
        self._baseline_params = {}
        self._dirty_names = set()
        self._active_vehicle_id = ""
        self._vehicle_contexts = {}
        self._tab_vehicle_ids = []
        self._fact_system = None
        self._fact_controller = FactPanelController(autopilot_plugin=ArduPilotAutoPilotPlugin())
        self.setStyleSheet(
            "QFrame { background:#121d2d; border:1px solid #2a4362; border-radius:10px; }"
            "QTableWidget { background:#0f1926; color:#d9e6f8; border:1px solid #27415f; border-radius:8px; }"
            "QHeaderView::section { background:#1c2b40; color:#dfe9f6; border:none; padding:6px; }"
            "QPushButton { background:#1e3a5a; color:#d9e6f8; border:1px solid #35506b; border-radius:8px; padding:6px 10px; }"
            "QPushButton:hover { background:#264b73; }"
            "QLabel { color:#d9e6f8; }"
            "QLineEdit, QComboBox { background:#0f1926; color:#d9e6f8; border:1px solid #27415f; border-radius:7px; padding:5px 8px; }"
            "QTabBar::tab { background:#162233; color:#d9e6f8; padding:5px 12px; margin-right:2px; border-top-left-radius:6px; border-top-right-radius:6px; }"
            "QTabBar::tab:selected { background:#1f6fb2; }"
        )
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 10, 10, 6)
        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(2)
        title = QLabel("参数面板")
        title.setStyleSheet("font-size:16px; font-weight:700; color:#eef5ff;")
        subtitle = QLabel("QGC 风格分组 / 收藏 / 搜索")
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

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 0, 10, 10)
        layout.setSpacing(8)

        self.vehicle_tabs = QTabBar()
        self.vehicle_tabs.setDocumentMode(True)
        self.vehicle_tabs.setDrawBase(False)
        self.vehicle_tabs.setExpanding(False)
        self.vehicle_tabs.hide()
        layout.addWidget(self.vehicle_tabs)

        self.context_label = QLabel("当前载具参数页: 全局")
        self.context_label.setStyleSheet("color:#9fb4cf;")
        layout.addWidget(self.context_label)

        toolbar = QHBoxLayout()
        self.group_combo = QComboBox()
        self.group_combo.addItems(["全部", "收藏"])
        self.group_combo.setMinimumWidth(110)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("筛选参数名，例如 EKF_ / PSC_ / WPNAV")
        self.btn_favorite = QPushButton("切换收藏")
        self.btn_compare = QPushButton("变更对比")
        self.btn_rollback = QPushButton("一键回滚")
        self.status_label = QLabel("未读取")
        self.status_label.setStyleSheet("color:#9fb4cf;")
        toolbar.addWidget(self.group_combo)
        toolbar.addWidget(self.search_edit, 1)
        toolbar.addWidget(self.btn_favorite)
        toolbar.addWidget(self.btn_compare)
        toolbar.addWidget(self.btn_rollback)
        toolbar.addWidget(self.status_label)
        layout.addLayout(toolbar)

        self.diff_summary = QLabel("参数变更对比：暂无改动，可直接导出当前快照。")
        self.diff_summary.setWordWrap(True)
        self.diff_summary.setStyleSheet("color:#c7d9ef; background:#142133; border-radius:6px; padding:6px 8px;")
        layout.addWidget(self.diff_summary)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["参数名", "数值", "单位", "说明"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 220)
        self.table.setColumnWidth(1, 120)
        self.table.horizontalHeader().setMinimumSectionSize(100)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumWidth(680)
        self.table.setMinimumHeight(600)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        self.btn_refresh = QPushButton("读取飞控")
        self.btn_save = QPushButton("写入飞控")
        self.btn_load = QPushButton("导入JSON")
        self.btn_export = QPushButton("导出快照")
        layout.addWidget(self.table)
        button_row = QHBoxLayout()
        button_row.setSpacing(6)
        button_row.addWidget(self.btn_refresh)
        button_row.addWidget(self.btn_save)
        button_row.addWidget(self.btn_load)
        button_row.addWidget(self.btn_export)
        layout.addLayout(button_row)
        main_layout.addLayout(layout)

        self.close_btn.clicked.connect(self.close_clicked.emit)
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)
        self.btn_save.clicked.connect(self.save_requested.emit)
        self.btn_load.clicked.connect(self.load_requested.emit)
        self.btn_export.clicked.connect(self.export_requested.emit)
        self.btn_favorite.clicked.connect(self.toggle_selected_favorite)
        self.btn_compare.clicked.connect(self.show_diff_overview)
        self.btn_rollback.clicked.connect(self.rollback_changes)
        self.group_combo.currentTextChanged.connect(self._apply_filter)
        self.search_edit.textChanged.connect(self._apply_filter)
        self.vehicle_tabs.currentChanged.connect(self._on_vehicle_tab_changed)
        self.table.itemChanged.connect(self._on_item_changed)

    def set_fact_system(self, fact_system):
        self._fact_system = fact_system
        self._fact_controller.set_fact_system(fact_system)

    def set_fact_controller(self, controller: FactPanelController):
        self._fact_controller = controller or self._fact_controller
        self._fact_controller.set_fact_system(self._fact_system)

    def _blank_vehicle_context(self) -> dict:
        return {
            "params": {},
            "baseline_params": {},
            "dirty_names": set(),
            "status": "未读取",
        }

    def _store_current_vehicle_context(self):
        vehicle_id = str(self._active_vehicle_id or "").strip()
        if not vehicle_id:
            return
        ctx = self._vehicle_contexts.setdefault(vehicle_id, self._blank_vehicle_context())
        ctx["params"] = dict(self._params)
        ctx["baseline_params"] = dict(self._baseline_params)
        ctx["dirty_names"] = set(self._dirty_names)
        ctx["status"] = str(self.status_label.text() or "未读取")

    def set_vehicle_tabs(self, vehicles: list, active_vehicle_id: str = ""):
        self._store_current_vehicle_context()
        tab_ids = []
        self.vehicle_tabs.blockSignals(True)
        while self.vehicle_tabs.count() > 0:
            self.vehicle_tabs.removeTab(0)
        for vehicle in vehicles or []:
            if isinstance(vehicle, dict):
                vehicle_id = str(vehicle.get("vehicle_id", "") or "").strip()
            else:
                vehicle_id = str(vehicle or "").strip()
            if not vehicle_id:
                continue
            tab_ids.append(vehicle_id)
            self.vehicle_tabs.addTab(vehicle_id)
            self._vehicle_contexts.setdefault(vehicle_id, self._blank_vehicle_context())
        self._tab_vehicle_ids = tab_ids
        self.vehicle_tabs.setVisible(bool(tab_ids))
        self.vehicle_tabs.blockSignals(False)

        target_id = str(active_vehicle_id or self._active_vehicle_id or "").strip()
        if not target_id and tab_ids:
            target_id = tab_ids[0]
        if target_id:
            self.activate_vehicle_tab(target_id, emit_signal=False)
        else:
            self._active_vehicle_id = ""
            self.context_label.setText("当前载具参数页: 全局")

    def activate_vehicle_tab(self, vehicle_id: str, emit_signal: bool = False):
        target_id = str(vehicle_id or "").strip()
        if not target_id:
            return
        same_target = target_id == self._active_vehicle_id
        if not same_target:
            self._store_current_vehicle_context()
        ctx = self._vehicle_contexts.setdefault(target_id, self._blank_vehicle_context())
        self._active_vehicle_id = target_id
        if target_id in self._tab_vehicle_ids:
            index = self._tab_vehicle_ids.index(target_id)
            self.vehicle_tabs.blockSignals(True)
            self.vehicle_tabs.setCurrentIndex(index)
            self.vehicle_tabs.blockSignals(False)
        if not same_target:
            self._params = {str(k): float(v) for k, v in (ctx.get("params") or {}).items()}
            self._baseline_params = {str(k): float(v) for k, v in (ctx.get("baseline_params") or {}).items()}
            self._dirty_names = set(ctx.get("dirty_names") or set())
            self._render_current_params()
            self.status_label.setText(str(ctx.get("status", "未读取") or "未读取"))
        self.context_label.setText(f"当前载具参数页: {target_id}")
        if emit_signal:
            self.vehicle_tab_changed.emit(target_id)

    def _on_vehicle_tab_changed(self, index: int):
        if not (0 <= index < len(self._tab_vehicle_ids)):
            return
        self.activate_vehicle_tab(self._tab_vehicle_ids[index], emit_signal=True)

    def _raw_param_name(self, item: QTableWidgetItem | None) -> str:
        if item is None:
            return ""
        return str(item.data(Qt.ItemDataRole.UserRole) or item.text().replace("★ ", "").strip())

    def _set_group_choices(self):
        groups = self._fact_controller.available_groups(self._params.keys())
        current = self.group_combo.currentText().strip() or "全部"
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        self.group_combo.addItems(groups)
        index = self.group_combo.findText(current)
        self.group_combo.setCurrentIndex(index if index >= 0 else 0)
        self.group_combo.blockSignals(False)

    def _update_status_summary(self):
        self.status_label.setText(
            self._fact_controller.status_text(len(self._params), len(self._dirty_names), self.group_combo.currentText())
        )
        self._refresh_diff_summary()

    def parameter_diff_rows(self, vehicle_id: str | None = None) -> list[dict]:
        target_id = str(vehicle_id or self._active_vehicle_id or "").strip()
        if target_id and target_id != self._active_vehicle_id:
            ctx = self._vehicle_contexts.get(target_id, self._blank_vehicle_context())
            params = dict(ctx.get("params") or {})
            baseline = dict(ctx.get("baseline_params") or {})
            dirty_names = set(ctx.get("dirty_names") or set())
        else:
            params = dict(self._params)
            baseline = dict(self._baseline_params)
            dirty_names = set(self._dirty_names)

        diffs = []
        for name in sorted(dirty_names):
            current_value = float(params.get(name, 0.0))
            baseline_value = float(baseline.get(name, current_value))
            diffs.append(
                {
                    "name": name,
                    "before": baseline_value,
                    "after": current_value,
                    "delta": current_value - baseline_value,
                }
            )
        return diffs

    def diff_summary_text(self, vehicle_id: str | None = None) -> str:
        diffs = self.parameter_diff_rows(vehicle_id=vehicle_id)
        if not diffs:
            return "参数变更对比：暂无改动，可直接导出当前快照。"
        preview = "； ".join(
            f"{item['name']}: {item['before']:.3f} → {item['after']:.3f}" for item in diffs[:3]
        )
        if len(diffs) > 3:
            preview += f"； 其余 {len(diffs) - 3} 项"
        return f"参数变更对比：{len(diffs)} 项待写入 | {preview}"

    def _refresh_diff_summary(self):
        if hasattr(self, "diff_summary") and self.diff_summary is not None:
            self.diff_summary.setText(self.diff_summary_text())

    def show_diff_overview(self, _checked: bool = False):
        self.status_label.setText(self.diff_summary_text())
        self._refresh_diff_summary()

    def rollback_changes(self, vehicle_id: str | None = None) -> dict:
        target_id = str(vehicle_id or self._active_vehicle_id or "").strip()
        if target_id and target_id != self._active_vehicle_id:
            ctx = self._vehicle_contexts.setdefault(target_id, self._blank_vehicle_context())
            params = dict(ctx.get("params") or {})
            baseline = dict(ctx.get("baseline_params") or {})
            dirty_names = set(ctx.get("dirty_names") or set())
            reverted = {name: float(baseline.get(name, params.get(name, 0.0))) for name in dirty_names}
            params.update(reverted)
            ctx["params"] = params
            ctx["dirty_names"] = set()
            ctx["status"] = "已回滚未保存改动"
            self._refresh_diff_summary()
            return reverted

        reverted = {name: float(self._baseline_params.get(name, self._params.get(name, 0.0))) for name in self._dirty_names}
        if not reverted:
            self.status_label.setText("没有可回滚的改动")
            self._refresh_diff_summary()
            return {}
        self._params.update(reverted)
        self._dirty_names.clear()
        self._render_current_params()
        self.status_label.setText("已回滚未保存改动")
        self._store_current_vehicle_context()
        self._refresh_diff_summary()
        return reverted

    def snapshot_payload(self, vehicle_id: str | None = None) -> dict:
        target_id = str(vehicle_id or self._active_vehicle_id or "").strip()
        if target_id and target_id != self._active_vehicle_id:
            ctx = self._vehicle_contexts.get(target_id, self._blank_vehicle_context())
            params = {str(k): float(v) for k, v in (ctx.get("params") or {}).items()}
            baseline = {str(k): float(v) for k, v in (ctx.get("baseline_params") or {}).items()}
        else:
            params = {str(k): float(v) for k, v in self._params.items()}
            baseline = {str(k): float(v) for k, v in self._baseline_params.items()}
        diff_rows = self.parameter_diff_rows(vehicle_id=target_id or None)
        return {
            "vehicle_id": target_id or "GLOBAL",
            "timestamp": QDateTime.currentDateTime().toString(Qt.DateFormat.ISODate),
            "total": len(params),
            "values": params,
            "baseline": baseline,
            "modified": {item["name"]: {"before": item["before"], "after": item["after"], "delta": item["delta"]} for item in diff_rows},
            "diff_rows": diff_rows,
        }

    def _render_current_params(self):
        self._set_group_choices()
        rows = self._fact_controller.build_rows(self._params, group_filter="全部")
        self._updating_table = True
        self.table.setRowCount(0)
        for row_data in rows:
            name = row_data["name"]
            row = self.table.rowCount()
            self.table.insertRow(row)
            display_name = f"★ {name}" if row_data.get("favorite") else name
            name_item = QTableWidgetItem(display_name)
            name_item.setData(Qt.ItemDataRole.UserRole, name)
            name_item.setData(Qt.ItemDataRole.UserRole + 1, row_data.get("group", "MISC"))
            name_item.setData(Qt.ItemDataRole.UserRole + 2, bool(row_data.get("favorite", False)))
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            fact = self._fact_system.get_fact(name) if self._fact_system is not None and hasattr(self._fact_system, "get_fact") else None
            metadata = getattr(fact, "metadata", None)
            decimals = int(getattr(metadata, "decimal_places", 6) or 6)
            value_item = QTableWidgetItem(f"{self._params[name]:.{decimals}f}")
            if name in self._dirty_names:
                value_item.setBackground(Qt.GlobalColor.darkBlue)
                value_item.setForeground(Qt.GlobalColor.cyan)
            unit_item = QTableWidgetItem(str(getattr(metadata, "units", "") or ""))
            desc_item = QTableWidgetItem(str(getattr(metadata, "short_description", "") or row_data.get("group_label", "") or ""))
            for meta_item in (unit_item, desc_item):
                meta_item.setFlags(meta_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if metadata is not None:
                range_text = [f"分组={row_data.get('group_label', row_data.get('group', 'MISC'))}"]
                if getattr(metadata, "min_value", None) is not None:
                    range_text.append(f"min={metadata.min_value}")
                if getattr(metadata, "max_value", None) is not None:
                    range_text.append(f"max={metadata.max_value}")
                tooltip = " | ".join(range_text)
                name_item.setToolTip(tooltip)
                value_item.setToolTip(tooltip)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, value_item)
            self.table.setItem(row, 2, unit_item)
            self.table.setItem(row, 3, desc_item)
        self._updating_table = False
        self._apply_filter(self.search_edit.text())
        self._update_status_summary()

    def set_parameters(self, params: dict, vehicle_id: str | None = None):
        normalized = {str(k): float(v) for k, v in (params or {}).items()}
        target_id = str(vehicle_id or self._active_vehicle_id or "").strip()
        if target_id:
            ctx = self._vehicle_contexts.setdefault(target_id, self._blank_vehicle_context())
            ctx["params"] = dict(normalized)
            ctx["baseline_params"] = dict(normalized)
            ctx["dirty_names"] = set()
            if target_id != self._active_vehicle_id and self._active_vehicle_id:
                return
            self._active_vehicle_id = target_id
        self._params = dict(normalized)
        self._baseline_params = dict(normalized)
        self._dirty_names.clear()
        self._render_current_params()
        if self._active_vehicle_id:
            self.context_label.setText(f"当前载具参数页: {self._active_vehicle_id}")

    def modified_parameters(self, vehicle_id: str | None = None) -> dict:
        target_id = str(vehicle_id or self._active_vehicle_id or "").strip()
        if target_id and target_id != self._active_vehicle_id:
            ctx = self._vehicle_contexts.get(target_id, self._blank_vehicle_context())
            params = dict(ctx.get("params") or {})
            return {name: float(params[name]) for name in (ctx.get("dirty_names") or set()) if name in params}
        return {name: float(self._params[name]) for name in self._dirty_names if name in self._params}

    def apply_param_values(self, values: dict, vehicle_id: str | None = None):
        if not values:
            return
        target_id = str(vehicle_id or self._active_vehicle_id or "").strip()
        if target_id and target_id != self._active_vehicle_id:
            ctx = self._vehicle_contexts.setdefault(target_id, self._blank_vehicle_context())
            params = dict(ctx.get("params") or {})
            baseline = dict(ctx.get("baseline_params") or {})
            for name, value in values.items():
                params[str(name)] = float(value)
                baseline[str(name)] = float(value)
            ctx["params"] = params
            ctx["baseline_params"] = baseline
            ctx["dirty_names"] = set(ctx.get("dirty_names") or set()).difference(set(values.keys()))
            return
        self._updating_table = True
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            if name_item is None:
                continue
            name = self._raw_param_name(name_item)
            if name not in values:
                continue
            value_item = self.table.item(row, 1)
            if value_item is not None:
                self._params[name] = float(values[name])
                self._baseline_params[name] = float(values[name])
                value_item.setText(f"{float(values[name]):.6f}")
                value_item.setBackground(Qt.GlobalColor.transparent)
                value_item.setForeground(Qt.GlobalColor.white)
        self._updating_table = False
        self._dirty_names.difference_update(set(values.keys()))
        self._store_current_vehicle_context()
        self._update_status_summary()

    def mark_status(self, text: str, vehicle_id: str | None = None):
        target_id = str(vehicle_id or self._active_vehicle_id or "").strip()
        if target_id and target_id != self._active_vehicle_id:
            ctx = self._vehicle_contexts.setdefault(target_id, self._blank_vehicle_context())
            ctx["status"] = str(text or "")
            return
        self.status_label.setText(text)
        self._store_current_vehicle_context()

    def toggle_selected_favorite(self):
        current_row = self.table.currentRow()
        if current_row < 0:
            self.status_label.setText("请选择一项参数后再切换收藏")
            return
        name_item = self.table.item(current_row, 0)
        name = self._raw_param_name(name_item)
        if not name:
            return
        self._fact_controller.toggle_favorite(name)
        is_favorite = name.upper() in self._fact_controller.favorites()
        if name_item is not None:
            name_item.setData(Qt.ItemDataRole.UserRole + 2, is_favorite)
            name_item.setText(f"★ {name}" if is_favorite else name)
        self._apply_filter(self.search_edit.text())

    def _on_item_changed(self, item):
        if self._updating_table or item.column() != 1:
            return
        name_item = self.table.item(item.row(), 0)
        if name_item is None:
            return
        name = self._raw_param_name(name_item)
        try:
            new_value = float(item.text().strip())
        except ValueError:
            item.setBackground(Qt.GlobalColor.darkRed)
            self.status_label.setText(f"参数 {name} 输入无效")
            return

        fact = self._fact_system.get_fact(name) if self._fact_system is not None and hasattr(self._fact_system, "get_fact") else None
        metadata = getattr(fact, "metadata", None)
        min_value = getattr(metadata, "min_value", None)
        max_value = getattr(metadata, "max_value", None)
        if min_value is not None and new_value < float(min_value):
            item.setBackground(Qt.GlobalColor.darkRed)
            self.status_label.setText(f"参数 {name} 低于最小值 {min_value}")
            return
        if max_value is not None and new_value > float(max_value):
            item.setBackground(Qt.GlobalColor.darkRed)
            self.status_label.setText(f"参数 {name} 高于最大值 {max_value}")
            return

        baseline_value = float(self._baseline_params.get(name, new_value))
        self._params[name] = new_value
        if abs(new_value - baseline_value) <= 1e-9:
            self._dirty_names.discard(name)
            item.setBackground(Qt.GlobalColor.transparent)
            item.setForeground(Qt.GlobalColor.white)
        else:
            self._dirty_names.add(name)
            item.setBackground(Qt.GlobalColor.darkBlue)
            item.setForeground(Qt.GlobalColor.cyan)
        self._store_current_vehicle_context()
        self._update_status_summary()

    def _apply_filter(self, text: str):
        keyword = (text or "").strip().lower()
        group_name = (self.group_combo.currentText() or "全部").strip()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            desc_item = self.table.item(row, 3)
            if item is None:
                continue
            haystack = self._raw_param_name(item).lower()
            if desc_item is not None:
                haystack += " " + desc_item.text().lower()
            group_key = str(item.data(Qt.ItemDataRole.UserRole + 1) or "MISC")
            is_favorite = bool(item.data(Qt.ItemDataRole.UserRole + 2))
            visible = (keyword in haystack) if keyword else True
            if group_name == "收藏":
                visible = visible and is_favorite
            elif group_name != "全部":
                visible = visible and group_key == group_name
            self.table.setRowHidden(row, not visible)
        self._update_status_summary()