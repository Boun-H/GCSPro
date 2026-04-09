import json
import math
import mimetypes
import os
import shutil
import threading
from array import array
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from PyQt6.QtCore import QBuffer, QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QImage
from PyQt6.QtWebEngineCore import QWebEngineUrlRequestJob, QWebEngineUrlSchemeHandler
from core.constants import DEFAULT_LAT, DEFAULT_LON, DEFAULT_ZOOM, MAP_SOURCES
from core.logger import get_app_logger

logger = get_app_logger("GCS.MapController", "map/map_controller.log")


class TileSchemeHandler(QWebEngineUrlSchemeHandler):
    """Serves offline map tiles and elevation data via gcstile:// scheme."""

    def __init__(self, cache_root: Path, parent=None):
        super().__init__(parent)
        self._root = cache_root

    def _resolve_local_path(self, url) -> Path:
        segments: list[str] = []
        host = (url.host() or "").strip("/")
        raw_path = (url.path() or "").strip("/")
        if host:
            segments.extend(part for part in host.split("/") if part)
        if raw_path:
            segments.extend(part for part in raw_path.split("/") if part)
        if not segments:
            return self._root
        return self._root.joinpath(*segments)

    def _resolve_existing_path(self, rel_path: Path) -> Path | None:
        direct_path = rel_path if rel_path.is_absolute() else self._root / rel_path
        if direct_path.is_file():
            return direct_path

        try:
            relative_path = direct_path.relative_to(self._root)
        except ValueError:
            relative_path = rel_path

        parts = relative_path.parts
        try:
            if len(parts) >= 5 and parts[0] == "tiles":
                layer_name = parts[1]
                zoom = int(parts[2])
                tile_x = int(parts[3])
                tile_y = int(Path(parts[4]).stem)
                for parent_zoom in range(zoom - 1, -1, -1):
                    shift = zoom - parent_zoom
                    fallback_x = tile_x >> shift
                    fallback_y = tile_y >> shift
                    fallback_path = self._root / "tiles" / layer_name / str(parent_zoom) / str(fallback_x) / f"{fallback_y}.png"
                    if fallback_path.is_file():
                        return fallback_path

            if len(parts) >= 4 and parts[0] == "elevation":
                zoom = int(parts[1])
                tile_x = int(parts[2])
                tile_y = int(Path(parts[3]).stem)
                for parent_zoom in range(zoom - 1, -1, -1):
                    shift = zoom - parent_zoom
                    fallback_x = tile_x >> shift
                    fallback_y = tile_y >> shift
                    fallback_path = self._root / "elevation" / str(parent_zoom) / str(fallback_x) / f"{fallback_y}.png"
                    if fallback_path.is_file():
                        return fallback_path
        except (TypeError, ValueError):
            return None

        return None

    @staticmethod
    def _guess_mime_type(path: Path) -> bytes:
        suffix = path.suffix.lower()
        if suffix == ".js":
            return b"text/javascript"
        if suffix == ".css":
            return b"text/css"
        if suffix == ".svg":
            return b"image/svg+xml"
        mime_type, _encoding = mimetypes.guess_type(path.name)
        return (mime_type or "application/octet-stream").encode("ascii")

    def requestStarted(self, job: QWebEngineUrlRequestJob):
        rel_path = self._resolve_local_path(job.requestUrl())
        local_path = self._resolve_existing_path(rel_path)
        if local_path and local_path.is_file():
            buf = QBuffer(parent=job)
            buf.setData(local_path.read_bytes())
            buf.open(QBuffer.OpenModeFlag.ReadOnly)
            job.reply(self._guess_mime_type(local_path), buf)
        else:
            job.fail(QWebEngineUrlRequestJob.Error.UrlNotFound)


OFFLINE_CACHE_DIR = Path(__file__).resolve().parent.parent / "offline_map_cache"
OFFLINE_TILE_DIR = OFFLINE_CACHE_DIR / "tiles"
OFFLINE_ELEVATION_DIR = OFFLINE_CACHE_DIR / "elevation"
OFFLINE_DEM_DIR = OFFLINE_CACHE_DIR / "dem"
ELEVATION_TERRARIUM_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
MAP_CACHE_DIR_NAMES = {
    "谷歌卫星": "google_satellite",
    "ArcGIS卫星": "arcgis_satellite",
}


