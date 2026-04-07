from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .protocol import MAV_CMD_NAV_WAYPOINT, normalize_waypoint


QGC_PLAN_FILE_TYPE = "Plan"
QGC_GROUND_STATION = "QGroundControl"
QGC_PLAN_VERSION = 1
QGC_MISSION_VERSION = 2
QGC_GEOFENCE_VERSION = 2
QGC_RALLYPOINT_VERSION = 2


@dataclass
class MissionItem:
    sequence_number: int
    command: int
    frame: int
    params: List[float]
    auto_continue: bool = True
    is_current_item: bool = False
    raw_type: str = "WAYPOINT"
    name: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_waypoint(cls, waypoint: Dict[str, Any], sequence_number: Optional[int] = None) -> "MissionItem":
        wp = normalize_waypoint(waypoint)
        seq = int(sequence_number if sequence_number is not None else wp.get("seq", 0))
        return cls(
            sequence_number=seq,
            command=int(wp.get("command", MAV_CMD_NAV_WAYPOINT)),
            frame=int(wp.get("frame", 6)),
            params=[
                float(wp.get("param1", 0.0) or 0.0),
                float(wp.get("param2", 0.0) or 0.0),
                float(wp.get("param3", 0.0) or 0.0),
                float(wp.get("param4", 0.0) or 0.0),
                float(wp.get("lat", 0.0) or 0.0),
                float(wp.get("lon", 0.0) or 0.0),
                float(wp.get("alt", 0.0) or 0.0),
            ],
            auto_continue=bool(wp.get("autocontinue", 1)),
            is_current_item=bool(wp.get("current", 0)),
            raw_type=str(wp.get("type", "WAYPOINT") or "WAYPOINT"),
            name=str(wp.get("name", "") or ""),
            metadata={
                "source_frame": wp.get("source_frame", wp.get("frame", 6)),
                "source_alt": wp.get("source_alt", wp.get("alt", 0.0)),
                "description": wp.get("description", ""),
                "loiter": wp.get("loiter", False),
                "loiter_radius": wp.get("loiter_radius", 0.0),
                "loiter_time": wp.get("loiter_time", 0.0),
            },
        )

    @classmethod
    def from_plan_json(cls, data: Dict[str, Any], sequence_number: Optional[int] = None) -> "MissionItem":
        params = list(data.get("params", []))
        while len(params) < 7:
            params.append(0.0)
        seq = int(data.get("doJumpId", data.get("sequenceNumber", sequence_number or 0)) or 0)
        return cls(
            sequence_number=seq,
            command=int(data.get("command", MAV_CMD_NAV_WAYPOINT) or MAV_CMD_NAV_WAYPOINT),
            frame=int(data.get("frame", 6) or 6),
            params=[float(value or 0.0) for value in params[:7]],
            auto_continue=bool(data.get("autoContinue", True)),
            is_current_item=bool(data.get("AMSLAltAboveTerrain", False) and False),
            raw_type=str(data.get("rawType", "WAYPOINT") or "WAYPOINT"),
            name=str(data.get("name", "") or ""),
            metadata={key: value for key, value in data.items() if key not in {
                "autoContinue", "command", "doJumpId", "frame", "params", "type", "sequenceNumber", "rawType", "name"
            }},
        )

    def to_plan_json(self) -> Dict[str, Any]:
        payload = {
            "type": "SimpleItem",
            "autoContinue": bool(self.auto_continue),
            "command": int(self.command),
            "doJumpId": int(self.sequence_number),
            "sequenceNumber": int(self.sequence_number),
            "frame": int(self.frame),
            "params": [float(value or 0.0) for value in self.params[:7]],
            "rawType": self.raw_type,
            "name": self.name,
        }
        payload.update(self.metadata)
        return payload

    def to_waypoint(self, sequence_number: Optional[int] = None) -> Dict[str, Any]:
        seq = int(self.sequence_number if sequence_number is None else sequence_number)
        return normalize_waypoint({
            "seq": seq,
            "command": int(self.command),
            "frame": int(self.frame),
            "param1": float(self.params[0]),
            "param2": float(self.params[1]),
            "param3": float(self.params[2]),
            "param4": float(self.params[3]),
            "lat": float(self.params[4]),
            "lon": float(self.params[5]),
            "alt": float(self.params[6]),
            "autocontinue": 1 if self.auto_continue else 0,
            "current": 1 if self.is_current_item else 0,
            "type": self.raw_type,
            "name": self.name,
            **self.metadata,
        })


