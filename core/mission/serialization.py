import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

from .config import RouteConfig
from .protocol import LEGACY_TO_VTOL_MISSION_TYPE, MAV_CMD_NAV_RETURN_TO_LAUNCH, normalize_waypoint, validate_waypoint


def export_to_kml(file_path: str, waypoints: List[Dict]):
    kml_content = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
<name>VTOL Drone Waypoints</name>
<Style id="waypointStyle">
  <IconStyle>
    <Icon>
      <href>http://maps.google.com/mapfiles/kml/pushpin/ylw-pushpin.png</href>
    </Icon>
  </IconStyle>
</Style>
<Placemark>
  <name>Full Route Line</name>
  <LineString>
    <coordinates>
"""
    for wp in waypoints:
        kml_content += f"{wp['lon']:.7f},{wp['lat']:.7f},{int(round(float(wp['alt'])))}\n"
    kml_content += """
    </coordinates>
  </LineString>
</Placemark>
"""
    for index, wp in enumerate(waypoints, 0):
        name = wp.get("name", f"Waypoint {wp.get('seq', index)}")
        desc = wp.get("description", f"航点{wp.get('seq', index)}，高度{int(wp['alt'])}米")
        kml_content += f"""
<Placemark>
  <name>{name}</name>
  <description>{desc}</description>
  <styleUrl>#waypointStyle</styleUrl>
  <Point>
    <coordinates>{wp['lon']:.7f},{wp['lat']:.7f},{int(round(float(wp['alt'])))}</coordinates>
  </Point>
</Placemark>
"""
    kml_content += """
