from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from .connection_manager import ConnectionManager


@dataclass
class ManagedLinkSession:
    key: str
    kind: str
    label: str
    payload: Dict[str, Any]
    manager: ConnectionManager
    state: str = "disconnected"
    last_error: str = ""
    last_status: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "key": self.key,
            "kind": self.kind,
            "label": self.label,
            "payload": dict(self.payload or {}),
            "state": self.state,
            "connected": self.state == "connected",
            "last_error": self.last_error,
            "created_at": self.created_at,
        }
        data.update(dict(self.last_status or {}))
        return data


class MultiLinkManager(QObject):
    """QGC-style multi-link wrapper that keeps multiple ConnectionManager sessions alive."""

    status_updated = pyqtSignal(dict)
    connection_state_changed = pyqtSignal(str)
    connection_error = pyqtSignal(str)
    mission_progress = pyqtSignal(dict)
    link_status_updated = pyqtSignal(dict)
    links_changed = pyqtSignal(list)
    active_link_changed = pyqtSignal(dict)

    def __init__(self, parent=None, manager_factory: Optional[Callable[..., ConnectionManager]] = None):
        super().__init__(parent)
        self._manager_factory = manager_factory or ConnectionManager
        self._links: Dict[str, ManagedLinkSession] = {}
        self._active_link_key: Optional[str] = None
        self._counter = 0
        self._auto_reconnect_enabled = True
        self._auto_reconnect_delay_ms = 1200
        self._auto_reconnect_max_attempts = 8

    @property
    def state(self) -> str:
        active = self._active_session()
        return active.state if active is not None else "disconnected"

    @property
    def thread(self):
        active = self._active_session()
        return active.manager.thread if active is not None else None

    @property
    def reconnecting(self) -> bool:
        active = self._active_session()
        return bool(getattr(active.manager, "reconnecting", False)) if active is not None else False

    def is_connected(self) -> bool:
        active = self._active_session()
        return bool(active and active.manager.is_connected())

    def configure_reconnect(self, enabled: bool = True, delay_ms: int | None = None, max_attempts: int | None = None):
        self._auto_reconnect_enabled = bool(enabled)
        if delay_ms is not None:
            self._auto_reconnect_delay_ms = max(100, int(delay_ms))
        if max_attempts is not None:
            self._auto_reconnect_max_attempts = max(1, int(max_attempts))
        for session in self._links.values():
            if hasattr(session.manager, "configure_reconnect"):
                session.manager.configure_reconnect(self._auto_reconnect_enabled, self._auto_reconnect_delay_ms, self._auto_reconnect_max_attempts)

    def connect_serial(self, port: str, baud: int) -> str:
        payload = {"port": str(port or "").strip(), "baud": int(baud or 115200)}
        label = f"{payload['port']}@{payload['baud']}"
        session = self._create_session("serial", label, payload)
        session.manager.connect_serial(payload["port"], payload["baud"])
        self.set_active_link(session.key)
        return session.key

    def connect_tcp(self, ip: str, port: int) -> str:
        payload = {"host": str(ip or "127.0.0.1").strip() or "127.0.0.1", "port": int(port or 5760)}
        label = f"{payload['host']}:{payload['port']}"
        session = self._create_session("tcp", label, payload)
        session.manager.connect_tcp(payload["host"], payload["port"])
        self.set_active_link(session.key)
        return session.key

    def connect_udp(self, host: str, port: int, mode: str = "udpin") -> str:
        payload = {
            "host": str(host or "0.0.0.0").strip() or "0.0.0.0",
            "port": int(port or 14550),
            "mode": str(mode or "udpin").strip().lower() or "udpin",
        }
        label = f"{payload['host']}:{payload['port']}"
        session = self._create_session("udp", label, payload)
        session.manager.connect_udp(payload["host"], payload["port"], payload["mode"])
        self.set_active_link(session.key)
        return session.key

    def set_active_link(self, key: str) -> Optional[Dict[str, Any]]:
        key = str(key or "").strip()
        if key not in self._links:
            return None
        self._active_link_key = key
        payload = self._links[key].to_dict()
        self.active_link_changed.emit(payload)
        self.connection_state_changed.emit(str(payload.get("state", "disconnected")))
        if self._links[key].last_status:
            self.status_updated.emit(dict(self._links[key].last_status))
        self.links_changed.emit(self.link_summaries())
        return payload

    def active_link_summary(self) -> Optional[Dict[str, Any]]:
        active = self._active_session()
        return active.to_dict() if active is not None else None

    def link_summary(self, key: str) -> Optional[Dict[str, Any]]:
        session = self._links.get(str(key or "").strip())
        return session.to_dict() if session is not None else None

    def manager_for_link(self, key: str) -> Optional[ConnectionManager]:
        session = self._links.get(str(key or "").strip())
        return session.manager if session is not None else None

    def thread_for_link(self, key: str):
        manager = self.manager_for_link(key)
        return manager.thread if manager is not None else None

    def link_summaries(self) -> list[Dict[str, Any]]:
        sessions = sorted(self._links.values(), key=lambda item: item.created_at)
        return [session.to_dict() for session in sessions]

    def disconnect(self, manual: bool = True):
        active = self._active_session()
        if active is None:
            self.connection_state_changed.emit("disconnected")
            return
        self.disconnect_link(active.key, manual=manual)

    def disconnect_link(self, key: str, manual: bool = True):
        session = self._links.pop(str(key or "").strip(), None)
        if session is None:
            return
        try:
            session.manager.disconnect(manual=manual)
        finally:
            if self._active_link_key == session.key:
                self._active_link_key = None
                fallback = self._pick_fallback_key()
                if fallback is not None:
                    self.set_active_link(fallback)
                else:
                    self.connection_state_changed.emit("disconnected")
                    self.active_link_changed.emit({})
            self.links_changed.emit(self.link_summaries())

    def reconnect_last(self):
        active = self._active_session()
        if active is None:
            self.connection_error.emit("没有可重连的活动链路")
            return
        active.manager.reconnect_last()

    def suppress_watchdog(self, suppressed: bool):
        active = self._active_session()
        if active is not None:
            active.manager.suppress_watchdog(suppressed)

    def shutdown(self):
        for session in list(self._links.values()):
            try:
                session.manager.shutdown()
            except Exception:
                pass
        self._links.clear()
        self._active_link_key = None
        self.links_changed.emit([])
        self.connection_state_changed.emit("disconnected")

    def _create_session(self, kind: str, label: str, payload: Dict[str, Any]) -> ManagedLinkSession:
        self._counter += 1
        key = f"{str(kind).lower()}-{self._counter}"
        manager = self._build_manager()
        if hasattr(manager, "configure_reconnect"):
            manager.configure_reconnect(self._auto_reconnect_enabled, self._auto_reconnect_delay_ms, self._auto_reconnect_max_attempts)
        session = ManagedLinkSession(key=key, kind=str(kind).lower(), label=str(label), payload=dict(payload or {}), manager=manager)
        self._links[key] = session
        manager.status_updated.connect(lambda payload, link_key=key: self._on_link_status_updated(link_key, payload))
        manager.connection_state_changed.connect(lambda state, link_key=key: self._on_link_state_changed(link_key, state))
        manager.connection_error.connect(lambda message, link_key=key: self._on_link_error(link_key, message))
        manager.mission_progress.connect(lambda payload, link_key=key: self._on_link_mission_progress(link_key, payload))
        self.links_changed.emit(self.link_summaries())
        return session

    def _build_manager(self) -> ConnectionManager:
        try:
            return self._manager_factory(self)
        except TypeError:
            return self._manager_factory()

    def _active_session(self) -> Optional[ManagedLinkSession]:
        if self._active_link_key in self._links:
            return self._links[self._active_link_key]
        fallback = self._pick_fallback_key()
        if fallback is not None:
            self._active_link_key = fallback
            return self._links[fallback]
        return None

    def _pick_fallback_key(self) -> Optional[str]:
        connected = [session.key for session in self._links.values() if session.state == "connected"]
        if connected:
            return connected[0]
        if self._links:
            return next(iter(self._links.keys()))
        return None

    def _on_link_status_updated(self, key: str, payload: Dict[str, Any]):
        session = self._links.get(key)
        if session is None:
            return
        data = dict(payload or {})
        data["link_key"] = session.key
        data["link_label"] = session.label
        data["link_kind"] = session.kind
        session.last_status = data
        self.link_status_updated.emit(dict(data))
        if session.key == self._active_link_key:
            self.status_updated.emit(dict(data))
            self.active_link_changed.emit(session.to_dict())
        self.links_changed.emit(self.link_summaries())

    def _on_link_state_changed(self, key: str, state: str):
        session = self._links.get(key)
        if session is None:
            return
        session.state = str(state or "disconnected")
        if self._active_link_key is None:
            self._active_link_key = key
        if key == self._active_link_key:
            self.connection_state_changed.emit(session.state)
            self.active_link_changed.emit(session.to_dict())
        self.links_changed.emit(self.link_summaries())

    def _on_link_error(self, key: str, message: str):
        session = self._links.get(key)
        if session is None:
            return
        session.last_error = str(message or "")
        prefix = f"[{session.kind.upper()} {session.label}] "
        self.connection_error.emit(prefix + session.last_error)
        self.links_changed.emit(self.link_summaries())

    def _on_link_mission_progress(self, key: str, payload: Dict[str, Any]):
        session = self._links.get(key)
        if session is None:
            return
        data = dict(payload or {})
        data["link_key"] = session.key
        data["link_label"] = session.label
        if key == self._active_link_key:
            self.mission_progress.emit(data)
