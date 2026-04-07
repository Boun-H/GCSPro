from __future__ import annotations


class VehicleContextService:
    def __init__(self):
        self._params_by_link: dict[str, dict] = {}
        self._mission_context_by_link: dict[str, dict] = {}
        self._params_by_vehicle: dict[str, dict] = {}
        self._mission_context_by_vehicle: dict[str, dict] = {}

    @staticmethod
    def _copy_params(values: dict | None) -> dict:
        return dict(values or {})

    @staticmethod
    def _copy_mission(
        home_position: dict | None = None,
        waypoints: list[dict] | None = None,
        auto_route_overrides: dict | None = None,
        plan_constraints: dict | None = None,
    ) -> dict:
        return {
            "home_position": dict(home_position) if isinstance(home_position, dict) else None,
            "waypoints": [dict(wp) for wp in (waypoints or [])],
            "auto_route_overrides": dict(auto_route_overrides or {}),
            "plan_constraints": dict(plan_constraints or {}),
        }

    def cache_vehicle_context(
        self,
        vehicle_id: str,
        *,
        param_values: dict | None = None,
        home_position: dict | None = None,
        waypoints: list[dict] | None = None,
        auto_route_overrides: dict | None = None,
        plan_constraints: dict | None = None,
        include_params: bool = True,
        include_mission: bool = True,
    ):
        key = str(vehicle_id or "").strip()
        if not key:
            return
        if include_params and param_values:
            self._params_by_vehicle[key] = self._copy_params(param_values)
        if include_mission:
            self._mission_context_by_vehicle[key] = self._copy_mission(
                home_position=home_position,
                waypoints=waypoints,
                auto_route_overrides=auto_route_overrides,
                plan_constraints=plan_constraints,
            )

    def cache_link_context(
        self,
        link_key: str,
        *,
        param_values: dict | None = None,
        home_position: dict | None = None,
        waypoints: list[dict] | None = None,
        auto_route_overrides: dict | None = None,
        plan_constraints: dict | None = None,
        include_params: bool = True,
        include_mission: bool = True,
    ):
        key = str(link_key or "").strip()
        if not key:
            return
        if include_params and param_values:
            self._params_by_link[key] = self._copy_params(param_values)
        if include_mission:
            self._mission_context_by_link[key] = self._copy_mission(
                home_position=home_position,
                waypoints=waypoints,
                auto_route_overrides=auto_route_overrides,
                plan_constraints=plan_constraints,
            )

    def resolve_link_context(self, link_key: str, active_vehicle_id: str = "", vehicle_link_key: str = "") -> dict:
        key = str(link_key or "").strip()
        vehicle_id = str(active_vehicle_id or "").strip()
        vehicle_key = str(vehicle_link_key or "").strip()
        params = None
        if vehicle_id and vehicle_key == key:
            params = self._params_by_vehicle.get(vehicle_id)
        if not params:
            params = self._params_by_link.get(key)

        mission = None
        if vehicle_id and vehicle_key == key:
            mission = self._mission_context_by_vehicle.get(vehicle_id)
        if mission is None:
            mission = self._mission_context_by_link.get(key)

        return {
            "params": self._copy_params(params) if params else None,
            "mission": self._copy_mission(**mission) if mission else None,
        }

    @staticmethod
    def build_vehicle_metrics(
        vehicle_id: str,
        *,
        param_values: dict | None = None,
        modified_count: int = 0,
        waypoints: list[dict] | None = None,
        auto_route_count: int = 0,
        home_set: bool = False,
        include_params: bool = True,
        include_mission: bool = True,
    ) -> dict:
        payload: dict[str, int | bool] = {}
        if include_params:
            payload["params_total"] = len(dict(param_values or {}))
            payload["params_modified"] = max(0, int(modified_count or 0))
        if include_mission:
            payload["mission_count"] = len(list(waypoints or []))
            payload["auto_route_count"] = max(0, int(auto_route_count or 0))
            payload["home_set"] = bool(home_set)
        return {"vehicle_id": str(vehicle_id or "").strip(), "payload": payload}

    @staticmethod
    def find_link_key_for_vehicle(vehicle: dict | None, link_summaries: list[dict] | None) -> str:
        item = dict(vehicle or {})
        direct_key = str(item.get("link_key", "") or "").strip()
        if direct_key:
            return direct_key
        target = str(item.get("link_name", "") or "").strip()
        if not target:
            return ""
        for link in (link_summaries or []):
            label = str(link.get("label", "") or "").strip()
            if label and (target == label or target.endswith(label)):
                return str(link.get("key", "") or "")
        return ""


__all__ = ["VehicleContextService"]
