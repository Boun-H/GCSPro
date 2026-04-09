import json
import math
import struct
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal

from core.logger import get_app_logger

logger = get_app_logger("GCS.MapBridge", "map/map_bridge.log")


class MapBridge(QObject):
    add_waypoint_signal = pyqtSignal(float, float)
    add_waypoint_detail_signal = pyqtSignal(dict)
    move_waypoint_signal = pyqtSignal(int, float, float)
    move_waypoint_realtime_signal = pyqtSignal(int, float, float)
    select_waypoint_signal = pyqtSignal(int)
    map_add_mode_signal = pyqtSignal(bool)
    measure_mode_signal = pyqtSignal(bool)
    follow_mode_signal = pyqtSignal(bool)
    cache_visible_region_signal = pyqtSignal(dict)
    offline_cache_summary_request_signal = pyqtSignal(str)
    home_point_signal = pyqtSignal(float, float, float)
    home_pick_from_map_signal = pyqtSignal(float, float)
    insert_waypoint_after_signal = pyqtSignal(int)
    delete_waypoint_signal = pyqtSignal(int)
    fly_to_waypoint_signal = pyqtSignal(int)
    upload_waypoint_signal = pyqtSignal(int)
    move_auto_route_point_signal = pyqtSignal(str, float, float)
    move_auto_route_point_realtime_signal = pyqtSignal(str, float, float)

    _DEM_CACHE_MAX = 8
    _DEM_MAX_NATIVE_ZOOM = 15

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dem_root = Path(__file__).resolve().parent.parent / "offline_map_cache" / "dem"
        # (zoom, tile_x, tile_y) → (width, height, west, east, south, north, raw_bytes)
        self._dem_tile_cache: dict = {}
        self._dem_cache_order: list = []

    @staticmethod
    def _decode_payload(payload):
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                return None
        return payload if isinstance(payload, dict) else None

    @pyqtSlot(float, float)
    def addWaypoint(self, lat, lon):
        logger.info(f"addWaypoint called: lat={lat}, lon={lon}")
        self.add_waypoint_signal.emit(lat, lon)

    @pyqtSlot(float, float)
    def addWaypointAny(self, lat, lon):
        logger.info(f"addWaypointAny called: lat={lat}, lon={lon}")
        self.add_waypoint_signal.emit(float(lat), float(lon))

    @pyqtSlot(str)
    def addWaypointDetailed(self, lat, lon=None, x=None, y=None, alt=None):
        decoded = self._decode_payload(lat)
        if decoded is not None:
            payload = {
                "lat": float(decoded.get("lat", 0.0) or 0.0),
                "lon": float(decoded.get("lon", 0.0) or 0.0),
                "x": float(decoded.get("x", 0.0) or 0.0),
                "y": float(decoded.get("y", 0.0) or 0.0),
                "alt": float(decoded.get("alt", 0.0) or 0.0),
            }
        else:
            payload = {
                "lat": float(lat or 0.0),
                "lon": float(lon or 0.0),
                "x": float(x or 0.0),
                "y": float(y or 0.0),
                "alt": float(alt or 0.0),
            }

        logger.info(f"addWaypointDetailed called: payload={payload}")
        self.add_waypoint_detail_signal.emit(payload)

    @pyqtSlot(int, float, float)
    @pyqtSlot(float, float, float)
    def moveWaypoint(self, index, lat, lon):
        self.move_waypoint_signal.emit(int(index), float(lat), float(lon))

    @pyqtSlot(int, float, float)
    @pyqtSlot(float, float, float)
    def moveWaypointAny(self, index, lat, lon):
        self.move_waypoint_signal.emit(int(index), float(lat), float(lon))

    @pyqtSlot(int, float, float)
    @pyqtSlot(float, float, float)
    def moveWaypointRealtime(self, index, lat, lon):
        self.move_waypoint_realtime_signal.emit(int(index), float(lat), float(lon))

    @pyqtSlot(int, float, float)
    @pyqtSlot(float, float, float)
    def moveWaypointRealtimeAny(self, index, lat, lon):
        self.move_waypoint_realtime_signal.emit(int(index), float(lat), float(lon))

    @pyqtSlot(int)
    @pyqtSlot(float)
    def selectWaypoint(self, index):
        self.select_waypoint_signal.emit(int(index))

    @pyqtSlot(int)
    @pyqtSlot(float)
    def selectWaypointAny(self, index):
        self.select_waypoint_signal.emit(int(index))

    @pyqtSlot(bool)
    def setAddModeAny(self, enabled):
        self.map_add_mode_signal.emit(bool(enabled))

    @pyqtSlot(bool)
    def setMeasureModeAny(self, enabled):
        self.measure_mode_signal.emit(bool(enabled))

    @pyqtSlot(bool)
    def setFollowModeAny(self, enabled):
        self.follow_mode_signal.emit(bool(enabled))

    @pyqtSlot(str)
    def cacheVisibleRegion(self, payload):
        decoded = self._decode_payload(payload)
        if decoded is not None:
            self.cache_visible_region_signal.emit(decoded)

    @pyqtSlot(str)
    def requestOfflineCacheSummary(self, map_name):
        self.offline_cache_summary_request_signal.emit(str(map_name or ""))

    @pyqtSlot(float, float, float)
    def setHomePoint(self, lat, lon, alt):
        self.home_point_signal.emit(float(lat), float(lon), float(alt))

    @pyqtSlot(str)
    def setHomePointAny(self, payload):
        decoded = self._decode_payload(payload)
        if decoded is not None:
            lat = float(decoded.get("lat", 0.0) or 0.0)
            lon = float(decoded.get("lon", 0.0) or 0.0)
            alt = float(decoded.get("alt", 0.0) or 0.0)
            self.home_point_signal.emit(lat, lon, alt)

    @pyqtSlot(str, float, float)
    def moveAutoRoutePoint(self, name, lat, lon):
        """Handle auto-route point drag completion."""
        self.move_auto_route_point_signal.emit(str(name), float(lat), float(lon))

    @pyqtSlot(str, float, float)
    def moveAutoRoutePointRealtime(self, name, lat, lon):
        """Handle auto-route point dragging in real-time for preview."""
        self.move_auto_route_point_realtime_signal.emit(str(name), float(lat), float(lon))

    @pyqtSlot(int)
    @pyqtSlot(float)
    def insertWaypointAfterAny(self, index):
        self.insert_waypoint_after_signal.emit(int(index))

    @pyqtSlot(int)
    @pyqtSlot(float)
    def deleteWaypointAny(self, index):
        self.delete_waypoint_signal.emit(int(index))

    @pyqtSlot(int)
    @pyqtSlot(float)
    def flyToWaypointAny(self, index):
        self.fly_to_waypoint_signal.emit(int(index))

    @pyqtSlot(int)
    @pyqtSlot(float)
    def uploadWaypointAny(self, index):
        self.upload_waypoint_signal.emit(int(index))

    @pyqtSlot(float, float)
    def homePickedFromMapAny(self, lat, lon):
        self.home_pick_from_map_signal.emit(float(lat), float(lon))

    @pyqtSlot(float, float, int, result=float)
    def getDemElevation(self, lat, lon, zoom):
        try:
            lat = float(lat)
            lon = float(lon)
            zoom = int(zoom)
            if not math.isfinite(lat) or not math.isfinite(lon):
                return float("nan")

            tile_data = self._resolve_dem_tile_with_fallback(lat, lon, zoom)
            if tile_data is None:
                return float("nan")

            width, height, west, east, south, north, raw_bytes = tile_data
            lon_span = east - west
            lat_span = north - south
            if abs(lon_span) < 1e-12 or abs(lat_span) < 1e-12:
                return float("nan")

            x_ratio = (lon - west) / lon_span
            y_ratio = (north - lat) / lat_span
            x = max(0, min(width - 1, int(round(x_ratio * (width - 1)))))
            y = max(0, min(height - 1, int(round(y_ratio * (height - 1)))))
            offset = (y * width + x) * 4

            value = struct.unpack_from("<f", raw_bytes, offset)[0]
            return float(value) if math.isfinite(value) else float("nan")
        except Exception:
            return float("nan")

    def _resolve_dem_tile_with_fallback(self, lat: float, lon: float, zoom: int):
        # Terrarium DEM native zoom is typically <= 15; above that we query from parent tiles.
        max_try_zoom = max(0, min(int(zoom), self._DEM_MAX_NATIVE_ZOOM))
        for candidate_zoom in range(max_try_zoom, -1, -1):
            tile_x, tile_y = self._latlon_to_tile(lat, lon, candidate_zoom)
            cache_key = (candidate_zoom, tile_x, tile_y)
            tile_data = self._dem_tile_cache.get(cache_key)
            if tile_data is not None:
                return tile_data

            meta_path = self._dem_root / str(candidate_zoom) / str(tile_x) / f"{tile_y}.dem.json"
            bin_path = self._dem_root / str(candidate_zoom) / str(tile_x) / f"{tile_y}.dem.bin"
            if not meta_path.exists() or not bin_path.exists():
                continue

            with meta_path.open("r", encoding="utf-8") as f:
                meta = json.load(f)

            width = int(meta.get("width", 256))
            height = int(meta.get("height", 256))
            if width <= 0 or height <= 0:
                continue

            bounds = meta.get("bounds") or {}
            west = float(bounds.get("west", meta.get("west", lon)))
            east = float(bounds.get("east", meta.get("east", lon)))
            south = float(bounds.get("south", meta.get("south", lat)))
            north = float(bounds.get("north", meta.get("north", lat)))

            raw_bytes = bin_path.read_bytes()
            if len(raw_bytes) < width * height * 4:
                continue

            tile_data = (width, height, west, east, south, north, raw_bytes)
            if len(self._dem_cache_order) >= self._DEM_CACHE_MAX:
                evict = self._dem_cache_order.pop(0)
                self._dem_tile_cache.pop(evict, None)
            self._dem_tile_cache[cache_key] = tile_data
            self._dem_cache_order.append(cache_key)
            return tile_data

        return None

    @staticmethod
    def _latlon_to_tile(lat, lon, zoom):
        lat = max(min(lat, 85.05112878), -85.05112878)
        n = 2.0 ** float(zoom)
        x = int((lon + 180.0) / 360.0 * n)
        lat_rad = math.radians(lat)
        y = int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
        x = max(0, min(int(n) - 1, x))
        y = max(0, min(int(n) - 1, y))
        return x, y