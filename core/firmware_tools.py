from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FirmwareImageInfo:
    path: Path
    file_name: str
    extension: str
    size_bytes: int
    crc32: str
    board_id: int | None = None
    image_size: int | None = None
    description: str = ""

    @property
    def display_text(self) -> str:
        board = f" | Board {self.board_id}" if self.board_id is not None else ""
        return f"{self.file_name} | {self.extension} | {self.size_bytes} bytes | CRC32 {self.crc32}{board}"


_SUPPORTED_SUFFIXES = {".apj", ".px4", ".bin"}


def inspect_firmware_image(file_path: str | Path) -> FirmwareImageInfo:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"固件文件不存在: {path}")

    suffix = path.suffix.lower()
    if suffix not in _SUPPORTED_SUFFIXES:
        raise ValueError(f"不支持的固件格式: {suffix or '<none>'}")

    raw = path.read_bytes()
    crc_value = _crc32_hex(raw)
    board_id: int | None = None
    image_size: int | None = len(raw)
    description = ""

    if suffix in {".apj", ".px4"}:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            board_raw = payload.get("board_id")
            board_id = int(board_raw) if board_raw not in {None, ""} else None
            description = str(payload.get("description", "") or payload.get("summary", "")).strip()
            image_blob = payload.get("image")
            if isinstance(image_blob, str) and image_blob.strip():
                decoded = base64.b64decode(image_blob)
                image_size = len(decoded)
                crc_value = _crc32_hex(decoded)

    return FirmwareImageInfo(
        path=path,
        file_name=path.name,
        extension=suffix,
        size_bytes=len(raw),
        crc32=crc_value,
        board_id=board_id,
        image_size=image_size,
        description=description,
    )


def build_firmware_upgrade_plan(link_summary: dict[str, Any] | None, image: FirmwareImageInfo) -> dict[str, Any]:
    link = dict(link_summary or {})
    payload = dict(link.get("payload", {}) or {})
    kind = str(link.get("kind", "")).strip().lower()
    port = str(payload.get("port", "") or "").strip()
    baud = int(payload.get("baud", 115200) or 115200)
    return {
        "kind": kind,
        "label": str(link.get("label", "") or ""),
        "port": port,
        "baud": baud,
        "can_reconnect": bool(kind == "serial" and port),
        "backup_recommended": True,
        "precheck_steps": [
            "升级前导出当前参数快照",
            "确认镜像板卡 ID / CRC 与机型匹配",
            "记录当前链路端口，便于刷写后自动重连",
        ],
        "postcheck_steps": [
            "重连后重新读取参数",
            "比对升级前快照，确认关键参数未漂移",
            "执行传感器 / GPS / 安全项快速复核",
        ],
        "image": image,
        "summary": image.display_text,
    }


def build_parameter_validation_report(
    before_params: dict[str, Any] | None,
    after_params: dict[str, Any] | None,
    tolerance: float = 1e-6,
) -> dict[str, Any]:
    before: dict[str, float] = {}
    after: dict[str, float] = {}
    for source, target in ((before_params or {}, before), (after_params or {}, after)):
        for name, value in source.items():
            try:
                target[str(name)] = float(value)
            except (TypeError, ValueError):
                continue

    changed: dict[str, dict[str, Any]] = {}
    all_names = sorted(set(before) | set(after))
    for name in all_names:
        before_value = before.get(name)
        after_value = after.get(name)
        if before_value is None or after_value is None:
            changed[name] = {"before": before_value, "after": after_value}
            continue
        if abs(after_value - before_value) > float(tolerance):
            changed[name] = {"before": before_value, "after": after_value, "delta": after_value - before_value}

    missing_after = sorted(name for name in before if name not in after)
    new_after = sorted(name for name in after if name not in before)
    if not changed:
        summary = "升级后参数校验通过：未发现关键漂移。"
    else:
        preview = ", ".join(list(changed.keys())[:5])
        summary = f"升级后参数校验发现 {len(changed)} 项变化：{preview}"

    return {
        "changed_count": len(changed),
        "changed": changed,
        "missing_after": missing_after,
        "new_after": new_after,
        "summary": summary,
    }


def _crc32_hex(raw: bytes) -> str:
    return f"{binascii.crc32(raw) & 0xFFFFFFFF:08X}"
