import math
from typing import Dict, List, Optional, Tuple

from .config import RouteConfig
from .protocol import MAV_CMD_NAV_WAYPOINT, SUPPORTED_MISSION_COMMANDS, normalize_waypoint


def _sorted_mission_items(downloaded: List[Dict]) -> List[Dict]:
    items: List[Dict] = []
    for index, item in enumerate(downloaded or []):
        if not isinstance(item, dict):
            continue
        normalized = normalize_waypoint({**item, "seq": int(item.get("seq", index))})
        items.append(normalized)
    items.sort(key=lambda wp: (int(wp.get("seq", 0)), str(wp.get("name", ""))))
    return items


def _make_home_upload_item(home_position: Dict) -> Dict:
    home_lat = float(home_position.get("lat", 0.0) or 0.0)
    home_lon = float(home_position.get("lon", 0.0) or 0.0)
    home_alt = float(home_position.get("alt", 0.0) or 0.0)
    return normalize_waypoint({
        "seq": 0,
        "type": "WAYPOINT",
        "name": "HOME",
        "command": MAV_CMD_NAV_WAYPOINT,
        "lat": home_lat,
        "lon": home_lon,
        "alt": home_alt,
        "frame": 0,
        "source_frame": 0,
        "source_alt": home_alt,
        "current": 0,
        "autocontinue": 1,
        "param1": 0.0,
        "param2": 0.0,
        "param3": 0.0,
        "param4": 0.0,
        "loiter": False,
        "loiter_radius": 0.0,
        "loiter_time": 0.0,
    })


def _visible_upload_items(visible_waypoints: List[Dict]) -> List[Dict]:
    mission_items: List[Dict] = []
    for index, wp in enumerate(visible_waypoints or [], start=1):
        if str(wp.get("type", "WAYPOINT") or "WAYPOINT").upper() == "HOME":
            continue
        mission_items.append(normalize_waypoint({**dict(wp), "seq": index}))
    return mission_items


def _is_home_item(item: Dict, home_position: Optional[Dict]) -> bool:
    seq = int(item.get("seq", -1)) if item.get("seq") is not None else -1
    if seq == 0:
        return True
    if str(item.get("name", "") or "").upper() == "HOME":
        return True
    if str(item.get("type", "") or "").upper() == "HOME":
        return True
    if not isinstance(home_position, dict):
        return False
    try:
        home_lat = float(home_position.get("lat", 0.0) or 0.0)
        home_lon = float(home_position.get("lon", 0.0) or 0.0)
        item_lat = float(item.get("lat", 0.0) or 0.0)
        item_lon = float(item.get("lon", 0.0) or 0.0)
        return abs(item_lat - home_lat) <= 1e-6 and abs(item_lon - home_lon) <= 1e-6
    except Exception:
        return False


def build_upload_waypoints(visible_waypoints: List[Dict], auto_route_items: List[Dict], home_position: Optional[Dict]) -> List[Dict]:
    _ = auto_route_items
    mission_waypoints = _visible_upload_items(visible_waypoints)

    home = home_position or {}
    home_lat = float(home.get("lat", 0.0) or 0.0)
    home_lon = float(home.get("lon", 0.0) or 0.0)
    if abs(home_lat) <= 1e-9 and abs(home_lon) <= 1e-9:
        return mission_waypoints

    return [_make_home_upload_item(home)] + mission_waypoints


def validate_upload_waypoints(waypoints: List[Dict]) -> Tuple[bool, str]:
    if not waypoints:
        return False, "没有可上传的航点"

    seen_seq = set()
    first_name = str((waypoints[0] or {}).get("name", "") or "").upper()
    if first_name != "HOME":
        return False, "上传中止：缺少 HOME 起始点，请先设置 H 点"

    for idx, wp in enumerate(waypoints):
        try:
            lat = float(wp.get("lat", 0.0) or 0.0)
            lon = float(wp.get("lon", 0.0) or 0.0)
            alt = float(wp.get("alt", 0.0) or 0.0)
            command = int(wp.get("command", MAV_CMD_NAV_WAYPOINT) or MAV_CMD_NAV_WAYPOINT)
            seq = int(wp.get("seq", idx) or idx)
        except Exception:
            return False, f"第 {idx + 1} 个航点字段格式无效"

        if seq in seen_seq:
            return False, f"第 {idx + 1} 个航点序号重复: {seq}"
        seen_seq.add(seq)

        if not math.isfinite(lat) or not math.isfinite(lon) or not math.isfinite(alt):
            return False, f"第 {idx + 1} 个航点包含非法数值"
        if not (-90.0 <= lat <= 90.0):
            return False, f"第 {idx + 1} 个航点纬度越界: {lat:.7f}"
        if not (-180.0 <= lon <= 180.0):
            return False, f"第 {idx + 1} 个航点经度越界: {lon:.7f}"
        if not (RouteConfig.MIN_ALT <= alt <= max(RouteConfig.MAX_ALT, 5000.0)):
            return False, f"第 {idx + 1} 个航点高度越界: {alt:.1f}m"
        if command <= 0:
            return False, f"第 {idx + 1} 个航点命令无效: {command}"
        if command not in SUPPORTED_MISSION_COMMANDS:
            return False, f"第 {idx + 1} 个航点包含当前界面不支持上传的命令: {command}"

    return True, ""

def split_downloaded_mission(downloaded: List[Dict], home_position: Optional[Dict], auto_route_items: List[Dict]) -> Tuple[Dict[str, Dict], List[Dict]]:
    _ = auto_route_items
    items = _sorted_mission_items(downloaded)
    if not items:
        return {}, []

    mission_items: List[Dict] = []
    for item in items:
        if _is_home_item(item, home_position):
            continue
        mission_items.append(item)

    # 可见任务点重新编号为 1..N，地图/列表统一依赖 seq 显示。
    visible_items: List[Dict] = []
    for seq, item in enumerate(mission_items, start=1):
        visible_items.append(normalize_waypoint({**dict(item), "seq": seq}))
    return {}, visible_items