@dataclass
class VisualMissionItem:
    sequence_number: int
    mission_item: MissionItem
    dirty: bool = False
    is_current_item: bool = False
    home_position: bool = False
    child_items: List[MissionItem] = field(default_factory=list)

    @property
    def last_sequence_number(self) -> int:
        if self.child_items:
            return max(item.sequence_number for item in self.child_items)
        return self.sequence_number

    def append_mission_items(self) -> List[MissionItem]:
        return [self.mission_item] + list(self.child_items)

    def to_plan_json(self) -> Dict[str, Any]:
        return self.mission_item.to_plan_json()


def _extract_mission_items_from_value(value: Any) -> List[MissionItem]:
    extracted: List[MissionItem] = []
    if isinstance(value, dict):
        item_type = str(value.get("type", "") or "")
        if item_type == "SimpleItem" and "params" in value and "command" in value:
            extracted.append(MissionItem.from_plan_json(value))
        for nested in value.values():
            extracted.extend(_extract_mission_items_from_value(nested))
    elif isinstance(value, list):
        for nested in value:
            extracted.extend(_extract_mission_items_from_value(nested))
    return extracted


@dataclass
class ComplexVisualMissionItem:
    sequence_number: int
    complex_item_type: str
    raw_object: Dict[str, Any]
    generated_items: List[MissionItem] = field(default_factory=list)
    dirty: bool = False

    @classmethod
    def from_plan_json(cls, data: Dict[str, Any], sequence_number: int) -> "ComplexVisualMissionItem":
        complex_type = str(data.get("complexItemType", data.get("complexItemTypeKey", "generic")) or "generic")
        generated_items = _extract_mission_items_from_value(data)
        if generated_items:
            for offset, item in enumerate(generated_items, start=sequence_number):
                item.sequence_number = offset
        return cls(sequence_number=sequence_number, complex_item_type=complex_type, raw_object=dict(data), generated_items=generated_items)

    @property
    def last_sequence_number(self) -> int:
        if self.generated_items:
            return max(item.sequence_number for item in self.generated_items)
        return self.sequence_number

    def append_mission_items(self) -> List[MissionItem]:
        return list(self.generated_items)

    def to_plan_json(self) -> Dict[str, Any]:
        payload = dict(self.raw_object)
        payload.setdefault("type", "ComplexItem")
        payload.setdefault("complexItemType", self.complex_item_type)
        return payload


@dataclass
class SurveyComplexItem(ComplexVisualMissionItem):
    pass


@dataclass
class CorridorComplexItem(ComplexVisualMissionItem):
    pass


@dataclass
class StructureComplexItem(ComplexVisualMissionItem):
    pass


