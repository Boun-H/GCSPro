import json
import logging
import shutil
import time
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_LEGACY_LOG_FILE_MAP = {
    "mavlink.log": Path("communication") / "mavlink.log",
    "gcs_record.log": Path("data") / "gcs_record.log",
    "main_window.log": Path("ui") / "main_window.log",
    "waypoint.log": Path("ui") / "waypoint.log",
    "map_controller.log": Path("map") / "map_controller.log",
    "map_bridge.log": Path("map") / "map_bridge.log",
}
_LEGACY_LOG_GLOBS = (
    ("user_actions_*.log", Path("user_actions")),
    ("gcs_record_*.log", Path("data") / "records"),
)

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _resolve_log_path(filename: str) -> Path:
    return LOG_DIR / Path(filename)


def _migrate_legacy_logs() -> None:
    for legacy_name, relative_target in _LEGACY_LOG_FILE_MAP.items():
        source = LOG_DIR / legacy_name
        target = _resolve_log_path(str(relative_target))
        if source.exists() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))

    for pattern, relative_dir in _LEGACY_LOG_GLOBS:
        target_dir = _resolve_log_path(str(relative_dir))
        target_dir.mkdir(parents=True, exist_ok=True)
        for source in LOG_DIR.glob(pattern):
            target = target_dir / source.name
            if source == target or target.exists():
                continue
            shutil.move(str(source), str(target))


_migrate_legacy_logs()


def _build_file_handler(log_path: Path) -> logging.FileHandler:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    return handler


def get_app_logger(name: str, filename: str = "gcs.log") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_path = _resolve_log_path(filename)
    target_path = str(log_path.resolve())
    has_handler = any(
        isinstance(handler, logging.FileHandler)
        and Path(getattr(handler, "baseFilename", "")).resolve() == Path(target_path)
        for handler in logger.handlers
    )
    if not has_handler:
        logger.addHandler(_build_file_handler(log_path))

    return logger


class UserActionLogger:
    def __init__(self):
        filename = f"user_actions/user_actions_{time.strftime('%Y%m%d')}.log"
        self.logger = get_app_logger("GCS.UserAction", filename)

    def log(self, action: str, **details):
        payload = {"action": action, "details": details}
        self.logger.info(json.dumps(payload, ensure_ascii=False))