</Document>
</kml>
"""
    with open(file_path, "w", encoding="utf-8") as file_obj:
        file_obj.write(kml_content)


def export_to_waypoints(file_path: str, waypoints: List[Dict]):
    lines: List[str] = ["QGC WPL 110"]
    normalized = [normalize_waypoint(wp) for wp in (waypoints or [])]

    if normalized:
        home = normalized[0]
        lines.append(
            f"0\t1\t0\t16\t0\t0\t0\t0\t{float(home.get('lat', 0.0) or 0.0):.7f}\t{float(home.get('lon', 0.0) or 0.0):.7f}\t0\t1"
        )
    else:
        lines.append("0\t1\t0\t16\t0\t0\t0\t0\t0\t0\t0\t1")

    seq = 1
    for wp in normalized:
        if int(wp.get("seq", -1) or -1) == 0 or str(wp.get("type", "") or "").upper() == "HOME":
            continue
        command = int(wp.get("command", 16) or 16)
        hold_time = float(wp.get("hold_time", wp.get("holdTime", wp.get("param1", 0.0))) or 0.0)
        param2 = float(wp.get("param2", 0.0) or 0.0)
        param3 = float(wp.get("param3", 0.0) or 0.0)
        lat = float(wp.get("lat", 0.0) or 0.0)
        lon = float(wp.get("lon", 0.0) or 0.0)
        alt = float(wp.get("alt", 0.0) or 0.0)
        lines.append(
            f"{seq}\t0\t3\t{command}\t{hold_time:.3f}\t{param2:.3f}\t{param3:.3f}\t0\t{lat:.7f}\t{lon:.7f}\t{alt:.2f}\t1"
        )
        seq += 1

    with open(file_path, "w", encoding="utf-8") as file_obj:
        file_obj.write("\n".join(lines))


def import_from_kml(file_path: str) -> List[Dict]:
    waypoints = []
    tree = ET.parse(file_path)
    root = tree.getroot()
    ns = {"kml": "http://www.opengis.net/kml/2.2"}
    placemarks = root.findall(".//kml:Placemark", ns)

    for placemark in placemarks:
        point = placemark.find(".//kml:Point/kml:coordinates", ns)
        if point is None or point.text is None:
            continue
        coord_text = point.text.strip()
        if not coord_text:
            continue
        try:
            coords = coord_text.split(",")
            lon = float(coords[0].strip())
            lat = float(coords[1].strip())
            alt = float(coords[2].strip()) if len(coords) > 2 else RouteConfig.DEFAULT_AUTO_ROUTE_ALT
            name_elem = placemark.find(".//kml:name", ns)
            name = name_elem.text.strip() if name_elem is not None and name_elem.text else ""
            waypoints.append(normalize_waypoint({
                "name": name,
                "type": "WAYPOINT",
                "lat": lat,
                "lon": lon,
                "alt": alt,
            }))
        except (ValueError, IndexError):
            continue
    return waypoints


def import_from_waypoints(file_path: str) -> List[Dict]:
    with open(file_path, "r", encoding="utf-8") as file_obj:
        lines = [line.strip() for line in file_obj.readlines() if line.strip()]

    if not lines or not lines[0].startswith("QGC WPL"):
        return []

    waypoints: List[Dict] = []
    for line in lines[1:]:
        cols = line.split("\t")
        if len(cols) < 12:
            continue
        try:
            seq = int(cols[0])
            command = int(cols[3])
            param1 = float(cols[4] or 0.0)
            param2 = float(cols[5] or 0.0)
            param3 = float(cols[6] or 0.0)
            lat = float(cols[8] or 0.0)
            lon = float(cols[9] or 0.0)
            alt = float(cols[10] or 0.0)
        except (TypeError, ValueError):
            continue

        if seq == 0:
            waypoints.append(normalize_waypoint({
                "seq": 0,
                "name": "HOME",
                "type": "HOME",
                "lat": lat,
                "lon": lon,
                "alt": alt,
                "command": 16,
            }))
            continue

        waypoints.append(normalize_waypoint({
            "seq": seq,
            "type": "WAYPOINT",
            "command": command,
            "param1": param1,
            "param2": param2,
            "param3": param3,
            "hold_time": param1,
            "holdTime": param1,
            "lat": lat,
            "lon": lon,
            "alt": alt,
        }))

    return waypoints


def preprocess_imported_waypoints(waypoints: List[Dict], home_wp: Optional[Dict]) -> List[Dict]:
    processed_waypoints = []
    for wp in waypoints:
        if wp.get("command") == MAV_CMD_NAV_RETURN_TO_LAUNCH:
            if home_wp:
                processed_waypoints.append(normalize_waypoint({
                    "name": "RTL",
                    "type": "WAYPOINT",
                    "lat": home_wp["lat"],
                    "lon": home_wp["lon"],
                    "alt": RouteConfig.DEFAULT_T2_ALT,
                    "description": "自动返航至H点",
                }))
            continue
        legacy_type = wp.get("type", "")
        if legacy_type in LEGACY_TO_VTOL_MISSION_TYPE:
            wp = dict(wp)
            wp["type"] = LEGACY_TO_VTOL_MISSION_TYPE[legacy_type]
            wp = normalize_waypoint(wp)
        processed_waypoints.append(wp)
    return processed_waypoints


def split_imported_route_points(waypoints: List[Dict]) -> Tuple[Optional[Dict], Dict, List[Dict]]:
    imported_home: Optional[Dict] = None
    route_points: Dict[str, Dict] = {}
    mission_waypoints: List[Dict] = []

    for raw_wp in waypoints or []:
        wp = normalize_waypoint(raw_wp)
        name_raw = str(wp.get("name", "") or "").strip()
        name_upper = name_raw.upper()
        wp_type = str(wp.get("type", "WAYPOINT") or "WAYPOINT").upper()
        seq = int(wp.get("seq", -1) or -1)

        if imported_home is None and (wp_type == "HOME" or name_upper in {"HOME", "H", "H点"} or seq == 0):
            imported_home = {
                "type": "HOME",
                "lat": float(wp.get("lat", 0.0) or 0.0),
                "lon": float(wp.get("lon", 0.0) or 0.0),
                "alt": float(wp.get("alt", 0.0) or 0.0),
            }
            continue

        if name_upper in {"T1", "T2", "L1", "L2", "L3"} and name_upper not in route_points:
            route_points[name_upper] = wp
            continue

        mission_waypoints.append(wp)

    if imported_home is None and "T1" in route_points:
        t1 = route_points["T1"]
        imported_home = {
            "type": "HOME",
            "lat": float(t1.get("lat", 0.0) or 0.0),
            "lon": float(t1.get("lon", 0.0) or 0.0),
            "alt": float(t1.get("alt", 0.0) or 0.0),
        }

    overrides: Dict[str, float] = {}
    t1 = route_points.get("T1")
    if t1 is not None:
        overrides["t1_alt"] = float(t1.get("alt", RouteConfig.DEFAULT_T1_ALT) or RouteConfig.DEFAULT_T1_ALT)

    t2 = route_points.get("T2")
    if t2 is not None:
        overrides.update({
            "t2_lat": float(t2.get("lat", 0.0) or 0.0),
            "t2_lon": float(t2.get("lon", 0.0) or 0.0),
            "t2_alt": float(t2.get("alt", RouteConfig.DEFAULT_T2_ALT) or RouteConfig.DEFAULT_T2_ALT),
            "t2_loiter_radius": float(t2.get("loiter_radius", 60.0) or 60.0),
            "t2_loiter_time": float(t2.get("loiter_time", 30.0) or 30.0),
        })

    l1 = route_points.get("L1")
    if l1 is not None:
        overrides.update({
            "l1_lat": float(l1.get("lat", 0.0) or 0.0),
            "l1_lon": float(l1.get("lon", 0.0) or 0.0),
            "l1_alt": float(l1.get("alt", RouteConfig.DEFAULT_L1_ALT) or RouteConfig.DEFAULT_L1_ALT),
            "l1_loiter_radius": float(l1.get("loiter_radius", 60.0) or 60.0),
        })

    l2 = route_points.get("L2")
    if l2 is not None:
        overrides.update({
            "l2_lat": float(l2.get("lat", 0.0) or 0.0),
            "l2_lon": float(l2.get("lon", 0.0) or 0.0),
            "l2_alt": float(l2.get("alt", RouteConfig.DEFAULT_L2_ALT) or RouteConfig.DEFAULT_L2_ALT),
        })

    l3 = route_points.get("L3")
    if l3 is not None:
        overrides.update({
            "l3_lat": float(l3.get("lat", 0.0) or 0.0),
            "l3_lon": float(l3.get("lon", 0.0) or 0.0),
            "l3_alt": float(l3.get("alt", RouteConfig.DEFAULT_L3_ALT) or RouteConfig.DEFAULT_L3_ALT),
        })

    return imported_home, overrides, mission_waypoints


def filter_valid_waypoints(waypoints: List[Dict]) -> Tuple[List[Dict], int]:
    valid_waypoints = []
    invalid_count = 0
    for wp in waypoints:
        if validate_waypoint(wp):
            valid_waypoints.append(wp)
        else:
            invalid_count += 1
    return valid_waypoints, invalid_count