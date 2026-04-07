import uuid
from typing import Dict

from .config import RouteConfig


MAV_CMD_NAV_WAYPOINT = 16
MAV_CMD_NAV_LOITER_UNLIM = 17
MAV_CMD_NAV_LOITER_TURNS = 18
MAV_CMD_NAV_LOITER_TIME = 19
MAV_CMD_NAV_RETURN_TO_LAUNCH = 20
MAV_CMD_NAV_LOITER_TO_ALT = 31
MAV_CMD_NAV_VTOL_TAKEOFF = 84
MAV_CMD_NAV_VTOL_LAND = 85
MAV_CMD_NAV_HOME = 179
MAV_CMD_DO_VTOL_TRANSITION = 3000

VTOL_TRANSITION_TO_FW = 4
VTOL_TRANSITION_TO_MC = 3

MISSION_TYPE_OPTIONS = [
    ("WAYPOINT", "航点巡航"),
    ("VTOL_TAKEOFF", "VTOL垂直起飞"),
    ("VTOL_LAND", "VTOL垂直降落"),
    ("VTOL_TRANSITION", "VTOL固定翼过渡"),
]
MISSION_TYPE_LABELS = {key: label for key, label in MISSION_TYPE_OPTIONS}
MISSION_TYPE_COMMANDS = {
    "WAYPOINT": MAV_CMD_NAV_WAYPOINT,
    "VTOL_TAKEOFF": MAV_CMD_NAV_VTOL_TAKEOFF,
    "VTOL_LAND": MAV_CMD_NAV_VTOL_LAND,
    "VTOL_TRANSITION": MAV_CMD_DO_VTOL_TRANSITION,
    "HOME": MAV_CMD_NAV_HOME,
}
LEGACY_TO_VTOL_MISSION_TYPE = {
    "TAKEOFF": "VTOL_TAKEOFF",
    "LAND": "VTOL_LAND",
}
LOITER_COMMANDS = {
    MAV_CMD_NAV_LOITER_UNLIM,
    MAV_CMD_NAV_LOITER_TURNS,
    MAV_CMD_NAV_LOITER_TIME,
    MAV_CMD_NAV_LOITER_TO_ALT,
}
SUPPORTED_MISSION_COMMANDS = {
    MAV_CMD_NAV_WAYPOINT,
    MAV_CMD_NAV_LOITER_UNLIM,
    MAV_CMD_NAV_LOITER_TURNS,
    MAV_CMD_NAV_LOITER_TIME,
    MAV_CMD_NAV_RETURN_TO_LAUNCH,
    MAV_CMD_NAV_LOITER_TO_ALT,
    MAV_CMD_NAV_VTOL_TAKEOFF,
    MAV_CMD_NAV_VTOL_LAND,
    MAV_CMD_NAV_HOME,
    MAV_CMD_DO_VTOL_TRANSITION,
}
COMMAND_TO_MISSION_TYPE = {
    MAV_CMD_NAV_VTOL_TAKEOFF: "VTOL_TAKEOFF",
    MAV_CMD_NAV_VTOL_LAND: "VTOL_LAND",
    MAV_CMD_DO_VTOL_TRANSITION: "VTOL_TRANSITION",
    MAV_CMD_NAV_HOME: "HOME",
}
FRAME_LABELS = {
    0: "GLOBAL_ABS",
    3: "GLOBAL_REL",
    5: "GLOBAL_REL_INT",
    6: "GLOBAL_REL_INT",
    10: "GLOBAL_TERRAIN",
    11: "GLOBAL_TERRAIN_INT",
}


def round_route_alt(alt: float, default: float = 0.0) -> float:
    try:
        alt = float(alt) if alt is not None else default
        return float(int(round(max(RouteConfig.MIN_ALT, alt))))
    except (ValueError, TypeError):
        return round_route_alt(default)


def safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def safe_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def config_or_default(config: Dict, key: str, default: float) -> float:
    if key in config and config.get(key) is not None:
        return safe_float(config.get(key), default)
    return float(default)


def command_default_loiter_radius(command: int, param2: float, param3: float) -> float:
    if int(command) == MAV_CMD_NAV_LOITER_TO_ALT:
        return param2 if abs(param2) > 1e-6 else 60.0
    return param3 if abs(param3) > 1e-6 else 60.0


def command_default_loiter_time(command: int, param1: float) -> float:
    command = int(command)
    if command == MAV_CMD_NAV_LOITER_TIME:
        return max(0.0, param1) / 60.0
    if command == MAV_CMD_NAV_LOITER_TURNS:
        return max(0.0, param1)
    return 0.0


