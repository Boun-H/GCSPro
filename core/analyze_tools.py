from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class LogEntry:
    path: Path
    size_bytes: int
    modified_ts: float

    @property
    def suffix(self) -> str:
        return self.path.suffix.lower()


_DEFAULT_PATTERNS = ("*.log", "*.bin", "*.ulg", "*.tlog", "*.json")


def discover_log_files(logs_root: str | Path, limit: int = 100, patterns: Iterable[str] | None = None) -> list[LogEntry]:
    root = Path(logs_root)
    if not root.exists():
        return []

    items: list[LogEntry] = []
    for pattern in patterns or _DEFAULT_PATTERNS:
        for path in root.rglob(pattern):
            if not path.is_file():
                continue
            stat = path.stat()
            items.append(LogEntry(path=path, size_bytes=int(stat.st_size), modified_ts=float(stat.st_mtime)))

    deduped: dict[str, LogEntry] = {str(item.path.resolve()): item for item in items}
    ordered = sorted(deduped.values(), key=lambda item: (item.modified_ts, item.path.name.lower()), reverse=True)
    return ordered[: max(1, int(limit or 100))]


def summarize_log_files(entries: Iterable[LogEntry]) -> dict:
    records = list(entries or [])
    by_extension: dict[str, int] = {}
    total_bytes = 0
    for item in records:
        suffix = item.suffix or "<none>"
        by_extension[suffix] = by_extension.get(suffix, 0) + 1
        total_bytes += int(item.size_bytes)

    latest = records[0].path.name if records else ""
    return {
        "total_files": len(records),
        "total_bytes": total_bytes,
        "by_extension": by_extension,
        "latest_file": latest,
    }


def preview_log_file(file_path: str | Path, max_bytes: int = 4096, max_lines: int = 60) -> str:
    path = Path(file_path)
    if not path.exists():
        return f"文件不存在: {path}"

    raw = path.read_bytes()[: max(64, int(max_bytes or 4096))]
    if _looks_like_text(raw):
        text = raw.decode("utf-8", errors="replace")
        trimmed = "\n".join(text.splitlines()[: max(1, int(max_lines or 60))])
        return f"文本预览 · {path.name}\n{'-' * 36}\n{trimmed}"

    hex_preview = " ".join(f"{byte:02X}" for byte in raw[:64])
    return f"二进制预览 · {path.name}\n{'-' * 36}\n{hex_preview}"


def _looks_like_text(raw: bytes) -> bool:
    if not raw:
        return True
    if b"\x00" in raw:
        return False
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    printable = sum(1 for ch in decoded if ch.isprintable() or ch in "\r\n\t")
    return printable / max(1, len(decoded)) >= 0.85
