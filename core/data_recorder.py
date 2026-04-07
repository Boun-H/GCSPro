import json
import time
from datetime import datetime

from core.logger import LOG_DIR
from core.logger import get_app_logger

logger = get_app_logger("GCS.DataRecorder", "data/gcs_record.log")

class DataRecorder:
    def __init__(self):
        self.is_recording = False
        self.log_file = None
        self.current_file_path = None

    def start_recording(self):
        if self.is_recording:
            return
        try:
            self.is_recording = True
            record_dir = LOG_DIR / "data" / "records"
            record_dir.mkdir(parents=True, exist_ok=True)
            filename = f"gcs_record_{time.strftime('%Y%m%d_%H%M%S')}.log"
            file_path = record_dir / filename
            self.log_file = open(file_path, "w", encoding="utf-8", buffering=1)
            self.current_file_path = str(file_path)
            logger.info(f"数据记录启动：{self.current_file_path}")
        except Exception as e:
            logger.error(f"记录启动失败：{str(e)}")
            self.is_recording = False
            self.log_file = None
            self.current_file_path = None

    def stop_recording(self):
        self.is_recording = False
        if self.log_file:
            try:
                self.log_file.flush()
                self.log_file.close()
            except Exception as e:
                logger.error(f"数据记录关闭失败：{str(e)}")
            self.log_file = None
            self.current_file_path = None
            logger.info("数据记录已停止")

    def write_data(self, data):
        if self.is_recording and self.log_file:
            try:
                record = {
                    "timestamp": time.time(),
                    "datetime": datetime.now().isoformat(timespec="seconds"),
                    "payload": data,
                }
                self.log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                self.log_file.flush()
            except Exception as e:
                logger.error(f"数据写入失败：{str(e)}")