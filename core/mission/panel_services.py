from typing import Dict, List, Optional, Tuple

from .config import RouteConfig
from .protocol import normalize_waypoint, round_route_alt, validate_waypoint
from .serialization import filter_valid_waypoints, preprocess_imported_waypoints


def mission_table_bounds(total_rows: int) -> Tuple[int, int]:
    mission_start_row = 0
    mission_end_row = max(0, int(total_rows))
    return mission_start_row, mission_end_row


def is_editable_mission_row(row: int, total_rows: int) -> bool:
    mission_start_row, mission_end_row = mission_table_bounds(total_rows)
    return mission_start_row <= int(row) < mission_end_row


def table_edit_field(column: int) -> Optional[str]:
    return {
        2: "lat",
        3: "lon",
        4: "alt",
        5: "speed",
        6: "hold_time",
    }.get(int(column))


def validate_table_value(field: str, value: float) -> Optional[str]:
    if field == "lat" and not (RouteConfig.MIN_LAT <= value <= RouteConfig.MAX_LAT):
        return f"纬度必须在{RouteConfig.MIN_LAT}~{RouteConfig.MAX_LAT}之间"
    if field == "lon" and not (RouteConfig.MIN_LON <= value <= RouteConfig.MAX_LON):
        return f"经度必须在{RouteConfig.MIN_LON}~{RouteConfig.MAX_LON}之间"
    if field == "alt" and not (RouteConfig.MIN_ALT <= value <= RouteConfig.MAX_ALT):
        return f"高度必须在{RouteConfig.MIN_ALT}~{RouteConfig.MAX_ALT}之间"
    if field == "speed" and not (RouteConfig.MIN_SPEED <= value <= RouteConfig.MAX_SPEED):
        return f"速度必须在{RouteConfig.MIN_SPEED}~{RouteConfig.MAX_SPEED}m/s之间"
    if field == "hold_time" and not (RouteConfig.MIN_HOLD_TIME <= value <= RouteConfig.MAX_HOLD_TIME):
        return f"停留时间必须在{RouteConfig.MIN_HOLD_TIME}~{RouteConfig.MAX_HOLD_TIME}秒之间"
    if field == "loiter_radius" and value < RouteConfig.MIN_LOITER_RADIUS:
        return f"盘旋半径最小为{RouteConfig.MIN_LOITER_RADIUS}米"
    if field == "loiter_time" and value < 0:
        return "盘旋时间不能为负数"
    return None


def apply_loiter_edit(row: int, is_loiter: bool, total_rows: int, waypoints: List[Dict]) -> Tuple[Optional[List[Dict]], Optional[str]]:
    if not is_editable_mission_row(row, total_rows):
        return None, "该行不可编辑"

    model_row = int(row)
    if not (0 <= model_row < len(waypoints or [])):
        return None, None

    updated_waypoints = list(waypoints or [])
    updated_wp = normalize_waypoint(updated_waypoints[model_row])
    updated_wp["loiter"] = bool(is_loiter)
    updated_waypoints[model_row] = updated_wp
    return updated_waypoints, None


def apply_table_cell_edit(row: int, column: int, text: str, total_rows: int, waypoints: List[Dict]) -> Tuple[Optional[List[Dict]], Optional[str]]:
    if not is_editable_mission_row(row, total_rows):
        return None, "该行不可编辑"

    field = table_edit_field(column)
    if field is None:
        return None, None

    try:
        value = float(text)
    except ValueError:
        return None, "请输入有效的数字"

    validation_error = validate_table_value(field, value)
    if validation_error:
        return None, validation_error

    model_row = int(row)
    if not (0 <= model_row < len(waypoints or [])):
        return None, None

    updated_waypoints = list(waypoints or [])
    updated_wp = normalize_waypoint(updated_waypoints[model_row])
    updated_wp[field] = round_route_alt(value) if field == "alt" else value
    if field == "hold_time":
        updated_wp["holdTime"] = value
    updated_waypoints[model_row] = updated_wp
    return updated_waypoints, None


