from __future__ import annotations

from .constants import MODE_AUTO, MODE_GUIDED, MODE_QGUIDED, MODE_QLOITER


class CommandRouter:
    _DISPLAY_NAMES = {
        "arm": "ARM",
        "disarm": "DISARM",
        "vtol_takeoff_30m": "VTOL 起飞",
        "vtol_qland": "QLAND",
        "vtol_qrtl": "QRTL",
    }
    _GUIDED_TARGETS = {
        "guided_hold": MODE_QLOITER,
        "guided_resume": MODE_AUTO,
    }
    _GUIDED_STATUS = {
        "guided_hold": "已切换到 Guided Hold / QLOITER",
        "guided_resume": "已恢复 AUTO 任务执行",
    }
    _CONFIRMATIONS = {
        "disarm": {"title": "确认上锁", "message": "请确认当前已落地或处于安全状态，是否继续执行上锁？"},
        "vtol_qland": {"title": "确认垂直降落", "message": "将立即触发 VTOL 垂直降落（QLAND），是否继续？"},
        "vtol_qrtl": {"title": "确认垂直返航", "message": "将触发 VTOL 垂直返航（QRTL），是否继续？"},
    }
    _MODE_REQUIREMENTS = {
        "vtol_takeoff_30m": {"target_mode": MODE_QGUIDED, "fallback_modes": {MODE_GUIDED, MODE_QLOITER}},
        "map_fly_to_waypoint": {"target_mode": MODE_GUIDED, "fallback_modes": {MODE_QGUIDED}},
    }

    @classmethod
    def display_name(cls, command_name: str) -> str:
        return cls._DISPLAY_NAMES.get(str(command_name or ""), str(command_name or "指令"))

    @classmethod
    def confirmation_for(cls, command_name: str) -> dict | None:
        item = cls._CONFIRMATIONS.get(str(command_name or ""))
        return dict(item) if item else None

    @classmethod
    def guided_target_mode(cls, action_key: str) -> str:
        return str(cls._GUIDED_TARGETS.get(str(action_key or "").strip().lower(), ""))

    @classmethod
    def guided_status_text(cls, action_key: str) -> str:
        return str(cls._GUIDED_STATUS.get(str(action_key or "").strip().lower(), ""))

    @classmethod
    def mode_requirement(cls, command_name: str) -> dict | None:
        item = cls._MODE_REQUIREMENTS.get(str(command_name or ""))
        return {"target_mode": item["target_mode"], "fallback_modes": set(item["fallback_modes"])} if item else None


__all__ = ["CommandRouter"]
