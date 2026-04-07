from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class AutoRouteBuildResult:
    route_items: List[Dict]
    summary: str
    notices: List[Tuple[str, str]] = field(default_factory=list)


def build_auto_route_items(home_wp: Optional[Dict], mission_waypoints: Optional[List[Dict]], overrides: Optional[Dict] = None) -> AutoRouteBuildResult:
    _ = overrides
    mission_count = len(mission_waypoints or [])

    if home_wp is None:
        return AutoRouteBuildResult([], "纯任务航点直连模式：设置 H 点后可上传 HOME+任务航点。")

    if mission_count > 0:
        summary = f"纯任务航点直连模式：飞控执行序号 0(H点)、1~{mission_count}(任务航点)。"
    else:
        summary = "纯任务航点直连模式：当前仅有 H 点，请先添加任务航点。"

    return AutoRouteBuildResult(route_items=[], summary=summary, notices=[])