def normalize_waypoint(wp: Dict) -> Dict:
    if not isinstance(wp, dict):
        wp = {}

    raw_type = str(wp.get("type", "WAYPOINT") or "WAYPOINT").upper()
    raw_type = LEGACY_TO_VTOL_MISSION_TYPE.get(raw_type, raw_type)

    default_command = MISSION_TYPE_COMMANDS.get(raw_type, MAV_CMD_NAV_WAYPOINT)
    command = safe_int(wp.get("command", default_command), default_command)
    if command not in SUPPORTED_MISSION_COMMANDS and raw_type in MISSION_TYPE_COMMANDS:
        command = default_command
    if command in COMMAND_TO_MISSION_TYPE:
        mission_type = COMMAND_TO_MISSION_TYPE[command]
    else:
        mission_type = raw_type if raw_type in MISSION_TYPE_COMMANDS else "WAYPOINT"

    requested_loiter = wp.get("loiter")
    if mission_type == "VTOL_TRANSITION":
        command = MAV_CMD_DO_VTOL_TRANSITION
    elif mission_type == "VTOL_TAKEOFF":
        command = MAV_CMD_NAV_VTOL_TAKEOFF
    elif mission_type == "VTOL_LAND":
        command = MAV_CMD_NAV_VTOL_LAND
    elif mission_type == "HOME":
        command = MAV_CMD_NAV_HOME
    elif mission_type == "WAYPOINT" and "command" not in wp and requested_loiter is not None:
        # Only infer command from loiter when caller did not explicitly provide MAV_CMD.
        command = MAV_CMD_NAV_LOITER_TIME if bool(requested_loiter) else MAV_CMD_NAV_WAYPOINT

    param1 = safe_float(wp.get("param1", 0.0), 0.0)
    param2 = safe_float(wp.get("param2", 0.0), 0.0)
    param3 = safe_float(wp.get("param3", 0.0), 0.0)
    param4 = safe_float(wp.get("param4", 0.0), 0.0)

    loiter_radius = safe_float(
        wp.get("loiter_radius", command_default_loiter_radius(command, param2, param3)),
        command_default_loiter_radius(command, param2, param3),
    )
    loiter_time = safe_float(
        wp.get("loiter_time", command_default_loiter_time(command, param1)),
        command_default_loiter_time(command, param1),
    )

    if command in LOITER_COMMANDS:
        loiter_radius = max(RouteConfig.MIN_LOITER_RADIUS, loiter_radius)
        loiter_time = max(0.0, loiter_time)
        if command == MAV_CMD_NAV_LOITER_UNLIM:
            param1 = 0.0
            param2 = 0.0
            param3 = loiter_radius
            loiter_time = 0.0
        elif command == MAV_CMD_NAV_LOITER_TURNS:
            param1 = loiter_time
            param3 = loiter_radius
        elif command == MAV_CMD_NAV_LOITER_TIME:
            param1 = loiter_time * 60.0
            param3 = loiter_radius
        elif command == MAV_CMD_NAV_LOITER_TO_ALT:
            param2 = loiter_radius
            loiter_time = 0.0
    elif command == MAV_CMD_DO_VTOL_TRANSITION:
        param1 = safe_float(wp.get("param1", VTOL_TRANSITION_TO_FW), VTOL_TRANSITION_TO_FW)
        param2 = safe_float(wp.get("param2", 0.0), 0.0)
        param3 = 0.0
        param4 = 0.0
        loiter_radius = max(RouteConfig.MIN_LOITER_RADIUS, loiter_radius)
        loiter_time = 0.0
    else:
        loiter_time = max(0.0, loiter_time)
        loiter_radius = max(RouteConfig.MIN_LOITER_RADIUS, loiter_radius)

    complex_group = wp.get("complex_group")
    try:
        complex_group = int(complex_group) if complex_group not in (None, "") else None
    except (TypeError, ValueError):
        complex_group = None

    waypoint_id = str(wp.get("id", "") or "").strip() or uuid.uuid4().hex[:8]
    speed = safe_float(wp.get("speed", RouteConfig.DEFAULT_SPEED), RouteConfig.DEFAULT_SPEED)
    speed = max(RouteConfig.MIN_SPEED, min(RouteConfig.MAX_SPEED, speed))

    hold_time = safe_float(
        wp.get("hold_time", wp.get("holdTime", wp.get("param1", RouteConfig.DEFAULT_HOLD_TIME))),
        RouteConfig.DEFAULT_HOLD_TIME,
    )
    hold_time = max(RouteConfig.MIN_HOLD_TIME, min(RouteConfig.MAX_HOLD_TIME, hold_time))

    return {
        "id": waypoint_id,
        "type": mission_type,
        "command": command,
        "lat": safe_float(wp.get("lat", 0.0), 0.0),
        "lon": safe_float(wp.get("lon", 0.0), 0.0),
        "alt": round_route_alt(wp.get("alt"), RouteConfig.DEFAULT_AUTO_ROUTE_ALT),
        "loiter": command in LOITER_COMMANDS,
        "loiter_radius": loiter_radius,
        "loiter_time": loiter_time,
        "frame": safe_int(wp.get("frame", 6), 6),
        "source_frame": safe_int(wp.get("source_frame", wp.get("frame", 6)), safe_int(wp.get("frame", 6), 6)),
        "source_alt": safe_float(wp.get("source_alt", wp.get("alt", 0.0)), safe_float(wp.get("alt", 0.0), 0.0)),
        "param1": param1,
        "param2": param2,
        "param3": param3,
        "param4": param4,
        "name": wp.get("name", ""),
        "phase": wp.get("phase", ""),
        "mode": wp.get("mode", ""),
        "description": wp.get("description", ""),
        "seq": safe_int(wp.get("seq", 0), 0),
        "speed": speed,
        "hold_time": hold_time,
        "holdTime": hold_time,
        "complex_group": complex_group,
        "complex_item_type": str(wp.get("complex_item_type", "") or ""),
    }


def validate_waypoint(wp: Dict) -> bool:
    try:
        wp = normalize_waypoint(wp)
        if not (RouteConfig.MIN_LAT <= wp["lat"] <= RouteConfig.MAX_LAT):
            return False
        if not (RouteConfig.MIN_LON <= wp["lon"] <= RouteConfig.MAX_LON):
            return False
        if not (RouteConfig.MIN_ALT <= wp["alt"] <= RouteConfig.MAX_ALT):
            return False
        if wp["type"] == "VTOL_TRANSITION" and int(wp["param1"]) not in (VTOL_TRANSITION_TO_FW, VTOL_TRANSITION_TO_MC):
            return False
        return True
    except Exception:
        return False