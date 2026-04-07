from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from .serialization import (
    export_to_kml,
    export_to_waypoints,
    import_from_kml,
    import_from_waypoints,
)

MISSION_IO_FORMATS: Dict[str, Dict[str, str]] = {
    "waypoints": {
        "label": "QGC WPL",
        "save_filter": "QGC WPL files (*.waypoints)",
        "open_filter": "QGC WPL files (*.waypoints)",
        "default_name": "vtol_waypoints.waypoints",
    },
    "kml": {
        "label": "KML",
        "save_filter": "KML files (*.kml)",
        "open_filter": "KML files (*.kml)",
        "default_name": "vtol_waypoints.kml",
    },
}


def normalize_format(format_type: str) -> str:
    key = str(format_type or "").strip().lower()
    if key in MISSION_IO_FORMATS:
        return key
    return "waypoints"


def detect_format_from_path(file_path: str, fallback: str = "waypoints") -> str:
    suffix = Path(str(file_path or "")).suffix.lower()
    if suffix == ".waypoints":
        return "waypoints"
    if suffix == ".kml":
        return "kml"
    return normalize_format(fallback)


def file_dialog_meta(format_type: str) -> Dict[str, str]:
    key = normalize_format(format_type)
    return dict(MISSION_IO_FORMATS.get(key, MISSION_IO_FORMATS["waypoints"]))


def export_mission_bundle(file_path: str, format_type: str, waypoints: List[Dict]):
    file_format = detect_format_from_path(file_path, fallback=format_type)
    if file_format == "kml":
        export_to_kml(file_path, waypoints)
        return
    export_to_waypoints(file_path, waypoints)


def import_mission_bundle(file_path: str, format_type: str) -> List[Dict]:
    file_format = detect_format_from_path(file_path, fallback=format_type)
    if file_format == "kml":
        return import_from_kml(file_path)
    return import_from_waypoints(file_path)
