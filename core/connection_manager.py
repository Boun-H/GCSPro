from enum import Enum
import time

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from core.mavlink_comms import MavlinkThread


class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"


class ConnectionManager(QObject):
    status_updated = pyqtSignal(dict)
    connection_state_changed = pyqtSignal(str)
    connection_error = pyqtSignal(str)
    mission_progress = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._state = ConnectionState.DISCONNECTED
        self._last_status_ts = 0.0
        self._status_timeout_sec = 8.0
        self._manual_disconnect = False
        self._last_connect_factory = None
        self._last_connect_desc = ""
        self._auto_reconnect_enabled = True
        self._auto_reconnect_delay_ms = 1200
        self._auto_reconnect_max_attempts = 8
        self._auto_reconnect_attempts = 0
        self._reconnecting = False

        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setInterval(1000)
        self._watchdog_timer.timeout.connect(self._watchdog_check)

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._attempt_reconnect)
        self._watchdog_suppressed = False
        self._last_link_type = None
        self._last_serial_port = None
        self._last_serial_baud = None

    @property
    def state(self) -> str:
        return self._state.value

    @property
    def thread(self):
        return self._thread

    def is_connected(self) -> bool:
        return self._state == ConnectionState.CONNECTED and self._thread is not None

    @property
    def reconnecting(self) -> bool:
        return self._reconnecting

    def connect_serial(self, port: str, baud: int):
        self._manual_disconnect = False
        self._last_link_type = "serial"
        self._last_serial_port = str(port)
        self._last_serial_baud = int(baud)
        self._last_connect_desc = f"串口 {port}@{baud}"
        self._last_connect_factory = lambda: MavlinkThread.connect_serial(port, baud)
        self._connect(self._last_connect_factory, allow_reconnect=False)

    def connect_tcp(self, ip: str, port: int):
        self._manual_disconnect = False
        self._last_link_type = "tcp"
        self._last_serial_port = None
        self._last_serial_baud = None
        self._last_connect_desc = f"TCP {ip}:{port}"
        self._last_connect_factory = lambda: MavlinkThread.connect_tcp(ip, port)
        self._connect(self._last_connect_factory, allow_reconnect=False)

    def connect_udp(self, host: str, port: int, mode: str = "udpin"):
        self._manual_disconnect = False
        self._last_link_type = "udp"
        self._last_serial_port = None
        self._last_serial_baud = None
        self._last_connect_desc = f"UDP {host}:{port}"
        self._last_connect_factory = lambda: MavlinkThread.connect_udp(host, port, mode)
        self._connect(self._last_connect_factory, allow_reconnect=False)

    def configure_reconnect(self, enabled: bool = True, delay_ms: int | None = None, max_attempts: int | None = None):
        self._auto_reconnect_enabled = bool(enabled)
        if delay_ms is not None:
            self._auto_reconnect_delay_ms = max(100, int(delay_ms))
        if max_attempts is not None:
            self._auto_reconnect_max_attempts = max(1, int(max_attempts))

    def last_serial_config(self):
        if self._last_link_type != "serial":
            return None
        if not self._last_serial_port or not self._last_serial_baud:
            return None
        return self._last_serial_port, int(self._last_serial_baud)

    def reconnect_last(self):
        if self._last_connect_factory is None:
            self.connection_error.emit("没有可用的历史连接信息")
            return
        self._manual_disconnect = False
        self._reconnecting = False
        self._auto_reconnect_attempts = 0
        self._connect(self._last_connect_factory, allow_reconnect=False)

    def disconnect(self, manual: bool = True):
        self._manual_disconnect = manual
        self._reconnecting = False
        self._reconnect_timer.stop()
        self._watchdog_timer.stop()
        if self._thread is None:
            self._set_state(ConnectionState.DISCONNECTED)
            return

        self._set_state(ConnectionState.DISCONNECTING)
        thread = self._thread
        self._thread = None
        try:
            thread.status_updated.disconnect(self._on_thread_status_updated)
        except TypeError:
            pass
        try:
            thread.mission_progress.disconnect(self.mission_progress.emit)
        except TypeError:
            pass
        try:
            thread.stop_thread()
        except Exception as exc:
            self.connection_error.emit(f"停止通信线程失败: {exc}")
        self._last_status_ts = 0.0
        self._set_state(ConnectionState.DISCONNECTED)

    def shutdown(self):
        """Stop all background work and release reconnect state before app exit."""
        self._manual_disconnect = True
        self._reconnecting = False
        self._reconnect_timer.stop()
        self._watchdog_timer.stop()
        self._auto_reconnect_attempts = 0
        self._last_connect_factory = None
        self._last_connect_desc = ""
        self.disconnect(manual=True)

    def _connect(self, factory, allow_reconnect: bool = False):
        if self._state in {ConnectionState.CONNECTING, ConnectionState.DISCONNECTING}:
            self.connection_error.emit("连接状态切换中，请稍后再试")
            return

        if self._thread is not None:
            self.disconnect(manual=False)

        self._set_state(ConnectionState.CONNECTING)
        try:
            thread = factory()
            thread.status_updated.connect(self._on_thread_status_updated)
            thread.mission_progress.connect(self.mission_progress.emit)
            self._thread = thread
            self._last_status_ts = time.monotonic()
            thread.start()
        except Exception as exc:
            self._thread = None
            self._set_state(ConnectionState.DISCONNECTED)
            self.connection_error.emit(str(exc))
            if allow_reconnect:
                self._schedule_reconnect()
            else:
                self._reconnecting = False
                self._auto_reconnect_attempts = 0
            return

        self._auto_reconnect_attempts = 0
        self._reconnecting = False
        self._watchdog_timer.start()
        self._set_state(ConnectionState.CONNECTED)

    def _on_thread_status_updated(self, payload: dict):
        self._last_status_ts = time.monotonic()
        self.status_updated.emit(payload)

    def suppress_watchdog(self, suppressed: bool):
        """Pause or resume the watchdog during mission transfer to prevent false disconnects."""
        self._watchdog_suppressed = suppressed
        # Refresh timestamp whenever the suppression state changes so long,
        # blocking UI-thread operations cannot immediately trip the timeout on resume.
        self._last_status_ts = time.monotonic()

    def _watchdog_check(self):
        if self._state != ConnectionState.CONNECTED or self._thread is None:
            return
        if self._last_status_ts <= 0:
            return
        # Mission transfer pauses telemetry; keep alive and skip timeout check
        if self._watchdog_suppressed or getattr(self._thread, '_mission_active', False):
            self._last_status_ts = time.monotonic()
            return
        if (time.monotonic() - self._last_status_ts) < self._status_timeout_sec:
            return

        self.connection_error.emit("连接中断，正在自动重连...")
        self.disconnect(manual=False)
        self._schedule_reconnect()

    def _schedule_reconnect(self):
        if self._manual_disconnect or not self._auto_reconnect_enabled:
            return
        if self._state != ConnectionState.DISCONNECTED or self._thread is not None:
            return
        if self._last_connect_factory is None:
            return
        if self._auto_reconnect_attempts >= self._auto_reconnect_max_attempts:
            self.connection_error.emit("自动重连已达上限，请手动重新连接")
            return
        self._auto_reconnect_attempts += 1
        self._reconnecting = True
        self._reconnect_timer.start(self._auto_reconnect_delay_ms)

    def _attempt_reconnect(self):
        if self._manual_disconnect or self._last_connect_factory is None:
            self._reconnecting = False
            return
        if self._state != ConnectionState.DISCONNECTED or self._thread is not None:
            self._reconnecting = False
            return
        self.connection_error.emit(f"自动重连中 ({self._auto_reconnect_attempts}/{self._auto_reconnect_max_attempts}) {self._last_connect_desc}")
        self._connect(self._last_connect_factory, allow_reconnect=True)

    def _set_state(self, state: ConnectionState):
        self._state = state
        self.connection_state_changed.emit(state.value)