@dataclass
class MissionController:
    planned_home_position: Optional[Dict[str, Any]] = None
    visual_items: List[object] = field(default_factory=list)
    cruise_speed: float = 15.0
    hover_speed: float = 5.0
    firmware_type: int = 12
    vehicle_type: int = 20

    @staticmethod
    def _complex_raw_with_generated_items(complex_item_type: str, items: List[MissionItem]) -> Dict[str, Any]:
        simple_items = [item.to_plan_json() for item in items]
        key = {
            "survey": "TransectStyleComplexItem",
            "corridorscan": "CorridorScanComplexItem",
            "structurescan": "StructureScanComplexItem",
        }.get(complex_item_type.lower(), "ComplexItemData")
        return {
            "type": "ComplexItem",
            "complexItemType": complex_item_type,
            key: {
                "items": simple_items,
            },
        }

    @classmethod
    def from_waypoints_with_complex_metadata(cls, waypoints: Sequence[Dict[str, Any]]) -> "MissionController":
        home: Optional[Dict[str, Any]] = None
        sequence = 1
        grouped: Dict[int, Dict[str, Any]] = {}
        ordered_entries: List[tuple[str, Any]] = []

        for raw in waypoints or []:
            wp = normalize_waypoint(raw)
            is_home = (
                int(wp.get("seq", -1)) == 0
                or str(wp.get("type", "") or "").upper() == "HOME"
                or str(wp.get("name", "") or "").upper() == "HOME"
            )
            if is_home and home is None:
                home = {
                    "type": "HOME",
                    "lat": float(wp.get("lat", 0.0) or 0.0),
                    "lon": float(wp.get("lon", 0.0) or 0.0),
                    "alt": float(wp.get("alt", 0.0) or 0.0),
                }
                continue

            group_raw = wp.get("complex_group")
            if group_raw in (None, ""):
                ordered_entries.append(("simple", wp))
                continue

            group_id = int(group_raw)
            if group_id not in grouped:
                grouped[group_id] = {
                    "complex_item_type": str(wp.get("complex_item_type", "survey") or "survey"),
                    "waypoints": [],
                }
                ordered_entries.append(("complex", group_id))
            grouped[group_id]["waypoints"].append(wp)

        visual_items: List[object] = []
        for entry_type, entry_value in ordered_entries:
            if entry_type == "simple":
                mission_item = MissionItem.from_waypoint(entry_value, sequence_number=sequence)
                visual_items.append(VisualMissionItem(sequence_number=sequence, mission_item=mission_item))
                sequence += 1
                continue

            group_payload = grouped.get(int(entry_value), {})
            complex_type = str(group_payload.get("complex_item_type", "survey") or "survey").lower()
            generated_items: List[MissionItem] = []
            for wp in group_payload.get("waypoints", []):
                item = MissionItem.from_waypoint(wp, sequence_number=sequence)
                generated_items.append(item)
                sequence += 1

            complex_cls_map = {
                "survey": SurveyComplexItem,
                "corridorscan": CorridorComplexItem,
                "structurescan": StructureComplexItem,
            }
            complex_cls = complex_cls_map.get(complex_type, ComplexVisualMissionItem)
            raw_object = cls._complex_raw_with_generated_items(complex_type, generated_items)
            visual_items.append(
                complex_cls(
                    sequence_number=generated_items[0].sequence_number if generated_items else sequence,
                    complex_item_type=complex_type,
                    raw_object=raw_object,
                    generated_items=generated_items,
                )
            )

        return cls(planned_home_position=home, visual_items=visual_items)

    @classmethod
    def from_waypoints(cls, waypoints: Sequence[Dict[str, Any]]) -> "MissionController":
        home: Optional[Dict[str, Any]] = None
        visual_items: List[object] = []
        sequence = 1
        for raw in waypoints or []:
            wp = normalize_waypoint(raw)
            is_home = (
                int(wp.get("seq", -1)) == 0
                or str(wp.get("type", "") or "").upper() == "HOME"
                or str(wp.get("name", "") or "").upper() == "HOME"
            )
            if is_home and home is None:
                home = {
                    "type": "HOME",
                    "lat": float(wp.get("lat", 0.0) or 0.0),
                    "lon": float(wp.get("lon", 0.0) or 0.0),
                    "alt": float(wp.get("alt", 0.0) or 0.0),
                }
                continue
            mission_item = MissionItem.from_waypoint(wp, sequence_number=sequence)
            visual_items.append(VisualMissionItem(sequence_number=sequence, mission_item=mission_item))
            sequence += 1
        return cls(planned_home_position=home, visual_items=visual_items)

    @classmethod
    def from_plan_json(cls, data: Dict[str, Any]) -> "MissionController":
        mission = dict(data.get("mission", data))
        home_position = None
        planned_home = mission.get("plannedHomePosition")
        if isinstance(planned_home, list) and len(planned_home) >= 3:
            home_position = {
                "type": "HOME",
                "lat": float(planned_home[0] or 0.0),
                "lon": float(planned_home[1] or 0.0),
                "alt": float(planned_home[2] or 0.0),
            }

        visual_items: List[object] = []
        sequence = 1
        for item_data in mission.get("items", []):
            item_type = str(item_data.get("type", "SimpleItem") or "SimpleItem")
            if item_type == "SimpleItem":
                mission_item = MissionItem.from_plan_json(item_data, sequence_number=sequence)
                mission_item.sequence_number = sequence
                visual_items.append(VisualMissionItem(sequence_number=sequence, mission_item=mission_item))
                sequence += 1
                continue

            complex_type = str(item_data.get("complexItemType", "generic") or "generic").lower()
            cls_map = {
                "survey": SurveyComplexItem,
                "corridorscan": CorridorComplexItem,
                "structurescan": StructureComplexItem,
            }
            complex_cls = cls_map.get(complex_type, ComplexVisualMissionItem)
            complex_item = complex_cls.from_plan_json(item_data, sequence)
            visual_items.append(complex_item)
            sequence = complex_item.last_sequence_number + 1

        return cls(
            planned_home_position=home_position,
            visual_items=visual_items,
            cruise_speed=float(mission.get("cruiseSpeed", 15.0) or 15.0),
            hover_speed=float(mission.get("hoverSpeed", 5.0) or 5.0),
            firmware_type=int(mission.get("firmwareType", 12) or 12),
            vehicle_type=int(mission.get("vehicleType", 20) or 20),
        )

    def to_mission_items(self) -> List[MissionItem]:
        mission_items: List[MissionItem] = []
        for visual_item in self.visual_items:
            mission_items.extend(visual_item.append_mission_items())
        for seq, item in enumerate(mission_items, start=1):
            item.sequence_number = seq
        return mission_items

    def to_waypoints(self, include_home: bool = True) -> List[Dict[str, Any]]:
        waypoints: List[Dict[str, Any]] = []
        if include_home and self.planned_home_position:
            waypoints.append(normalize_waypoint({**self.planned_home_position, "seq": 0, "name": "HOME", "type": "HOME"}))
        complex_group = 1
        for visual_item in self.visual_items:
            if isinstance(visual_item, VisualMissionItem):
                waypoints.append(visual_item.mission_item.to_waypoint())
                continue
            if isinstance(visual_item, ComplexVisualMissionItem):
                for item in visual_item.append_mission_items():
                    wp = item.to_waypoint()
                    wp["complex_group"] = complex_group
                    wp["complex_item_type"] = visual_item.complex_item_type
                    waypoints.append(normalize_waypoint(wp))
                complex_group += 1
        return waypoints

    def to_plan_json(self) -> Dict[str, Any]:
        mission_items_json = [visual_item.to_plan_json() for visual_item in self.visual_items]
        home = self.planned_home_position or {"lat": 0.0, "lon": 0.0, "alt": 0.0}
        return {
            "fileType": QGC_PLAN_FILE_TYPE,
            "groundStation": QGC_GROUND_STATION,
            "version": QGC_PLAN_VERSION,
            "mission": {
                "version": QGC_MISSION_VERSION,
                "firmwareType": int(self.firmware_type),
                "vehicleType": int(self.vehicle_type),
                "cruiseSpeed": float(self.cruise_speed),
                "hoverSpeed": float(self.hover_speed),
                "plannedHomePosition": [
                    float(home.get("lat", 0.0) or 0.0),
                    float(home.get("lon", 0.0) or 0.0),
                    float(home.get("alt", 0.0) or 0.0),
                ],
                "items": mission_items_json,
            },
            "geoFence": {"version": QGC_GEOFENCE_VERSION, "circles": [], "polygons": []},
            "rallyPoints": {"version": QGC_RALLYPOINT_VERSION, "points": []},
        }


