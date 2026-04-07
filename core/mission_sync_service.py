from __future__ import annotations

import math
from typing import Optional

from core.mission import build_upload_waypoints as mission_build_upload_waypoints
from core.mission import split_downloaded_mission as mission_split_downloaded_mission
from core.mission import validate_upload_waypoints as mission_validate_upload_waypoints


class MissionSyncService:
    @staticmethod
    def build_upload_waypoints(visible_waypoints: list[dict], auto_route_items: list[dict], home_position: Optional[dict]) -> list[dict]:
        return mission_build_upload_waypoints(visible_waypoints, auto_route_items, home_position)

    @staticmethod
    def validate_upload_waypoints(waypoints: list[dict]) -> tuple[bool, str]:
        return mission_validate_upload_waypoints(waypoints)

    @staticmethod
    def describe_upload(mission_waypoints: list[dict], visible_count: int = 0) -> dict:
        items = [dict(wp) for wp in (mission_waypoints or [])]
        has_home_item = bool(items and str(items[0].get("name", "") or "").upper() == "HOME")
        display_count = max(0, len(items) - (1 if has_home_item else 0))
        if visible_count > 0:
            display_count = int(visible_count)
        return {
            "mission_waypoints": items,
            "total_count": len(items),
            "display_count": display_count,
            "has_home_item": has_home_item,
        }

    @staticmethod
    def _extract_home_position(downloaded: list[dict], existing_home_position: Optional[dict] = None) -> Optional[dict]:
        if existing_home_position:
            return dict(existing_home_position)
        for item in (downloaded or []):
            try:
                seq = int((item or {}).get("seq", -1) or -1)
                name = str((item or {}).get("name", "") or "").upper()
                wp_type = str((item or {}).get("type", "") or "").upper()
                if seq != 0 and name != "HOME" and wp_type != "HOME":
                    continue
                lat = float((item or {}).get("lat", 0.0) or 0.0)
                lon = float((item or {}).get("lon", 0.0) or 0.0)
                alt = float((item or {}).get("alt", 0.0) or 0.0)
            except Exception:
                continue
            if not (math.isfinite(lat) and math.isfinite(lon)):
                continue
            return {
                "type": "HOME",
                "lat": lat,
                "lon": lon,
                "alt": alt,
                "source": "mission_wp0",
            }
        return None

    @classmethod
    def describe_download(
        cls,
        downloaded: list[dict],
        existing_home_position: Optional[dict] = None,
        auto_route_items: Optional[list[dict]] = None,
    ) -> dict:
        downloaded_items = [dict(wp) for wp in (downloaded or [])]
        home_position = cls._extract_home_position(downloaded_items, existing_home_position)
        auto_route_overrides, waypoints = mission_split_downloaded_mission(
            downloaded_items,
            home_position,
            list(auto_route_items or []),
        )
        return {
            "home_position": home_position,
            "auto_route_overrides": dict(auto_route_overrides or {}),
            "waypoints": [dict(wp) for wp in (waypoints or [])],
            "total_downloaded": len(downloaded_items),
            "visible_count": len(waypoints or []),
        }

    def prepare_upload(self, visible_waypoints: list[dict], auto_route_items: list[dict], home_position: Optional[dict]) -> dict:
        mission_waypoints = self.build_upload_waypoints(visible_waypoints, auto_route_items, home_position)
        valid, message = self.validate_upload_waypoints(mission_waypoints)
        summary = self.describe_upload(mission_waypoints, visible_count=len(visible_waypoints or []))
        summary.update({"valid": bool(valid), "message": str(message or "")})
        return summary

    @staticmethod
    def _visible_compare_rows(items: list[dict]) -> list[dict]:
        rows: list[dict] = []
        for item in (items or []):
            data = dict(item or {})
            if str(data.get("name", "") or "").upper() == "HOME":
                continue
            rows.append(
                {
                    "type": str(data.get("type", "WAYPOINT") or "WAYPOINT").upper(),
                    "command": int(data.get("command", 0) or 0),
                    "lat": float(data.get("lat", 0.0) or 0.0),
                    "lon": float(data.get("lon", 0.0) or 0.0),
                    "alt": float(data.get("alt", 0.0) or 0.0),
                }
            )
        return rows

    def verify_roundtrip(
        self,
        visible_waypoints: list[dict],
        downloaded: list[dict],
        *,
        home_position: Optional[dict] = None,
        auto_route_items: Optional[list[dict]] = None,
        tolerance: float = 1e-5,
        alt_tolerance: float = 1.0,
    ) -> dict:
        upload_plan = self.prepare_upload(list(visible_waypoints or []), list(auto_route_items or []), home_position)
        download_plan = self.prepare_download(
            list(downloaded or []),
            existing_home_position=home_position,
            auto_route_items=list(auto_route_items or []),
        )
        expected_rows = self._visible_compare_rows(upload_plan.get("mission_waypoints") or [])
        actual_rows = self._visible_compare_rows(download_plan.get("waypoints") or [])
        messages: list[str] = []

        if len(expected_rows) != len(actual_rows):
            messages.append(f"任务点数量不一致: 期望 {len(expected_rows)}，回读 {len(actual_rows)}")

        for index, (expected, actual) in enumerate(zip(expected_rows, actual_rows), start=1):
            if expected["type"] != actual["type"] or expected["command"] != actual["command"]:
                messages.append(
                    f"第 {index} 点类型不一致: {expected['type']}/{expected['command']} -> {actual['type']}/{actual['command']}"
                )
                continue
            if abs(expected["lat"] - actual["lat"]) > tolerance or abs(expected["lon"] - actual["lon"]) > tolerance:
                messages.append(
                    f"第 {index} 点坐标偏移: ({expected['lat']:.6f}, {expected['lon']:.6f}) -> ({actual['lat']:.6f}, {actual['lon']:.6f})"
                )
            if abs(expected["alt"] - actual["alt"]) > alt_tolerance:
                messages.append(f"第 {index} 点高度偏移: {expected['alt']:.1f}m -> {actual['alt']:.1f}m")

        matched = len(messages) == 0
        summary = (
            f"上传回读校验通过：{len(actual_rows)}/{len(expected_rows)} 个任务点一致"
            if matched
            else f"上传回读校验发现 {len(messages)} 处差异"
        )
        return {
            "matched": matched,
            "summary": summary,
            "mismatch_count": len(messages),
            "messages": messages,
            "expected_count": len(expected_rows),
            "actual_count": len(actual_rows),
        }

    def prepare_download(
        self,
        downloaded: list[dict],
        existing_home_position: Optional[dict] = None,
        auto_route_items: Optional[list[dict]] = None,
    ) -> dict:
        return self.describe_download(
            downloaded,
            existing_home_position=existing_home_position,
            auto_route_items=auto_route_items,
        )


__all__ = ["MissionSyncService"]