def build_upload_confirmation_message(mission_count: int) -> str:
    n = int(mission_count)
    return (
        f"确定要上传航线吗？\n"
        f"飞控序号：0(H)、1~{n}(任务航点)\n"
        f"共 {n + 1} 个航点（含H点占位），将覆盖飞控原有任务。"
    )


def split_downloaded_waypoints(downloaded: List[Dict]) -> Tuple[Optional[Dict], List[Dict]]:
    home_wp: Optional[Dict] = None
    mission_waypoints: List[Dict] = []
    ordered = sorted((downloaded or []), key=lambda wp: int((wp or {}).get("seq", 0) or 0))
    for wp in ordered:
        _seq_raw = wp.get("seq")
        seq = int(_seq_raw) if _seq_raw is not None else -1
        name = str(wp.get("name", "") or "").upper()
        type_ = str(wp.get("type", "") or "").upper()
        if home_wp is None and (seq == 0 or name == "HOME" or type_ == "HOME"):
            home_wp = wp
            continue
        mission_waypoints.append(normalize_waypoint({**wp, "seq": len(mission_waypoints) + 1}))
    valid_home = home_wp if home_wp and validate_waypoint(home_wp) else None
    valid_mission = [wp for wp in mission_waypoints if validate_waypoint(wp)]
    return valid_home, valid_mission


def resolve_delete_selection(selected_rows: List[int], total_rows: int) -> Tuple[List[int], bool]:
    mission_rows: List[int] = []
    forbidden = False
    for row in sorted(set(int(row) for row in (selected_rows or []))):
        if is_editable_mission_row(row, total_rows):
            mission_rows.append(row)
        else:
            forbidden = True
    return mission_rows, forbidden


def uniform_height_default(waypoints: List[Dict]) -> float:
    if not waypoints:
        return RouteConfig.DEFAULT_AUTO_ROUTE_ALT
    first = normalize_waypoint(waypoints[0])
    return float(first.get("alt", RouteConfig.DEFAULT_AUTO_ROUTE_ALT) or RouteConfig.DEFAULT_AUTO_ROUTE_ALT)


def validate_uniform_height_value(height: float) -> bool:
    return float(height) >= float(RouteConfig.MIN_ALT)


def prepare_import_preview(imported_waypoints: List[Dict]) -> Tuple[List[Dict], int, int, str]:
    total = len(imported_waypoints or [])
    valid_waypoints, invalid_count = filter_valid_waypoints(imported_waypoints or [])
    message = f"解析到 {total} 个航点，{invalid_count} 个无效，是否导入有效航点？"
    if invalid_count > 0:
        message += "\n无效航点会被忽略。"
    return valid_waypoints, total, invalid_count, message


def process_imported_waypoints(valid_waypoints: List[Dict], home_wp: Optional[Dict]) -> Tuple[Optional[Dict], Dict, List[Dict], int]:
    processed_waypoints = preprocess_imported_waypoints(valid_waypoints, home_wp)
    imported_home: Optional[Dict] = None
    mission_waypoints: List[Dict] = []
    for wp in processed_waypoints:
        wp_norm = normalize_waypoint(wp)
        seq = int(wp_norm.get("seq", -1) or -1)
        name = str(wp_norm.get("name", "") or "").upper()
        wp_type = str(wp_norm.get("type", "WAYPOINT") or "WAYPOINT").upper()
        if imported_home is None and (seq == 0 or name == "HOME" or wp_type == "HOME"):
            imported_home = {
                "type": "HOME",
                "lat": float(wp_norm.get("lat", 0.0) or 0.0),
                "lon": float(wp_norm.get("lon", 0.0) or 0.0),
                "alt": float(wp_norm.get("alt", 0.0) or 0.0),
            }
            continue
        mission_waypoints.append(wp_norm)
    return imported_home, {}, mission_waypoints, len(processed_waypoints)


def build_import_success_message(mission_count: int, has_overrides: bool, has_home: bool) -> str:
    _ = has_overrides
    return (
        f"已导入任务航点 {int(mission_count)} 个"
        + ("，并更新H点" if has_home else "")
    )
