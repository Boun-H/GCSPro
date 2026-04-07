from __future__ import annotations

from .mission_sync_service import MissionSyncService


class MissionTransferController:
    OPERATION_LABELS = {
        "upload": "上传",
        "download": "下载",
    }

    def __init__(self, mission_sync_service: MissionSyncService | None = None):
        self.mission_sync_service = mission_sync_service or MissionSyncService()
        self._active = False

    @property
    def active(self) -> bool:
        return bool(self._active)

    @classmethod
    def operation_label(cls, operation: str) -> str:
        return cls.OPERATION_LABELS.get(str(operation or "upload"), str(operation or "任务传输"))

    @staticmethod
    def block_not_connected() -> dict:
        return {"title": "未连接", "message": "请先建立飞控连接", "status_text": ""}

    @staticmethod
    def block_missing_home() -> dict:
        return {"title": "上传中止", "message": "请先设置H点，H点为飞控0号航点", "status_text": "上传中止"}

    def begin(self, operation: str, link_label: str, total: int = 0) -> dict:
        action = "通过" if str(operation or "upload") == "upload" else "从"
        self._active = True
        return {
            "operation": str(operation or "upload"),
            "current": 0,
            "total": max(0, int(total or 0)),
            "percent": 0,
            "message": f"准备{action} {str(link_label or '当前链路')} {self.operation_label(operation)}航线",
            "active": True,
        }

    def finish_success(self, operation: str, link_label: str, current: int, total: int) -> dict:
        self._active = False
        return {
            "operation": str(operation or "upload"),
            "current": int(current or 0),
            "total": int(total or 0),
            "percent": 100,
            "message": f"{str(link_label or '当前链路')} 航线{self.operation_label(operation)}完成",
            "active": False,
            "status_text": f"{self.operation_label(operation)}完成",
        }

    def finish_failure(self, operation: str, reason: str | None = None) -> dict:
        self._active = False
        return {
            "operation": str(operation or "upload"),
            "current": 0,
            "total": 0,
            "percent": 0,
            "message": str(reason or ""),
            "active": False,
            "status_text": f"{self.operation_label(operation)}失败",
        }

    def format_progress_event(self, payload: dict | None) -> dict:
        item = dict(payload or {})
        message = str(item.get("message", "") or "")
        link_label = str(item.get("link_label", "") or "")
        if link_label and link_label not in message:
            message = f"[{link_label}] {message}"
        self._active = bool(item.get("active", False))
        return {
            "operation": str(item.get("operation", "upload") or "upload"),
            "current": int(item.get("current", 0) or 0),
            "total": int(item.get("total", 0) or 0),
            "percent": int(item.get("percent", 0) or 0),
            "message": message,
            "active": self._active,
        }

    def prepare_upload(self, visible_waypoints: list[dict], auto_route_items: list[dict], home_position: dict | None) -> dict:
        return self.mission_sync_service.prepare_upload(visible_waypoints, auto_route_items, home_position)

    def prepare_download(self, downloaded: list[dict], existing_home_position: dict | None = None, auto_route_items: list[dict] | None = None) -> dict:
        return self.mission_sync_service.prepare_download(
            downloaded,
            existing_home_position=existing_home_position,
            auto_route_items=auto_route_items,
        )


__all__ = ["MissionTransferController"]