@dataclass
class GeoFenceCircle:
    center: List[float]
    radius: float
    inclusion: bool = True

    @classmethod
    def from_plan_json(cls, data: Dict[str, Any]) -> "GeoFenceCircle":
        center = list(data.get("center", [0.0, 0.0]))
        while len(center) < 2:
            center.append(0.0)
        return cls(
            center=[float(center[0] or 0.0), float(center[1] or 0.0)],
            radius=float(data.get("radius", 0.0) or 0.0),
            inclusion=bool(data.get("inclusion", True)),
        )

    def to_plan_json(self) -> Dict[str, Any]:
        return {
            "center": [float(self.center[0]), float(self.center[1])],
            "radius": float(self.radius),
            "inclusion": bool(self.inclusion),
        }


@dataclass
class GeoFencePolygon:
    points: List[List[float]]
    inclusion: bool = True

    @classmethod
    def from_plan_json(cls, data: Dict[str, Any]) -> "GeoFencePolygon":
        points: List[List[float]] = []
        for point in data.get("polygon", data.get("points", [])):
            if isinstance(point, list) and len(point) >= 2:
                points.append([float(point[0] or 0.0), float(point[1] or 0.0)])
        return cls(points=points, inclusion=bool(data.get("inclusion", True)))

    def to_plan_json(self) -> Dict[str, Any]:
        return {
            "polygon": [[float(point[0]), float(point[1])] for point in self.points],
            "inclusion": bool(self.inclusion),
        }


