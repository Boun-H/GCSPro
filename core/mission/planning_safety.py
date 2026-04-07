from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

from .geometry import calculate_horizontal_distance


def _safe_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _polygon_points(record: Any) -> list[tuple[float, float]]:
    if isinstance(record, dict):
        payload = record.get("polygon") or record.get("points") or record.get("vertices") or []
    else:
        payload = record or []
    points: list[tuple[float, float]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        lat = _safe_float(item.get("lat"), None)
        lon = _safe_float(item.get("lon"), None)
        if lat is None or lon is None:
            continue
        points.append((lat, lon))
    return points


def _point_in_polygon(lat: float, lon: float, points: Sequence[tuple[float, float]]) -> bool:
    if len(points) < 3:
        return False
    inside = False
    j = len(points) - 1
    for i in range(len(points)):
        lat_i, lon_i = points[i]
        lat_j, lon_j = points[j]
        intersects = ((lat_i > lat) != (lat_j > lat)) and (
            lon < (lon_j - lon_i) * (lat - lat_i) / max(1e-12, (lat_j - lat_i)) + lon_i
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def _point_in_circle(lat: float, lon: float, circle: dict[str, Any]) -> bool:
    center = circle.get("center") or circle
    c_lat = _safe_float(center.get("lat"), None) if isinstance(center, dict) else None
    c_lon = _safe_float(center.get("lon"), None) if isinstance(center, dict) else None
    radius = _safe_float(circle.get("radius") or circle.get("radius_m"), None) if isinstance(circle, dict) else None
    if c_lat is None or c_lon is None or radius is None:
        return False
    distance = calculate_horizontal_distance(lat, lon, c_lat, c_lon)
    return distance <= radius


def _geofence_messages(lat: float, lon: float, geofence: dict[str, Any] | None) -> list[str]:
    payload = dict(geofence or {})
    messages: list[str] = []
    for circle in payload.get("circles", []) or []:
        if not isinstance(circle, dict):
            continue
        inclusion = bool(circle.get("inclusion", True))
        if _point_in_circle(lat, lon, circle):
            if not inclusion:
                messages.append("进入禁飞圆形区域")
        elif inclusion:
            messages.append("位于允许飞行圆形区域外")
    for polygon in payload.get("polygons", []) or []:
        if not isinstance(polygon, dict):
            continue
        inclusion = bool(polygon.get("inclusion", True))
        points = _polygon_points(polygon)
        if not points:
            continue
        inside = _point_in_polygon(lat, lon, points)
        if inside and not inclusion:
            messages.append("进入禁飞多边形区域")
        elif not inside and inclusion:
            messages.append("位于允许飞行多边形区域外")
    return messages


def _project_xy(lat: float, lon: float, ref_lat: float) -> tuple[float, float]:
    scale = math.cos(math.radians(ref_lat))
    return lon * scale, lat


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1])


