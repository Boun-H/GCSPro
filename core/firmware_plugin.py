from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple


@dataclass(frozen=True)
class FirmwarePlugin:
    key: str
    display_name: str
    brand_name: str = "Generic"

    def supports_mission_manager(self) -> bool:
        return True

    def supports_parameter_editor(self) -> bool:
        return True


@dataclass(frozen=True)
class AutoPilotPlugin:
    key: str
    display_name: str
    group_labels: Dict[str, str]

    def parameter_group_for_name(self, name: str) -> str:
        text = str(name or "").strip().upper()
        if not text:
            return "MISC"
        if "_" not in text:
            return text[:4] if len(text) > 4 else text
        return text.split("_", 1)[0]

    def parameter_group_label(self, group_key: str) -> str:
        key = str(group_key or "MISC").strip().upper() or "MISC"
        return self.group_labels.get(key, key)

    def available_groups(self, names: Iterable[str]) -> list[str]:
        groups = {self.parameter_group_for_name(name) for name in (names or []) if str(name).strip()}
        return sorted(groups)


class ArduPilotFirmwarePlugin(FirmwarePlugin):
    def __init__(self):
        super().__init__(key="ardupilot", display_name="ArduPilot Firmware", brand_name="ArduPilot")


class GenericFirmwarePlugin(FirmwarePlugin):
    def __init__(self):
        super().__init__(key="generic", display_name="Generic Firmware", brand_name="Generic")


class ArduPilotAutoPilotPlugin(AutoPilotPlugin):
    def __init__(self):
        super().__init__(
            key="ardupilot",
            display_name="ArduPilot AutoPilot",
            group_labels={
                "AHRS": "AHRS 姿态",
                "ARMING": "解锁与安全",
                "BATT": "电池电源",
                "COMPASS": "罗盘",
                "EKF": "EKF 导航",
                "GPS": "GPS",
                "INS": "惯导",
                "LOG": "日志",
                "MIS": "任务",
                "PSC": "位置控制",
                "Q": "VTOL",
                "RTL": "返航",
                "SERVO": "舵机",
                "WPNAV": "航点导航",
                "MISC": "其他",
            },
        )


class GenericAutoPilotPlugin(AutoPilotPlugin):
    def __init__(self):
        super().__init__(key="generic", display_name="Generic AutoPilot", group_labels={"MISC": "其他"})


_ARDUPILOT_FIRMWARE = ArduPilotFirmwarePlugin()
_GENERIC_FIRMWARE = GenericFirmwarePlugin()
_ARDUPILOT_AUTOPILOT = ArduPilotAutoPilotPlugin()
_GENERIC_AUTOPILOT = GenericAutoPilotPlugin()


def resolve_plugins(status: Dict | None = None, thread=None) -> Tuple[FirmwarePlugin, AutoPilotPlugin]:
    status = dict(status or {})
    mode = str(status.get("mode", "") or "").upper()
    mode_mapping = None
    if thread is not None:
        try:
            mode_mapping = getattr(getattr(thread, "master", None), "mode_mapping", lambda: None)()
        except Exception:
            mode_mapping = None

    ardupilot_markers = {"QGUIDED", "QLAND", "QRTL", "AUTO", "RTL", "LOITER", "GUIDED", "FBWA"}
    if mode in ardupilot_markers:
        return _ARDUPILOT_FIRMWARE, _ARDUPILOT_AUTOPILOT
    if isinstance(mode_mapping, dict) and any(str(key).upper().startswith("Q") for key in mode_mapping.keys()):
        return _ARDUPILOT_FIRMWARE, _ARDUPILOT_AUTOPILOT
    return _GENERIC_FIRMWARE, _GENERIC_AUTOPILOT