@dataclass
class GeoFenceController:
    circles: List[GeoFenceCircle] = field(default_factory=list)
    polygons: List[GeoFencePolygon] = field(default_factory=list)

    @classmethod
    def from_plan_json(cls, data: Dict[str, Any]) -> "GeoFenceController":
        payload = dict(data or {})
        circles = [GeoFenceCircle.from_plan_json(item) for item in payload.get("circles", []) if isinstance(item, dict)]
        polygons = [GeoFencePolygon.from_plan_json(item) for item in payload.get("polygons", []) if isinstance(item, dict)]
        return cls(circles=circles, polygons=polygons)

    def to_plan_json(self) -> Dict[str, Any]:
        return {
            "version": QGC_GEOFENCE_VERSION,
            "circles": [item.to_plan_json() for item in self.circles],
            "polygons": [item.to_plan_json() for item in self.polygons],
        }


@dataclass
class RallyPoint:
    lat: float
    lon: float
    alt: float = 0.0

    @classmethod
    def from_plan_json(cls, data: Dict[str, Any]) -> "RallyPoint":
        return cls(
            lat=float(data.get("lat", 0.0) or 0.0),
            lon=float(data.get("lon", 0.0) or 0.0),
            alt=float(data.get("alt", 0.0) or 0.0),
        )

    def to_plan_json(self) -> Dict[str, Any]:
        return {
            "lat": float(self.lat),
            "lon": float(self.lon),
            "alt": float(self.alt),
        }


@dataclass
class RallyPointController:
    points: List[RallyPoint] = field(default_factory=list)

    @classmethod
    def from_plan_json(cls, data: Dict[str, Any]) -> "RallyPointController":
        payload = dict(data or {})
        points = [RallyPoint.from_plan_json(item) for item in payload.get("points", []) if isinstance(item, dict)]
        return cls(points=points)

    def to_plan_json(self) -> Dict[str, Any]:
        return {
            "version": QGC_RALLYPOINT_VERSION,
            "points": [item.to_plan_json() for item in self.points],
        }


@dataclass
class PlanMasterController:
    mission: MissionController = field(default_factory=MissionController)
    geo_fence: GeoFenceController = field(default_factory=GeoFenceController)
    rally_points: RallyPointController = field(default_factory=RallyPointController)
    file_type: str = QGC_PLAN_FILE_TYPE
    ground_station: str = QGC_GROUND_STATION
    version: int = QGC_PLAN_VERSION

    @classmethod
    def from_plan_json(cls, data: Dict[str, Any]) -> "PlanMasterController":
        payload = dict(data or {})
        if payload.get("fileType") == QGC_PLAN_FILE_TYPE or "mission" in payload:
            mission_payload = payload.get("mission", {})
            geo_payload = payload.get("geoFence", {})
            rally_payload = payload.get("rallyPoints", {})
        else:
            mission_payload = payload
            geo_payload = {}
            rally_payload = {}

        return cls(
            mission=MissionController.from_plan_json(mission_payload),
            geo_fence=GeoFenceController.from_plan_json(geo_payload),
            rally_points=RallyPointController.from_plan_json(rally_payload),
            file_type=str(payload.get("fileType", QGC_PLAN_FILE_TYPE) or QGC_PLAN_FILE_TYPE),
            ground_station=str(payload.get("groundStation", QGC_GROUND_STATION) or QGC_GROUND_STATION),
            version=int(payload.get("version", QGC_PLAN_VERSION) or QGC_PLAN_VERSION),
        )

    @classmethod
    def from_waypoints(cls, waypoints: Sequence[Dict[str, Any]]) -> "PlanMasterController":
        mission = MissionController.from_waypoints_with_complex_metadata(waypoints)
        return cls(mission=mission)

    def to_plan_json(self) -> Dict[str, Any]:
        mission_payload = self.mission.to_plan_json().get("mission", {})
        return {
            "fileType": self.file_type,
            "groundStation": self.ground_station,
            "version": int(self.version),
            "mission": mission_payload,
            "geoFence": self.geo_fence.to_plan_json(),
            "rallyPoints": self.rally_points.to_plan_json(),
        }

    def to_waypoints(self, include_home: bool = True) -> List[Dict[str, Any]]:
        return self.mission.to_waypoints(include_home=include_home)

    def sync_mission_from_waypoints(self, waypoints: Sequence[Dict[str, Any]]):
        self.mission = MissionController.from_waypoints_with_complex_metadata(waypoints)