def _on_segment(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> bool:
    return min(a[0], c[0]) <= b[0] <= max(a[0], c[0]) and min(a[1], c[1]) <= b[1] <= max(a[1], c[1])


def _segments_intersect(p1: tuple[float, float], p2: tuple[float, float], q1: tuple[float, float], q2: tuple[float, float]) -> bool:
    o1 = _orientation(p1, p2, q1)
    o2 = _orientation(p1, p2, q2)
    o3 = _orientation(q1, q2, p1)
    o4 = _orientation(q1, q2, p2)

    if (o1 > 0 > o2 or o1 < 0 < o2) and (o3 > 0 > o4 or o3 < 0 < o4):
        return True
    if abs(o1) < 1e-12 and _on_segment(p1, q1, p2):
        return True
    if abs(o2) < 1e-12 and _on_segment(p1, q2, p2):
        return True
    if abs(o3) < 1e-12 and _on_segment(q1, p1, q2):
        return True
    if abs(o4) < 1e-12 and _on_segment(q1, p2, q2):
        return True
    return False


def analyze_plan_safety(
    home: dict[str, Any] | None = None,
    waypoints: Iterable[dict[str, Any]] | None = None,
    geofence: dict[str, Any] | None = None,
    min_clearance_m: float = 30.0,
    min_spacing_m: float = 8.0,
    max_alt_step_m: float = 80.0,
) -> dict[str, Any]:
    mission = [dict(item) for item in (waypoints or []) if isinstance(item, dict)]
    if not mission:
        return {
            "score": 100,
            "issue_count": 0,
            "level": "ok",
            "summary": "规划检查：暂无任务点。",
            "messages": [],
            "clearance_min_m": None,
        }

    issues: list[tuple[str, str]] = []
    clearance_min: float | None = None

    def add_issue(level: str, message: str):
        issues.append((str(level or "warn"), str(message or "")))

    for idx, wp in enumerate(mission, start=1):
        lat = _safe_float(wp.get("lat"), 0.0) or 0.0
        lon = _safe_float(wp.get("lon"), 0.0) or 0.0
        alt = _safe_float(wp.get("alt"), 0.0) or 0.0
        terrain = _safe_float(wp.get("terrain_alt"), None)
        if terrain is not None:
            clearance = alt - terrain
            clearance_min = clearance if clearance_min is None else min(clearance_min, clearance)
            if clearance < float(min_clearance_m):
                add_issue("danger", f"WP{idx} 地形净空仅 {clearance:.1f}m，建议提高航点高度。")
        for fence_message in _geofence_messages(lat, lon, geofence):
            add_issue("danger", f"WP{idx} {fence_message}。")

    travel_points = []
    if isinstance(home, dict):
        travel_points.append(dict(home))
    travel_points.extend(mission)
    for index, (prev, curr) in enumerate(zip(travel_points, travel_points[1:]), start=1):
        prev_lat = _safe_float(prev.get("lat"), 0.0) or 0.0
        prev_lon = _safe_float(prev.get("lon"), 0.0) or 0.0
        curr_lat = _safe_float(curr.get("lat"), 0.0) or 0.0
        curr_lon = _safe_float(curr.get("lon"), 0.0) or 0.0
        distance = calculate_horizontal_distance(prev_lat, prev_lon, curr_lat, curr_lon)
        if distance < float(min_spacing_m):
            add_issue("warn", f"航段 {index} 与前一点距离仅 {distance:.1f}m，可能出现航线冲突或重复点。")
        alt_step = abs((_safe_float(curr.get("alt"), 0.0) or 0.0) - (_safe_float(prev.get("alt"), 0.0) or 0.0))
        if alt_step > float(max_alt_step_m):
            add_issue("warn", f"航段 {index} 高度突变 {alt_step:.1f}m，建议平滑爬升/下降。")

    ref_lat = sum((_safe_float(item.get("lat"), 0.0) or 0.0) for item in mission) / max(1, len(mission))
    for first in range(len(mission) - 1):
        p1 = mission[first]
        p2 = mission[first + 1]
        a1 = _project_xy(_safe_float(p1.get("lat"), 0.0) or 0.0, _safe_float(p1.get("lon"), 0.0) or 0.0, ref_lat)
        a2 = _project_xy(_safe_float(p2.get("lat"), 0.0) or 0.0, _safe_float(p2.get("lon"), 0.0) or 0.0, ref_lat)
        for second in range(first + 2, len(mission) - 1):
            if second == first + 1:
                continue
            q1 = mission[second]
            q2 = mission[second + 1]
            b1 = _project_xy(_safe_float(q1.get("lat"), 0.0) or 0.0, _safe_float(q1.get("lon"), 0.0) or 0.0, ref_lat)
            b2 = _project_xy(_safe_float(q2.get("lat"), 0.0) or 0.0, _safe_float(q2.get("lon"), 0.0) or 0.0, ref_lat)
            if _segments_intersect(a1, a2, b1, b2):
                add_issue("warn", f"航线段 {first + 1}-{first + 2} 与 {second + 1}-{second + 2} 存在交叉。")

    danger_count = sum(1 for level, _ in issues if level == "danger")
    warn_count = sum(1 for level, _ in issues if level == "warn")
    score = max(0, 100 - danger_count * 20 - warn_count * 10)
    level = "danger" if danger_count else "warn" if warn_count else "ok"

    if not issues:
        summary = "规划检查通过：未发现明显地形/冲突/禁飞区风险。"
        if clearance_min is not None:
            summary += f" 最小离地净空约 {clearance_min:.1f}m。"
    else:
        summary = f"规划风险：共 {len(issues)} 项，安全分 {score}/100。"
        if any("禁飞" in message for _, message in issues):
            summary += " 包含禁飞区预警。"
        if clearance_min is not None:
            summary += f" 最小离地净空约 {clearance_min:.1f}m。"

    return {
        "score": int(score),
        "issue_count": len(issues),
        "level": level,
        "summary": summary,
        "messages": [message for _, message in issues],
        "clearance_min_m": None if clearance_min is None else round(clearance_min, 2),
    }
