from __future__ import annotations

from .constants import (
    GPS_CRITICAL,
    GPS_WARN,
    LOW_BATTERY_CRITICAL,
    LOW_BATTERY_WARN,
    READY_FLIGHT_MODES,
)


class SetupWizardService:
    @staticmethod
    def describe_vehicle(vehicle: dict | None) -> dict:
        item = dict(vehicle or {})
        vehicle_id = str(item.get("vehicle_id", "--") or "--")
        mode = str(item.get("mode", "UNKNOWN") or "UNKNOWN")
        battery = int(item.get("battery_remaining", 0) or 0)
        gps = int(item.get("gps", 0) or 0)
        volt = float(item.get("volt", 0.0) or 0.0)
        firmware = str(item.get("firmware_name", "--") or "--")
        plugin = str(item.get("plugin_name", "--") or "--")
        link_name = str(item.get("link_name", "--") or "--")
        queue_depth = int(item.get("queue_depth", 0) or 0)
        mission_count = int(item.get("mission_count", 0) or 0)
        params_total = int(item.get("params_total", 0) or 0)
        home_set = bool(item.get("home_set", False))

        battery_tone = "danger" if battery < LOW_BATTERY_CRITICAL else "warn" if battery < LOW_BATTERY_WARN else "ok"
        gps_tone = "danger" if gps < GPS_CRITICAL else "warn" if gps < GPS_WARN else "ok"
        mode_tone = "info" if mode.upper() in READY_FLIGHT_MODES else "neutral"
        safety_text = "Home 已设置" if home_set else "Home 未设置"

        return {
            "vehicle_id": vehicle_id,
            "mode": mode,
            "battery": battery,
            "gps": gps,
            "volt": volt,
            "firmware": firmware,
            "plugin": plugin,
            "link_name": link_name,
            "queue_depth": queue_depth,
            "mission_count": mission_count,
            "params_total": params_total,
            "home_set": home_set,
            "battery_tone": battery_tone,
            "gps_tone": gps_tone,
            "mode_tone": mode_tone,
            "safety_text": safety_text,
            "overview_banner": (
                f"载具 {vehicle_id} 正在使用 {firmware} / {plugin}。"
                f" 当前模式 {mode}，任务点 {mission_count} 个，待执行命令 {queue_depth} 条。"
            ),
            "quick_actions": (
                f"快捷操作: Firmware / Sensors / Power / Safety | 当前模式 {mode} | 电池 {battery}% | GPS {gps}"
            ),
        }

    @classmethod
    def evaluate(cls, vehicle: dict | None) -> dict:
        info = cls.describe_vehicle(vehicle)
        checks = [
            {"key": "firmware", "title": "Firmware / Airframe 检查", "done": bool(info["firmware"] and info["firmware"] != "--"), "detail": f"当前固件：{info['firmware'] or '--'}"},
            {"key": "sensors", "title": "Sensors 校准", "done": info["gps"] >= GPS_WARN, "detail": f"当前 GPS: {info['gps']} 颗，建议 ≥ {GPS_WARN}"},
            {"key": "radio", "title": "Radio / Servo 检查", "done": info["params_total"] > 0, "detail": f"参数缓存: {info['params_total']} 项"},
            {"key": "power", "title": "Power 健康检查", "done": info["battery"] >= LOW_BATTERY_WARN and info["volt"] >= 11.1, "detail": f"电池 {info['battery']}% / {info['volt']:.2f}V"},
            {"key": "safety", "title": "Safety / Failsafe 检查", "done": info["home_set"], "detail": f"Home 状态: {'已设置' if info['home_set'] else '未设置'}"},
            {"key": "mission", "title": "Mission / 飞前准备", "done": info["mission_count"] > 0, "detail": f"任务点数量: {info['mission_count']}"},
        ]
        completed = sum(1 for step in checks if step["done"])
        total = max(1, len(checks))

        next_step = "下一步：校准向导已完成，可进入 Fly View 进行联调或试飞。"
        for step in checks:
            if step["done"]:
                continue
            if step["key"] == "firmware":
                next_step = "下一步：确认固件与机型匹配，再执行后续校准。"
            elif step["key"] == "sensors":
                next_step = "下一步：进入 Sensors 完成 GPS / Compass / IMU 校准。"
            elif step["key"] == "radio":
                next_step = "下一步：进入 Radio 检查 RC / Servo / 通道映射。"
            elif step["key"] == "power":
                next_step = "下一步：进入 Power 核对 BATT、电压阈值和电流传感器。"
            elif step["key"] == "safety":
                next_step = "下一步：进入 Safety 确认 Home、围栏和失控保护。"
            else:
                next_step = "下一步：下载或导入任务，完成飞前准备。"
            break

        return {
            "steps": checks,
            "completed": completed,
            "total": total,
            "progress_value": int(round(completed * 100 / total)),
            "next_step": next_step,
            "summary_text": f"校准进度: {completed}/{total} 已完成\n{next_step}",
            "hint_text": "建议：按顺序完成上述步骤。\n优先级：Firmware → Sensors → Radio → Power → Safety → Mission",
        }


__all__ = ["SetupWizardService"]
