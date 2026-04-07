from copy import deepcopy
from typing import Dict, List

from PyQt6.QtCore import QObject, pyqtSignal

from .protocol import normalize_waypoint, round_route_alt, validate_waypoint


class WaypointModel(QObject):
    waypoints_changed = pyqtSignal(list)
    changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._waypoints: List[Dict] = []
        self._undo_stack: List[List[Dict]] = []
        self._redo_stack: List[List[Dict]] = []
        self._max_undo = 50

    def _push_undo_snapshot(self):
        self._undo_stack.append(deepcopy(self._waypoints))
        if len(self._undo_stack) > self._max_undo:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def waypoints(self) -> List[Dict]:
        return deepcopy(self._waypoints)

    def set_waypoints(self, waypoints: List[Dict], track_undo: bool = False):
        if track_undo:
            self._push_undo_snapshot()
        self._waypoints = [normalize_waypoint(wp) for wp in waypoints if validate_waypoint(wp)]
        self._emit_changed()

    def clear(self, track_undo: bool = True):
        if track_undo:
            self._push_undo_snapshot()
        self._waypoints.clear()
        self._emit_changed()

    def set_uniform_height(self, alt: float, track_undo: bool = True):
        if not self._waypoints:
            return
        if track_undo:
            self._push_undo_snapshot()
        valid_alt = round_route_alt(alt)
        for wp in self._waypoints:
            wp["alt"] = valid_alt
        self._emit_changed()

    def delete_rows(self, rows: List[int], track_undo: bool = True):
        if not self._waypoints or not rows:
            return
        if track_undo:
            self._push_undo_snapshot()
        for row in sorted(set(rows), reverse=True):
            if 0 <= row < len(self._waypoints):
                del self._waypoints[row]
        self._emit_changed()

    def undo(self):
        if self._undo_stack:
            self._redo_stack.append(deepcopy(self._waypoints))
            if len(self._redo_stack) > self._max_undo:
                self._redo_stack.pop(0)
            self._waypoints = self._undo_stack.pop()
            self._emit_changed()

    def redo(self):
        if self._redo_stack:
            self._undo_stack.append(deepcopy(self._waypoints))
            if len(self._undo_stack) > self._max_undo:
                self._undo_stack.pop(0)
            self._waypoints = self._redo_stack.pop()
            self._emit_changed()

    def add_waypoint(self, waypoint: Dict, track_undo: bool = True):
        if track_undo:
            self._push_undo_snapshot()
        self._waypoints.append(normalize_waypoint(waypoint))
        self._emit_changed()

    def insert_waypoint(self, index: int, waypoint: Dict, track_undo: bool = True):
        if track_undo:
            self._push_undo_snapshot()
        self._waypoints.insert(index, normalize_waypoint(waypoint))
        self._emit_changed()

    def remove_waypoint(self, waypoint_id: str, track_undo: bool = True):
        if track_undo:
            self._push_undo_snapshot()
        self._waypoints = [wp for wp in self._waypoints if str(wp.get("id", "")) != str(waypoint_id)]
        self._emit_changed()

    def update_waypoint(self, waypoint_id: str, patch: Dict, track_undo: bool = True) -> bool:
        found = False
        if track_undo:
            self._push_undo_snapshot()
        updated = []
        for wp in self._waypoints:
            if str(wp.get("id", "")) == str(waypoint_id):
                found = True
                updated.append(normalize_waypoint({**wp, **dict(patch or {})}))
            else:
                updated.append(wp)
        if found:
            self._waypoints = updated
            self._emit_changed()
        return found

    def reorder_waypoints(self, from_index: int, to_index: int, track_undo: bool = True) -> bool:
        if not (0 <= from_index < len(self._waypoints) and 0 <= to_index < len(self._waypoints)):
            return False
        if from_index == to_index:
            return True
        if track_undo:
            self._push_undo_snapshot()
        moving = self._waypoints.pop(from_index)
        self._waypoints.insert(to_index, moving)
        self._emit_changed()
        return True

    def patch_position(self, index: int, lat: float, lon: float) -> bool:
        if not (0 <= index < len(self._waypoints)):
            return False
        self._waypoints[index]["lat"] = lat
        self._waypoints[index]["lon"] = lon
        return True

    def update_cell(self, row: int, field: str, value) -> bool:
        if not (0 <= row < len(self._waypoints)):
            return False
        if field not in {"lat", "lon", "alt", "type", "loiter_radius", "loiter_time", "speed", "hold_time", "holdTime"}:
            return False
        self._waypoints[row][field] = value
        if field in {"hold_time", "holdTime"}:
            self._waypoints[row]["hold_time"] = value
            self._waypoints[row]["holdTime"] = value
        self._emit_changed()
        return True

    def _emit_changed(self):
        payload = self.waypoints()
        self.waypoints_changed.emit(payload)
        self.changed.emit(payload)