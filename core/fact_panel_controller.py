from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Set

from PyQt6.QtCore import QObject, pyqtSignal

from .fact_system import FactSystem
from .firmware_plugin import AutoPilotPlugin, GenericAutoPilotPlugin
from .settings_manager import SettingsManager


class FactPanelController(QObject):
    groups_changed = pyqtSignal(list)
    favorites_changed = pyqtSignal(list)

    def __init__(
        self,
        fact_system: Optional[FactSystem] = None,
        autopilot_plugin: Optional[AutoPilotPlugin] = None,
        settings_manager: Optional[SettingsManager] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._fact_system = fact_system or FactSystem()
        self._autopilot_plugin = autopilot_plugin or GenericAutoPilotPlugin()
        self._settings_manager = settings_manager
        self._favorite_names: Set[str] = set(
            self._settings_manager.fact_favorites() if self._settings_manager is not None else []
        )

    def set_fact_system(self, fact_system: FactSystem):
        self._fact_system = fact_system or FactSystem()

    def set_autopilot_plugin(self, autopilot_plugin: Optional[AutoPilotPlugin]):
        self._autopilot_plugin = autopilot_plugin or GenericAutoPilotPlugin()

    def favorites(self) -> Set[str]:
        return set(self._favorite_names)

    def toggle_favorite(self, name: str):
        key = str(name or "").strip().upper()
        if not key:
            return
        if key in self._favorite_names:
            self._favorite_names.remove(key)
        else:
            self._favorite_names.add(key)
        if self._settings_manager is not None:
            self._settings_manager.set_fact_favorites(sorted(self._favorite_names))
        self.favorites_changed.emit(sorted(self._favorite_names))

    def available_groups(self, names: Iterable[str]) -> List[str]:
        groups = ["全部", "收藏"]
        groups.extend(self._autopilot_plugin.available_groups(names))
        # preserve order while deduplicating
        result = []
        seen = set()
        for item in groups:
            key = str(item)
            if key in seen:
                continue
            seen.add(key)
            result.append(key)
        self.groups_changed.emit(result)
        return result

    def build_rows(
        self,
        params: Dict[str, float],
        favorites: Optional[Iterable[str]] = None,
        search_text: str = "",
        group_filter: str = "全部",
    ) -> List[Dict]:
        favorite_keys = {str(name or "").strip().upper() for name in (favorites or self._favorite_names)}
        keyword = str(search_text or "").strip().lower()
        selected_group = str(group_filter or "全部").strip().upper() or "全部"

        rows: List[Dict] = []
        for name, value in sorted((params or {}).items()):
            fact = self._fact_system.get_fact(name) if self._fact_system is not None else None
            metadata = getattr(fact, "metadata", None)
            description = str(getattr(metadata, "short_description", "") or "")
            units = str(getattr(metadata, "units", "") or "")
            group_key = self._autopilot_plugin.parameter_group_for_name(name)
            if keyword and keyword not in str(name).lower() and keyword not in description.lower():
                continue
            if selected_group == "收藏" and str(name).strip().upper() not in favorite_keys:
                continue
            if selected_group not in {"全部", "收藏"} and group_key != selected_group:
                continue
            rows.append(
                {
                    "name": str(name),
                    "value": float(value),
                    "units": units,
                    "description": description,
                    "group": group_key,
                    "group_label": self._autopilot_plugin.parameter_group_label(group_key),
                    "favorite": str(name).strip().upper() in favorite_keys,
                }
            )

        rows.sort(
            key=lambda row: (
                0 if row["favorite"] else 1,
                row["group"],
                row["name"],
            )
        )
        return rows

    @staticmethod
    def status_text(total: int, modified: int, group_name: str = "全部") -> str:
        return f"分组: {group_name} | 共 {int(total)} 项，修改 {int(modified)} 项"
