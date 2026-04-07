import math
from typing import Tuple


def calculate_offset_coordinate(lat: float, lon: float, bearing_deg: float, distance_m: float) -> Tuple[float, float]:
    r = 6378137.0
    bearing_rad = math.radians(bearing_deg)
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)

    angular_distance = distance_m / r
    new_lat_rad = math.asin(
        math.sin(lat_rad) * math.cos(angular_distance)
        + math.cos(lat_rad) * math.sin(angular_distance) * math.cos(bearing_rad)
    )
    new_lon_rad = lon_rad + math.atan2(
        math.sin(bearing_rad) * math.sin(angular_distance) * math.cos(lat_rad),
        math.cos(angular_distance) - math.sin(lat_rad) * math.sin(new_lat_rad),
    )
    new_lon_rad = (new_lon_rad + 3 * math.pi) % (2 * math.pi) - math.pi
    return math.degrees(new_lat_rad), math.degrees(new_lon_rad)


def calculate_horizontal_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6378137.0
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    d_lat = lat2_rad - lat1_rad
    d_lon = lon2_rad - lon1_rad
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(d_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c