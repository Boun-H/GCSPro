import time
from PyQt6.QtCore import QObject, pyqtSignal
from core.constants import BATTERY_WARN, LOST_HEARTBEAT

class AlarmSystem(QObject):
    alert_signal = pyqtSignal(str, str)
    def __init__(self):
        super().__init__()
        self.last_heartbeat = time.time()
        self.battery_triggered = False
        self.connection_triggered = False

    def refresh_heartbeat(self):
        self.last_heartbeat = time.time()
        self.connection_triggered = False

    def check_status(self, drone_data: dict):
        current_time = time.time()
        battery = drone_data.get("battery_remaining", 100)
        if battery <= BATTERY_WARN and not self.battery_triggered:
            self.battery_triggered = True
            self.alert_signal.emit("电池告警", f"电量过低：{battery}%")
        if current_time - self.last_heartbeat > LOST_HEARTBEAT and not self.connection_triggered:
            self.connection_triggered = True
            self.alert_signal.emit("连接告警", "飞控心跳丢失！")