class MapController(QObject):
    offline_cache_progress_signal = pyqtSignal(dict)
    offline_cache_summary_signal = pyqtSignal(dict)

    def __init__(self, web_view, map_bridge, parent=None):
        super().__init__(parent)
        OFFLINE_TILE_DIR.mkdir(parents=True, exist_ok=True)
        OFFLINE_ELEVATION_DIR.mkdir(parents=True, exist_ok=True)
        OFFLINE_DEM_DIR.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_cache_dirs()
        self.web_view = web_view
        self.map_bridge = map_bridge
        self.current_map = "谷歌卫星"
        self.current_center = [DEFAULT_LAT, DEFAULT_LON]
        self.current_zoom = DEFAULT_ZOOM
        self.add_mode_enabled = False
        self.vehicle_position = None
        self.home_position = None
        self._page_ready = False
        self._pending_waypoints = []
        self._pending_auto_route = []
        self._rendered_waypoints = []
        self._pending_map_source = self.current_map
        self._cache_jobs = set()
        self._cache_jobs_lock = threading.Lock()
        self._last_waypoint_payload = None
        self._last_auto_route_payload = None
        self._last_vehicle_payload = None
        self._last_home_payload = None
        self._overlay_state = {
            "home": None,
            "vehicle": None,
            "measureMode": False,
            "followAircraft": False,
        }
        self._last_overlay_payload = None
        self._map_init_retries = 0
        self._tile_handler = TileSchemeHandler(OFFLINE_CACHE_DIR, parent=self)
        self.offline_cache_progress_signal.connect(self._push_offline_cache_progress)
        self.offline_cache_summary_signal.connect(self._push_offline_cache_summary)
        self.web_view.page().profile().installUrlSchemeHandler(b"gcstile", self._tile_handler)
        self.web_view.loadFinished.connect(self._on_load_finished)
        self.map_bridge.cache_visible_region_signal.connect(self.cache_visible_region)
        self.map_bridge.offline_cache_summary_request_signal.connect(self.request_offline_cache_summary)

    def initialize(self, map_name: str, center=None, zoom=None):
        self.current_map = map_name
        self.current_center = center or [DEFAULT_LAT, DEFAULT_LON]
        self.current_zoom = zoom or DEFAULT_ZOOM
        self._pending_map_source = self.current_map
        self._page_ready = False
        self.web_view.setHtml(self._build_html())

    def set_map_source(self, map_name: str):
        self.current_map = map_name
        self._pending_map_source = map_name
        if self._page_ready:
            self.web_view.page().runJavaScript(
                f"window.setMapSource({json.dumps(map_name, ensure_ascii=False)});"
            )
            self.request_offline_cache_summary(map_name)

    def set_center(self, lat: float, lon: float):
        self.current_center = [lat, lon]
        if self._page_ready:
            self.web_view.page().runJavaScript(f"window.map.setView([{lat}, {lon}], window.map.getZoom());")
            self._schedule_cache_for_center(self.current_map, lat, lon, self.current_zoom)

    def update_waypoints(self, waypoints: list):
        self._pending_waypoints = [dict(item) for item in waypoints]
        payload = json.dumps(self._pending_waypoints, ensure_ascii=False, separators=(",", ":"))
        if not self._page_ready:
            return
        if payload == self._last_waypoint_payload or not waypoints:
            return
        self._last_waypoint_payload = payload
        new_waypoints = [dict(item) for item in waypoints]
        if not self._rendered_waypoints:
            self.web_view.page().runJavaScript(f"window.updateWaypoints({payload});")
            self._rendered_waypoints = new_waypoints
            return

        old_keys = [self._waypoint_signature(item) for item in self._rendered_waypoints]
        new_keys = [self._waypoint_signature(item) for item in new_waypoints]
        prefix = 0
        max_prefix = min(len(old_keys), len(new_keys))
        while prefix < max_prefix and old_keys[prefix] == new_keys[prefix]:
            prefix += 1

        suffix = 0
        max_suffix = min(len(old_keys), len(new_keys)) - prefix
        while suffix < max_suffix and old_keys[len(old_keys) - 1 - suffix] == new_keys[len(new_keys) - 1 - suffix]:
            suffix += 1

        if prefix == len(old_keys) == len(new_keys):
            self._rendered_waypoints = new_waypoints
            return

        remove_count = len(old_keys) - prefix - suffix
        insert_items = new_waypoints[prefix:len(new_waypoints) - suffix]
        if prefix == 0 and suffix == 0 and (len(old_keys) + len(new_keys)) > 20:
            self.web_view.page().runJavaScript(f"window.updateWaypoints({payload});")
        else:
            delta_payload = json.dumps(insert_items, ensure_ascii=False, separators=(",", ":"))
            self.web_view.page().runJavaScript(
                f"if (window.syncWaypointRange) window.syncWaypointRange({prefix}, {remove_count}, {delta_payload});"
            )
        self._rendered_waypoints = new_waypoints
        self._last_waypoint_payload = payload
        new_waypoints = [dict(item) for item in waypoints]
        if not self._rendered_waypoints:
            self.web_view.page().runJavaScript(f"window.updateWaypoints({payload});")
            self._rendered_waypoints = new_waypoints
            return

        old_keys = [self._waypoint_signature(item) for item in self._rendered_waypoints]
        new_keys = [self._waypoint_signature(item) for item in new_waypoints]
        prefix = 0
        max_prefix = min(len(old_keys), len(new_keys))
        while prefix < max_prefix and old_keys[prefix] == new_keys[prefix]:
            prefix += 1

        suffix = 0
        max_suffix = min(len(old_keys), len(new_keys)) - prefix
        while suffix < max_suffix and old_keys[len(old_keys) - 1 - suffix] == new_keys[len(new_keys) - 1 - suffix]:
            suffix += 1

        if prefix == len(old_keys) == len(new_keys):
            self._rendered_waypoints = new_waypoints
            return

        remove_count = len(old_keys) - prefix - suffix
        insert_items = new_waypoints[prefix:len(new_waypoints) - suffix]
        if prefix == 0 and suffix == 0 and (len(old_keys) + len(new_keys)) > 20:
            self.web_view.page().runJavaScript(f"window.updateWaypoints({payload});")
        else:
            delta_payload = json.dumps(insert_items, ensure_ascii=False, separators=(",", ":"))
            self.web_view.page().runJavaScript(
                f"if (window.syncWaypointRange) window.syncWaypointRange({prefix}, {remove_count}, {delta_payload});"
            )
        self._rendered_waypoints = new_waypoints

    def set_vehicle_position(self, lat: float, lon: float, altitude: float, heading: float = 0.0):
        self.vehicle_position = {
            "lat": lat,
            "lon": lon,
            "altitude": altitude,
            "heading": heading,
        }
        self._overlay_state["vehicle"] = self.vehicle_position.copy()
        vehicle_payload = {
            "lat": round(float(lat), 7),
            "lon": round(float(lon), 7),
            "altitude": round(float(altitude), 1),
            "heading": round(float(heading), 1),
        }
        if not self._page_ready:
            return
        if vehicle_payload == self._last_vehicle_payload:
            return
        self._last_vehicle_payload = vehicle_payload
        self._sync_overlay_state({"vehicle": self.vehicle_position})

    def set_home_position(self, waypoint: dict | None):
        self.home_position = waypoint
        self._overlay_state["home"] = waypoint.copy() if isinstance(waypoint, dict) else None
        home_payload = json.dumps(self.home_position, ensure_ascii=False, separators=(",", ":"))
        if not self._page_ready:
            return
        if home_payload == self._last_home_payload:
            return
        self._last_home_payload = home_payload
        self._sync_overlay_state({"home": self.home_position})

    def update_auto_route(self, route_items: list[dict] | None = None):
        """Update takeoff/landing route overlay on map with geometric constraints."""
        self._pending_auto_route = [dict(item) for item in (route_items or [])]
        route_payload = json.dumps(self._pending_auto_route, ensure_ascii=False, separators=(",", ":"))
        home_payload = json.dumps(self.home_position or {}, ensure_ascii=False, separators=(",", ":"))
        if not self._page_ready:
            return
        cache_key = f"{route_payload}|{home_payload}"
        if cache_key == self._last_auto_route_payload:
            return
        self._last_auto_route_payload = cache_key
        self.web_view.page().runJavaScript(
            f"if (window.updateAutoRoute) window.updateAutoRoute({route_payload}, {home_payload});"
        )

    def clear_vehicle_position(self):
        self.vehicle_position = None
        self._overlay_state["vehicle"] = None
        self._last_vehicle_payload = None
        if self._page_ready:
            self._sync_overlay_state({"vehicle": None})

    def set_measure_mode(self, enabled: bool):
        self._overlay_state["measureMode"] = bool(enabled)
        if self._page_ready:
            self._sync_overlay_state({"measureMode": bool(enabled)})

    def is_measure_mode_enabled(self) -> bool:
        return bool(self._overlay_state.get("measureMode", False))

    def toggle_measure_mode(self):
        self.set_measure_mode(not self.is_measure_mode_enabled())

    def clear_measure(self):
        self._overlay_state["measureMode"] = False
        if self._page_ready:
            self.web_view.page().runJavaScript("if (window.clearMeasure) window.clearMeasure();")
            self._sync_overlay_state({"measureMode": False})

    def set_follow_aircraft(self, enabled: bool):
        self._overlay_state["followAircraft"] = bool(enabled)
        if self._page_ready:
            self._sync_overlay_state({"followAircraft": bool(enabled)})

    def is_follow_aircraft_enabled(self) -> bool:
        return bool(self._overlay_state.get("followAircraft", False))

    def toggle_follow_aircraft(self):
        self.set_follow_aircraft(not self.is_follow_aircraft_enabled())

    def fit_mission_route(self):
        if self._page_ready:
            self.web_view.page().runJavaScript("if (window.fitMissionRoute) window.fitMissionRoute();")

    def locate_aircraft(self):
        if self._page_ready:
            self.web_view.page().runJavaScript("if (window.locateAircraft) window.locateAircraft();")

    def _sync_overlay_state(self, payload: dict | None = None, force: bool = False):
        if not self._page_ready:
            return
        merged = payload if payload is not None else self._overlay_state
        data = json.dumps(merged, ensure_ascii=False, separators=(",", ":"))
        if not force and payload is None and data == self._last_overlay_payload:
            return
        if payload is None:
            self._last_overlay_payload = data
        self.web_view.page().runJavaScript(f"if (window.applyOverlayState) window.applyOverlayState({data});")

    def move_waypoint(self, index: int, waypoint: dict):
        if not self._page_ready:
            return
        if 0 <= index < len(self._rendered_waypoints):
            self._rendered_waypoints[index] = dict(waypoint)
            self._last_waypoint_payload = json.dumps(self._rendered_waypoints, ensure_ascii=False, separators=(",", ":"))
        payload = json.dumps(waypoint, ensure_ascii=False, separators=(",", ":"))
        self.web_view.page().runJavaScript(
            f"if (window.moveWaypointMarker) window.moveWaypointMarker({int(index)}, {payload});"
        )

    def select_waypoint_on_map(self, index: int):
        if not self._page_ready:
            return
        self.web_view.page().runJavaScript(
            f"if (window.selectWaypointOnMap) window.selectWaypointOnMap({int(index)});"
        )

    def set_home_pick_mode(self, enabled: bool):
        if not self._page_ready:
            return
        state = 'true' if enabled else 'false'
        self.web_view.page().runJavaScript(
            f"if (window.setHomePickMode) window.setHomePickMode({state});"
        )

    @staticmethod
    def _waypoint_signature(waypoint: dict) -> str:
        return json.dumps(waypoint, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def set_add_mode(self, enabled: bool):
        self.add_mode_enabled = enabled
        logger.info(f"set_add_mode called: enabled={enabled}, _page_ready={self._page_ready}")
        if self._page_ready:
            state = 'true' if enabled else 'false'
            js_code = f"window.setAddWaypointMode({state});"
            logger.info(f"Executing JavaScript: {js_code}")
            self.web_view.page().runJavaScript(js_code)

    def _on_load_finished(self, ok: bool):
        if not ok:
            self._page_ready = False
            logger.warning("map page load failed (ok=False)")
            return
        # HTML loaded but Leaflet JS may still be initializing (or CDN failed).
        # Poll window.mapReady instead of dispatching JS calls immediately.
        self._page_ready = False
        self._map_init_retries = 0
        self._poll_map_ready()

    def _poll_map_ready(self):
        """Poll window.mapReady at 200 ms intervals; dispatch map init once JS confirms ready."""
        def on_result(value):
            if value:
                self._page_ready = True
                self._last_waypoint_payload = None
                self._last_auto_route_payload = None
                self._last_vehicle_payload = None
                self._last_home_payload = None
                self._last_overlay_payload = None
                self._rendered_waypoints = []
                self.set_map_source(self._pending_map_source)
                self.set_add_mode(self.add_mode_enabled)
                self._sync_overlay_state(force=True)
                self.update_waypoints(self._pending_waypoints)
                self.update_auto_route(self._pending_auto_route)
                self._schedule_cache_for_center(
                    self._pending_map_source,
                    float(self.current_center[0]),
                    float(self.current_center[1]),
                    int(self.current_zoom),
                )
                self.web_view.page().runJavaScript(
                    "if (window.requestOfflineCache) window.requestOfflineCache();"
                )
                self.request_offline_cache_summary(self._pending_map_source)
            elif self._map_init_retries < 20:
                self._map_init_retries += 1
                QTimer.singleShot(200, self._poll_map_ready)
            else:
                logger.error(
                    "map JavaScript initialization timed out after %d retries "
                    "- Leaflet CDN may be unreachable",
                    self._map_init_retries,
                )
        self.web_view.page().runJavaScript("!!(window.mapReady)", on_result)

    def cache_visible_region(self, payload: dict):
        try:
            map_name = str(payload.get("map_name", self.current_map) or self.current_map)
            zoom = int(payload.get("zoom", self.current_zoom) or self.current_zoom)
            x_min = int(payload.get("x_min"))
            x_max = int(payload.get("x_max"))
            y_min = int(payload.get("y_min"))
            y_max = int(payload.get("y_max"))
        except Exception:
            logger.warning("Invalid offline cache payload: %s", payload)
            return

        if map_name not in MAP_SOURCES:
            logger.warning("Unknown map source for cache request: %s", map_name)
            return

        if x_max < x_min or y_max < y_min or zoom < 0:
            logger.warning("Invalid tile range for cache request: %s", payload)
            return

        logger.info(
            "Cache request accepted: source=%s z=%s x=[%s,%s] y=[%s,%s]",
            map_name,
            zoom,
            x_min,
            x_max,
            y_min,
            y_max,
        )

        max_span = 18
        if (x_max - x_min) > max_span or (y_max - y_min) > max_span:
            logger.info("Tile range too large, clipping cache request: %s", payload)
            x_max = min(x_max, x_min + max_span)
            y_max = min(y_max, y_min + max_span)

        total_tiles = (x_max - x_min + 1) * (y_max - y_min + 1)
        self.current_zoom = zoom
        job_key = (map_name, zoom, x_min, x_max, y_min, y_max)
        with self._cache_jobs_lock:
            if job_key in self._cache_jobs:
                self._emit_offline_cache_progress(
                    map_name,
                    zoom,
                    total_tiles,
                    total_tiles,
                    "duplicate",
                    f"{map_name} Z{zoom} 的同一区域已在后台队列中。",
                )
                return
            self._cache_jobs.add(job_key)

        self._emit_offline_cache_progress(
            map_name,
            zoom,
            0,
            total_tiles,
            "queued",
            f"已加入后台下载：{map_name} Z{zoom}（共 {total_tiles} 张瓦片）",
        )

        worker = threading.Thread(
            target=self._download_offline_region,
            args=(job_key,),
            daemon=True,
            name=f"cache-{map_name}-{zoom}-{x_min}-{y_min}",
        )
        worker.start()

    def _download_offline_region(self, job_key):
        map_name, zoom, x_min, x_max, y_min, y_max = job_key
        total = (x_max - x_min + 1) * (y_max - y_min + 1)
        downloaded = 0
        new_tiles = 0
        reused_tiles = 0
        try:
            OFFLINE_TILE_DIR.mkdir(parents=True, exist_ok=True)
            OFFLINE_DEM_DIR.mkdir(parents=True, exist_ok=True)
            tile_tpl = MAP_SOURCES[map_name]["tiles"]
            dem_zoom = min(int(zoom), 15)
            dem_scale = 1 << max(0, int(zoom) - dem_zoom)
            requested_dem_tiles = set()
            map_dir_name = self._map_cache_dir_name(map_name)
            progress_step = max(1, total // 8)

            self._emit_offline_cache_progress(
                map_name,
                zoom,
                0,
                total,
                "running",
                f"开始缓存 {map_name} Z{zoom}…",
            )

            for x in range(x_min, x_max + 1):
                for y in range(y_min, y_max + 1):
                    tile_url = tile_tpl.format(x=x, y=y, z=zoom)
                    tile_path = OFFLINE_TILE_DIR / map_dir_name / str(zoom) / str(x) / f"{y}.png"

                    tile_state = self._download_if_missing(tile_url, tile_path)
                    if tile_state == "downloaded":
                        new_tiles += 1
                    elif tile_state == "cached":
                        reused_tiles += 1

                    dem_x = x // dem_scale
                    dem_y = y // dem_scale
                    dem_key = (dem_zoom, dem_x, dem_y)
                    if dem_key not in requested_dem_tiles:
                        requested_dem_tiles.add(dem_key)
                        self._download_and_convert_dem_direct(
                            ELEVATION_TERRARIUM_URL.format(x=dem_x, y=dem_y, z=dem_zoom),
                            dem_zoom,
                            dem_x,
                            dem_y,
                        )
                    downloaded += 1
                    if downloaded == 1 or downloaded == total or (downloaded % progress_step) == 0:
                        self._emit_offline_cache_progress(
                            map_name,
                            zoom,
                            downloaded,
                            total,
                            "running",
                            f"正在缓存 {map_name} Z{zoom}：{downloaded}/{total}",
                            new_tiles=new_tiles,
                            reused_tiles=reused_tiles,
                        )

            logger.info(
                "Offline cache ready: source=%s z=%s x=[%s,%s] y=[%s,%s] tiles=%s",
                map_name,
                zoom,
                x_min,
                x_max,
                y_min,
                y_max,
                downloaded,
            )
            self._emit_offline_cache_progress(
                map_name,
                zoom,
                total,
                total,
                "done",
                f"缓存完成：{map_name} Z{zoom}，新增 {new_tiles} 张，复用 {reused_tiles} 张",
                new_tiles=new_tiles,
                reused_tiles=reused_tiles,
            )
            self.request_offline_cache_summary(map_name)
        except Exception as exc:
            logger.warning("Offline cache download failed: %s", exc)
            self._emit_offline_cache_progress(
                map_name,
                zoom,
                downloaded,
                total,
                "error",
                f"缓存失败：{map_name} Z{zoom}（{exc}）",
                new_tiles=new_tiles,
                reused_tiles=reused_tiles,
            )
        finally:
            with self._cache_jobs_lock:
                self._cache_jobs.discard(job_key)

    def _download_and_convert_dem_direct(self, elev_url: str, z: int, x: int, y: int):
        """
        Download elevation tile directly and convert to DEM without saving intermediate PNG.
        """
        dem_bin = OFFLINE_DEM_DIR / str(z) / str(x) / f"{y}.dem.bin"
        dem_meta = OFFLINE_DEM_DIR / str(z) / str(x) / f"{y}.dem.json"
        if dem_bin.exists() and dem_meta.exists():
            return
        
        try:
            req = Request(elev_url, headers={"User-Agent": "GCSPro/1.0"})
            with urlopen(req, timeout=8) as resp:
                png_data = resp.read()
            
            image = QImage()
            if not image.loadFromData(png_data):
                return
            self._write_dem_from_qimage(image, z, x, y, dem_bin, dem_meta)
        except Exception as exc:
            logger.debug("DEM conversion failed for tile z=%s x=%s y=%s: %s", z, x, y, exc)

    @staticmethod
    def _download_if_missing(url: str, target: Path) -> str:
        if target.exists() and target.stat().st_size > 0:
            return "cached"
        target.parent.mkdir(parents=True, exist_ok=True)
        req = Request(url, headers={"User-Agent": "GCSPro/1.0"})
        try:
            with urlopen(req, timeout=8) as resp:
                data = resp.read()
                if data:
                    target.write_bytes(data)
                    return "downloaded"
        except (HTTPError, URLError, TimeoutError, OSError):
            return "failed"
        return "failed"

    def _convert_terrarium_to_dem(self, terrarium_path: Path):
        try:
            z = int(terrarium_path.parent.parent.name)
            x = int(terrarium_path.parent.name)
            y = int(terrarium_path.stem)
        except Exception:
            return

        dem_bin = OFFLINE_DEM_DIR / str(z) / str(x) / f"{y}.dem.bin"
        dem_meta = OFFLINE_DEM_DIR / str(z) / str(x) / f"{y}.dem.json"
        if dem_bin.exists() and dem_meta.exists():
            return

        image = QImage(str(terrarium_path))
        if image.isNull():
            return

        self._write_dem_from_qimage(image, z, x, y, dem_bin, dem_meta)

    def _write_dem_from_qimage(self, image: QImage, z: int, x: int, y: int, dem_bin: Path, dem_meta: Path):
        width = image.width()
        height = image.height()
        values = array('f')
        min_elev = float('inf')
        max_elev = float('-inf')

        for py in range(height):
            for px in range(width):
                color = image.pixelColor(px, py)
                elevation = (color.red() * 256.0 + color.green() + color.blue() / 256.0) - 32768.0
                values.append(float(elevation))
                if elevation < min_elev:
                    min_elev = elevation
                if elevation > max_elev:
                    max_elev = elevation

        dem_bin.parent.mkdir(parents=True, exist_ok=True)
        with open(dem_bin, 'wb') as f:
            values.tofile(f)

        bounds = self._tile_bounds(z, x, y)
        meta = {
            "format": "float32_le",
            "source": "terrarium",
            "z": z,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "min_elevation_m": round(min_elev, 3),
            "max_elevation_m": round(max_elev, 3),
            "bounds": bounds,
            "data_file": dem_bin.name,
        }
        dem_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')

    @staticmethod
    def _tile_bounds(z: int, x: int, y: int) -> dict:
        n = 2.0 ** z
        west = x / n * 360.0 - 180.0
        east = (x + 1) / n * 360.0 - 180.0

        def tile2lat(ty: int) -> float:
            merc = math.pi * (1.0 - 2.0 * ty / n)
            return math.degrees(math.atan(math.sinh(merc)))

        north = tile2lat(y)
        south = tile2lat(y + 1)
        return {
            "west": west,
            "east": east,
            "north": north,
            "south": south,
        }

    def _schedule_cache_for_center(self, map_name: str, lat: float, lon: float, zoom: int):
        if map_name not in MAP_SOURCES:
            return
        try:
            z = max(0, int(zoom))
            n = 2 ** z
            x = int((float(lon) + 180.0) / 360.0 * n)
            lat_rad = math.radians(float(lat))
            y = int((1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
            r = 2
            payload = {
                "map_name": map_name,
                "zoom": z,
                "x_min": max(0, x - r),
                "x_max": min(n - 1, x + r),
                "y_min": max(0, y - r),
                "y_max": min(n - 1, y + r),
            }
            logger.info("Trigger center-based cache: %s", payload)
            self.cache_visible_region(payload)
        except Exception as exc:
            logger.warning("Center cache scheduling failed: %s", exc)

    def _has_offline_tiles(self, map_name: str) -> bool:
        dir_name = self._map_cache_dir_name(map_name)
        root = OFFLINE_TILE_DIR / dir_name
        if not root.exists():
            return False
        return next(root.rglob("*.png"), None) is not None

    def request_offline_cache_summary(self, map_name: str | None = None):
        source_name = str(map_name or self.current_map or "")
        if source_name not in MAP_SOURCES:
            source_name = self.current_map if self.current_map in MAP_SOURCES else next(iter(MAP_SOURCES), "")
        if not source_name:
            return
        self.offline_cache_summary_signal.emit(self._collect_offline_cache_summary(source_name))

    def _emit_offline_cache_progress(
        self,
        map_name: str,
        zoom: int,
        current: int,
        total: int,
        status: str,
        message: str,
        *,
        new_tiles: int = 0,
        reused_tiles: int = 0,
    ):
        safe_total = max(0, int(total or 0))
        safe_current = max(0, min(safe_total or max(0, int(current or 0)), int(current or 0)))
        percent = round((safe_current / safe_total) * 100.0, 1) if safe_total > 0 else 0.0
        self.offline_cache_progress_signal.emit({
            "mapName": str(map_name or self.current_map),
            "zoom": int(zoom or 0),
            "current": safe_current,
            "total": safe_total,
            "percent": percent,
            "status": str(status or "idle"),
            "message": str(message or ""),
            "newTiles": max(0, int(new_tiles or 0)),
            "reusedTiles": max(0, int(reused_tiles or 0)),
        })

    def _push_offline_cache_progress(self, payload: dict):
        if not self._page_ready:
            return
        data = json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":"))
        self.web_view.page().runJavaScript(
            f"if (window.updateOfflineCacheProgress) window.updateOfflineCacheProgress({data});"
        )

    def _push_offline_cache_summary(self, summary: dict):
        if not self._page_ready:
            return
        data = json.dumps(summary or {}, ensure_ascii=False, separators=(",", ":"))
        self.web_view.page().runJavaScript(
            f"if (window.updateOfflineCacheCoverage) window.updateOfflineCacheCoverage({data});"
        )

    def _collect_offline_cache_summary(self, map_name: str) -> dict:
        dir_name = self._map_cache_dir_name(map_name)
        root = OFFLINE_TILE_DIR / dir_name
        summary = {
            "mapName": map_name,
            "available": False,
            "tileCount": 0,
            "zoomMin": None,
            "zoomMax": None,
            "west": None,
            "east": None,
            "south": None,
            "north": None,
            "message": f"{map_name} 暂无已缓存瓦片，可先下载当前视野。",
        }
        if not root.exists():
            return summary

        tile_count = 0
        zoom_levels: set[int] = set()
        west = east = south = north = None
        for tile_path in root.rglob("*.png"):
            try:
                zoom = int(tile_path.parent.parent.name)
                tile_x = int(tile_path.parent.name)
                tile_y = int(tile_path.stem)
            except (TypeError, ValueError):
                continue
            tile_count += 1
            zoom_levels.add(zoom)
            bounds = self._tile_bounds(zoom, tile_x, tile_y)
            west = bounds["west"] if west is None else min(west, bounds["west"])
            east = bounds["east"] if east is None else max(east, bounds["east"])
            south = bounds["south"] if south is None else min(south, bounds["south"])
            north = bounds["north"] if north is None else max(north, bounds["north"])

        if tile_count <= 0 or not zoom_levels:
            return summary

        summary.update({
            "available": True,
            "tileCount": tile_count,
            "zoomMin": min(zoom_levels),
            "zoomMax": max(zoom_levels),
            "west": round(float(west), 5) if west is not None else None,
            "east": round(float(east), 5) if east is not None else None,
            "south": round(float(south), 5) if south is not None else None,
            "north": round(float(north), 5) if north is not None else None,
            "message": (
                f"{map_name} · {tile_count} 张瓦片 · Z{min(zoom_levels)}-Z{max(zoom_levels)}"
                + (
                    f" · 纬 {float(south):.3f}~{float(north):.3f} · 经 {float(west):.3f}~{float(east):.3f}"
                    if None not in (south, north, west, east)
                    else ""
                )
            ),
        })
        return summary

    def _build_html(self) -> str:
        force_offline_bootstrap = str(os.environ.get("GCS_FORCE_OFFLINE_MAP", "")).strip().lower() in {"1", "true", "yes", "on"}
        tile_config = {
            name: {
                "tiles": source["tiles"],
                "attr": source["attr"],
                "maxZoom": 21,
                "offline": self._offline_tile_template(name),
                "offlineAvailable": self._has_offline_tiles(name),
                "dem_online": ELEVATION_TERRARIUM_URL,
                "dem_offline": self._offline_elevation_template(),
            }
            for name, source in MAP_SOURCES.items()
        }
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <style>
        html, body, #map {{ height: 100%; margin: 0; padding: 0; }}
        #mapStatus {{
            position: absolute;
            top: 12px;
            left: 12px;
            z-index: 1200;
            max-width: min(420px, calc(100vw - 24px));
            padding: 8px 10px;
            border-radius: 10px;
            background: rgba(15, 23, 42, 0.86);
            color: #f8fafc;
            border: 1px solid rgba(148, 163, 184, 0.32);
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.22);
            font-size: 12px;
            line-height: 1.4;
            display: none;
        }}
        #mapStatus.error {{
            background: rgba(127, 29, 29, 0.92);
            border-color: rgba(252, 165, 165, 0.4);
        }}
        #mapStatus.warning {{
            background: rgba(120, 53, 15, 0.92);
            border-color: rgba(253, 186, 116, 0.4);
        }}
        .leaflet-top.leaflet-right {{
            margin-top: 265px;
            margin-right: 2px;
        }}
        .leaflet-top .leaflet-control-zoom {{
            clear: none;
            float: left;
            margin: 0;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 8px 18px rgba(15, 23, 42, 0.28);
        }}
        .leaflet-top .leaflet-control.zoom-level-control {{
            clear: none;
            float: left;
            margin: 15px 6px 0 0;
            background: transparent;
            border: none;
            box-shadow: none;
        }}
        .zoom-level-pill {{
            min-width: 64px;
            height: 58px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 3px;
            border-radius: 8px;
            border: 1px solid rgba(148, 163, 184, 0.55);
            background: rgba(15, 23, 42, 0.9);
            color: #e2e8f0;
            font-size: 11px;
            font-weight: 700;
            line-height: 1;
            user-select: none;
        }}
        .zoom-level-pill span {{
            font-size: 17px;
            font-weight: 800;
            color: #f8fafc;
        }}
        .waypoint-badge {{
            display: inline-flex;
            justify-content: center;
            align-items: center;
            width: 28px;
            height: 28px;
            font-size: 14px;
            font-weight: bold;
            color: #fff;
            background: #007bff;
            border: 2px solid #ffffff;
            border-radius: 50%;
            box-shadow: 0 0 4px rgba(0, 0, 0, 0.35);
            pointer-events: none;
        }}
        .waypoint-badge.takeoff {{ background: #17a34a; }}
        .waypoint-badge.land {{ background: #dc2626; }}
        .waypoint-badge.rtl {{ background: #f59e0b; color: #1f2937; }}
        .waypoint-badge.start {{
            background: #0f766e;
            box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.18), 0 0 4px rgba(0, 0, 0, 0.35);
        }}
        .waypoint-badge.selected {{
            background: #16a34a;
            width: 32px;
            height: 32px;
            font-size: 16px;
            border-width: 3px;
            box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.55), 0 0 10px rgba(22, 163, 74, 0.45);
        }}
        .wpt-ctx-menu {{
            position: absolute;
            z-index: 9000;
            background: rgba(15, 22, 36, 0.97);
            border: 1px solid #3d5a7a;
            border-radius: 8px;
            padding: 4px 0;
            min-width: 144px;
            box-shadow: 0 8px 24px rgba(2, 6, 23, 0.5);
            display: none;
            user-select: none;
        }}
        .wpt-ctx-item {{
            padding: 7px 16px;
            color: #d9e6f8;
            font-size: 13px;
            cursor: pointer;
            line-height: 1.4;
        }}
        .wpt-ctx-item:hover {{ background: rgba(50, 100, 160, 0.3); }}
        .wpt-ctx-item.danger {{ color: #f87171; }}
        .wpt-ctx-item.danger:hover {{ background: rgba(160, 40, 40, 0.25); }}
        .wpt-ctx-sep {{ border: none; border-top: 1px solid #293f5a; margin: 3px 0; }}
        .vehicle-marker {{
            width: 40px;
            height: 40px;
            display: flex;
            align-items: center;
            justify-content: center;
            filter: drop-shadow(0 2px 8px rgba(15, 23, 42, 0.35));
        }}
        .map-legend {{
            position: absolute;
            right: 14px;
            bottom: 14px;
            z-index: 999;
            background: rgba(255, 255, 255, 0.94);
            border: 1px solid rgba(15, 23, 42, 0.12);
            border-radius: 12px;
            padding: 10px 12px;
            box-shadow: 0 10px 24px rgba(15, 23, 42, 0.12);
            font-size: 12px;
            color: #17324d;
        }}
        .map-legend-title {{
            font-weight: 700;
            margin-bottom: 8px;
        }}
        .map-legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 6px;
        }}
        .map-legend-item:last-child {{
            margin-bottom: 0;
        }}
        .legend-dot {{
            width: 16px;
            height: 16px;
            border-radius: 50%;
            border: 2px solid #fff;
            box-shadow: 0 0 4px rgba(0, 0, 0, 0.22);
        }}
        .legend-dot.start {{ background: #0f766e; }}
        .legend-dot.route {{ background: #007bff; }}
        .legend-aircraft {{
            width: 18px;
            height: 18px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
        }}
        .map-toolbar {{
            position: absolute;
            left: 50%;
            bottom: 8px;
            transform: translateX(-50%);
            z-index: 1100;
            display: flex;
            align-items: center;
            gap: 8px;
            width: 750px;
            background: rgba(19, 26, 37, 0.92);
            border: 1px solid rgba(148, 163, 184, 0.35);
            border-radius: 12px;
            padding: 8px 10px;
            color: #e5eefc;
            font-size: 12px;
            box-shadow: 0 8px 16px rgba(2, 6, 23, 0.35);
            backdrop-filter: blur(2px);
        }}
        .map-toolbar-data {{
            display: flex;
            align-items: center;
            gap: 12px;
            white-space: nowrap;
            padding: 0 6px;
            flex: 1;
            min-width: 0;
            overflow-x: auto;
            scrollbar-width: thin;
        }}
        .map-toolbar-btn {{
            min-width: 34px;
            height: 28px;
            border: 1px solid #4b5f79;
            border-radius: 6px;
            background: #233246;
            color: #e6f0ff;
            cursor: pointer;
            font-size: 12px;
            font-weight: 700;
            padding: 0 8px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 4px;
        }}
        .map-toolbar-btn:hover {{
            background: #2d3f56;
        }}
        .map-toolbar-btn.active {{
            background: #1d4ed8;
            border-color: #60a5fa;
        }}
        .map-toolbar-btn.disabled {{
            opacity: 0.45;
            cursor: not-allowed;
            pointer-events: auto;
        }}
        .map-toolbar-btn .icon {{
            font-size: 13px;
            line-height: 1;
        }}
        .map-toolbar-btn .label {{
            line-height: 1;
        }}
        .map-toolbar-sep {{
            width: 1px;
            height: 18px;
            background: rgba(148, 163, 184, 0.4);
        }}
        .map-download-panel {{
            position: absolute;
            left: 50%;
            bottom: 52px;
            transform: translateX(-50%);
            z-index: 1150;
            width: min(380px, calc(100vw - 16px));
            display: none;
            flex-direction: column;
            gap: 8px;
            padding: 10px 12px;
            border-radius: 12px;
            background: rgba(15, 23, 42, 0.96);
            color: #e5eefc;
            border: 1px solid rgba(148, 163, 184, 0.35);
            box-shadow: 0 12px 28px rgba(2, 6, 23, 0.42);
        }}
        .map-download-panel.open {{
            display: flex;
        }}
        .map-download-title {{
            font-size: 13px;
            font-weight: 700;
            color: #f8fafc;
        }}
        .map-download-row {{
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .map-download-row label {{
            width: 48px;
            color: #cbd5e1;
            font-size: 12px;
            flex: 0 0 auto;
        }}
        .map-download-row select,
        .map-download-row input {{
            flex: 1;
            min-width: 0;
            height: 30px;
            border-radius: 7px;
            border: 1px solid #4b5f79;
            background: #172233;
            color: #f8fafc;
            padding: 0 8px;
            font-size: 12px;
        }}
        .map-download-inline {{
            display: flex;
            align-items: center;
            gap: 6px;
            flex: 1;
        }}
        .map-download-inline span {{
            color: #94a3b8;
            font-size: 12px;
        }}
        .map-download-actions {{
            display: flex;
            flex-wrap: wrap;
            justify-content: flex-end;
            gap: 8px;
        }}
        .map-download-btn {{
            min-width: 88px;
            height: 30px;
            border: 1px solid #4b5f79;
            border-radius: 7px;
            background: #233246;
            color: #e6f0ff;
            cursor: pointer;
            font-size: 12px;
            font-weight: 700;
            padding: 0 10px;
        }}
        .map-download-btn.primary {{
            background: #1d4ed8;
            border-color: #60a5fa;
        }}
        .map-download-hint {{
            font-size: 12px;
            color: #94a3b8;
            line-height: 1.4;
        }}
        .map-download-hint.ok {{
            color: #86efac;
        }}
        .map-download-hint.warn {{
            color: #fdba74;
        }}
        .map-download-progress {{
            padding: 8px 10px;
            border-radius: 8px;
            background: rgba(15, 23, 42, 0.62);
            border: 1px solid rgba(148, 163, 184, 0.24);
        }}
        .map-download-progress-head {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 8px;
            margin-bottom: 6px;
            font-size: 12px;
            color: #cbd5e1;
        }}
        .map-download-progress-bar {{
            width: 100%;
            height: 8px;
            border-radius: 999px;
            background: rgba(51, 65, 85, 0.92);
            overflow: hidden;
        }}
        .map-download-progress-fill {{
            width: 0%;
            height: 100%;
            border-radius: inherit;
            background: linear-gradient(90deg, #38bdf8 0%, #22c55e 100%);
            transition: width 0.18s ease;
        }}
        .map-download-progress-fill.warn {{
            background: linear-gradient(90deg, #f59e0b 0%, #ef4444 100%);
        }}
        .map-download-coverage {{
            font-size: 11px;
            line-height: 1.45;
            color: #cbd5e1;
            padding: 8px 10px;
            border-radius: 8px;
            background: rgba(15, 23, 42, 0.62);
            border: 1px solid rgba(148, 163, 184, 0.24);
        }}
        .map-download-coverage.ok {{
            color: #bfdbfe;
        }}
        .map-download-coverage.warn {{
            color: #fdba74;
        }}
        @media (max-width: 760px) {{
            .leaflet-top.leaflet-right {{
                margin-top: 208px;
                margin-right: 2px;
            }}
            .zoom-level-pill {{
                min-width: 52px;
                height: 50px;
                font-size: 10px;
            }}
            .zoom-level-pill span {{
                font-size: 15px;
            }}
            .map-legend {{
                display: none;
            }}
            .map-toolbar {{
                width: calc(100vw - 12px);
                max-width: calc(100vw - 12px);
                bottom: 6px;
                gap: 6px;
                padding: 6px 8px;
                border-radius: 10px;
            }}
            .map-toolbar-data {{
                gap: 8px;
                padding: 0 2px;
                font-size: 11px;
                overflow-x: auto;
                scrollbar-width: none;
            }}
            .map-toolbar-data::-webkit-scrollbar {{
                display: none;
            }}
            .map-toolbar-sep {{
                display: none;
            }}
            .map-toolbar-btn {{
                min-width: 30px;
                padding: 0 6px;
            }}
            .map-toolbar-btn .label {{
                display: none;
            }}
        }}
        .auto-route-badge {{
            display: inline-flex;
            justify-content: center;
            align-items: center;
            width: 28px;
            height: 28px;
            font-size: 14px;
            font-weight: bold;
            color: #fff;
            background: #8b5cf6;
            border: 2px solid #ffffff;
            border-radius: 50%;
            box-shadow: 0 0 4px rgba(0, 0, 0, 0.35);
        }}
        .auto-route-badge.takeoff {{ background: #06b6d4; }}
        .auto-route-badge.landing {{ background: #f97316; }}
        .auto-route-badge.locked {{
            opacity: 0.88;
            box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.26), 0 0 4px rgba(0, 0, 0, 0.4);
        }}
        .auto-route-line {{
            stroke: #9333ea;
            stroke-width: 2;
            stroke-dasharray: 5,5;
            opacity: 0.6;
        }}
    </style>
</head>
<body>
    <div id="map"></div>
    <div id="mapStatus"></div>
    <div id="waypointContextMenu" class="wpt-ctx-menu">
        <div class="wpt-ctx-item" id="menuAddAtHere">在此添加航点</div>
        <hr class="wpt-ctx-sep" id="menuSepMap">
        <div class="wpt-ctx-item" id="menuInsertAfter">在此之后插入航点</div>
        <div class="wpt-ctx-item" id="menuFlyToWaypoint">飞向此航点</div>
        <div class="wpt-ctx-item" id="menuUploadWaypoint">上传此航点</div>
        <hr class="wpt-ctx-sep">
        <div class="wpt-ctx-item danger" id="menuDeleteWaypoint">删除此航点</div>
    </div>
    <div class="map-legend">
        <div class="map-legend-title">地图图例</div>
        <div class="map-legend-item"><span class="legend-aircraft"><svg width="18" height="18" viewBox="0 0 64 64" aria-hidden="true"><path d="M32 6 L38 22 L58 26 L58 34 L38 38 L32 58 L26 38 L6 34 L6 26 L26 22 Z" fill="#0f766e"/><path d="M32 10 L35 20 L29 20 Z" fill="#0b3b35"/></svg></span><span>当前飞机位置</span></div>
        <div class="map-legend-item"><span class="legend-dot start"></span><span>H 点(Home)</span></div>
        <div class="map-legend-item"><span class="legend-dot route"></span><span>普通任务航点</span></div>
    </div>
    <div class="map-toolbar">
        <div class="map-toolbar-data">
            <span id="coordLon">经度: --</span>
            <span id="coordLat">纬度: --</span>
            <span id="coordAlt">高程: --</span>
            <span id="measureInfo">测距: --</span>
        </div>
        <div class="map-toolbar-sep"></div>
        <button id="btnFitMission" class="map-toolbar-btn" title="缩放到任务航线"><span class="icon">▣</span><span class="label">全览</span></button>
        <button id="btnLocateAircraft" class="map-toolbar-btn" title="定位飞机"><span class="icon">✈</span><span class="label">定位</span></button>
        <button id="btnMeasure" class="map-toolbar-btn" title="测距"><span class="icon">⟷</span><span class="label">测距</span></button>
        <button id="btnFollowAircraft" class="map-toolbar-btn" title="飞机居中跟随"><span class="icon">◎</span><span class="label">居中</span></button>
        <button id="btnOfflineDownload" class="map-toolbar-btn" title="下载离线地图"><span class="icon">⬇</span><span class="label">离线</span></button>
    </div>
    <div id="offlineDownloadPanel" class="map-download-panel" aria-hidden="true">
        <div class="map-download-title">离线地图下载</div>
        <div class="map-download-row">
            <label for="offlineMapSource">底图</label>
            <select id="offlineMapSource"></select>
        </div>
        <div class="map-download-row">
            <label for="offlineMinZoom">层级</label>
            <div class="map-download-inline">
                <input id="offlineMinZoom" type="number" min="4" max="21" value="5" />
                <span>至</span>
                <input id="offlineMaxZoom" type="number" min="4" max="21" value="8" />
            </div>
        </div>
        <div class="map-download-row">
            <label for="offlineTilePadding">视野</label>
            <select id="offlineTilePadding">
                <option value="1">当前视野</option>
                <option value="2" selected>视野 + 1 圈</option>
                <option value="4">更大范围</option>
            </select>
        </div>
        <div class="map-download-row">
            <label for="offlineCenterRadius">中心</label>
            <select id="offlineCenterRadius">
                <option value="1">3 × 3 瓦片</option>
                <option value="2" selected>5 × 5 瓦片</option>
                <option value="3">7 × 7 瓦片</option>
            </select>
        </div>
        <div class="map-download-actions">
            <button id="btnQueueVisibleDownload" class="map-download-btn primary">下载当前视野</button>
            <button id="btnQueueCenterDownload" class="map-download-btn">下载中心区域</button>
            <button id="btnCloseOfflineDownload" class="map-download-btn">关闭</button>
        </div>
        <div class="map-download-progress">
            <div class="map-download-progress-head">
                <span>下载进度</span>
                <span id="offlineDownloadProgressValue">--</span>
            </div>
            <div class="map-download-progress-bar">
                <div id="offlineDownloadProgressFill" class="map-download-progress-fill"></div>
            </div>
            <div id="offlineDownloadProgressText" class="map-download-hint">等待下载任务。</div>
        </div>
        <div id="offlineCacheCoverage" class="map-download-coverage">已缓存范围：正在读取…</div>
        <div id="offlineDownloadHint" class="map-download-hint">选择缩放范围后即可缓存离线地图。</div>
    </div>
    <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
    <script>
        window.mapReady = false;
        window._gcsMapStarted = false;
        window._gcsMapBootstrapError = '';
        window._gcsForceOffline = {json.dumps(force_offline_bootstrap)};
        window._gcsLeafletAssets = {{
            css: [
                'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
                'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css',
                'https://cdn.bootcdn.net/ajax/libs/leaflet/1.9.4/leaflet.css'
            ],
            js: [
                'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
                'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js',
                'https://cdn.bootcdn.net/ajax/libs/leaflet/1.9.4/leaflet.js'
            ]
        }};

        function setMapStatus(message, level) {{
            const statusEl = document.getElementById('mapStatus');
            if (!statusEl) {{
                return;
            }}
            statusEl.className = level || '';
            statusEl.textContent = message || '';
            statusEl.style.display = message ? 'block' : 'none';
        }}

        function loadLeafletStylesheet(index) {{
            if (document.getElementById('leafletCssLink')) {{
                return;
            }}
            if (index >= window._gcsLeafletAssets.css.length) {{
                return;
            }}
            const href = window._gcsLeafletAssets.css[index];
            const link = document.createElement('link');
            link.id = 'leafletCssLink';
            link.rel = 'stylesheet';
            link.href = href;
            link.onerror = function() {{
                link.remove();
                loadLeafletStylesheet(index + 1);
            }};
            document.head.appendChild(link);
        }}

        function loadLeafletScript(index) {{
            if (window._gcsForceOffline) {{
                setMapStatus('正在以离线缓存模式启动地图…', 'warning');
                window.startOfflineMapFallback();
                return;
            }}
            if (typeof L !== 'undefined') {{
                window.startGcsMap();
                return;
            }}
            if (index >= window._gcsLeafletAssets.js.length) {{
                window._gcsMapBootstrapError = 'Leaflet 所有 CDN 均不可访问';
                console.warn('[GCS] Leaflet failed to load from all CDN candidates, switching to offline fallback');
                if (typeof window.startOfflineMapFallback === 'function') {{
                    window.startOfflineMapFallback();
                }} else {{
                    document.getElementById('map').innerHTML = '<div style="padding:40px;color:#ef4444;font-size:14px;font-weight:600;background:#1e293b;height:100%;box-sizing:border-box;">⚠ 地图加载失败：Leaflet 资源不可访问。</div>';
                    setMapStatus(window._gcsMapBootstrapError, 'error');
                }}
                return;
            }}
            const src = window._gcsLeafletAssets.js[index];
            setMapStatus('正在加载地图内核…', 'warning');
            const script = document.createElement('script');
            script.src = src;
            script.async = true;
            script.onload = function() {{
                window.startGcsMap();
            }};
            script.onerror = function() {{
                script.remove();
                loadLeafletScript(index + 1);
            }};
            document.head.appendChild(script);
        }}

        const mapSources = {json.dumps(tile_config, ensure_ascii=False)};
        let currentTileLayer = null;
        let currentDemLayer = null;
        let currentMapName = Object.keys(mapSources)[0];
        let providerFailures = {{}};
        let activeTileFailures = 0;
        let activeTileRecovered = false;
        let waypointLayer = null;
        let loiterLayer = null;
        let routeLine = null;
        let mapBridge = null;
        let bridgeBindingInProgress = false;
        let pendingWaypointAdds = [];
        let addWaypointMode = false;
        let homePickMode = false;
        let vehicleMarker = null;
        let homeMarker = null;
        let followAircraft = false;
        let measureMode = false;
        let measurePoints = [];
        let measureMarkers = [];
        let measureLine = null;
        let ctxMenuLatLng = null;
        let lastVehicle = null;
        let lastCacheRequestKey = null;
        let cacheRequestTimer = null;
        let waypointMarkers = [];
        let loiterCircles = [];
        let waypointCoords = [];
        let selectedWaypointIndex = -1;
        let ctxMenuTargetIndex = -1;
        let zoomLevelValueEl = null;
        let zoomLayoutRaf = 0;
        let autoRouteMarkers = {{}};
        let autoRouteCircles = {{}};
        let autoRouteData = null;
        let autoRouteLine = null;
        let autoRouteLayer = null;
        let homePosition = null;
        const DEM_MAX_NATIVE_ZOOM = 15;
        const overlayState = {{
            home: null,
            vehicle: null,
            measureMode: false,
            followAircraft: false,
        }};
        const offlineDownloadPanel = document.getElementById('offlineDownloadPanel');
        const btnOfflineDownload = document.getElementById('btnOfflineDownload');
        const offlineMapSource = document.getElementById('offlineMapSource');
        const offlineMinZoom = document.getElementById('offlineMinZoom');
        const offlineMaxZoom = document.getElementById('offlineMaxZoom');
        const offlineTilePadding = document.getElementById('offlineTilePadding');
        const offlineCenterRadius = document.getElementById('offlineCenterRadius');
        const btnQueueVisibleDownload = document.getElementById('btnQueueVisibleDownload');
        const btnQueueCenterDownload = document.getElementById('btnQueueCenterDownload');
        const btnCloseOfflineDownload = document.getElementById('btnCloseOfflineDownload');
        const offlineDownloadHint = document.getElementById('offlineDownloadHint');
        const offlineDownloadProgressFill = document.getElementById('offlineDownloadProgressFill');
        const offlineDownloadProgressValue = document.getElementById('offlineDownloadProgressValue');
        const offlineDownloadProgressText = document.getElementById('offlineDownloadProgressText');
        const offlineCacheCoverage = document.getElementById('offlineCacheCoverage');

        function setOfflineDownloadHint(message, tone) {{
            if (!offlineDownloadHint) {{
                return;
            }}
            offlineDownloadHint.textContent = message || '选择范围后即可缓存离线地图。';
            offlineDownloadHint.className = 'map-download-hint ' + (tone || '');
        }}

        function updateOfflineCacheProgress(payload) {{
            const info = payload && typeof payload === 'object' ? payload : {{}};
            const total = Math.max(0, Number(info.total || 0));
            const current = Math.max(0, Number(info.current || 0));
            const percent = total > 0
                ? Math.max(0, Math.min(100, Number(info.percent || ((current / total) * 100.0))))
                : 0;
            if (offlineDownloadProgressFill) {{
                offlineDownloadProgressFill.style.width = String(percent.toFixed(1)) + '%';
                offlineDownloadProgressFill.classList.toggle('warn', info.status === 'error');
            }}
            if (offlineDownloadProgressValue) {{
                offlineDownloadProgressValue.textContent = total > 0 ? String(Math.round(percent)) + '%' : '--';
            }}
            if (offlineDownloadProgressText) {{
                const details = [];
                const newTiles = Number(info.newTiles || 0);
                const reusedTiles = Number(info.reusedTiles || 0);
                if (total > 0) {{
                    details.push(String(current) + '/' + String(total));
                }}
                if (newTiles > 0) {{
                    details.push('新增 ' + String(newTiles));
                }}
                if (reusedTiles > 0) {{
                    details.push('复用 ' + String(reusedTiles));
                }}
                offlineDownloadProgressText.textContent = info.message
                    ? String(info.message) + (details.length ? '（' + details.join('，') + '）' : '')
                    : '等待下载任务。';
                offlineDownloadProgressText.className = 'map-download-hint ' + (info.status === 'error' ? 'warn' : (info.status === 'done' ? 'ok' : ''));
            }}
        }}
        window.updateOfflineCacheProgress = updateOfflineCacheProgress;

        function updateOfflineCacheCoverage(summary) {{
            const info = summary && typeof summary === 'object' ? summary : {{}};
            const mapName = info.mapName || (offlineMapSource && offlineMapSource.value) || currentMapName || '';
            if (mapName && mapSources[mapName]) {{
                mapSources[mapName].offlineAvailable = Boolean(info.available);
            }}
            if (offlineCacheCoverage) {{
                offlineCacheCoverage.textContent = info.message
                    ? '已缓存范围：' + String(info.message)
                    : '已缓存范围：暂无统计数据。';
                offlineCacheCoverage.className = 'map-download-coverage ' + (info.available ? 'ok' : 'warn');
            }}
            if (offlineMapSource) {{
                const selected = offlineMapSource.value || mapName;
                updateOfflineDownloadSourceOptions();
                if (selected && mapSources[selected]) {{
                    offlineMapSource.value = selected;
                }}
            }}
        }}
        window.updateOfflineCacheCoverage = updateOfflineCacheCoverage;

        function requestOfflineCacheCoverage(mapName) {{
            const targetName = mapName || (offlineMapSource && offlineMapSource.value) || currentMapName || Object.keys(mapSources)[0];
            if (offlineCacheCoverage) {{
                offlineCacheCoverage.textContent = '已缓存范围：正在读取 ' + String(targetName) + '…';
                offlineCacheCoverage.className = 'map-download-coverage';
            }}
            if (mapBridge && typeof mapBridge.requestOfflineCacheSummary === 'function') {{
                mapBridge.requestOfflineCacheSummary(String(targetName));
                return;
            }}
            if (offlineCacheCoverage) {{
                offlineCacheCoverage.textContent = '已缓存范围：地图桥接尚未就绪，稍后会自动刷新。';
                offlineCacheCoverage.className = 'map-download-coverage warn';
            }}
        }}

        function updateOfflineDownloadSourceOptions() {{
            if (!offlineMapSource) {{
                return;
            }}
            const names = Object.keys(mapSources);
            offlineMapSource.innerHTML = names.map(function(name) {{
                const cached = mapSources[name] && mapSources[name].offlineAvailable ? '（已缓存）' : '';
                const selected = name === currentMapName ? ' selected' : '';
                return '<option value="' + name + '"' + selected + '>' + name + cached + '</option>';
            }}).join('');
        }}

        function syncOfflineDownloadDefaults() {{
            const fallbackZoom = Number({self.current_zoom});
            const baseZoom = window.map && typeof window.map.getZoom === 'function'
                ? Number(window.map.getZoom())
                : fallbackZoom;
            const minZ = Math.max(4, Math.min(21, Math.floor(baseZoom)));
            const maxZ = Math.max(minZ, Math.min(21, minZ + 2));
            if (offlineMinZoom) {{
                offlineMinZoom.value = String(minZ);
            }}
            if (offlineMaxZoom) {{
                offlineMaxZoom.value = String(maxZ);
            }}
            if (offlineMapSource) {{
                offlineMapSource.value = currentMapName || Object.keys(mapSources)[0];
            }}
        }}

        function toggleOfflineDownloadPanel(forceOpen) {{
            if (!offlineDownloadPanel) {{
                return;
            }}
            const nextOpen = typeof forceOpen === 'boolean' ? forceOpen : !offlineDownloadPanel.classList.contains('open');
            offlineDownloadPanel.classList.toggle('open', nextOpen);
            offlineDownloadPanel.setAttribute('aria-hidden', nextOpen ? 'false' : 'true');
            if (btnOfflineDownload) {{
                btnOfflineDownload.classList.toggle('active', nextOpen);
            }}
            if (nextOpen) {{
                updateOfflineDownloadSourceOptions();
                syncOfflineDownloadDefaults();
                setOfflineDownloadHint('选择缩放范围后即可缓存离线地图。', '');
                updateOfflineCacheProgress({{ status: 'idle', current: 0, total: 0, message: '等待下载任务。' }});
                requestOfflineCacheCoverage(offlineMapSource ? offlineMapSource.value : currentMapName);
            }}
        }}

        function lon2tileIndex(lon, z) {{
            return Math.floor((Number(lon) + 180.0) / 360.0 * Math.pow(2, z));
        }}

        function lat2tileIndex(lat, z) {{
            const rad = Number(lat) * Math.PI / 180.0;
            return Math.floor((1.0 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2.0 * Math.pow(2, z));
        }}

        function clampTileRange(xMin, xMax, yMin, yMax, zoom) {{
            const maxIndex = Math.pow(2, zoom) - 1;
            return {{
                x_min: Math.max(0, Math.min(maxIndex, xMin)),
                x_max: Math.max(0, Math.min(maxIndex, xMax)),
                y_min: Math.max(0, Math.min(maxIndex, yMin)),
                y_max: Math.max(0, Math.min(maxIndex, yMax)),
            }};
        }}

        function buildVisibleDownloadRange(zoom, padding) {{
            const bounds = window.map.getBounds();
            return clampTileRange(
                lon2tileIndex(bounds.getWest(), zoom) - padding,
                lon2tileIndex(bounds.getEast(), zoom) + padding,
                lat2tileIndex(bounds.getNorth(), zoom) - padding,
                lat2tileIndex(bounds.getSouth(), zoom) + padding,
                zoom
            );
        }}

        function buildCenterDownloadRange(zoom, radius) {{
            const bounds = window.map.getBounds();
            const centerLat = (Number(bounds.getNorth()) + Number(bounds.getSouth())) / 2.0;
            const centerLon = (Number(bounds.getWest()) + Number(bounds.getEast())) / 2.0;
            const centerX = lon2tileIndex(centerLon, zoom);
            const centerY = lat2tileIndex(centerLat, zoom);
            return clampTileRange(centerX - radius, centerX + radius, centerY - radius, centerY + radius, zoom);
        }}

        function queueOfflineMapDownload(mode) {{
            if (!mapBridge || typeof mapBridge.cacheVisibleRegion !== 'function' || !window.map) {{
                setOfflineDownloadHint('地图下载接口尚未就绪，请稍后重试。', 'warn');
                return;
            }}
            const mapName = offlineMapSource && mapSources[offlineMapSource.value]
                ? offlineMapSource.value
                : (currentMapName || Object.keys(mapSources)[0]);
            let minZoom = Math.max(4, Math.min(21, parseInt(offlineMinZoom && offlineMinZoom.value ? offlineMinZoom.value : String(window.map.getZoom()), 10) || 4));
            let maxZoom = Math.max(4, Math.min(21, parseInt(offlineMaxZoom && offlineMaxZoom.value ? offlineMaxZoom.value : String(minZoom), 10) || minZoom));
            if (minZoom > maxZoom) {{
                const temp = minZoom;
                minZoom = maxZoom;
                maxZoom = temp;
                if (offlineMinZoom) {{
                    offlineMinZoom.value = String(minZoom);
                }}
                if (offlineMaxZoom) {{
                    offlineMaxZoom.value = String(maxZoom);
                }}
            }}
            const padding = Math.max(1, Math.min(6, parseInt(offlineTilePadding && offlineTilePadding.value ? offlineTilePadding.value : '2', 10) || 2));
            const centerRadius = Math.max(1, Math.min(6, parseInt(offlineCenterRadius && offlineCenterRadius.value ? offlineCenterRadius.value : '2', 10) || 2));
            let queuedJobs = 0;
            for (let zoom = minZoom; zoom <= maxZoom; zoom += 1) {{
                const range = mode === 'center'
                    ? buildCenterDownloadRange(zoom, centerRadius)
                    : buildVisibleDownloadRange(zoom, padding);
                mapBridge.cacheVisibleRegion(JSON.stringify({{
                    map_name: mapName,
                    zoom: zoom,
                    x_min: range.x_min,
                    x_max: range.x_max,
                    y_min: range.y_min,
                    y_max: range.y_max,
                }}));
                queuedJobs += 1;
            }}
            const modeLabel = mode === 'center' ? '中心区域' : '当前视野';
            setOfflineDownloadHint('已加入离线下载队列：' + mapName + ' ' + modeLabel + ' Z' + minZoom + '-Z' + maxZoom + '（' + queuedJobs + ' 级）', 'ok');
            updateOfflineCacheProgress({{ status: 'queued', current: 0, total: 0, message: '后台队列已创建，等待开始…' }});
            setMapStatus('离线地图下载已加入后台队列：' + mapName + ' ' + modeLabel + ' Z' + minZoom + '-Z' + maxZoom, 'warning');
        }}

        if (btnOfflineDownload) {{
            btnOfflineDownload.addEventListener('click', function(event) {{
                event.preventDefault();
                event.stopPropagation();
                toggleOfflineDownloadPanel();
            }});
        }}
        if (btnCloseOfflineDownload) {{
            btnCloseOfflineDownload.addEventListener('click', function() {{
                toggleOfflineDownloadPanel(false);
            }});
        }}
        if (offlineMapSource) {{
            offlineMapSource.addEventListener('change', function() {{
                requestOfflineCacheCoverage(offlineMapSource.value);
            }});
        }}
        if (btnQueueVisibleDownload) {{
            btnQueueVisibleDownload.addEventListener('click', function() {{
                queueOfflineMapDownload('visible');
            }});
        }}
        if (btnQueueCenterDownload) {{
            btnQueueCenterDownload.addEventListener('click', function() {{
                queueOfflineMapDownload('center');
            }});
        }}
        document.addEventListener('click', function(event) {{
            if (!offlineDownloadPanel || !btnOfflineDownload || !offlineDownloadPanel.classList.contains('open')) {{
                return;
            }}
            if (offlineDownloadPanel.contains(event.target) || btnOfflineDownload.contains(event.target)) {{
                return;
            }}
            toggleOfflineDownloadPanel(false);
        }});

        function getFallbackMapName(excludedName) {{
            const names = Object.keys(mapSources);
            const sorted = names.slice().sort(function(a, b) {{
                const aCached = mapSources[a] && mapSources[a].offlineAvailable ? 1 : 0;
                const bCached = mapSources[b] && mapSources[b].offlineAvailable ? 1 : 0;
                if (aCached !== bCached) {{
                    return bCached - aCached;
                }}
                return (providerFailures[a] || 0) - (providerFailures[b] || 0);
            }});
            for (const name of sorted) {{
                if (name !== excludedName) {{
                    return name;
                }}
            }}
            return excludedName;
        }}

        function switchToFallbackMapSource(failedMapName) {{
            const fallback = getFallbackMapName(failedMapName);
            if (!fallback || fallback === failedMapName) {{
                setMapStatus('当前地图源不可用，且无可切换的备用源。', 'error');
                return;
            }}
            setMapStatus('当前底图源不可用，已切换到 ' + fallback, 'warning');
            window.setMapSource(fallback);
        }}

        window.startOfflineMapFallback = function() {{
            if (window._gcsMapStarted) {{
                return;
            }}
            window._gcsMapStarted = true;
            window._gcsOfflineFallback = true;

            const mapEl = document.getElementById('map');
            const coordLonEl = document.getElementById('coordLon');
            const coordLatEl = document.getElementById('coordLat');
            const coordAltEl = document.getElementById('coordAlt');
            const measureInfoEl = document.getElementById('measureInfo');
            const btnFitMission = document.getElementById('btnFitMission');
            const btnLocateAircraft = document.getElementById('btnLocateAircraft');
            const btnMeasure = document.getElementById('btnMeasure');
            const btnFollowAircraft = document.getElementById('btnFollowAircraft');
            const cachedDefaultMap = Object.keys(mapSources).find(function(name) {{
                return mapSources[name] && mapSources[name].offlineAvailable;
            }});
            if ((!currentMapName || !mapSources[currentMapName] || !mapSources[currentMapName].offlineAvailable) && cachedDefaultMap) {{
                currentMapName = cachedDefaultMap;
            }}

            const fallbackState = {{
                center: {{ lat: Number({self.current_center[0]}), lng: Number({self.current_center[1]}) }},
                zoom: Math.max(4, Math.min(21, Number({self.current_zoom}))),
                mapName: currentMapName || Object.keys(mapSources)[0],
                waypoints: [],
                autoRoute: [],
                overlay: {{ home: null, vehicle: null, measureMode: false, followAircraft: false }},
            }};
            const fallbackHandlers = {{}};
            let isDragging = false;
            let dragStartPoint = null;
            let dragStartCenter = null;

            function updateOfflineCursor() {{
                if (isDragging) {{
                    mapEl.style.cursor = 'grabbing';
                    return;
                }}
                mapEl.style.cursor = homePickMode ? 'cell' : (addWaypointMode ? 'crosshair' : 'grab');
            }}

            function normalizeLatLng(value) {{
                if (!value) {{
                    return null;
                }}
                if (Array.isArray(value) && value.length >= 2) {{
                    const lat = Number(value[0]);
                    const lng = Number(value[1]);
                    return Number.isFinite(lat) && Number.isFinite(lng) ? {{ lat: lat, lng: lng }} : null;
                }}
                const lat = Number(value.lat);
                const lng = Number(Object.prototype.hasOwnProperty.call(value, 'lng') ? value.lng : value.lon);
                return Number.isFinite(lat) && Number.isFinite(lng) ? {{ lat: lat, lng: lng }} : null;
            }}

            function lonToWorldX(lon, zoom) {{
                return ((Number(lon) + 180.0) / 360.0) * 256 * Math.pow(2, zoom);
            }}

            function latToWorldY(lat, zoom) {{
                const clampedLat = Math.max(-85.05112878, Math.min(85.05112878, Number(lat)));
                const rad = clampedLat * Math.PI / 180.0;
                return (1.0 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2.0 * 256 * Math.pow(2, zoom);
            }}

            function worldToLon(x, zoom) {{
                return x / (256 * Math.pow(2, zoom)) * 360.0 - 180.0;
            }}

            function worldToLat(y, zoom) {{
                const n = Math.PI - (2.0 * Math.PI * y) / (256 * Math.pow(2, zoom));
                return 180.0 / Math.PI * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
            }}

            function getBoundsObject() {{
                const width = Math.max(320, mapEl.clientWidth || mapEl.offsetWidth || 320);
                const height = Math.max(240, mapEl.clientHeight || mapEl.offsetHeight || 240);
                const centerX = lonToWorldX(fallbackState.center.lng, fallbackState.zoom);
                const centerY = latToWorldY(fallbackState.center.lat, fallbackState.zoom);
                const west = worldToLon(centerX - width / 2, fallbackState.zoom);
                const east = worldToLon(centerX + width / 2, fallbackState.zoom);
                const north = worldToLat(centerY - height / 2, fallbackState.zoom);
                const south = worldToLat(centerY + height / 2, fallbackState.zoom);
                return {{
                    getWest: function() {{ return west; }},
                    getEast: function() {{ return east; }},
                    getNorth: function() {{ return north; }},
                    getSouth: function() {{ return south; }},
                }};
            }}

            function latLngToContainerPoint(latlng) {{
                const point = normalizeLatLng(latlng);
                if (!point) {{
                    return {{ x: 0, y: 0 }};
                }}
                const width = Math.max(320, mapEl.clientWidth || mapEl.offsetWidth || 320);
                const height = Math.max(240, mapEl.clientHeight || mapEl.offsetHeight || 240);
                const centerX = lonToWorldX(fallbackState.center.lng, fallbackState.zoom);
                const centerY = latToWorldY(fallbackState.center.lat, fallbackState.zoom);
                return {{
                    x: lonToWorldX(point.lng, fallbackState.zoom) - centerX + width / 2,
                    y: latToWorldY(point.lat, fallbackState.zoom) - centerY + height / 2,
                }};
            }}

            function containerEventToLatLng(event) {{
                const rect = mapEl.getBoundingClientRect();
                const width = Math.max(1, rect.width || mapEl.clientWidth || 1);
                const height = Math.max(1, rect.height || mapEl.clientHeight || 1);
                const offsetX = Number(event.clientX - rect.left);
                const offsetY = Number(event.clientY - rect.top);
                const centerX = lonToWorldX(fallbackState.center.lng, fallbackState.zoom);
                const centerY = latToWorldY(fallbackState.center.lat, fallbackState.zoom);
                return {{
                    lat: worldToLat(centerY - height / 2 + offsetY, fallbackState.zoom),
                    lng: worldToLon(centerX - width / 2 + offsetX, fallbackState.zoom),
                }};
            }}

            function emitMapEvent(name, payload) {{
                (fallbackHandlers[name] || []).forEach(function(handler) {{
                    try {{
                        handler(payload);
                    }} catch (err) {{
                        console.warn('[GCS] offline fallback event failed', name, err);
                    }}
                }});
            }}

            function setCoordDisplay(latlng) {{
                if (coordLonEl) {{
                    coordLonEl.textContent = '经度: ' + (latlng ? Number(latlng.lng).toFixed(7) : '--');
                }}
                if (coordLatEl) {{
                    coordLatEl.textContent = '纬度: ' + (latlng ? Number(latlng.lat).toFixed(7) : '--');
                }}
                if (coordAltEl) {{
                    coordAltEl.textContent = '高程: --';
                }}
            }}

            function setMeasureInfo(text) {{
                if (measureInfoEl) {{
                    measureInfoEl.textContent = '测距: ' + (text || '--');
                }}
            }}

            function buildTileUrl(mapName, z, x, y) {{
                const source = mapSources[mapName] || mapSources[Object.keys(mapSources)[0]];
                if (!source || !source.offline) {{
                    return '';
                }}
                return source.offline
                    .replace('{{z}}', String(z))
                    .replace('{{x}}', String(x))
                    .replace('{{y}}', String(y));
            }}

            function emitAddWaypointAtFallback(latlng) {{
                if (!latlng) {{
                    return;
                }}
                const point = latLngToContainerPoint(latlng);
                const payload = {{
                    lat: Number(latlng.lat),
                    lon: Number(latlng.lng),
                    x: Number(point.x || 0),
                    y: Number(point.y || 0),
                    alt: 50.0,
                }};
                if (!mapBridge) {{
                    if (pendingWaypointAdds.length > 30) {{
                        pendingWaypointAdds.shift();
                    }}
                    pendingWaypointAdds.push(payload);
                    setMapStatus('地图桥接未就绪，正在重试…', 'warning');
                    bindBridgeFallback();
                    return;
                }}
                if (typeof mapBridge.addWaypointDetailed === 'function') {{
                    mapBridge.addWaypointDetailed(JSON.stringify(payload));
                    return;
                }}
                if (typeof mapBridge.addWaypointAny === 'function') {{
                    mapBridge.addWaypointAny(Number(payload.lat), Number(payload.lon));
                    return;
                }}
                if (typeof mapBridge.addWaypoint === 'function') {{
                    mapBridge.addWaypoint(Number(payload.lat), Number(payload.lon));
                }}
            }}

            function emitHomePickFallback(latlng) {{
                if (!latlng || !mapBridge) {{
                    return;
                }}
                if (typeof mapBridge.setHomePointAny === 'function') {{
                    mapBridge.setHomePointAny(JSON.stringify({{ lat: Number(latlng.lat), lon: Number(latlng.lng), alt: 0.0 }}));
                    return;
                }}
                if (typeof mapBridge.homePickedFromMapAny === 'function') {{
                    mapBridge.homePickedFromMapAny(Number(latlng.lat), Number(latlng.lng));
                }}
            }}

            function renderFallback() {{
                if (!document.getElementById('offlineFallbackRoot')) {{
                    mapEl.innerHTML = '<div id="offlineFallbackRoot" style="position:relative;width:100%;height:100%;overflow:hidden;background:#0f172a;">'
                        + '<div id="offlineFallbackTiles" style="position:absolute;inset:0;background:#0b1220;"></div>'
                        + '<svg id="offlineFallbackRoutes" style="position:absolute;inset:0;width:100%;height:100%;pointer-events:none;"></svg>'
                        + '<div id="offlineFallbackMarkers" style="position:absolute;inset:0;pointer-events:none;"></div>'
                        + '<div id="offlineFallbackBadge" style="position:absolute;right:12px;top:12px;padding:6px 10px;border-radius:10px;background:rgba(15,23,42,0.86);border:1px solid rgba(148,163,184,0.35);color:#f8fafc;font-size:12px;box-shadow:0 8px 20px rgba(15,23,42,0.24);">离线地图缓存</div>'
                        + '<div id="offlineFallbackControls" style="position:absolute;left:12px;top:12px;display:flex;align-items:center;gap:6px;padding:6px 8px;border-radius:10px;background:rgba(15,23,42,0.86);border:1px solid rgba(148,163,184,0.35);color:#f8fafc;box-shadow:0 8px 20px rgba(15,23,42,0.24);">'
                        + '<button id="offlineZoomOut" style="width:28px;height:28px;border:none;border-radius:6px;background:#233246;color:#fff;font-size:18px;cursor:pointer;">−</button>'
                        + '<span id="offlineZoomLabel" style="min-width:42px;text-align:center;font-size:12px;font-weight:700;">Z--</span>'
                        + '<button id="offlineZoomIn" style="width:28px;height:28px;border:none;border-radius:6px;background:#233246;color:#fff;font-size:18px;cursor:pointer;">+</button>'
                        + '</div>'
                        + '</div>';
                }}

                const width = Math.max(320, mapEl.clientWidth || mapEl.offsetWidth || 320);
                const height = Math.max(240, mapEl.clientHeight || mapEl.offsetHeight || 240);
                const tilesEl = document.getElementById('offlineFallbackTiles');
                const routesEl = document.getElementById('offlineFallbackRoutes');
                const markersEl = document.getElementById('offlineFallbackMarkers');
                const badgeEl = document.getElementById('offlineFallbackBadge');
                const zoomLabelEl = document.getElementById('offlineZoomLabel');
                if (!tilesEl || !routesEl || !markersEl) {{
                    return;
                }}
                if (badgeEl) {{
                    badgeEl.textContent = '离线地图 | ' + fallbackState.mapName + ' | Z' + fallbackState.zoom;
                }}
                if (zoomLabelEl) {{
                    zoomLabelEl.textContent = 'Z' + fallbackState.zoom;
                }}

                const tileSize = 256;
                const maxIndex = Math.max(1, Math.pow(2, fallbackState.zoom));
                const centerX = lonToWorldX(fallbackState.center.lng, fallbackState.zoom);
                const centerY = latToWorldY(fallbackState.center.lat, fallbackState.zoom);
                const leftX = centerX - width / 2;
                const topY = centerY - height / 2;
                const startX = Math.floor(leftX / tileSize);
                const endX = Math.floor((leftX + width) / tileSize);
                const startY = Math.floor(topY / tileSize);
                const endY = Math.floor((topY + height) / tileSize);

                let tilesHtml = '';
                for (let x = startX; x <= endX; x += 1) {{
                    for (let y = startY; y <= endY; y += 1) {{
                        if (y < 0 || y >= maxIndex) {{
                            continue;
                        }}
                        const px = Math.round(x * tileSize - leftX);
                        const py = Math.round(y * tileSize - topY);
                        const wrappedX = ((x % maxIndex) + maxIndex) % maxIndex;
                        const src = buildTileUrl(fallbackState.mapName, fallbackState.zoom, wrappedX, y);
                        tilesHtml += '<img alt="tile" src="' + src + '" style="position:absolute;left:' + px + 'px;top:' + py + 'px;width:' + tileSize + 'px;height:' + tileSize + 'px;object-fit:cover;background:#172033;border:1px solid rgba(15,23,42,0.12);" onerror="this.style.opacity=0.18;this.style.backgroundColor=&quot;#1e293b&quot;;" />';
                    }}
                }}
                tilesEl.innerHTML = tilesHtml;
                routesEl.innerHTML = '';
                markersEl.innerHTML = '';

                function placeMarker(lat, lng, label, bg) {{
                    const point = latLngToContainerPoint({{ lat: lat, lng: lng }});
                    if (!Number.isFinite(point.x) || !Number.isFinite(point.y)) {{
                        return;
                    }}
                    const node = document.createElement('div');
                    node.textContent = label;
                    node.style.cssText = 'position:absolute;left:' + (point.x - 14) + 'px;top:' + (point.y - 14) + 'px;width:28px;height:28px;border-radius:50%;background:' + bg + ';color:#fff;border:2px solid #ffffff;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;box-shadow:0 4px 10px rgba(15,23,42,0.35);';
                    markersEl.appendChild(node);
                }}

                const routePoints = [];
                fallbackState.waypoints.forEach(function(wp, index) {{
                    const lat = Number(wp.lat);
                    const lon = Number(wp.lon);
                    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {{
                        return;
                    }}
                    const pt = latLngToContainerPoint({{ lat: lat, lng: lon }});
                    routePoints.push(Math.round(pt.x) + ',' + Math.round(pt.y));
                    const seq = Number(wp && wp.seq);
                    const label = Number.isFinite(seq) && seq > 0 ? String(Math.floor(seq)) : String(index + 1);
                    placeMarker(lat, lon, label, '#2563eb');
                }});
                if (routePoints.length > 1) {{
                    routesEl.innerHTML += '<polyline points="' + routePoints.join(' ') + '" fill="none" stroke="#38bdf8" stroke-width="3" opacity="0.92" />';
                }}

                const autoRoutePoints = [];
                (fallbackState.autoRoute || []).forEach(function(item) {{
                    const lat = Number(item.lat);
                    const lon = Number(item.lon);
                    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {{
                        return;
                    }}
                    const pt = latLngToContainerPoint({{ lat: lat, lng: lon }});
                    autoRoutePoints.push(Math.round(pt.x) + ',' + Math.round(pt.y));
                    placeMarker(lat, lon, String(item.name || 'A'), '#7c3aed');
                }});
                if (autoRoutePoints.length > 1) {{
                    routesEl.innerHTML += '<polyline points="' + autoRoutePoints.join(' ') + '" fill="none" stroke="#a855f7" stroke-width="2" opacity="0.8" stroke-dasharray="5,5" />';
                }}

                if (fallbackState.overlay.home && Number.isFinite(Number(fallbackState.overlay.home.lat)) && Number.isFinite(Number(fallbackState.overlay.home.lon))) {{
                    placeMarker(Number(fallbackState.overlay.home.lat), Number(fallbackState.overlay.home.lon), 'H', '#0f766e');
                }}
                if (fallbackState.overlay.vehicle && Number.isFinite(Number(fallbackState.overlay.vehicle.lat)) && Number.isFinite(Number(fallbackState.overlay.vehicle.lon))) {{
                    placeMarker(Number(fallbackState.overlay.vehicle.lat), Number(fallbackState.overlay.vehicle.lon), '✈', '#16a34a');
                }}
            }}

            function bindBridgeFallback() {{
                if (mapBridge || bridgeBindingInProgress) {{
                    return;
                }}
                if (!window.qt || !window.qt.webChannelTransport) {{
                    window.setTimeout(bindBridgeFallback, 120);
                    return;
                }}
                bridgeBindingInProgress = true;
                try {{
                    new QWebChannel(window.qt.webChannelTransport, function(channel) {{
                        bridgeBindingInProgress = false;
                        const candidate = channel && channel.objects ? channel.objects.mapBridge : null;
                        if (!candidate) {{
                            window.setTimeout(bindBridgeFallback, 180);
                            return;
                        }}
                        mapBridge = candidate;
                        if (pendingWaypointAdds.length > 0) {{
                            const queued = pendingWaypointAdds.slice();
                            pendingWaypointAdds = [];
                            queued.forEach(function(item) {{
                                if (typeof mapBridge.addWaypointDetailed === 'function') {{
                                    mapBridge.addWaypointDetailed(JSON.stringify(item));
                                }} else if (typeof mapBridge.addWaypointAny === 'function') {{
                                    mapBridge.addWaypointAny(Number(item.lat), Number(item.lon));
                                }} else if (typeof mapBridge.addWaypoint === 'function') {{
                                    mapBridge.addWaypoint(Number(item.lat), Number(item.lon));
                                }}
                            }});
                        }}
                        if (window.requestOfflineCacheCoverage) {{
                            window.requestOfflineCacheCoverage(currentMapName);
                        }}
                    }});
                }} catch (err) {{
                    bridgeBindingInProgress = false;
                    console.warn('[GCS] offline bridge bind failed', err);
                    window.setTimeout(bindBridgeFallback, 200);
                }}
            }}

            if (!mapEl.dataset.offlineFallbackBound) {{
                mapEl.dataset.offlineFallbackBound = '1';
                updateOfflineCursor();
                mapEl.addEventListener('mousedown', function(event) {{
                    if (event.button !== 0) {{
                        return;
                    }}
                    isDragging = true;
                    dragStartPoint = {{ x: Number(event.clientX || 0), y: Number(event.clientY || 0) }};
                    dragStartCenter = {{ lat: fallbackState.center.lat, lng: fallbackState.center.lng }};
                    updateOfflineCursor();
                }});
                mapEl.addEventListener('mousemove', function(event) {{
                    if (isDragging && dragStartPoint && dragStartCenter) {{
                        const dx = Number(event.clientX || 0) - dragStartPoint.x;
                        const dy = Number(event.clientY || 0) - dragStartPoint.y;
                        const worldX = lonToWorldX(dragStartCenter.lng, fallbackState.zoom) - dx;
                        const worldY = latToWorldY(dragStartCenter.lat, fallbackState.zoom) - dy;
                        fallbackState.center = {{
                            lat: worldToLat(worldY, fallbackState.zoom),
                            lng: worldToLon(worldX, fallbackState.zoom),
                        }};
                        renderFallback();
                    }}
                    const latlng = containerEventToLatLng(event);
                    setCoordDisplay(latlng);
                    emitMapEvent('mousemove', {{ latlng: latlng }});
                }});
                mapEl.addEventListener('mouseleave', function() {{
                    if (isDragging) {{
                        isDragging = false;
                        dragStartPoint = null;
                        dragStartCenter = null;
                        updateOfflineCursor();
                        emitMapEvent('moveend', {{ latlng: fallbackState.center }});
                        if (window.scheduleOfflineCacheRequest) {{
                            window.scheduleOfflineCacheRequest();
                        }}
                    }}
                    setCoordDisplay(null);
                    emitMapEvent('mouseout', {{}});
                }});
                window.addEventListener('mouseup', function() {{
                    if (!isDragging) {{
                        return;
                    }}
                    isDragging = false;
                    dragStartPoint = null;
                    dragStartCenter = null;
                    updateOfflineCursor();
                    emitMapEvent('moveend', {{ latlng: fallbackState.center }});
                    if (window.scheduleOfflineCacheRequest) {{
                        window.scheduleOfflineCacheRequest();
                    }}
                }});
                mapEl.addEventListener('wheel', function(event) {{
                    event.preventDefault();
                    const delta = Number(event.deltaY || 0);
                    const nextZoom = Math.max(4, Math.min(21, fallbackState.zoom + (delta < 0 ? 1 : -1)));
                    if (nextZoom === fallbackState.zoom) {{
                        return;
                    }}
                    fallbackState.zoom = nextZoom;
                    renderFallback();
                    emitMapEvent('zoomend', {{ zoom: fallbackState.zoom }});
                    if (window.scheduleOfflineCacheRequest) {{
                        window.scheduleOfflineCacheRequest();
                    }}
                }}, {{ passive: false }});
                mapEl.addEventListener('click', function(event) {{
                    const latlng = containerEventToLatLng(event);
                    if (measureMode) {{
                        setMeasureInfo('离线简化模式');
                    }} else if (homePickMode) {{
                        homePickMode = false;
                        updateOfflineCursor();
                        emitHomePickFallback(latlng);
                    }} else if (addWaypointMode) {{
                        emitAddWaypointAtFallback(latlng);
                    }}
                    emitMapEvent('click', {{ latlng: latlng }});
                }});
                mapEl.addEventListener('contextmenu', function(event) {{
                    event.preventDefault();
                    emitMapEvent('contextmenu', {{ latlng: containerEventToLatLng(event), originalEvent: event }});
                }});
                window.addEventListener('resize', function() {{
                    renderFallback();
                    emitMapEvent('moveend', {{ latlng: fallbackState.center }});
                }});
            }}

            if (!btnFitMission.dataset.fallbackBound) {{
                btnFitMission.dataset.fallbackBound = '1';
                btnFitMission.addEventListener('click', function() {{
                    window.fitMissionRoute();
                }});
                btnLocateAircraft.addEventListener('click', function() {{
                    window.locateAircraft();
                }});
                btnMeasure.addEventListener('click', function() {{
                    measureMode = !measureMode;
                    fallbackState.overlay.measureMode = measureMode;
                    btnMeasure.classList.toggle('active', measureMode);
                    setMeasureInfo(measureMode ? '离线简化模式' : '--');
                }});
                btnFollowAircraft.addEventListener('click', function() {{
                    followAircraft = !followAircraft;
                    fallbackState.overlay.followAircraft = followAircraft;
                    btnFollowAircraft.classList.toggle('active', followAircraft);
                    if (followAircraft && fallbackState.overlay.vehicle) {{
                        window.locateAircraft();
                    }}
                }});
                const btnOfflineZoomIn = document.getElementById('offlineZoomIn');
                const btnOfflineZoomOut = document.getElementById('offlineZoomOut');
                if (btnOfflineZoomIn) {{
                    btnOfflineZoomIn.addEventListener('click', function() {{
                        fallbackState.zoom = Math.max(4, Math.min(21, fallbackState.zoom + 1));
                        renderFallback();
                        if (window.scheduleOfflineCacheRequest) {{
                            window.scheduleOfflineCacheRequest();
                        }}
                    }});
                }}
                if (btnOfflineZoomOut) {{
                    btnOfflineZoomOut.addEventListener('click', function() {{
                        fallbackState.zoom = Math.max(4, Math.min(21, fallbackState.zoom - 1));
                        renderFallback();
                        if (window.scheduleOfflineCacheRequest) {{
                            window.scheduleOfflineCacheRequest();
                        }}
                    }});
                }}
            }}

            window.map = {{
                setView: function(center, zoom) {{
                    const nextCenter = normalizeLatLng(center);
                    if (nextCenter) {{
                        fallbackState.center = nextCenter;
                    }}
                    if (zoom !== undefined && zoom !== null && Number.isFinite(Number(zoom))) {{
                        fallbackState.zoom = Math.max(4, Math.min(21, Number(zoom)));
                    }}
                    renderFallback();
                    emitMapEvent('moveend', {{ latlng: fallbackState.center }});
                    emitMapEvent('zoomend', {{ zoom: fallbackState.zoom }});
                    return this;
                }},
                getZoom: function() {{
                    return fallbackState.zoom;
                }},
                getBounds: function() {{
                    return getBoundsObject();
                }},
                getContainer: function() {{
                    return mapEl;
                }},
                latLngToContainerPoint: function(latlng) {{
                    return latLngToContainerPoint(latlng);
                }},
                panTo: function(center) {{
                    return this.setView(center, fallbackState.zoom);
                }},
                fitBounds: function(bounds) {{
                    if (!bounds) {{
                        return this;
                    }}
                    let west = null;
                    let east = null;
                    let north = null;
                    let south = null;
                    if (typeof bounds.getWest === 'function') {{
                        west = Number(bounds.getWest());
                        east = Number(bounds.getEast());
                        north = Number(bounds.getNorth());
                        south = Number(bounds.getSouth());
                    }} else if (Array.isArray(bounds) && bounds.length >= 2) {{
                        const p1 = normalizeLatLng(bounds[0]);
                        const p2 = normalizeLatLng(bounds[1]);
                        if (p1 && p2) {{
                            west = Math.min(p1.lng, p2.lng);
                            east = Math.max(p1.lng, p2.lng);
                            south = Math.min(p1.lat, p2.lat);
                            north = Math.max(p1.lat, p2.lat);
                        }}
                    }}
                    if (west !== null && east !== null && north !== null && south !== null) {{
                        return this.setView({{ lat: (north + south) / 2, lng: (west + east) / 2 }}, fallbackState.zoom);
                    }}
                    return this;
                }},
                on: function(name, handler) {{
                    if (!fallbackHandlers[name]) {{
                        fallbackHandlers[name] = [];
                    }}
                    fallbackHandlers[name].push(handler);
                    return this;
                }},
                off: function(name, handler) {{
                    if (!fallbackHandlers[name]) {{
                        return this;
                    }}
                    if (!handler) {{
                        fallbackHandlers[name] = [];
                        return this;
                    }}
                    fallbackHandlers[name] = fallbackHandlers[name].filter(function(item) {{ return item !== handler; }});
                    return this;
                }},
                removeLayer: function() {{ return this; }},
                addLayer: function() {{ return this; }},
            }};

            window.setMapSource = function(mapName) {{
                if (!mapSources[mapName]) {{
                    return;
                }}
                fallbackState.mapName = mapName;
                currentMapName = mapName;
                updateOfflineDownloadSourceOptions();
                if (offlineMapSource) {{
                    offlineMapSource.value = currentMapName;
                }}
                if (window.requestOfflineCacheCoverage) {{
                    window.requestOfflineCacheCoverage(currentMapName);
                }}
                renderFallback();
                if (window.scheduleOfflineCacheRequest) {{
                    window.scheduleOfflineCacheRequest();
                }}
            }};

            window.setAddWaypointMode = function(enabled) {{
                addWaypointMode = Boolean(enabled);
                updateOfflineCursor();
            }};

            window.setHomePickMode = function(enabled) {{
                homePickMode = Boolean(enabled);
                updateOfflineCursor();
            }};

            window.clearMeasure = function() {{
                measureMode = false;
                fallbackState.overlay.measureMode = false;
                btnMeasure.classList.remove('active');
                setMeasureInfo('--');
            }};

            window.fitMissionRoute = function() {{
                const points = [];
                (fallbackState.waypoints || []).forEach(function(wp) {{
                    const lat = Number(wp.lat);
                    const lon = Number(wp.lon);
                    if (Number.isFinite(lat) && Number.isFinite(lon)) {{
                        points.push({{ lat: lat, lng: lon }});
                    }}
                }});
                if (points.length === 0) {{
                    setMapStatus('当前没有任务航点可全览', 'warning');
                    return;
                }}
                const avgLat = points.reduce(function(sum, point) {{ return sum + point.lat; }}, 0) / points.length;
                const avgLng = points.reduce(function(sum, point) {{ return sum + point.lng; }}, 0) / points.length;
                window.map.setView({{ lat: avgLat, lng: avgLng }}, fallbackState.zoom);
            }};

            window.locateAircraft = function() {{
                if (fallbackState.overlay.vehicle) {{
                    window.map.panTo(fallbackState.overlay.vehicle);
                    return;
                }}
                setMapStatus('暂无飞机位置可定位', 'warning');
            }};

            window.applyOverlayState = function(partialState) {{
                if (!partialState || typeof partialState !== 'object') {{
                    return;
                }}
                if (Object.prototype.hasOwnProperty.call(partialState, 'home')) {{
                    fallbackState.overlay.home = partialState.home;
                }}
                if (Object.prototype.hasOwnProperty.call(partialState, 'vehicle')) {{
                    fallbackState.overlay.vehicle = partialState.vehicle;
                }}
                if (Object.prototype.hasOwnProperty.call(partialState, 'measureMode')) {{
                    measureMode = Boolean(partialState.measureMode);
                    fallbackState.overlay.measureMode = measureMode;
                    btnMeasure.classList.toggle('active', measureMode);
                }}
                if (Object.prototype.hasOwnProperty.call(partialState, 'followAircraft')) {{
                    followAircraft = Boolean(partialState.followAircraft);
                    fallbackState.overlay.followAircraft = followAircraft;
                    btnFollowAircraft.classList.toggle('active', followAircraft);
                }}
                if (followAircraft && fallbackState.overlay.vehicle) {{
                    const vehiclePos = normalizeLatLng(fallbackState.overlay.vehicle);
                    if (vehiclePos) {{
                        fallbackState.center = vehiclePos;
                    }}
                }}
                renderFallback();
            }};

            window.setHomePosition = function(home) {{
                window.applyOverlayState({{ home: home }});
            }};

            window.setVehiclePosition = function(vehicle) {{
                window.applyOverlayState({{ vehicle: vehicle }});
            }};

            window.clearVehiclePosition = function() {{
                window.applyOverlayState({{ vehicle: null }});
            }};

            window.updateAutoRoute = function(routeItems, homeWp) {{
                fallbackState.autoRoute = Array.isArray(routeItems) ? routeItems.slice() : [];
                if (homeWp) {{
                    fallbackState.overlay.home = homeWp;
                }}
                renderFallback();
            }};

            window.updateWaypoints = function(waypoints) {{
                fallbackState.waypoints = Array.isArray(waypoints) ? waypoints.slice() : [];
                renderFallback();
            }};

            window.syncWaypointRange = function(startIndex, removeCount, insertItems) {{
                const start = Math.max(0, Number(startIndex) || 0);
                const removeTotal = Math.max(0, Number(removeCount) || 0);
                const items = Array.isArray(insertItems) ? insertItems : [];
                fallbackState.waypoints.splice(start, removeTotal, ...items);
                renderFallback();
            }};

            window.moveWaypointMarker = function(index, waypoint) {{
                if (!Number.isInteger(index) || index < 0) {{
                    return;
                }}
                fallbackState.waypoints[index] = waypoint;
                renderFallback();
            }};

            window.selectWaypointOnMap = function(newIndex) {{
                selectedWaypointIndex = Number.isInteger(newIndex) ? newIndex : -1;
                renderFallback();
            }};

            window.requestOfflineCache = function() {{
                if (!mapBridge || !mapBridge.cacheVisibleRegion || !window.map) {{
                    window.setTimeout(window.requestOfflineCache, 200);
                    return;
                }}
                const bounds = window.map.getBounds();
                const zoom = window.map.getZoom();
                const maxIndex = Math.pow(2, zoom) - 1;
                function lon2tile(lon, z) {{
                    return Math.floor((lon + 180.0) / 360.0 * Math.pow(2, z));
                }}
                function lat2tile(lat, z) {{
                    const rad = lat * Math.PI / 180.0;
                    return Math.floor((1.0 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2.0 * Math.pow(2, z));
                }}
                let xMin = lon2tile(bounds.getWest(), zoom) - 1;
                let xMax = lon2tile(bounds.getEast(), zoom) + 1;
                let yMin = lat2tile(bounds.getNorth(), zoom) - 1;
                let yMax = lat2tile(bounds.getSouth(), zoom) + 1;
                xMin = Math.max(0, Math.min(maxIndex, xMin));
                xMax = Math.max(0, Math.min(maxIndex, xMax));
                yMin = Math.max(0, Math.min(maxIndex, yMin));
                yMax = Math.max(0, Math.min(maxIndex, yMax));
                const requestKey = [fallbackState.mapName || Object.keys(mapSources)[0], zoom, xMin, xMax, yMin, yMax].join(':');
                if (requestKey === lastCacheRequestKey) {{
                    return;
                }}
                lastCacheRequestKey = requestKey;
                mapBridge.cacheVisibleRegion(JSON.stringify({{
                    map_name: fallbackState.mapName || Object.keys(mapSources)[0],
                    zoom: zoom,
                    x_min: xMin,
                    x_max: xMax,
                    y_min: yMin,
                    y_max: yMax,
                }}));
            }};

            window.scheduleOfflineCacheRequest = function() {{
                if (cacheRequestTimer) {{
                    window.clearTimeout(cacheRequestTimer);
                }}
                cacheRequestTimer = window.setTimeout(function() {{
                    cacheRequestTimer = null;
                    if (window.requestOfflineCache) {{
                        window.requestOfflineCache();
                    }}
                }}, 180);
            }};

            bindBridgeFallback();
            renderFallback();
            setCoordDisplay(null);
            setMeasureInfo('--');
            window.mapReady = true;
            setMapStatus('离线地图模式已启用：已从本地缓存加载底图。', 'warning');
            window.setTimeout(function() {{
                if (window.requestOfflineCache) {{
                    window.requestOfflineCache();
                }}
            }}, 120);
        }};

        window.startGcsMap = function() {{
            if (window._gcsMapStarted || typeof L === 'undefined') {{
                return;
            }}
            window._gcsMapStarted = true;
            setMapStatus('', '');
            window.map = L.map('map', {{
                zoomControl: false,
                minZoom: 4,
                maxZoom: 21,
                preferCanvas: true,
                markerZoomAnimation: false,
                fadeAnimation: false,
            }}).setView({json.dumps(self.current_center)}, {self.current_zoom});

            const ZoomLevelControl = L.Control.extend({{
                options: {{ position: 'topright' }},
                onAdd: function() {{
                    const container = L.DomUtil.create('div', 'leaflet-control zoom-level-control');
                    container.innerHTML = '<div class="zoom-level-pill">地图等级<span id="mapZoomLevel">--</span></div>';
                    L.DomEvent.disableClickPropagation(container);
                    L.DomEvent.disableScrollPropagation(container);
                    return container;
                }}
            }});
            window.map.addControl(new ZoomLevelControl());
            L.control.zoom({{ position: 'topright' }}).addTo(window.map);

            function updateZoomLevelDisplay() {{
                if (!zoomLevelValueEl) {{
                    zoomLevelValueEl = document.getElementById('mapZoomLevel');
                }}
                if (zoomLevelValueEl) {{
                    zoomLevelValueEl.textContent = String(window.map.getZoom());
                }}
            }}

            function resolveRightAnchorOffset() {{
                const mapEl = window.map ? window.map.getContainer() : null;
                if (!mapEl) {{
                    return window.innerWidth <= 760 ? 208 : 265;
                }}
                const mapH = Number(mapEl.clientHeight || 0);
                if (window.innerWidth <= 760) {{
                    return Math.max(178, Math.min(250, Math.round(mapH * 0.34) + 10));
                }}
                return Math.max(240, Math.min(330, Math.round(mapH * 0.36) + 10));
            }}

            function layoutZoomControls() {{
                if (!window.map) {{
                    return;
                }}
                const corner = window.map.getContainer().querySelector('.leaflet-top.leaflet-right');
                if (!corner) {{
                    return;
                }}
                corner.style.marginRight = '2px';
                corner.style.marginTop = String(resolveRightAnchorOffset()) + 'px';
            }}

            function scheduleLayoutZoomControls() {{
                if (zoomLayoutRaf) {{
                    cancelAnimationFrame(zoomLayoutRaf);
                }}
                zoomLayoutRaf = requestAnimationFrame(function() {{
                    zoomLayoutRaf = 0;
                    layoutZoomControls();
                }});
            }}

            window.map.on('zoomend', updateZoomLevelDisplay);
            window.map.on('zoomend', scheduleLayoutZoomControls);
            window.map.on('moveend', scheduleLayoutZoomControls);
            updateZoomLevelDisplay();
            scheduleLayoutZoomControls();
            window.addEventListener('resize', scheduleLayoutZoomControls);

            waypointLayer = L.layerGroup().addTo(window.map);
            loiterLayer = L.layerGroup().addTo(window.map);
            autoRouteLayer = L.layerGroup().addTo(window.map);
            const mapContainer = window.map.getContainer();
            mapContainer.addEventListener('contextmenu', function(evt) {{ evt.preventDefault(); }});
            window.map.on('contextmenu', function(evt) {{
                if (evt && evt.originalEvent) {{
                    evt.originalEvent.preventDefault();
                }}
            }});
        

        const coordLonEl = document.getElementById('coordLon');
        const coordLatEl = document.getElementById('coordLat');
        const coordAltEl = document.getElementById('coordAlt');
        const measureInfoEl = document.getElementById('measureInfo');
        const btnFitMission = document.getElementById('btnFitMission');
        const btnLocateAircraft = document.getElementById('btnLocateAircraft');
        const btnMeasure = document.getElementById('btnMeasure');
        const btnFollowAircraft = document.getElementById('btnFollowAircraft');

        function formatCoord(value) {{
            return Number.isFinite(value) ? value.toFixed(7) : '--';
        }}

        function decodeTerrarium(color) {{
            return (color.r * 256.0 + color.g + color.b / 256.0) - 32768.0;
        }}

        function getMouseDemElevation(latlng) {{
            if (!currentDemLayer || !latlng) {{
                return null;
            }}
            const demZoom = currentDemLayer && Number.isFinite(Number(currentDemLayer._tileZoom))
                ? Number(currentDemLayer._tileZoom)
                : Math.min(Number(window.map.getZoom()), DEM_MAX_NATIVE_ZOOM);
            const point = window.map.project(latlng, demZoom);
            const tileSize = 256;
            const tileX = Math.floor(point.x / tileSize);
            const tileY = Math.floor(point.y / tileSize);
            const px = Math.floor(point.x - tileX * tileSize);
            const py = Math.floor(point.y - tileY * tileSize);
            const key = tileX + ':' + tileY + ':' + demZoom;
            const tileRecord = currentDemLayer._tiles ? currentDemLayer._tiles[key] : null;
            if (!tileRecord || !tileRecord.el || !(tileRecord.el instanceof HTMLImageElement)) {{
                return null;
            }}
            const img = tileRecord.el;
            if (!img.complete || img.naturalWidth <= 0) {{
                return null;
            }}
            try {{
                const canvas = document.createElement('canvas');
                canvas.width = tileSize;
                canvas.height = tileSize;
                const ctx = canvas.getContext('2d', {{ willReadFrequently: true }});
                ctx.drawImage(img, 0, 0, tileSize, tileSize);
                const data = ctx.getImageData(Math.max(0, Math.min(255, px)), Math.max(0, Math.min(255, py)), 1, 1).data;
                return decodeTerrarium({{ r: data[0], g: data[1], b: data[2] }});
            }} catch (_e) {{
                return null;
            }}
        }}

        let demQueryToken = 0;
        function updateCoordDisplay(latlng) {{
            if (!latlng) {{
                coordLonEl.textContent = '经度: --';
                coordLatEl.textContent = '纬度: --';
                coordAltEl.textContent = '高程: --';
                demQueryToken += 1;
                return;
            }}
            coordLonEl.textContent = '经度: ' + formatCoord(latlng.lng);
            coordLatEl.textContent = '纬度: ' + formatCoord(latlng.lat);

            const localDem = getMouseDemElevation(latlng);
            if (Number.isFinite(localDem)) {{
                coordAltEl.textContent = '高程: ' + localDem.toFixed(1) + 'm';
                return;
            }}

            coordAltEl.textContent = '高程: --';
            const token = ++demQueryToken;
            if (!mapBridge || typeof mapBridge.getDemElevation !== 'function') {{
                return;
            }}
            const demZoom = currentDemLayer && Number.isFinite(Number(currentDemLayer._tileZoom))
                ? Number(currentDemLayer._tileZoom)
                : Math.min(Number(window.map.getZoom()), DEM_MAX_NATIVE_ZOOM);
            mapBridge.getDemElevation(Number(latlng.lat), Number(latlng.lng), demZoom, function(value) {{
                if (token !== demQueryToken) {{
                    return;
                }}
                const altitude = Number(value);
                coordAltEl.textContent = '高程: ' + (Number.isFinite(altitude) ? altitude.toFixed(1) + 'm' : '--');
            }});
        }}

        function updateMeasureInfo(text) {{
            measureInfoEl.textContent = '测距: ' + (text || '--');
        }}

        function clearMeasure() {{
            measurePoints = [];
            if (measureLine) {{
                window.map.removeLayer(measureLine);
                measureLine = null;
            }}
            measureMarkers.forEach(function(m) {{ window.map.removeLayer(m); }});
            measureMarkers = [];
            updateMeasureInfo('--');
        }}
        window.clearMeasure = function() {{
            clearMeasure();
            setMeasureMode(false);
        }};

        function fitMissionRoute() {{
            if (!window.map) {{
                return;
            }}
            if (waypointCoords.length === 0) {{
                setMapStatus('当前没有任务航点可全览', 'warning');
                return;
            }}
            if (waypointCoords.length === 1) {{
                window.map.setView(waypointCoords[0], Math.max(window.map.getZoom(), 16), {{ animate: true }});
                return;
            }}
            const bounds = L.latLngBounds(waypointCoords);
            window.map.fitBounds(bounds.pad(0.18), {{ animate: true, maxZoom: 18 }});
        }}
        window.fitMissionRoute = fitMissionRoute;

        window.locateAircraft = function() {{
            if (vehicleMarker) {{
                window.map.panTo(vehicleMarker.getLatLng(), {{ animate: true }});
                return;
            }}
            setMapStatus('暂无飞机位置可定位', 'warning');
        }};

        function emitAddWaypointAt(latlng) {{
            if (!latlng) {{
                return;
            }}
            const clickLat = Number(latlng.lat);
            const clickLon = Number(latlng.lng);
            const clickPoint = window.map.latLngToContainerPoint(latlng);
            const terrain = getMouseDemElevation(latlng);
            const altHint = Number.isFinite(terrain) ? Number(terrain) : 50.0;
            const payload = {{
                lat: clickLat,
                lon: clickLon,
                x: Number(clickPoint.x || 0),
                y: Number(clickPoint.y || 0),
                alt: altHint,
            }};
            if (!mapBridge) {{
                if (pendingWaypointAdds.length > 30) {{
                    pendingWaypointAdds.shift();
                }}
                pendingWaypointAdds.push(payload);
                setMapStatus('地图桥接未就绪，正在重试…', 'warning');
                bindBridge();
                return;
            }}
            if (typeof mapBridge.addWaypointDetailed === 'function') {{
                mapBridge.addWaypointDetailed(JSON.stringify(payload));
                return;
            }}
            if (typeof mapBridge.addWaypointAny === 'function') {{
                mapBridge.addWaypointAny(clickLat, clickLon);
                return;
            }}
            if (typeof mapBridge.addWaypoint === 'function') {{
                mapBridge.addWaypoint(clickLat, clickLon);
            }}
        }}

        function setMeasureMode(enabled) {{
            measureMode = Boolean(enabled);
            overlayState.measureMode = measureMode;
            btnMeasure.classList.toggle('active', measureMode);
            if (!measureMode) {{
                clearMeasure();
            }}
        }}

        function setFollowAircraft(enabled) {{
            followAircraft = Boolean(enabled);
            overlayState.followAircraft = followAircraft;
            btnFollowAircraft.classList.toggle('active', followAircraft);
            if (followAircraft && vehicleMarker) {{
                window.map.panTo(vehicleMarker.getLatLng(), {{ animate: true }});
            }}
        }}

        function applyHomeMarker(home) {{
            if (!home || !Number.isFinite(Number(home.lat)) || !Number.isFinite(Number(home.lon))) {{
                if (homeMarker) {{
                    window.map.removeLayer(homeMarker);
                    homeMarker = null;
                }}
                return;
            }}
            const lat = Number(home.lat);
            const lon = Number(home.lon);
            const alt = Number(home.alt || 0);
            const icon = L.divIcon({{
                className: '',
                html: '<div class="waypoint-badge start">H</div>',
                iconSize: [28, 28],
                iconAnchor: [14, 14],
            }});
            if (!homeMarker) {{
                homeMarker = L.marker([lat, lon], {{ icon, interactive: false, zIndexOffset: 800 }}).addTo(window.map);
            }} else {{
                homeMarker.setLatLng([lat, lon]);
                homeMarker.setIcon(icon);
            }}
            homeMarker.bindTooltip('Home 点\\n相对高度 ' + alt.toFixed(1) + 'm', {{ direction: 'top', offset: [0, -16] }});
        }}

        function applyVehicleMarker(vehicle) {{
            if (!vehicle || !Number.isFinite(Number(vehicle.lat)) || !Number.isFinite(Number(vehicle.lon))) {{
                if (vehicleMarker) {{
                    window.map.removeLayer(vehicleMarker);
                    vehicleMarker = null;
                }}
                lastVehicle = null;
                return;
            }}
            const lat = Number(vehicle.lat);
            const lon = Number(vehicle.lon);
            const heading = Number(vehicle.heading || 0);
            const altitude = Number(vehicle.altitude || 0);
            lastVehicle = {{ lat: lat, lon: lon, alt: altitude }};
            const icon = L.divIcon({{
                className: '',
                html: '<div class="vehicle-marker" style="transform: rotate(' + heading + 'deg);"><svg width="40" height="40" viewBox="0 0 64 64" aria-hidden="true"><path d="M32 6 L38 22 L58 26 L58 34 L38 38 L32 58 L26 38 L6 34 L6 26 L26 22 Z" fill="#0f766e"/><path d="M32 10 L35 20 L29 20 Z" fill="#0b3b35"/></svg></div>',
                iconSize: [40, 40],
                iconAnchor: [20, 20],
            }});
            if (!vehicleMarker) {{
                vehicleMarker = L.marker([lat, lon], {{ icon, interactive: false, zIndexOffset: 1000 }}).addTo(window.map);
            }} else {{
                vehicleMarker.setLatLng([lat, lon]);
                vehicleMarker.setIcon(icon);
            }}
            if (followAircraft) {{
                window.map.panTo([lat, lon], {{ animate: true }});
            }}
            vehicleMarker.bindTooltip('飞机位置\\n相对高度 ' + altitude.toFixed(1) + 'm', {{ direction: 'top', offset: [0, -16] }});
        }}

        window.applyOverlayState = function(partialState) {{
            if (!partialState || typeof partialState !== 'object') {{
                return;
            }}
            if (Object.prototype.hasOwnProperty.call(partialState, 'home')) {{
                overlayState.home = partialState.home;
                applyHomeMarker(overlayState.home);
            }}
            if (Object.prototype.hasOwnProperty.call(partialState, 'vehicle')) {{
                overlayState.vehicle = partialState.vehicle;
                applyVehicleMarker(overlayState.vehicle);
            }}
            if (Object.prototype.hasOwnProperty.call(partialState, 'measureMode')) {{
                setMeasureMode(Boolean(partialState.measureMode));
            }}
            if (Object.prototype.hasOwnProperty.call(partialState, 'followAircraft')) {{
                setFollowAircraft(Boolean(partialState.followAircraft));
            }}
        }};

        function applyHomeFromVehicle() {{
            if (!lastVehicle) {{
                return;
            }}
            window.applyOverlayState({{
                home: {{
                    lat: lastVehicle.lat,
                    lon: lastVehicle.lon,
                    alt: lastVehicle.alt,
                }},
            }});
            if (!mapBridge) {{
                return;
            }}
            if (typeof mapBridge.setHomePointAny === 'function') {{
                mapBridge.setHomePointAny(JSON.stringify({{ lat: lastVehicle.lat, lon: lastVehicle.lon, alt: lastVehicle.alt }}));
            }} else if (typeof mapBridge.setHomePoint === 'function') {{
                mapBridge.setHomePoint(Number(lastVehicle.lat), Number(lastVehicle.lon), Number(lastVehicle.alt));
            }}
        }}

        btnFitMission.addEventListener('click', function() {{
            fitMissionRoute();
        }});
        btnLocateAircraft.addEventListener('click', function() {{
            window.locateAircraft();
        }});
        btnMeasure.addEventListener('click', function() {{
            const next = !measureMode;
            if (mapBridge && typeof mapBridge.setMeasureModeAny === 'function') {{
                mapBridge.setMeasureModeAny(next);
            }} else {{
                setMeasureMode(next);
            }}
        }});
        btnFollowAircraft.addEventListener('click', function() {{
            const next = !followAircraft;
            if (mapBridge && typeof mapBridge.setFollowModeAny === 'function') {{
                mapBridge.setFollowModeAny(next);
            }} else {{
                setFollowAircraft(next);
            }}
        }});

        window.map.on('mousemove', function(e) {{ updateCoordDisplay(e.latlng); }});
        window.map.on('mouseout', function() {{ updateCoordDisplay(null); }});
        window.map.on('click', function(e) {{
            if (!measureMode) {{
                return;
            }}
            measurePoints.push([e.latlng.lat, e.latlng.lng]);
            const marker = L.circleMarker([e.latlng.lat, e.latlng.lng], {{ radius: 4, color: '#f97316', weight: 2, fillOpacity: 0.9 }}).addTo(window.map);
            measureMarkers.push(marker);

            if (measurePoints.length === 2) {{
                if (measureLine) {{
                    window.map.removeLayer(measureLine);
                }}
                measureLine = L.polyline(measurePoints, {{ color: '#f97316', weight: 2, dashArray: '6,6' }}).addTo(window.map);
                const p1 = L.latLng(measurePoints[0][0], measurePoints[0][1]);
                const p2 = L.latLng(measurePoints[1][0], measurePoints[1][1]);
                const dist = p1.distanceTo(p2);
                updateMeasureInfo(dist >= 1000 ? (dist / 1000).toFixed(3) + ' km' : dist.toFixed(1) + ' m');
                measurePoints = [measurePoints[1]];
                if (measureMarkers.length > 2) {{
                    const old = measureMarkers.shift();
                    window.map.removeLayer(old);
                }}
            }} else {{
                updateMeasureInfo('选取第二个点');
            }}
        }});

        // MP-style: click handling is bound once and only depends on runtime mode state.
        window.map.on('click', function(event) {{
            if (measureMode) {{
                return;
            }}
            if (!event || !event.latlng) {{
                return;
            }}
            if (homePickMode) {{
                const pickedLat = Number(event.latlng.lat);
                const pickedLon = Number(event.latlng.lng);

                function emitHomePickWithAltitude(terrainAlt) {{
                    if (mapBridge && typeof mapBridge.setHomePointAny === 'function' && Number.isFinite(terrainAlt)) {{
                        mapBridge.setHomePointAny(JSON.stringify({{ lat: pickedLat, lon: pickedLon, alt: Number(terrainAlt) }}));
                        return;
                    }}
                    if (mapBridge && typeof mapBridge.homePickedFromMapAny === 'function') {{
                        mapBridge.homePickedFromMapAny(pickedLat, pickedLon);
                    }}
                }}

                homePickMode = false;
                window.map.getContainer().style.cursor = addWaypointMode ? 'crosshair' : '';

                const localTerrain = getMouseDemElevation(event.latlng);
                if (Number.isFinite(localTerrain)) {{
                    emitHomePickWithAltitude(localTerrain);
                    return;
                }}

                if (mapBridge && typeof mapBridge.getDemElevation === 'function') {{
                    const demZoom = currentDemLayer && Number.isFinite(Number(currentDemLayer._tileZoom))
                        ? Number(currentDemLayer._tileZoom)
                        : Math.min(Number(window.map.getZoom()), DEM_MAX_NATIVE_ZOOM);
                    mapBridge.getDemElevation(pickedLat, pickedLon, demZoom, function(value) {{
                        const remoteTerrain = Number(value);
                        emitHomePickWithAltitude(remoteTerrain);
                    }});
                    return;
                }}

                emitHomePickWithAltitude(NaN);
                return;
            }}
            if (!addWaypointMode) {{
                return;
            }}
            emitAddWaypointAt(event.latlng);
        }});

        // ── 上下文菜单 ─────────────────────────────────────────
        const waypointCtxMenu = document.getElementById('waypointContextMenu');

        function showWaypointContextMenu(x, y, index, mapLatLng) {{
            ctxMenuTargetIndex = Number.isInteger(index) ? index : -1;
            ctxMenuLatLng = mapLatLng || null;
            const container = window.map.getContainer();
            const cw = container.offsetWidth;
            const ch = container.offsetHeight;
            waypointCtxMenu.style.left = Math.min(x, cw - 150) + 'px';
            waypointCtxMenu.style.top  = Math.min(y, ch - 112) + 'px';
            const addAt = document.getElementById('menuAddAtHere');
            const sepMap = document.getElementById('menuSepMap');
            const insertAfter = document.getElementById('menuInsertAfter');
            const flyToWaypoint = document.getElementById('menuFlyToWaypoint');
            const uploadWaypoint = document.getElementById('menuUploadWaypoint');
            const deleteWaypoint = document.getElementById('menuDeleteWaypoint');
            const markerMode = (ctxMenuTargetIndex >= 0);
            addAt.style.display = markerMode ? 'none' : 'block';
            sepMap.style.display = markerMode ? 'none' : 'block';
            insertAfter.style.display = markerMode ? 'block' : 'none';
            flyToWaypoint.style.display = markerMode ? 'block' : 'none';
            uploadWaypoint.style.display = markerMode ? 'block' : 'none';
            deleteWaypoint.style.display = markerMode ? 'block' : 'none';
            waypointCtxMenu.style.display = 'block';
        }}

        function hideWaypointContextMenu() {{
            waypointCtxMenu.style.display = 'none';
            ctxMenuTargetIndex = -1;
            ctxMenuLatLng = null;
        }}

        document.getElementById('menuAddAtHere').addEventListener('click', function() {{
            const target = ctxMenuLatLng;
            hideWaypointContextMenu();
            if (!target) {{
                return;
            }}
            emitAddWaypointAt(target);
        }});

        document.getElementById('menuInsertAfter').addEventListener('click', function() {{
            const idx = ctxMenuTargetIndex;
            hideWaypointContextMenu();
            if (idx >= 0 && mapBridge && typeof mapBridge.insertWaypointAfterAny === 'function') {{
                mapBridge.insertWaypointAfterAny(idx);
            }}
        }});

        document.getElementById('menuFlyToWaypoint').addEventListener('click', function() {{
            const idx = ctxMenuTargetIndex;
            hideWaypointContextMenu();
            if (idx >= 0 && mapBridge && typeof mapBridge.flyToWaypointAny === 'function') {{
                mapBridge.flyToWaypointAny(idx);
            }}
        }});

        document.getElementById('menuUploadWaypoint').addEventListener('click', function() {{
            const idx = ctxMenuTargetIndex;
            hideWaypointContextMenu();
            if (idx >= 0 && mapBridge && typeof mapBridge.uploadWaypointAny === 'function') {{
                mapBridge.uploadWaypointAny(idx);
            }}
        }});

        document.getElementById('menuDeleteWaypoint').addEventListener('click', function() {{
            const idx = ctxMenuTargetIndex;
            hideWaypointContextMenu();
            if (idx >= 0 && mapBridge && typeof mapBridge.deleteWaypointAny === 'function') {{
                mapBridge.deleteWaypointAny(idx);
            }}
        }});

        window.map.on('click', function() {{ hideWaypointContextMenu(); }});
        window.map.on('contextmenu', function(event) {{
            if (!event || !event.latlng) {{
                return;
            }}
            const pt = window.map.latLngToContainerPoint(event.latlng);
            showWaypointContextMenu(pt.x, pt.y, -1, event.latlng);
        }});
        document.addEventListener('click', function(e) {{
            if (waypointCtxMenu.style.display !== 'none' && !waypointCtxMenu.contains(e.target)) {{
                hideWaypointContextMenu();
            }}
        }});

        // ── 航点选中高亮 ───────────────────────────────────────
        window.selectWaypointOnMap = function(newIndex) {{
            const oldIndex = selectedWaypointIndex;
            selectedWaypointIndex = (Number.isInteger(newIndex) && newIndex >= 0) ? newIndex : -1;
            if (oldIndex >= 0 && oldIndex < waypointMarkers.length) {{
                const oldMarker = waypointMarkers[oldIndex];
                const oldWp = renderedWaypoints[oldIndex];
                if (oldMarker && oldWp) {{
                    oldMarker.setIcon(buildWaypointIcon(oldIndex, String(oldWp.type || 'WAYPOINT'), oldWp));
                }}
            }}
            if (selectedWaypointIndex >= 0 && selectedWaypointIndex < waypointMarkers.length) {{
                const marker = waypointMarkers[selectedWaypointIndex];
                const wp = renderedWaypoints[selectedWaypointIndex];
                if (marker && wp) {{
                    marker.setIcon(buildWaypointIcon(selectedWaypointIndex, String(wp.type || 'WAYPOINT'), wp));
                }}
            }}
        }};

        function bindBridge() {{
            if (mapBridge) {{
                return;
            }}
            if (bridgeBindingInProgress) {{
                return;
            }}
            if (!window.qt || !window.qt.webChannelTransport) {{
                window.setTimeout(bindBridge, 100);
                return;
            }}
            bridgeBindingInProgress = true;
            try {{
                new QWebChannel(window.qt.webChannelTransport, function(channel) {{
                    bridgeBindingInProgress = false;
                    const candidate = channel && channel.objects ? channel.objects.mapBridge : null;
                    if (!candidate) {{
                        window.setTimeout(bindBridge, 180);
                        return;
                    }}
                    mapBridge = candidate;
                    console.log("WebChannel bound successfully, mapBridge:", mapBridge);
                    if (pendingWaypointAdds.length > 0) {{
                        const queued = pendingWaypointAdds.slice();
                        pendingWaypointAdds = [];
                        queued.forEach(function(item) {{
                            if (typeof mapBridge.addWaypointDetailed === 'function') {{
                                mapBridge.addWaypointDetailed(JSON.stringify(item));
                            }} else if (typeof mapBridge.addWaypointAny === 'function') {{
                                mapBridge.addWaypointAny(Number(item.lat), Number(item.lon));
                            }} else if (typeof mapBridge.addWaypoint === 'function') {{
                                mapBridge.addWaypoint(Number(item.lat), Number(item.lon));
                            }}
                        }});
                    }}
                    setMapStatus('', '');
                    if (window.requestOfflineCacheCoverage) {{
                        window.requestOfflineCacheCoverage(currentMapName);
                    }}
                }});
            }} catch (e) {{
                bridgeBindingInProgress = false;
                console.error("WebChannel binding error:", e);
                window.setTimeout(bindBridge, 200);
            }}
        }}

        window.setHomePosition = function(home) {{
            window.applyOverlayState({{ home: home }});
        }};

        window.setAddWaypointMode = function(enabled) {{
            addWaypointMode = Boolean(enabled);
            console.log("setAddWaypointMode called: enabled=" + enabled + ", addWaypointMode=" + addWaypointMode);
            const container = window.map.getContainer();
            container.style.cursor = homePickMode ? 'cell' : (addWaypointMode ? 'crosshair' : '');
        }};

        window.setHomePickMode = function(enabled) {{
            homePickMode = Boolean(enabled);
            const container = window.map.getContainer();
            container.style.cursor = homePickMode ? 'cell' : (addWaypointMode ? 'crosshair' : '');
        }};

        window.setMapSource = function(mapName) {{
            const source = mapSources[mapName];
            if (!source) {{
                return;
            }}
            currentMapName = mapName;
            updateOfflineDownloadSourceOptions();
            if (offlineMapSource) {{
                offlineMapSource.value = currentMapName;
            }}
            if (window.requestOfflineCacheCoverage) {{
                window.requestOfflineCacheCoverage(currentMapName);
            }}
            activeTileFailures = 0;
            activeTileRecovered = false;
            const preferOfflineTiles = Boolean(window._gcsOfflineFallback || window._gcsForceOffline || (window.navigator && window.navigator.onLine === false));
            const tileTemplate = (preferOfflineTiles && source.offlineAvailable && source.offline) ? source.offline : source.tiles;
            const demTemplate = (preferOfflineTiles && source.dem_offline) ? source.dem_offline : source.dem_online;
            const previousTileLayer = currentTileLayer;
            const previousDemLayer = currentDemLayer;
            currentTileLayer = L.tileLayer(tileTemplate, {{
                attribution: source.attr,
                maxZoom: source.maxZoom,
                updateWhenZooming: false,
                updateWhenIdle: true,
                keepBuffer: 4,
            }}).addTo(window.map);
            currentTileLayer.on('tileload', function() {{
                activeTileRecovered = true;
                providerFailures[currentMapName] = 0;
                if (previousTileLayer) {{
                    window.map.removeLayer(previousTileLayer);
                }}
                if (document.getElementById('mapStatus') && document.getElementById('mapStatus').textContent.indexOf('底图源不可用') === -1) {{
                    setMapStatus('', '');
                }}
            }});
            currentTileLayer.on('tileerror', function(event) {{
                if (!event || !event.coords || !event.tile || !source.offline) {{
                    activeTileFailures += 1;
                    providerFailures[currentMapName] = (providerFailures[currentMapName] || 0) + 1;
                    if (!activeTileRecovered && activeTileFailures >= 8) {{
                        switchToFallbackMapSource(currentMapName);
                    }}
                    return;
                }}
                const c = event.coords;
                const offline = source.offline
                    .replace('{{z}}', String(c.z))
                    .replace('{{x}}', String(c.x))
                    .replace('{{y}}', String(c.y));
                if (event.tile.src !== offline) {{
                    event.tile.src = offline;
                    return;
                }}
                activeTileFailures += 1;
                providerFailures[currentMapName] = (providerFailures[currentMapName] || 0) + 1;
                if (!activeTileRecovered && activeTileFailures >= 8) {{
                    switchToFallbackMapSource(currentMapName);
                }}
            }});

            currentDemLayer = L.tileLayer(demTemplate, {{
                maxZoom: source.maxZoom,
                maxNativeZoom: DEM_MAX_NATIVE_ZOOM,
                opacity: 0.01,
                crossOrigin: 'anonymous',
                pane: 'overlayPane',
                attribution: '',
                updateWhenZooming: false,
                updateWhenIdle: true,
                keepBuffer: 4,
            }}).addTo(window.map);
            currentDemLayer.on('tileload', function() {{
                if (previousDemLayer) {{
                    window.map.removeLayer(previousDemLayer);
                }}
            }});
            currentDemLayer.on('tileerror', function(event) {{
                if (!event || !event.coords || !event.tile || !source.dem_offline) {{
                    return;
                }}
                const c = event.coords;
                const offlineDem = source.dem_offline
                    .replace('{{z}}', String(c.z))
                    .replace('{{x}}', String(c.x))
                    .replace('{{y}}', String(c.y));
                if (event.tile.src !== offlineDem) {{
                    event.tile.src = offlineDem;
                }}
            }});

            lastCacheRequestKey = null;
            window.setTimeout(function() {{
                if (window.scheduleOfflineCacheRequest) {{
                    window.scheduleOfflineCacheRequest();
                }}
            }}, 150);
        }};

        window.scheduleOfflineCacheRequest = function() {{
            if (cacheRequestTimer) {{
                window.clearTimeout(cacheRequestTimer);
            }}
            cacheRequestTimer = window.setTimeout(function() {{
                cacheRequestTimer = null;
                if (window.requestOfflineCache) {{
                    window.requestOfflineCache();
                }}
            }}, 180);
        }};

        window.requestOfflineCache = function() {{
            if (!mapBridge || !mapBridge.cacheVisibleRegion || !window.map) {{
                window.setTimeout(window.requestOfflineCache, 200);
                return;
            }}
            const bounds = window.map.getBounds();
            const zoom = window.map.getZoom();
            const maxIndex = Math.pow(2, zoom) - 1;
            function lon2tile(lon, z) {{
                return Math.floor((lon + 180.0) / 360.0 * Math.pow(2, z));
            }}
            function lat2tile(lat, z) {{
                const rad = lat * Math.PI / 180.0;
                return Math.floor((1.0 - Math.log(Math.tan(rad) + 1 / Math.cos(rad)) / Math.PI) / 2.0 * Math.pow(2, z));
            }}
            let xMin = lon2tile(bounds.getWest(), zoom) - 1;
            let xMax = lon2tile(bounds.getEast(), zoom) + 1;
            let yMin = lat2tile(bounds.getNorth(), zoom) - 1;
            let yMax = lat2tile(bounds.getSouth(), zoom) + 1;
            xMin = Math.max(0, Math.min(maxIndex, xMin));
            xMax = Math.max(0, Math.min(maxIndex, xMax));
            yMin = Math.max(0, Math.min(maxIndex, yMin));
            yMax = Math.max(0, Math.min(maxIndex, yMax));
            const requestKey = [currentMapName || Object.keys(mapSources)[0], zoom, xMin, xMax, yMin, yMax].join(':');
            if (requestKey === lastCacheRequestKey) {{
                return;
            }}
            lastCacheRequestKey = requestKey;
            mapBridge.cacheVisibleRegion(JSON.stringify({{
                map_name: currentMapName || Object.keys(mapSources)[0],
                zoom: zoom,
                x_min: xMin,
                x_max: xMax,
                y_min: yMin,
                y_max: yMax,
            }}));
        }};

        window.map.on('moveend', function() {{
            if (window.scheduleOfflineCacheRequest) {{
                window.scheduleOfflineCacheRequest();
            }}
        }});
        window.map.on('zoomend', function() {{
            if (window.scheduleOfflineCacheRequest) {{
                window.scheduleOfflineCacheRequest();
            }}
        }});

        function waypointDisplayIndex(index, wp) {{
            const seq = Number(wp && wp.seq);
            if (Number.isFinite(seq) && seq >= 0) {{
                return Math.floor(seq);
            }}
            return Number(index) + 1;
        }}

        function buildWaypointPopup(index, wp) {{
            const lat = Number(wp.lat);
            const lon = Number(wp.lon);
            const alt = Number(wp.alt || 0);
            const displayIndex = waypointDisplayIndex(index, wp);
            const missionType = String(wp.type || 'WAYPOINT');
            const loiter = Boolean(wp.loiter);
            const loiterRadius = Number(wp.loiter_radius || wp.param3 || 60);
            const typeLabelMap = {{ TAKEOFF: '起飞', LAND: '降落', RTL: '返航', WAYPOINT: '普通航点' }};
            const typeLabel = typeLabelMap[missionType] || missionType;
            return (typeLabel + ' #' + displayIndex)
                + ': ' + lat.toFixed(7) + ', ' + lon.toFixed(7)
                + ', 相对高度 ' + Math.round(alt) + 'm'
                + (loiter ? ', 盘旋半径 ' + loiterRadius.toFixed(0) + 'm' : '')
                + (loiter ? ', 盘旋时间 ' + Number(wp.loiter_time || 30).toFixed(0) + 'min' : '');
        }}

        function buildWaypointIcon(index, missionType, wp) {{
            const typeClassMap = {{ TAKEOFF: 'takeoff', LAND: 'land', RTL: 'rtl', WAYPOINT: '' }};
            const baseClass = (typeClassMap[missionType] || '').trim();
            const selected = (index === selectedWaypointIndex);
            const displayIndex = waypointDisplayIndex(index, wp);
            const cssClass = [baseClass, selected ? 'selected' : ''].filter(Boolean).join(' ');
            const size = selected ? 32 : 28;
            const anchor = selected ? 16 : 14;
            return L.divIcon({{
                className: '',
                html: '<div class="waypoint-badge ' + cssClass + '">' + displayIndex + '</div>',
                iconSize: [size, size],
                iconAnchor: [anchor, anchor],
            }});
        }}

        function buildAutoRouteIcon(name, phase, locked) {{
            const isPhaseClass = phase === '起飞' ? 'takeoff' : 'landing';
            const cssClass = [isPhaseClass, locked ? 'locked' : ''].filter(Boolean).join(' ');
            const size = 28;
            const anchor = 14;
            return L.divIcon({{
                className: '',
                html: '<div class="auto-route-badge ' + cssClass + '">' + name + '</div>',
                iconSize: [size, size],
                iconAnchor: [anchor, anchor],
            }});
        }}

        function calculateDistance(lat1, lon1, lat2, lon2) {{
            const R = 6371000;
            const dLat = (lat2 - lat1) * Math.PI / 180;
            const dLon = (lon2 - lon1) * Math.PI / 180;
            const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                      Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                      Math.sin(dLon / 2) * Math.sin(dLon / 2);
            const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
            return R * c;
        }}

        function offsetPoint(lat, lon, distanceM, bearingRad) {{
            const angular = Number(distanceM || 0) / 6371000;
            const lat1 = lat * Math.PI / 180;
            const lon1 = lon * Math.PI / 180;
            const lat2 = Math.asin(
                Math.sin(lat1) * Math.cos(angular) +
                Math.cos(lat1) * Math.sin(angular) * Math.cos(bearingRad)
            );
            const lon2 = lon1 + Math.atan2(
                Math.sin(bearingRad) * Math.sin(angular) * Math.cos(lat1),
                Math.cos(angular) - Math.sin(lat1) * Math.sin(lat2)
            );
            return [lat2 * 180 / Math.PI, lon2 * 180 / Math.PI];
        }}

        function bearingFromPoints(lat1, lon1, lat2, lon2) {{
            return Math.atan2(
                (lon2 - lon1) * Math.cos((lat1 + lat2) * Math.PI / 360),
                (lat2 - lat1)
            );
        }}

        function projectDistanceOnBearing(originLat, originLon, targetLat, targetLon, bearingRad) {{
            const dNorth = (targetLat - originLat) * Math.PI / 180 * 6371000;
            const dEast = (targetLon - originLon) * Math.PI / 180 * 6371000 * Math.cos((originLat + targetLat) * Math.PI / 360);
            return dNorth * Math.cos(bearingRad) + dEast * Math.sin(bearingRad);
        }}

        function getMetersOffset(originLat, originLon, targetLat, targetLon) {{
            return {{
                north: (targetLat - originLat) * Math.PI / 180 * 6371000,
                east: (targetLon - originLon) * Math.PI / 180 * 6371000 * Math.cos((originLat + targetLat) * Math.PI / 360),
            }};
        }}

        function decomposeDragOffset(north, east, bearingRad) {{
            return {{
                radial: north * Math.cos(bearingRad) + east * Math.sin(bearingRad),
                tangential: -north * Math.sin(bearingRad) + east * Math.cos(bearingRad),
            }};
        }}

        function buildSmartDragState(centerName, primaryName, linkedName) {{
            const centerData = autoRouteData.find(i => i.name === centerName);
            const primaryData = autoRouteData.find(i => i.name === primaryName);
            const linkedData = autoRouteData.find(i => i.name === linkedName);
            if (!centerData || !primaryData || !linkedData) {{
                return null;
            }}
            const centerLat = Number(centerData.lat || 0);
            const centerLon = Number(centerData.lon || 0);
            const primaryLat = Number(primaryData.lat || 0);
            const primaryLon = Number(primaryData.lon || 0);
            const linkedLat = Number(linkedData.lat || 0);
            const linkedLon = Number(linkedData.lon || 0);
            return {{
                centerLat,
                centerLon,
                startLat: primaryLat,
                startLon: primaryLon,
                initialBearing: bearingFromPoints(centerLat, centerLon, primaryLat, primaryLon),
                initialPrimaryRadius: calculateDistance(centerLat, centerLon, primaryLat, primaryLon),
                initialLinkedRadius: calculateDistance(centerLat, centerLon, linkedLat, linkedLon),
            }};
        }}

        function applySmartDrag(lat, lon, dragState, minPrimaryRadius) {{
            if (!dragState) {{
                return null;
            }}
            const offset = getMetersOffset(dragState.startLat, dragState.startLon, lat, lon);
            const parts = decomposeDragOffset(offset.north, offset.east, dragState.initialBearing);
            const radialDamped = parts.radial * 0.72;
            const tangentialDamped = parts.tangential * 0.55;
            const nextPrimaryRadius = Math.max(minPrimaryRadius, dragState.initialPrimaryRadius + radialDamped);
            const turningRadius = Math.max((dragState.initialPrimaryRadius + nextPrimaryRadius) / 2.0, 1.0);
            const deltaBearing = tangentialDamped / turningRadius;
            const nextBearing = dragState.initialBearing + deltaBearing;
            return {{
                primary: offsetPoint(dragState.centerLat, dragState.centerLon, nextPrimaryRadius, nextBearing),
                linked: offsetPoint(dragState.centerLat, dragState.centerLon, dragState.initialLinkedRadius, nextBearing),
            }};
        }}

        function syncAutoRouteLine() {{
            if (!autoRouteLine || !Array.isArray(autoRouteData)) {{
                return;
            }}
            autoRouteLine.setLatLngs(buildAutoRouteLinePath());
        }}

        function buildAutoRouteLinePath() {{
            const points = [];
            const routeMap = Array.isArray(autoRouteData)
                ? Object.fromEntries(autoRouteData.map(function(item) {{ return [String(item.name || ''), item]; }}))
                : {{}};
            const t1 = routeMap['T1'];
            const t2 = routeMap['T2'];
            const l1 = routeMap['L1'];
            const l2 = routeMap['L2'];
            const l3 = routeMap['L3'];
            [t1, t2].forEach(function(item) {{
                if (!item) {{
                    return;
                }}
                points.push([Number(item.lat || 0), Number(item.lon || 0)]);
            }});
            [l1, l2, l3].forEach(function(item) {{
                if (!item) {{
                    return;
                }}
                points.push([Number(item.lat || 0), Number(item.lon || 0)]);
            }});
            return points;
        }}

        function updateAutoRoutePointData(name, lat, lon) {{
            if (!Array.isArray(autoRouteData)) {{
                return;
            }}
            const target = autoRouteData.find(function(item) {{ return item.name === name; }});
            if (target) {{
                target.lat = lat;
                target.lon = lon;
            }}
        }}

        function constrainT2Position(lat, lon, t1Lat, t1Lon) {{
            const minDist = 300;
            const maxDist = 900;
            const dist = calculateDistance(t1Lat, t1Lon, lat, lon);
            if (dist < minDist || dist > maxDist) {{
                const bearing = Math.atan2(
                    (lon - t1Lon) * Math.cos((t1Lat + lat) / 2 * Math.PI / 180),
                    (lat - t1Lat)
                );
                const targetDist = Math.min(maxDist, Math.max(minDist, dist));
                const dLat = targetDist / 6371000 * Math.cos(bearing);
                const dLon = targetDist / 6371000 / Math.cos((t1Lat + lat) / 2 * Math.PI / 180) * Math.sin(bearing);
                return [t1Lat + dLat * 180 / Math.PI, t1Lon + dLon * 180 / Math.PI];
            }}
            return [lat, lon];
        }}

        function getProjectionOnLine(pLat, pLon, l1Lat, l1Lon, l3Lat, l3Lon) {{
            const dx = l3Lon - l1Lon;
            const dy = l3Lat - l1Lat;
            const t = Math.max(0, Math.min(1, ((pLon - l1Lon) * dx + (pLat - l1Lat) * dy) / (dx * dx + dy * dy)));
            return [l1Lat + t * dy, l1Lon + t * dx];
        }}

        function constrainL2Position(lat, lon, l1Lat, l1Lon, l3Lat, l3Lon) {{
            const minDistL3 = 100;
            const totalDist = calculateDistance(l1Lat, l1Lon, l3Lat, l3Lon);
            const projected = getProjectionOnLine(lat, lon, l1Lat, l1Lon, l3Lat, l3Lon);
            const bearing = bearingFromPoints(l3Lat, l3Lon, l1Lat, l1Lon);
            const projectedDistL3 = calculateDistance(projected[0], projected[1], l3Lat, l3Lon);
            const clampedDist = Math.max(minDistL3, Math.min(projectedDistL3, Math.max(minDistL3, totalDist - 1)));
            return offsetPoint(l3Lat, l3Lon, clampedDist, bearing);
        }}

        function constrainL1Position(lat, lon, l2Lat, l2Lon, l3Lat, l3Lon) {{
            const bearing = bearingFromPoints(l3Lat, l3Lon, l2Lat, l2Lon);
            const l2DistL3 = calculateDistance(l2Lat, l2Lon, l3Lat, l3Lon);
            const projectedDistL3 = projectDistanceOnBearing(l3Lat, l3Lon, lat, lon, bearing);
            const clampedDist = Math.max(l2DistL3 + 1, projectedDistL3);
            return offsetPoint(l3Lat, l3Lon, clampedDist, bearing);
        }}

        function constrainL3Position(lat, lon, l1Lat, l1Lon, l2Lat, l2Lon) {{
            const bearing = bearingFromPoints(l2Lat, l2Lon, l1Lat, l1Lon) + Math.PI;
            const distFromL2 = Math.max(1, projectDistanceOnBearing(l2Lat, l2Lon, lat, lon, bearing));
            return offsetPoint(l2Lat, l2Lon, Math.max(1, distFromL2), bearing);
        }}

        function updateAutoRoute(routeItems, homeWp) {{
            if (!autoRouteLayer) {{
                autoRouteLayer = L.layerGroup().addTo(window.map);
            }}
            autoRouteLayer.clearLayers();
            autoRouteMarkers = {{}};
            autoRouteCircles = {{}};
            autoRouteData = routeItems && routeItems.length > 0 ? routeItems : null;
            homePosition = homeWp;
            if (!autoRouteData || autoRouteData.length === 0) {{
                return;
            }}
            const autoRouteCoords = [];
            autoRouteData.forEach(function(item) {{
                const lat = Number(item.lat);
                const lon = Number(item.lon);
                if (!Number.isFinite(lat) || !Number.isFinite(lon)) {{
                    return;
                }}
                autoRouteCoords.push([lat, lon]);
                const isLocked = false;
                const marker = L.marker([lat, lon], {{
                    icon: buildAutoRouteIcon(item.name, item.phase, isLocked),
                    draggable: !isLocked,
                    title: item.description,
                    zIndexOffset: 5000
                }}).addTo(autoRouteLayer);
                const tooltipText = [
                    (Number(item.sequence || 0) > 0 ? ('航点' + Number(item.sequence) + ' / ') : '') + String(item.name || ''),
                    String(item.name || ''),
                    String(item.mode || ''),
                    '高度 ' + Number(item.alt || 0).toFixed(0) + 'm'
                ].filter(function(value, index, arr) {{ return value && arr.indexOf(value) === index; }}).join(' | ');
                marker.bindTooltip(tooltipText, {{ direction: 'top', offset: [0, -18] }});
                autoRouteMarkers[item.name] = marker;
                const shouldShowLoiterCircle = (item.name === 'T2' || item.name === 'L1')
                    && Boolean(item.loiter)
                    && Number(item.loiter_radius || 0) > 0;
                if (shouldShowLoiterCircle) {{
                    autoRouteCircles[item.name] = L.circle([lat, lon], {{
                        radius: Number(item.loiter_radius || 0),
                        color: item.name === 'T2' ? '#06b6d4' : '#f97316',
                        weight: 2,
                        opacity: 0.8,
                        fillColor: item.name === 'T2' ? '#67e8f9' : '#fdba74',
                        fillOpacity: 0.08,
                        dashArray: '8,6',
                        interactive: false,
                    }}).addTo(autoRouteLayer);
                }}
                if (!isLocked) {{
                    let smartDragState = null;
                    let lastRealtimeEmitMs = 0;
                    marker.on('dragstart', function() {{
                        if (item.name === 'L1') {{
                            smartDragState = buildSmartDragState('L3', 'L1', 'L2');
                        }} else if (item.name === 'L3') {{
                            smartDragState = buildSmartDragState('L1', 'L3', 'L2');
                        }} else {{
                            smartDragState = null;
                        }}
                    }});
                    marker.on('drag', function(event) {{
                        const pos = event.target.getLatLng();
                        const itemName = item.name;
                        let constrainedPos = [pos.lat, pos.lng];
                        let linkedL2Pos = null;
                        if (itemName === 'T2') {{
                            const t1Data = autoRouteData.find(i => i.name === 'T1');
                            constrainedPos = constrainT2Position(pos.lat, pos.lng,
                                Number((t1Data && t1Data.lat) || homeWp.lat || 0), Number((t1Data && t1Data.lon) || homeWp.lon || 0));
                        }} else if (itemName === 'T1') {{
                            constrainedPos = [pos.lat, pos.lng];
                        }} else if (itemName === 'L1') {{
                            const smartResult = applySmartDrag(
                                pos.lat,
                                pos.lng,
                                smartDragState,
                                (smartDragState ? smartDragState.initialLinkedRadius + 1.0 : 1.0)
                            );
                            if (smartResult) {{
                                constrainedPos = smartResult.primary;
                                linkedL2Pos = smartResult.linked;
                            }}
                        }} else if (itemName === 'L2') {{
                            const l1Data = autoRouteData.find(i => i.name === 'L1');
                            const l3Data = autoRouteData.find(i => i.name === 'L3');
                            if (l1Data && l3Data) {{
                                constrainedPos = constrainL2Position(pos.lat, pos.lng,
                                    Number(l1Data.lat || 0), Number(l1Data.lon || 0),
                                    Number(l3Data.lat || 0), Number(l3Data.lon || 0));
                            }}
                        }} else if (itemName === 'L3') {{
                            const smartResult = applySmartDrag(
                                pos.lat,
                                pos.lng,
                                smartDragState,
                                (smartDragState ? smartDragState.initialLinkedRadius + 100.0 : 100.0)
                            );
                            if (smartResult) {{
                                constrainedPos = smartResult.primary;
                                linkedL2Pos = smartResult.linked;
                            }}
                        }}
                        marker.setLatLng(constrainedPos);
                        updateAutoRoutePointData(itemName, constrainedPos[0], constrainedPos[1]);
                        if (autoRouteCircles[itemName]) {{
                            autoRouteCircles[itemName].setLatLng(constrainedPos);
                        }}
                        if ((itemName === 'L1' || itemName === 'L3') && linkedL2Pos) {{
                            const linkedL2Marker = autoRouteMarkers['L2'];
                            if (linkedL2Marker) {{
                                linkedL2Marker.setLatLng(linkedL2Pos);
                            }}
                            updateAutoRoutePointData('L2', linkedL2Pos[0], linkedL2Pos[1]);
                        }}
                        syncAutoRouteLine();
                        const now = Date.now();
                        if ((now - lastRealtimeEmitMs) > 33 && mapBridge && typeof mapBridge.moveAutoRoutePointRealtime === 'function') {{
                            lastRealtimeEmitMs = now;
                            mapBridge.moveAutoRoutePointRealtime(itemName, constrainedPos[0], constrainedPos[1]);
                            if ((itemName === 'L1' || itemName === 'L3') && linkedL2Pos) {{
                                mapBridge.moveAutoRoutePointRealtime('L2', linkedL2Pos[0], linkedL2Pos[1]);
                            }}
                        }}
                    }});
                    marker.on('dragend', function(event) {{
                        const pos = event.target.getLatLng();
                        smartDragState = null;
                        if (mapBridge && typeof mapBridge.moveAutoRoutePoint === 'function') {{
                            mapBridge.moveAutoRoutePoint(item.name, pos.lat, pos.lng);
                            if (item.name === 'L1' || item.name === 'L3') {{
                                const linkedL2 = autoRouteData.find(i => i.name === 'L2');
                                if (linkedL2) {{
                                    mapBridge.moveAutoRoutePoint('L2', Number(linkedL2.lat || 0), Number(linkedL2.lon || 0));
                                }}
                            }}
                        }}
                    }});
                }}
            }});
            if (autoRouteLine) {{
                autoRouteLayer.removeLayer(autoRouteLine);
            }}
            const linePath = buildAutoRouteLinePath();
            if (linePath.length > 1) {{
                autoRouteLine = L.polyline(linePath, {{ color: '#9333ea', weight: 2, opacity: 0.6, dashArray: '5,5', interactive: false }}).addTo(autoRouteLayer);
            }}
        }}

        window.updateAutoRoute = updateAutoRoute;

        let renderedWaypoints = [];

        function redrawRouteLine() {{
            if (routeLine) {{
                window.map.removeLayer(routeLine);
                routeLine = null;
            }}
            if (waypointCoords.length > 1) {{
                routeLine = L.polyline(waypointCoords, {{ color: '#0284c7', weight: 3, opacity: 0.85 }}).addTo(window.map);
            }}
        }}

        function attachWaypointEvents(marker, index, getLoiterCircle) {{
            let lastRealtimeEmitMs = 0;
            marker.off('click');
            marker.off('drag');
            marker.off('dragend');
            marker.off('contextmenu');
            marker.on('click', function() {{
                if (mapBridge && mapBridge.selectWaypoint) {{
                    if (mapBridge.selectWaypointAny) {{
                        mapBridge.selectWaypointAny(index);
                    }} else {{
                        mapBridge.selectWaypoint(Number(index));
                    }}
                }}
                // 本地立即更新图标高亮（无需等待 Python 回调）
                if (window.selectWaypointOnMap) {{ window.selectWaypointOnMap(index); }}
            }});
            marker.on('contextmenu', function(event) {{
                if (event && event.originalEvent) {{
                    event.originalEvent.preventDefault();
                }}
                const pt = window.map.latLngToContainerPoint(event.latlng);
                showWaypointContextMenu(pt.x, pt.y, index);
            }});
            marker.on('drag', function(event) {{
                const position = event.target.getLatLng();
                waypointCoords[index] = [position.lat, position.lng];
                if (routeLine) {{
                    routeLine.setLatLngs(waypointCoords);
                }}
                const loiterCircle = getLoiterCircle();
                if (loiterCircle) {{
                    loiterCircle.setLatLng(position);
                }}
                const now = Date.now();
                const hasRealtimeAny = mapBridge && typeof mapBridge.moveWaypointRealtimeAny === 'function';
                const hasRealtime = mapBridge && typeof mapBridge.moveWaypointRealtime === 'function';
                if ((hasRealtimeAny || hasRealtime) && (now - lastRealtimeEmitMs) > 33) {{
                    lastRealtimeEmitMs = now;
                    if (hasRealtimeAny) {{
                        mapBridge.moveWaypointRealtimeAny(index, position.lat, position.lng);
                    }} else {{
                        mapBridge.moveWaypointRealtime(Number(index), Number(position.lat), Number(position.lng));
                    }}
                }}
            }});
            marker.on('dragend', function(event) {{
                const position = event.target.getLatLng();
                waypointCoords[index] = [position.lat, position.lng];
                if (routeLine) {{
                    routeLine.setLatLngs(waypointCoords);
                }}
                const hasMoveAny = mapBridge && typeof mapBridge.moveWaypointAny === 'function';
                const hasMove = mapBridge && typeof mapBridge.moveWaypoint === 'function';
                if (hasMoveAny || hasMove) {{
                    if (hasMoveAny) {{
                        mapBridge.moveWaypointAny(index, position.lat, position.lng);
                    }} else {{
                        mapBridge.moveWaypoint(Number(index), Number(position.lat), Number(position.lng));
                    }}
                }}
            }});
        }}

        function rebuildWaypointIndexes(startIndex) {{
            for (let index = Math.max(0, startIndex); index < waypointMarkers.length; index += 1) {{
                const marker = waypointMarkers[index];
                const waypoint = renderedWaypoints[index];
                if (!marker || !waypoint) {{
                    continue;
                }}
                marker.setIcon(buildWaypointIcon(index, String(waypoint.type || 'WAYPOINT'), waypoint));
                marker.bindPopup(buildWaypointPopup(index, waypoint));
                attachWaypointEvents(marker, index, function() {{ return loiterCircles[index] || null; }});
            }}
        }}

        window.updateWaypoints = function(waypoints) {{
            waypointLayer.clearLayers();
            loiterLayer.clearLayers();
            waypointMarkers = [];
            loiterCircles = [];
            waypointCoords = [];
            renderedWaypoints = Array.isArray(waypoints) ? waypoints.slice() : [];
            if (routeLine) {{
                window.map.removeLayer(routeLine);
                routeLine = null;
            }}
            if (!Array.isArray(waypoints) || waypoints.length === 0) {{
                return;
            }}
            waypoints.forEach(function(wp, index) {{
                const lat = Number(wp.lat);
                const lon = Number(wp.lon);
                const alt = Number(wp.alt || 0);
                const missionType = String(wp.type || 'WAYPOINT');
                const loiter = Boolean(wp.loiter);
                const loiterRadius = Number(wp.loiter_radius || wp.param3 || 60);
                if (!Number.isFinite(lat) || !Number.isFinite(lon)) {{
                    return;
                }}
                waypointCoords.push([lat, lon]);
                const icon = buildWaypointIcon(index, missionType, wp);
                const popupText = buildWaypointPopup(index, wp);
                let loiterCircle = null;
                const marker = L.marker([lat, lon], {{ icon, draggable: true }}).bindPopup(
                    popupText
                ).addTo(waypointLayer);
                // 确保拖动功能启用（popup打开时可能会禁用）
                if (marker.dragging) {{
                    marker.dragging.enable();
                }}
                waypointMarkers[index] = marker;
                attachWaypointEvents(marker, index, function() {{ return loiterCircle; }});
                if (loiter) {{
                    loiterCircle = L.circle([lat, lon], {{
                        radius: Number.isFinite(loiterRadius) && loiterRadius > 0 ? loiterRadius : 60,
                        color: '#0f766e',
                        weight: 2,
                        opacity: 0.8,
                        fillColor: '#34d399',
                        fillOpacity: 0.08,
                        dashArray: '8,6',
                        interactive: false,
                    }}).addTo(loiterLayer);
                }}
                loiterCircles[index] = loiterCircle;
            }});
            redrawRouteLine();
            if (selectedWaypointIndex >= 0 && selectedWaypointIndex < waypointMarkers.length) {{
                const m = waypointMarkers[selectedWaypointIndex];
                const w = renderedWaypoints[selectedWaypointIndex];
                if (m && w) {{
                    m.setIcon(buildWaypointIcon(selectedWaypointIndex, String(w.type || 'WAYPOINT'), w));
                }}
            }}
        }};

        window.syncWaypointRange = function(startIndex, removeCount, insertItems) {{
            const start = Math.max(0, Number(startIndex) || 0);
            const removeTotal = Math.max(0, Number(removeCount) || 0);
            const items = Array.isArray(insertItems) ? insertItems : [];

            for (let offset = 0; offset < removeTotal; offset += 1) {{
                const marker = waypointMarkers[start + offset];
                const loiterCircle = loiterCircles[start + offset];
                if (marker) {{
                    waypointLayer.removeLayer(marker);
                }}
                if (loiterCircle) {{
                    loiterLayer.removeLayer(loiterCircle);
                }}
            }}

            waypointMarkers.splice(start, removeTotal);
            loiterCircles.splice(start, removeTotal);
            waypointCoords.splice(start, removeTotal);
            renderedWaypoints.splice(start, removeTotal, ...items);

            const createdMarkers = [];
            const createdCircles = [];
            const createdCoords = [];
            items.forEach(function(wp, offset) {{
                const index = start + offset;
                const lat = Number(wp.lat);
                const lon = Number(wp.lon);
                if (!Number.isFinite(lat) || !Number.isFinite(lon)) {{
                    return;
                }}
                const marker = L.marker([lat, lon], {{
                    icon: buildWaypointIcon(index, String(wp.type || 'WAYPOINT'), wp),
                    draggable: true,
                }}).bindPopup(buildWaypointPopup(index, wp)).addTo(waypointLayer);
                // 确保拖动功能启用（popup打开时可能会禁用）
                if (marker.dragging) {{
                    marker.dragging.enable();
                }}
                let loiterCircle = null;
                const loiter = Boolean(wp.loiter);
                const loiterRadius = Number(wp.loiter_radius || wp.param3 || 60);
                if (loiter) {{
                    loiterCircle = L.circle([lat, lon], {{
                        radius: Number.isFinite(loiterRadius) && loiterRadius > 0 ? loiterRadius : 60,
                        color: '#0f766e',
                        weight: 2,
                        opacity: 0.8,
                        fillColor: '#34d399',
                        fillOpacity: 0.08,
                        dashArray: '8,6',
                        interactive: false,
                    }}).addTo(loiterLayer);
                }}
                createdMarkers.push(marker);
                createdCircles.push(loiterCircle);
                createdCoords.push([lat, lon]);
            }});

            waypointMarkers.splice(start, 0, ...createdMarkers);
            loiterCircles.splice(start, 0, ...createdCircles);
            waypointCoords.splice(start, 0, ...createdCoords);
            rebuildWaypointIndexes(start);
            redrawRouteLine();
            if (selectedWaypointIndex >= 0 && selectedWaypointIndex < waypointMarkers.length) {{
                const m = waypointMarkers[selectedWaypointIndex];
                const w = renderedWaypoints[selectedWaypointIndex];
                if (m && w) {{
                    m.setIcon(buildWaypointIcon(selectedWaypointIndex, String(w.type || 'WAYPOINT'), w));
                }}
            }}
        }};

        window.moveWaypointMarker = function(index, waypoint) {{
            if (!Number.isInteger(index) || index < 0) {{
                return;
            }}
            const marker = waypointMarkers[index];
            if (!marker || !waypoint) {{
                return;
            }}
            const lat = Number(waypoint.lat);
            const lon = Number(waypoint.lon);
            if (!Number.isFinite(lat) || !Number.isFinite(lon)) {{
                return;
            }}
            marker.setLatLng([lat, lon]);
            marker.setIcon(buildWaypointIcon(index, String(waypoint.type || 'WAYPOINT'), waypoint));
            marker.bindPopup(buildWaypointPopup(index, waypoint));
            // 确保拖动功能启用（popup更新时可能会禁用）
            if (marker.dragging) {{
                marker.dragging.enable();
            }}
            waypointCoords[index] = [lat, lon];
            if (routeLine) {{
                routeLine.setLatLngs(waypointCoords);
            }}
            const loiter = Boolean(waypoint.loiter);
            const loiterRadius = Number(waypoint.loiter_radius || waypoint.param3 || 60);
            if (loiter) {{
                if (!loiterCircles[index]) {{
                    loiterCircles[index] = L.circle([lat, lon], {{
                        radius: Number.isFinite(loiterRadius) && loiterRadius > 0 ? loiterRadius : 60,
                        color: '#0f766e',
                        weight: 2,
                        opacity: 0.8,
                        fillColor: '#34d399',
                        fillOpacity: 0.08,
                        dashArray: '8,6',
                        interactive: false,
                    }}).addTo(loiterLayer);
                }} else {{
                    loiterCircles[index].setLatLng([lat, lon]);
                    loiterCircles[index].setRadius(Number.isFinite(loiterRadius) && loiterRadius > 0 ? loiterRadius : 60);
                }}
            }} else if (loiterCircles[index]) {{
                loiterLayer.removeLayer(loiterCircles[index]);
                loiterCircles[index] = null;
            }}
        }};

        window.setVehiclePosition = function(vehicle) {{
            window.applyOverlayState({{ vehicle: vehicle }});
        }};

        window.clearVehiclePosition = function() {{
            window.applyOverlayState({{ vehicle: null }});
        }};

            window.mapReady = true;
            bindBridge();
        }};

        loadLeafletStylesheet(0);
        loadLeafletScript(0);
    </script>
</body>
</html>
"""

    @staticmethod
    def _map_cache_dir_name(map_name: str) -> str:
        return MAP_CACHE_DIR_NAMES.get(map_name, map_name.lower().replace(" ", "_"))

    @classmethod
    def _migrate_legacy_cache_dirs(cls):
        for map_name, dir_name in MAP_CACHE_DIR_NAMES.items():
            legacy_dir = OFFLINE_TILE_DIR / map_name
            english_dir = OFFLINE_TILE_DIR / dir_name
            if not legacy_dir.exists() or english_dir.exists():
                continue
            try:
                english_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(legacy_dir), str(english_dir))
                logger.info("Migrated legacy cache directory: %s -> %s", legacy_dir, english_dir)
            except Exception as exc:
                logger.warning("Failed to migrate legacy cache directory %s: %s", legacy_dir, exc)

    @staticmethod
    def _offline_tile_template(map_name: str) -> str:
        dir_name = MapController._map_cache_dir_name(map_name)
        return f"gcstile:///tiles/{dir_name}/{{z}}/{{x}}/{{y}}.png"

    @staticmethod
    def _offline_elevation_template() -> str:
        return "gcstile:///elevation/{z}/{x}/{y}.png"
