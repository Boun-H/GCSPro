import os
import math
import threading
import time
import json

from PyQt6.QtCore import QThread, pyqtSignal
from serial.serialutil import SerialException

from core.logger import get_app_logger
from core.mission import COMMAND_TO_MISSION_TYPE, FRAME_LABELS, LEGACY_TO_VTOL_MISSION_TYPE, LOITER_COMMANDS, MAV_CMD_NAV_LOITER_TO_ALT, MISSION_TYPE_COMMANDS

os.environ.setdefault("MAVLINK20", "1")

from pymavlink import mavutil


logger = get_app_logger("GCS.Mavlink", "communication/mavlink.log")


class MavlinkThread(QThread):
    status_updated = pyqtSignal(dict)
    mission_progress = pyqtSignal(dict)

    LOITER_TO_ALT_COMMAND = MAV_CMD_NAV_LOITER_TO_ALT
    VTOL_STATE_FW = int(getattr(mavutil.mavlink, 'MAV_VTOL_STATE_FW', 4))
    VTOL_STATE_MC = int(getattr(mavutil.mavlink, 'MAV_VTOL_STATE_MC', 3))
    MISSION_TYPE_TO_COMMAND = {
        key: value for key, value in MISSION_TYPE_COMMANDS.items() if key != 'HOME'
    }
    LEGACY_TO_VTOL_MISSION_TYPE = dict(LEGACY_TO_VTOL_MISSION_TYPE)
    LEGACY_TO_VTOL_MISSION_TYPE['RTL'] = 'VTOL_LAND'
    LOITER_COMMANDS = set(LOITER_COMMANDS)
    COMMAND_TO_MISSION_TYPE = dict(COMMAND_TO_MISSION_TYPE)
    COMMAND_TO_MISSION_TYPE.update({
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF: 'VTOL_TAKEOFF',
        mavutil.mavlink.MAV_CMD_NAV_LAND: 'VTOL_LAND',
        mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH: 'VTOL_LAND',
    })
    DEFAULT_MISSION_FRAME = mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT
    FRAME_LABELS = dict(FRAME_LABELS)
    FRAME_LABELS.update({
        mavutil.mavlink.MAV_FRAME_GLOBAL_INT: 'GLOBAL_ABS_INT',
    })
    MISSION_TYPE_MISSION = getattr(mavutil.mavlink, 'MAV_MISSION_TYPE_MISSION', 0)
    MISSION_TYPE_FENCE = getattr(mavutil.mavlink, 'MAV_MISSION_TYPE_FENCE', 1)
    MISSION_TYPE_RALLY = getattr(mavutil.mavlink, 'MAV_MISSION_TYPE_RALLY', 2)
    FENCE_CMD_POLYGON_INCLUSION = int(getattr(mavutil.mavlink, 'MAV_CMD_NAV_FENCE_POLYGON_VERTEX_INCLUSION', 5001))
    FENCE_CMD_POLYGON_EXCLUSION = int(getattr(mavutil.mavlink, 'MAV_CMD_NAV_FENCE_POLYGON_VERTEX_EXCLUSION', 5002))
    FENCE_CMD_CIRCLE_INCLUSION = int(getattr(mavutil.mavlink, 'MAV_CMD_NAV_FENCE_CIRCLE_INCLUSION', 5003))
    FENCE_CMD_CIRCLE_EXCLUSION = int(getattr(mavutil.mavlink, 'MAV_CMD_NAV_FENCE_CIRCLE_EXCLUSION', 5004))
    RALLY_CMD_NAV_POINT = int(getattr(mavutil.mavlink, 'MAV_CMD_NAV_RALLY_POINT', 5100))
    MISSION_ACK_LABELS = {
        int(getattr(mavutil.mavlink, 'MAV_MISSION_ACCEPTED', 0)): 'ACCEPTED',
        int(getattr(mavutil.mavlink, 'MAV_MISSION_ERROR', 1)): 'ERROR',
        int(getattr(mavutil.mavlink, 'MAV_MISSION_UNSUPPORTED_FRAME', 2)): 'UNSUPPORTED_FRAME',
        int(getattr(mavutil.mavlink, 'MAV_MISSION_UNSUPPORTED', 3)): 'UNSUPPORTED',
        int(getattr(mavutil.mavlink, 'MAV_MISSION_NO_SPACE', 4)): 'NO_SPACE',
        int(getattr(mavutil.mavlink, 'MAV_MISSION_INVALID', 5)): 'INVALID',
        int(getattr(mavutil.mavlink, 'MAV_MISSION_INVALID_PARAM1', 6)): 'INVALID_PARAM1',
        int(getattr(mavutil.mavlink, 'MAV_MISSION_INVALID_PARAM2', 7)): 'INVALID_PARAM2',
        int(getattr(mavutil.mavlink, 'MAV_MISSION_INVALID_PARAM3', 8)): 'INVALID_PARAM3',
        int(getattr(mavutil.mavlink, 'MAV_MISSION_INVALID_PARAM4', 9)): 'INVALID_PARAM4',
        int(getattr(mavutil.mavlink, 'MAV_MISSION_INVALID_PARAM5_X', 10)): 'INVALID_PARAM5_X',
        int(getattr(mavutil.mavlink, 'MAV_MISSION_INVALID_PARAM6_Y', 11)): 'INVALID_PARAM6_Y',
        int(getattr(mavutil.mavlink, 'MAV_MISSION_INVALID_PARAM7', 12)): 'INVALID_PARAM7',
        int(getattr(mavutil.mavlink, 'MAV_MISSION_INVALID_SEQUENCE', 13)): 'INVALID_SEQUENCE',
        int(getattr(mavutil.mavlink, 'MAV_MISSION_DENIED', 14)): 'DENIED',
        int(getattr(mavutil.mavlink, 'MAV_MISSION_OPERATION_CANCELLED', 15)): 'OPERATION_CANCELLED',
    }
    ACK_NONE = 'ACK_NONE'
    ACK_MISSION_COUNT = 'ACK_MISSION_COUNT'
    ACK_MISSION_ITEM = 'ACK_MISSION_ITEM'
    ACK_MISSION_REQUEST = 'ACK_MISSION_REQUEST'
    ACK_TIMEOUT_SECONDS = 1.5
    RETRY_TIMEOUT_SECONDS = 0.25
    MAX_RETRY_COUNT = 5

    def __init__(self, master):
        super().__init__()
        self.master = master
        self.running = True
        self._mission_active = False
        self._mission_guard = threading.Lock()
        self._last_heartbeat_component = int(getattr(master, 'target_component', 0) or 0)
        self.telemetry = {
            'lat': 0.0,
            'lon': 0.0,
            'alt': 0.0,
            'alt_abs': 0.0,
            'home_lat': None,
            'home_lon': None,
            'heading': 0.0,
            'roll': 0.0,
            'pitch': 0.0,
            'yaw': 0.0,
            'gps': 0,
            'volt': 0.0,
            'battery_remaining': 100,
            'vel': 0.0,
            'mode': 'UNKNOWN',
            'home_alt_abs': None,
        }

    @classmethod
    def connect_serial(cls, port: str, baud: int):
        master = mavutil.mavlink_connection(port, baud=baud, source_system=255)
        master.mavlink_version = 2
        master.wait_heartbeat(timeout=5)
        return cls(master)

    @classmethod
    def connect_tcp(cls, ip: str, port: int):
        master = mavutil.mavlink_connection(f'tcp:{ip}:{port}', source_system=255)
        master.mavlink_version = 2
        master.wait_heartbeat(timeout=5)
        return cls(master)

    @classmethod
    def connect_udp(cls, host: str, port: int, mode: str = 'udpin'):
        mode_name = str(mode or 'udpin').strip().lower() or 'udpin'
        if mode_name not in {'udpin', 'udpout', 'udp'}:
            mode_name = 'udpin'
        master = mavutil.mavlink_connection(f'{mode_name}:{host}:{port}', source_system=255)
        master.mavlink_version = 2
        master.wait_heartbeat(timeout=5)
        return cls(master)

    def run(self):
        while self.running:
            if self._mission_active:
                time.sleep(0.05)
                continue
            try:
                msg = self.master.recv_match(blocking=True, timeout=0.1)
            except Exception:
                continue
            if not msg:
                continue
            try:
                self._update_telemetry(msg)
                self.status_updated.emit(self.telemetry.copy())
            except Exception:
                continue

    def _update_telemetry(self, msg):
        msg_type = msg.get_type()

        if msg_type == 'ATTITUDE':
            self.telemetry['roll'] = math.degrees(getattr(msg, 'roll', 0.0) or 0.0)
            self.telemetry['pitch'] = math.degrees(getattr(msg, 'pitch', 0.0) or 0.0)
            yaw_degrees = math.degrees(getattr(msg, 'yaw', 0.0) or 0.0) % 360.0
            self.telemetry['yaw'] = yaw_degrees
            self.telemetry['heading'] = yaw_degrees

        elif msg_type == 'GLOBAL_POSITION_INT':
            lat = getattr(msg, 'lat', 0)
            lon = getattr(msg, 'lon', 0)
            absolute_alt = getattr(msg, 'alt', 0)
            relative_alt = getattr(msg, 'relative_alt', 0)
            heading = getattr(msg, 'hdg', 65535)
            self.telemetry['lat'] = lat / 1e7 if lat else self.telemetry['lat']
            self.telemetry['lon'] = lon / 1e7 if lon else self.telemetry['lon']
            self.telemetry['alt_abs'] = absolute_alt / 1000.0 if absolute_alt else self.telemetry['alt_abs']
            self.telemetry['alt'] = relative_alt / 1000.0 if relative_alt else self.telemetry['alt']
            if heading not in (None, 65535):
                self.telemetry['heading'] = heading / 100.0
                if not self.telemetry['yaw']:
                    self.telemetry['yaw'] = self.telemetry['heading']

        elif msg_type == 'HOME_POSITION':
            home_lat = getattr(msg, 'latitude', None)
            home_lon = getattr(msg, 'longitude', None)
            home_altitude = getattr(msg, 'altitude', None)
            if home_lat is not None and home_lon is not None:
                self.telemetry['home_lat'] = float(home_lat) / 1e7
                self.telemetry['home_lon'] = float(home_lon) / 1e7
            if home_altitude is not None:
                self.telemetry['home_alt_abs'] = float(home_altitude) / 1000.0

        elif msg_type == 'VFR_HUD':
            groundspeed = getattr(msg, 'groundspeed', None)
            heading = getattr(msg, 'heading', None)
            altitude = getattr(msg, 'alt', None)
            if groundspeed is not None:
                self.telemetry['vel'] = float(groundspeed)
            if heading is not None:
                self.telemetry['heading'] = float(heading)
            if altitude is not None:
                self.telemetry['alt'] = float(altitude)

        elif msg_type == 'GPS_RAW_INT':
            self.telemetry['gps'] = int(getattr(msg, 'satellites_visible', 0) or 0)

        elif msg_type == 'SYS_STATUS':
            voltage = getattr(msg, 'voltage_battery', -1)
            remaining = getattr(msg, 'battery_remaining', -1)
            if voltage not in (None, -1):
                self.telemetry['volt'] = float(voltage) / 1000.0
            if remaining not in (None, -1):
                self.telemetry['battery_remaining'] = int(remaining)

        elif msg_type == 'HEARTBEAT':
            try:
                src_component = int(msg.get_srcComponent())
            except Exception:
                src_component = 0
            if src_component > 0:
                self._last_heartbeat_component = src_component
            self.telemetry['mode'] = getattr(self.master, 'flightmode', 'UNKNOWN') or 'UNKNOWN'

        else:
            # Fall back to master-level cached values when available.
            self.telemetry['mode'] = getattr(self.master, 'flightmode', self.telemetry['mode']) or self.telemetry['mode']
            groundspeed = getattr(self.master, 'groundspeed', None)
            if groundspeed is not None:
                self.telemetry['vel'] = float(groundspeed or self.telemetry['vel'])

    @classmethod
    def _mission_ack_label(cls, ack_type: int) -> str:
        return cls.MISSION_ACK_LABELS.get(int(ack_type), f'UNKNOWN_{ack_type}')

    @staticmethod
    def _is_connection_lost_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return (
            isinstance(exc, SerialException)
            or 'clearcommerror failed' in text
            or 'invalid handle' in text
            or '句柄无效' in text
        )

    def _raise_connection_lost(self, exc: Exception, stage: str):
        logger.error("mission connection lost during %s: %s", stage, exc)
        raise ConnectionError(f"飞控链路已断开或串口句柄失效（{stage}）") from exc

    def _message_mission_type(self, message):
        mission_type = getattr(message, 'mission_type', None)
        if mission_type is None:
            return self.MISSION_TYPE_MISSION
        try:
            return int(mission_type)
        except Exception:
            return self.MISSION_TYPE_MISSION

    def _mission_target(self) -> tuple[int, int]:
        target_system = int(getattr(self.master, 'target_system', 0) or 0)
        component_candidates = (
            getattr(self.master, 'target_component', None),
            getattr(self, '_last_heartbeat_component', None),
            getattr(mavutil.mavlink, 'MAV_COMP_ID_AUTOPILOT1', 1),
        )
        for candidate in component_candidates:
            try:
                component = int(candidate)
            except Exception:
                continue
            if component > 0:
                return target_system, component
        return target_system, int(getattr(mavutil.mavlink, 'MAV_COMP_ID_AUTOPILOT1', 1) or 1)

    @staticmethod
    def _mission_trace_value(value):
        if isinstance(value, float):
            return round(value, 7)
        return value

    def _mission_trace_fields(self, message=None, **overrides):
        fields = {}
        candidate_names = (
            'target_system',
            'target_component',
            'seq',
            'count',
            'type',
            'mission_type',
            'opaque_id',
            'frame',
            'command',
            'current',
            'autocontinue',
            'x',
            'y',
            'z',
            'param1',
            'param2',
            'param3',
            'param4',
        )
        if message is not None:
            for name in candidate_names:
                value = getattr(message, name, None)
                if value is not None:
                    fields[name] = self._mission_trace_value(value)
        for name, value in overrides.items():
            if value is not None:
                fields[name] = self._mission_trace_value(value)
        return fields

    def _log_mission_trace(self, direction: str, stage: str, message_type: str, message=None, **fields):
        payload = self._mission_trace_fields(message, **fields)
        if payload:
            logger.info('mission trace %s %s %s: %s', direction, stage, message_type, payload)
            return
        logger.info('mission trace %s %s %s', direction, stage, message_type)

    def _is_mission_type_match(self, message, expected_type: int | None = None) -> bool:
        target_type = self.MISSION_TYPE_MISSION if expected_type is None else int(expected_type)
        return self._message_mission_type(message) == target_type

    def _recv_match_safe(self, *, message_types=None, blocking=True, timeout=None):
        try:
            if message_types is None:
                return self.master.recv_match(blocking=blocking, timeout=timeout)
            return self.master.recv_match(type=list(message_types), blocking=blocking, timeout=timeout)
        except Exception as exc:
            if self._is_connection_lost_error(exc):
                self._raise_connection_lost(exc, '接收MAVLink消息')
            raise

    def _normalize_mission_payload(self, waypoint: dict) -> dict:
        mission_type = str(waypoint.get('type', 'WAYPOINT') or 'WAYPOINT').upper()
        mission_type = self.LEGACY_TO_VTOL_MISSION_TYPE.get(mission_type, mission_type)
        if mission_type not in self.MISSION_TYPE_TO_COMMAND:
            mission_type = 'WAYPOINT'

        default_command = self.MISSION_TYPE_TO_COMMAND.get(mission_type, mavutil.mavlink.MAV_CMD_NAV_WAYPOINT)
        command = int(waypoint.get('command', default_command) or default_command)
        requested_loiter = waypoint.get('loiter')
        if mission_type == 'VTOL_TRANSITION':
            command = self.MISSION_TYPE_TO_COMMAND['VTOL_TRANSITION']
        elif mission_type == 'VTOL_TAKEOFF':
            command = self.MISSION_TYPE_TO_COMMAND['VTOL_TAKEOFF']
        elif mission_type == 'VTOL_LAND':
            command = self.MISSION_TYPE_TO_COMMAND['VTOL_LAND']
        elif mission_type == 'WAYPOINT' and requested_loiter is not None and bool(requested_loiter) != (command in self.LOITER_COMMANDS):
            command = mavutil.mavlink.MAV_CMD_NAV_LOITER_TIME if bool(requested_loiter) else mavutil.mavlink.MAV_CMD_NAV_WAYPOINT

        frame = int(waypoint.get('frame', self.DEFAULT_MISSION_FRAME))
        current = int(waypoint.get('current', 0))
        autocontinue = int(waypoint.get('autocontinue', 1))
        param1 = float(waypoint.get('param1', 0.0) or 0.0)
        param2 = float(waypoint.get('param2', 0.0) or 0.0)
        param3 = float(waypoint.get('param3', 0.0) or 0.0)
        param4 = float(waypoint.get('param4', 0.0) or 0.0)

        loiter_radius = float(waypoint.get('loiter_radius', 60.0) or 60.0)
        loiter_time = float(waypoint.get('loiter_time', 0.0) or 0.0)
        if command in self.LOITER_COMMANDS:
            autocontinue = 1
            if command == mavutil.mavlink.MAV_CMD_NAV_LOITER_UNLIM:
                param1 = 0.0
                param2 = 0.0
                param3 = loiter_radius
            elif command == mavutil.mavlink.MAV_CMD_NAV_LOITER_TURNS:
                if 'loiter_time' in waypoint:
                    param1 = loiter_time
                param3 = loiter_radius
            elif command == mavutil.mavlink.MAV_CMD_NAV_LOITER_TIME:
                if 'loiter_time' in waypoint:
                    param1 = loiter_time * 60.0
                param3 = loiter_radius
            elif command == self.LOITER_TO_ALT_COMMAND:
                param2 = loiter_radius
        elif command == self.MISSION_TYPE_TO_COMMAND['VTOL_TRANSITION']:
            param1 = float(waypoint.get('param1', self.VTOL_STATE_FW) or self.VTOL_STATE_FW)
            param2 = float(waypoint.get('param2', 0.0) or 0.0)
            param3 = 0.0
            param4 = 0.0

        latitude = float(waypoint['lat'])
        longitude = float(waypoint['lon'])
        return {
            'frame': frame,
            'command': command,
            'current': current,
            'autocontinue': autocontinue,
            'param1': param1,
            'param2': param2,
            'param3': param3,
            'param4': param4,
            'lat': latitude,
            'lon': longitude,
            'lat_int': int(latitude * 1e7),
            'lon_int': int(longitude * 1e7),
            'alt': float(waypoint['alt']),
        }

    def _send_mission_item(
        self,
        target_system: int,
        target_component: int,
        seq: int,
        payload: dict,
        use_int: bool,
        mission_type: int | None = None,
    ):
        target_mission_type = self.MISSION_TYPE_MISSION if mission_type is None else int(mission_type)
        try:
            if use_int:
                self._log_mission_trace(
                    'send',
                    'upload_item',
                    'MISSION_ITEM_INT',
                    target_system=target_system,
                    target_component=target_component,
                    seq=seq,
                    frame=payload['frame'],
                    command=payload['command'],
                    current=payload['current'],
                    autocontinue=payload['autocontinue'],
                    param1=payload['param1'],
                    param2=payload['param2'],
                    param3=payload['param3'],
                    param4=payload['param4'],
                    x=payload['lat_int'],
                    y=payload['lon_int'],
                    z=payload['alt'],
                    mission_type=target_mission_type,
                )
                try:
                    self.master.mav.mission_item_int_send(
                        target_system,
                        target_component,
                        seq,
                        payload['frame'],
                        payload['command'],
                        payload['current'],
                        payload['autocontinue'],
                        payload['param1'],
                        payload['param2'],
                        payload['param3'],
                        payload['param4'],
                        payload['lat_int'],
                        payload['lon_int'],
                        payload['alt'],
                        target_mission_type,
                    )
                except TypeError:
                    self.master.mav.mission_item_int_send(
                        target_system,
                        target_component,
                        seq,
                        payload['frame'],
                        payload['command'],
                        payload['current'],
                        payload['autocontinue'],
                        payload['param1'],
                        payload['param2'],
                        payload['param3'],
                        payload['param4'],
                        payload['lat_int'],
                        payload['lon_int'],
                        payload['alt'],
                    )
                return

            self._log_mission_trace(
                'send',
                'upload_item',
                'MISSION_ITEM',
                target_system=target_system,
                target_component=target_component,
                seq=seq,
                frame=payload['frame'],
                command=payload['command'],
                current=payload['current'],
                autocontinue=payload['autocontinue'],
                param1=payload['param1'],
                param2=payload['param2'],
                param3=payload['param3'],
                param4=payload['param4'],
                x=payload['lat'],
                y=payload['lon'],
                z=payload['alt'],
                mission_type=target_mission_type,
            )
            try:
                self.master.mav.mission_item_send(
                    target_system,
                    target_component,
                    seq,
                    payload['frame'],
                    payload['command'],
                    payload['current'],
                    payload['autocontinue'],
                    payload['param1'],
                    payload['param2'],
                    payload['param3'],
                    payload['param4'],
                    payload['lat'],
                    payload['lon'],
                    payload['alt'],
                    target_mission_type,
                )
            except TypeError:
                self.master.mav.mission_item_send(
                    target_system,
                    target_component,
                    seq,
                    payload['frame'],
                    payload['command'],
                    payload['current'],
                    payload['autocontinue'],
                    payload['param1'],
                    payload['param2'],
                    payload['param3'],
                    payload['param4'],
                    payload['lat'],
                    payload['lon'],
                    payload['alt'],
                )
        except Exception as exc:
            if self._is_connection_lost_error(exc):
                self._raise_connection_lost(exc, '发送任务点')
            raise

    def _send_mission_request_list(self, target_system: int, target_component: int, mission_type: int | None = None):
        target_mission_type = self.MISSION_TYPE_MISSION if mission_type is None else int(mission_type)
        try:
            self._log_mission_trace(
                'send',
                'download_begin',
                'MISSION_REQUEST_LIST',
                target_system=target_system,
                target_component=target_component,
                mission_type=target_mission_type,
            )
            self.master.mav.mission_request_list_send(
                target_system,
                target_component,
                target_mission_type,
            )
        except TypeError:
            self.master.mav.mission_request_list_send(target_system, target_component)
        except Exception as exc:
            if self._is_connection_lost_error(exc):
                self._raise_connection_lost(exc, '请求飞控任务列表')
            raise

    def _send_mission_request(
        self,
        target_system: int,
        target_component: int,
        sequence: int,
        use_int: bool = True,
        mission_type: int | None = None,
    ):
        target_mission_type = self.MISSION_TYPE_MISSION if mission_type is None else int(mission_type)
        try:
            if use_int:
                self._log_mission_trace(
                    'send',
                    'download_request',
                    'MISSION_REQUEST_INT',
                    target_system=target_system,
                    target_component=target_component,
                    seq=sequence,
                    mission_type=target_mission_type,
                )
                try:
                    self.master.mav.mission_request_int_send(
                        target_system,
                        target_component,
                        sequence,
                        target_mission_type,
                    )
                except TypeError:
                    self.master.mav.mission_request_int_send(target_system, target_component, sequence)
                return

            self._log_mission_trace(
                'send',
                'download_request',
                'MISSION_REQUEST',
                target_system=target_system,
                target_component=target_component,
                seq=sequence,
                mission_type=target_mission_type,
            )
            try:
                self.master.mav.mission_request_send(
                    target_system,
                    target_component,
                    sequence,
                    target_mission_type,
                )
            except TypeError:
                self.master.mav.mission_request_send(target_system, target_component, sequence)
        except Exception as exc:
            if self._is_connection_lost_error(exc):
                self._raise_connection_lost(exc, '请求任务点')
            raise

    def _send_mission_ack(
        self,
        target_system: int,
        target_component: int,
        ack_type: int,
        mission_type: int | None = None,
    ):
        target_mission_type = self.MISSION_TYPE_MISSION if mission_type is None else int(mission_type)
        try:
            self._log_mission_trace(
                'send',
                'ack',
                'MISSION_ACK',
                target_system=target_system,
                target_component=target_component,
                type=ack_type,
                mission_type=target_mission_type,
            )
            self.master.mav.mission_ack_send(
                target_system,
                target_component,
                ack_type,
                target_mission_type,
            )
        except TypeError:
            self.master.mav.mission_ack_send(target_system, target_component, ack_type)
        except Exception as exc:
            if self._is_connection_lost_error(exc):
                self._raise_connection_lost(exc, '发送任务ACK')
            raise

    def _ack_state_label(self, ack_state: str) -> str:
        labels = {
            self.ACK_NONE: 'No Ack',
            self.ACK_MISSION_COUNT: 'MISSION_COUNT',
            self.ACK_MISSION_ITEM: 'MISSION_ITEM',
            self.ACK_MISSION_REQUEST: 'MISSION_REQUEST',
        }
        return labels.get(ack_state, ack_state)

    def _ack_state_timeout(self, ack_state: str) -> float:
        if ack_state == self.ACK_MISSION_ITEM:
            return self.RETRY_TIMEOUT_SECONDS
        return self.ACK_TIMEOUT_SECONDS

    def _wait_for_ack_state_message(self, ack_state: str, predicate=None, mission_type: int | None = None):
        target_mission_type = self.MISSION_TYPE_MISSION if mission_type is None else int(mission_type)
        message_types = {
            self.ACK_MISSION_COUNT: {'MISSION_COUNT', 'MISSION_ACK'},
            self.ACK_MISSION_ITEM: {'MISSION_ITEM_INT', 'MISSION_ITEM', 'MISSION_ACK'},
            self.ACK_MISSION_REQUEST: {'MISSION_REQUEST_INT', 'MISSION_REQUEST', 'MISSION_ACK'},
        }.get(ack_state, set())
        logger.info(
            'mission trace wait %s: expecting=%s timeout=%.2fs',
            self._ack_state_label(ack_state),
            sorted(message_types),
            self._ack_state_timeout(ack_state),
        )
        deadline = time.time() + self._ack_state_timeout(ack_state)
        while time.time() < deadline:
            remaining = max(0.05, deadline - time.time())
            message = self._recv_match_safe(message_types=message_types, blocking=True, timeout=remaining)
            if message is None:
                continue
            self._log_mission_trace('recv', self._ack_state_label(ack_state), message.get_type(), message=message)
            if not self._is_mission_type_match(message, expected_type=target_mission_type):
                logger.debug(
                    'mission message dropped due to mission_type mismatch while expecting %s: %s type=%s',
                    self._ack_state_label(ack_state),
                    message.get_type(),
                    getattr(message, 'mission_type', None),
                )
                continue
            if predicate is not None and not predicate(message):
                logger.debug(
                    'out-of-sequence mission message while expecting %s: %s',
                    self._ack_state_label(ack_state),
                    message.get_type(),
                )
                continue
            return message
        logger.warning('mission trace wait timeout: state=%s', self._ack_state_label(ack_state))
        return None

    def _validate_upload_ack(self, message, pending_indices: list[int]):
        ack_type = int(getattr(message, 'type', mavutil.mavlink.MAV_MISSION_ACCEPTED))
        ack_label = self._mission_ack_label(ack_type)
        invalid_sequence = int(getattr(mavutil.mavlink, 'MAV_MISSION_INVALID_SEQUENCE', 13))
        if ack_type == invalid_sequence:
            logger.warning('ignoring transient MAV_MISSION_INVALID_SEQUENCE during upload')
            return False
        if ack_type == mavutil.mavlink.MAV_MISSION_ACCEPTED and not pending_indices:
            return True
        if ack_type == mavutil.mavlink.MAV_MISSION_ACCEPTED and pending_indices:
            raise RuntimeError(
                f'飞控过早返回上传完成确认，仍有 {len(pending_indices)} 个任务点未请求'
            )
        raise RuntimeError(f'飞控拒绝任务上传，ACK={ack_label}({ack_type})')

    def _upload_mission_protocol(self, waypoints: list[dict], use_int: bool):
        total = len(waypoints)
        target_system, target_component = self._mission_target()
        protocol_name = 'MISSION_ITEM_INT' if use_int else 'MISSION_ITEM'
        pending_indices = list(range(total))
        retry_count = 0
        last_requested = -1

        self._emit_mission_progress('upload', 0, total, f'正在发送任务总数（{protocol_name}）', active=True)
        self._send_mission_count(target_system, target_component, total, use_legacy=not use_int)

        while True:
            message = self._wait_for_ack_state_message(self.ACK_MISSION_REQUEST)
            if message is None:
                if pending_indices and pending_indices[0] == 0:
                    if retry_count >= self.MAX_RETRY_COUNT:
                        raise TimeoutError('Mission write mission count failed, maximum retries exceeded.')
                    retry_count += 1
                    logger.warning(
                        'Retrying mission count in %s mode (%d/%d)',
                        protocol_name,
                        retry_count,
                        self.MAX_RETRY_COUNT,
                    )
                    self._send_mission_count(target_system, target_component, total, use_legacy=not use_int)
                    continue
                if not pending_indices:
                    raise TimeoutError('Mission write failed, vehicle failed to send final ack.')
                raise TimeoutError(
                    f'飞控未请求全部任务点，最后请求序号={last_requested}，剩余 {len(pending_indices)} 个'
                )

            if message.get_type() == 'MISSION_ACK':
                if self._validate_upload_ack(message, pending_indices):
                    self._emit_mission_progress('upload', total, total, '航线上传完成', active=False)
                    return
                continue

            _seq = getattr(message, 'seq', None)
            request_seq = int(_seq) if _seq is not None else -1
            logger.info('mission upload request in %s mode: seq=%d pending=%d', protocol_name, request_seq, len(pending_indices))
            if request_seq > total - 1:
                raise RuntimeError(f'飞控请求越界任务点，任务总数={total}，请求序号={request_seq}')
            if request_seq < 0:
                continue

            last_requested = request_seq
            if request_seq in pending_indices:
                pending_indices.remove(request_seq)
            else:
                logger.warning('duplicate mission request received, resending seq=%d', request_seq)

            payload = self._normalize_mission_payload(waypoints[request_seq])
            self._send_mission_item(target_system, target_component, request_seq, payload, use_int=use_int)
            retry_count = 0
            current = total - len(pending_indices)
            self._emit_mission_progress(
                'upload',
                current,
                total,
                f'已上传 {current}/{total} 个任务点',
                active=True,
            )

    def upload_mission(self, waypoints: list[dict]):
        if not waypoints:
            raise ValueError("没有可上传的航点")

        with self._mission_session():
            upload_errors = []
            for use_int in (True, False):
                try:
                    self._upload_mission_protocol(waypoints, use_int=use_int)
                    return
                except ConnectionError:
                    raise
                except Exception as exc:
                    upload_errors.append((use_int, exc))
                    logger.warning(
                        "mission upload attempt failed in %s mode: %s",
                        'MISSION_ITEM_INT' if use_int else 'MISSION_ITEM',
                        exc,
                    )
                    if not use_int:
                        break
                    self._emit_mission_progress(
                        'upload',
                        0,
                        len(waypoints),
                        '当前飞控不接受 INT 协议，切换为 legacy 上传重试',
                        active=True,
                    )
                    time.sleep(0.2)

            if upload_errors:
                _, last_error = upload_errors[-1]
                raise last_error
            raise RuntimeError('航线上传失败：未进入有效上传流程')

    def _send_mission_write_partial_list(
        self,
        target_system: int,
        target_component: int,
        start_index: int,
        end_index: int,
        use_legacy: bool = False,
    ):
        if use_legacy:
            try:
                self._log_mission_trace(
                    'send',
                    'partial_begin',
                    'MISSION_WRITE_PARTIAL_LIST',
                    target_system=target_system,
                    target_component=target_component,
                    start_index=start_index,
                    end_index=end_index,
                    legacy=True,
                )
                self.master.mav.mission_write_partial_list_send(
                    target_system,
                    target_component,
                    start_index,
                    end_index,
                )
                return
            except Exception as exc:
                if self._is_connection_lost_error(exc):
                    self._raise_connection_lost(exc, '发送部分任务写入请求')
                raise

        try:
            self._log_mission_trace(
                'send',
                'partial_begin',
                'MISSION_WRITE_PARTIAL_LIST',
                target_system=target_system,
                target_component=target_component,
                start_index=start_index,
                end_index=end_index,
                mission_type=self.MISSION_TYPE_MISSION,
            )
            self.master.mav.mission_write_partial_list_send(
                target_system,
                target_component,
                start_index,
                end_index,
                self.MISSION_TYPE_MISSION,
            )
        except TypeError:
            self.master.mav.mission_write_partial_list_send(
                target_system,
                target_component,
                start_index,
                end_index,
            )
        except Exception as exc:
            if self._is_connection_lost_error(exc):
                self._raise_connection_lost(exc, '发送部分任务写入请求')
            raise

    def _upload_single_mission_item_protocol(self, index: int, waypoint: dict, use_int: bool):
        target_system, target_component = self._mission_target()
        protocol_name = 'MISSION_ITEM_INT' if use_int else 'MISSION_ITEM'
        retry_count = 0

        self._emit_mission_progress('upload', 0, 1, f'正在请求单航点上传（{protocol_name}）', active=True)
        self._send_mission_write_partial_list(
            target_system,
            target_component,
            int(index),
            int(index),
            use_legacy=not use_int,
        )

        while True:
            message = self._wait_for_ack_state_message(self.ACK_MISSION_REQUEST)
            if message is None:
                if retry_count >= self.MAX_RETRY_COUNT:
                    raise TimeoutError('单航点上传超时：飞控未请求目标航点')
                retry_count += 1
                logger.warning(
                    'Retrying partial mission write in %s mode (%d/%d)',
                    protocol_name,
                    retry_count,
                    self.MAX_RETRY_COUNT,
                )
                self._send_mission_write_partial_list(
                    target_system,
                    target_component,
                    int(index),
                    int(index),
                    use_legacy=not use_int,
                )
                continue

            if message.get_type() == 'MISSION_ACK':
                if self._validate_upload_ack(message, [int(index)]):
                    continue

            request_seq = int(getattr(message, 'seq', -1) or -1)
            if request_seq != int(index):
                raise RuntimeError(f'飞控请求了错误的航点序号：期待 {index}，实际 {request_seq}')

            payload = self._normalize_mission_payload(waypoint)
            self._send_mission_item(target_system, target_component, request_seq, payload, use_int=use_int)
            break

        while True:
            message = self._wait_for_ack_state_message(self.ACK_MISSION_ITEM)
            if message is None:
                raise TimeoutError('单航点上传失败：等待飞控确认超时')
            if message.get_type() != 'MISSION_ACK':
                continue
            if self._validate_upload_ack(message, []):
                self._emit_mission_progress('upload', 1, 1, '单航点上传完成', active=False)
                return

    def upload_single_mission_item(self, index: int, waypoint: dict):
        if index is None or int(index) < 0:
            raise ValueError('单航点上传失败：序号无效')
        if not isinstance(waypoint, dict):
            raise ValueError('单航点上传失败：航点数据无效')

        with self._mission_session():
            upload_errors = []
            for use_int in (True, False):
                try:
                    self._upload_single_mission_item_protocol(int(index), dict(waypoint), use_int=use_int)
                    return
                except ConnectionError:
                    raise
                except Exception as exc:
                    upload_errors.append((use_int, exc))
                    logger.warning(
                        'single waypoint upload attempt failed in %s mode: %s',
                        'MISSION_ITEM_INT' if use_int else 'MISSION_ITEM',
                        exc,
                    )
                    if not use_int:
                        break
                    self._emit_mission_progress(
                        'upload',
                        0,
                        1,
                        '当前飞控不接受 INT 协议，切换为 legacy 单航点上传重试',
                        active=True,
                    )
                    time.sleep(0.2)

            if upload_errors:
                _, last_error = upload_errors[-1]
                raise last_error
            raise RuntimeError('单航点上传失败：未进入有效上传流程')

    def _send_mission_clear_all(self, target_system: int, target_component: int):
        try:
            self._log_mission_trace(
                'send',
                'clear_all',
                'MISSION_CLEAR_ALL',
                target_system=target_system,
                target_component=target_component,
                mission_type=self.MISSION_TYPE_MISSION,
            )
            self.master.mav.mission_clear_all_send(
                target_system,
                target_component,
                self.MISSION_TYPE_MISSION,
            )
        except TypeError:
            self.master.mav.mission_clear_all_send(target_system, target_component)
        except Exception as exc:
            if self._is_connection_lost_error(exc):
                self._raise_connection_lost(exc, '清空飞控任务')
            raise

    def _send_mission_count(
        self,
        target_system: int,
        target_component: int,
        total: int,
        use_legacy: bool = False,
        mission_type: int | None = None,
    ):
        target_mission_type = self.MISSION_TYPE_MISSION if mission_type is None else int(mission_type)
        if use_legacy:
            try:
                self._log_mission_trace(
                    'send',
                    'upload_begin',
                    'MISSION_COUNT',
                    target_system=target_system,
                    target_component=target_component,
                    count=total,
                    legacy=True,
                )
                self.master.mav.mission_count_send(target_system, target_component, total)
                return
            except Exception as exc:
                if self._is_connection_lost_error(exc):
                    self._raise_connection_lost(exc, '发送任务总数')
                raise
        try:
            self._log_mission_trace(
                'send',
                'upload_begin',
                'MISSION_COUNT',
                target_system=target_system,
                target_component=target_component,
                count=total,
                mission_type=target_mission_type,
                legacy=False,
            )
            self.master.mav.mission_count_send(
                target_system,
                target_component,
                total,
                target_mission_type,
            )
        except TypeError:
            self.master.mav.mission_count_send(target_system, target_component, total)
        except Exception as exc:
            if self._is_connection_lost_error(exc):
                self._raise_connection_lost(exc, '发送任务总数')
            raise

    def download_mission(self) -> list[dict]:
        with self._mission_session():
            target_system, target_component = self._mission_target()

            self._ensure_home_altitude(target_system, target_component)
            self._emit_mission_progress('download', 0, 0, '正在请求飞控任务列表', active=True)
            retry_count = 0
            self._send_mission_request_list(target_system, target_component)
            count_msg = None
            while count_msg is None:
                count_msg = self._wait_for_ack_state_message(self.ACK_MISSION_COUNT)
                if count_msg is not None:
                    break
                if retry_count >= self.MAX_RETRY_COUNT:
                    raise TimeoutError('Mission request list failed, maximum retries exceeded.')
                retry_count += 1
                logger.warning('Retrying mission request list (%d/%d)', retry_count, self.MAX_RETRY_COUNT)
                self._send_mission_request_list(target_system, target_component)

            if count_msg.get_type() == 'MISSION_ACK':
                ack_type = int(getattr(count_msg, 'type', mavutil.mavlink.MAV_MISSION_ACCEPTED))
                ack_label = self._mission_ack_label(ack_type)
                raise RuntimeError(f'飞控拒绝任务下载，ACK={ack_label}({ack_type})')

            mission_count = int(getattr(count_msg, 'count', 0) or 0)
            self._emit_mission_progress('download', 0, mission_count, f'飞控返回 {mission_count} 个任务点', active=True)
            if mission_count == 0:
                self._send_mission_ack(target_system, target_component, int(mavutil.mavlink.MAV_MISSION_ACCEPTED))
                self._log_downloaded_mission_heights([])
                self._emit_mission_progress('download', 0, 0, '航线下载完成', active=False)
                return []

            pending_indices = list(range(mission_count))
            mission_items_by_seq = {}
            retry_count = 0
            use_int_request = True

            while pending_indices:
                current_seq = pending_indices[0]
                self._emit_mission_progress(
                    'download',
                    mission_count - len(pending_indices),
                    mission_count,
                    f'正在下载第 {current_seq + 1} 个任务点',
                    active=True,
                )
                self._send_mission_request(target_system, target_component, current_seq, use_int=use_int_request)
                item_msg = self._wait_for_ack_state_message(self.ACK_MISSION_ITEM)
                if item_msg is None:
                    if use_int_request:
                        use_int_request = False
                        retry_count = 0
                        logger.warning(
                            'MISSION_REQUEST_INT timed out at seq=%d; falling back to legacy MISSION_REQUEST',
                            current_seq,
                        )
                        self._emit_mission_progress(
                            'download',
                            mission_count - len(pending_indices),
                            mission_count,
                            f'INT 下载超时，切换 legacy 模式重试第 {current_seq + 1} 个任务点',
                            active=True,
                        )
                        continue
                    if retry_count >= self.MAX_RETRY_COUNT:
                        raise TimeoutError(f'Mission read failed, maximum retries exceeded at seq={current_seq}')
                    retry_count += 1
                    logger.warning('Retrying mission request seq=%d (%d/%d)', current_seq, retry_count, self.MAX_RETRY_COUNT)
                    continue

                if item_msg.get_type() == 'MISSION_ACK':
                    ack_type = int(getattr(item_msg, 'type', mavutil.mavlink.MAV_MISSION_ACCEPTED))
                    ack_label = self._mission_ack_label(ack_type)
                    if use_int_request and ack_type in {
                        int(getattr(mavutil.mavlink, 'MAV_MISSION_UNSUPPORTED', 3)),
                        int(getattr(mavutil.mavlink, 'MAV_MISSION_UNSUPPORTED_FRAME', 2)),
                    }:
                        use_int_request = False
                        retry_count = 0
                        logger.warning(
                            'MISSION_REQUEST_INT was rejected with %s(%d); falling back to legacy MISSION_REQUEST',
                            ack_label,
                            ack_type,
                        )
                        continue
                    raise RuntimeError(f'飞控在下载过程中返回错误ACK={ack_label}({ack_type})')

                _seq = getattr(item_msg, 'seq', None)
                seq = int(_seq) if _seq is not None else -1
                if seq != current_seq:
                    logger.warning('mission item received out of order, expected=%d got=%d - discarding', current_seq, seq)
                    continue

                mission_items_by_seq[seq] = self._mission_item_to_waypoint(item_msg)
                pending_indices.pop(0)
                retry_count = 0
                self._emit_mission_progress(
                    'download',
                    mission_count - len(pending_indices),
                    mission_count,
                    f'已下载 {mission_count - len(pending_indices)}/{mission_count} 个任务点',
                    active=True,
                )

            mission_items = [mission_items_by_seq[index] for index in range(mission_count)]
            self._send_mission_ack(target_system, target_component, int(mavutil.mavlink.MAV_MISSION_ACCEPTED))
            self._log_downloaded_mission_heights(mission_items)
            self._emit_mission_progress('download', mission_count, mission_count, '航线下载完成', active=False)
            return mission_items

    @staticmethod
    def _normalize_raw_item(item: dict) -> dict:
        lat = float(item.get('lat', 0.0) or 0.0)
        lon = float(item.get('lon', 0.0) or 0.0)
        alt = float(item.get('alt', 0.0) or 0.0)
        return {
            'frame': int(item.get('frame', mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT) or mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT),
            'command': int(item.get('command', mavutil.mavlink.MAV_CMD_NAV_WAYPOINT) or mavutil.mavlink.MAV_CMD_NAV_WAYPOINT),
            'current': int(item.get('current', 0) or 0),
            'autocontinue': int(item.get('autocontinue', 1) or 1),
            'param1': float(item.get('param1', 0.0) or 0.0),
            'param2': float(item.get('param2', 0.0) or 0.0),
            'param3': float(item.get('param3', 0.0) or 0.0),
            'param4': float(item.get('param4', 0.0) or 0.0),
            'lat': lat,
            'lon': lon,
            'lat_int': int(round(lat * 1e7)),
            'lon_int': int(round(lon * 1e7)),
            'alt': alt,
        }

    def _upload_raw_items(self, items: list[dict], mission_type: int, operation_label: str):
        total = len(items)
        target_system, target_component = self._mission_target()
        pending_indices = list(range(total))

        self._emit_mission_progress('upload', 0, total, f'正在上传{operation_label}', active=True)
        self._send_mission_count(target_system, target_component, total, mission_type=mission_type)

        while True:
            message = self._wait_for_ack_state_message(self.ACK_MISSION_REQUEST, mission_type=mission_type)
            if message is None:
                if not pending_indices:
                    raise TimeoutError(f'{operation_label}上传失败：等待飞控确认超时')
                raise TimeoutError(f'{operation_label}上传失败：飞控未请求全部任务点')

            if message.get_type() == 'MISSION_ACK':
                if self._validate_upload_ack(message, pending_indices):
                    self._emit_mission_progress('upload', total, total, f'{operation_label}上传完成', active=False)
                    return
                continue

            request_seq = int(getattr(message, 'seq', -1) or -1)
            if request_seq < 0 or request_seq >= total:
                continue
            if request_seq in pending_indices:
                pending_indices.remove(request_seq)

            payload = self._normalize_raw_item(items[request_seq])
            self._send_mission_item(
                target_system,
                target_component,
                request_seq,
                payload,
                use_int=True,
                mission_type=mission_type,
            )
            current = total - len(pending_indices)
            self._emit_mission_progress('upload', current, total, f'已上传 {current}/{total} 个点', active=True)

    def _download_raw_items(self, mission_type: int, operation_label: str) -> list[dict]:
        target_system, target_component = self._mission_target()
        self._emit_mission_progress('download', 0, 0, f'正在下载{operation_label}', active=True)
        self._send_mission_request_list(target_system, target_component, mission_type=mission_type)
        count_msg = self._wait_for_ack_state_message(self.ACK_MISSION_COUNT, mission_type=mission_type)
        if count_msg is None:
            raise TimeoutError(f'{operation_label}下载失败：等待任务数量超时')
        if count_msg.get_type() == 'MISSION_ACK':
            ack_type = int(getattr(count_msg, 'type', mavutil.mavlink.MAV_MISSION_ACCEPTED))
            raise RuntimeError(f'{operation_label}下载被拒绝，ACK={self._mission_ack_label(ack_type)}({ack_type})')

        mission_count = int(getattr(count_msg, 'count', 0) or 0)
        if mission_count <= 0:
            self._send_mission_ack(target_system, target_component, int(mavutil.mavlink.MAV_MISSION_ACCEPTED), mission_type=mission_type)
            self._emit_mission_progress('download', 0, 0, f'{operation_label}下载完成', active=False)
            return []

        mission_items = {}
        pending = list(range(mission_count))
        use_int_request = True
        legacy_retry_count = 0
        while pending:
            seq = pending[0]
            self._send_mission_request(target_system, target_component, seq, use_int=use_int_request, mission_type=mission_type)
            item_msg = self._wait_for_ack_state_message(self.ACK_MISSION_ITEM, mission_type=mission_type)
            if item_msg is None:
                if use_int_request:
                    use_int_request = False
                    legacy_retry_count = 0
                    logger.warning('%s download INT request timed out at seq=%d; retrying in legacy mode', operation_label, seq)
                    continue
                if legacy_retry_count >= self.MAX_RETRY_COUNT:
                    raise TimeoutError(f'{operation_label}下载失败：等待任务点 {seq} 超时')
                legacy_retry_count += 1
                continue
            if item_msg.get_type() == 'MISSION_ACK':
                ack_type = int(getattr(item_msg, 'type', mavutil.mavlink.MAV_MISSION_ACCEPTED))
                if use_int_request and ack_type in {
                    int(getattr(mavutil.mavlink, 'MAV_MISSION_UNSUPPORTED', 3)),
                    int(getattr(mavutil.mavlink, 'MAV_MISSION_UNSUPPORTED_FRAME', 2)),
                }:
                    use_int_request = False
                    legacy_retry_count = 0
                    logger.warning('%s download INT request rejected with ACK=%s(%d); retrying in legacy mode', operation_label, self._mission_ack_label(ack_type), ack_type)
                    continue
                raise RuntimeError(f'{operation_label}下载失败，ACK={self._mission_ack_label(ack_type)}({ack_type})')

            item_seq = int(getattr(item_msg, 'seq', -1) or -1)
            if item_seq != seq:
                continue
            mission_items[item_seq] = self._mission_item_to_waypoint(item_msg)
            pending.pop(0)
            legacy_retry_count = 0
            self._emit_mission_progress('download', mission_count - len(pending), mission_count, f'已下载 {mission_count - len(pending)}/{mission_count} 个点', active=True)

        ordered = [mission_items[index] for index in range(mission_count)]
        self._send_mission_ack(target_system, target_component, int(mavutil.mavlink.MAV_MISSION_ACCEPTED), mission_type=mission_type)
        self._emit_mission_progress('download', mission_count, mission_count, f'{operation_label}下载完成', active=False)
        return ordered

    def _geofence_to_mission_items(self, payload: dict) -> list[dict]:
        circles = list((payload or {}).get('circles', []))
        polygons = list((payload or {}).get('polygons', []))
        items = []

        for polygon in polygons:
            points = list(polygon.get('polygon', polygon.get('points', [])) or [])
            inclusion = bool(polygon.get('inclusion', True))
            command = self.FENCE_CMD_POLYGON_INCLUSION if inclusion else self.FENCE_CMD_POLYGON_EXCLUSION
            vertex_count = float(len(points))
            for point in points:
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    continue
                items.append({
                    'frame': mavutil.mavlink.MAV_FRAME_GLOBAL,
                    'command': command,
                    'param1': vertex_count,
                    'param2': 0.0,
                    'param3': 0.0,
                    'param4': 0.0,
                    'lat': float(point[0] or 0.0),
                    'lon': float(point[1] or 0.0),
                    'alt': 0.0,
                })

        for circle in circles:
            center = list(circle.get('center', []))
            if len(center) < 2:
                continue
            inclusion = bool(circle.get('inclusion', True))
            command = self.FENCE_CMD_CIRCLE_INCLUSION if inclusion else self.FENCE_CMD_CIRCLE_EXCLUSION
            items.append({
                'frame': mavutil.mavlink.MAV_FRAME_GLOBAL,
                'command': command,
                'param1': float(circle.get('radius', 0.0) or 0.0),
                'param2': 0.0,
                'param3': 0.0,
                'param4': 0.0,
                'lat': float(center[0] or 0.0),
                'lon': float(center[1] or 0.0),
                'alt': 0.0,
            })

        return items

    def _mission_items_to_geofence(self, items: list[dict]) -> dict:
        polygons = []
        circles = []
        current_vertices = []
        current_vertex_total = 0
        current_inclusion = True

        for item in items:
            command = int(item.get('command', 0) or 0)
            if command in (self.FENCE_CMD_POLYGON_INCLUSION, self.FENCE_CMD_POLYGON_EXCLUSION):
                expected = int(item.get('param1', 0) or 0)
                if current_vertex_total == 0 or expected != current_vertex_total or command != (
                    self.FENCE_CMD_POLYGON_INCLUSION if current_inclusion else self.FENCE_CMD_POLYGON_EXCLUSION
                ):
                    if current_vertices:
                        polygons.append({'polygon': current_vertices, 'inclusion': current_inclusion})
                    current_vertices = []
                    current_vertex_total = expected
                    current_inclusion = command == self.FENCE_CMD_POLYGON_INCLUSION
                current_vertices.append([float(item.get('lat', 0.0) or 0.0), float(item.get('lon', 0.0) or 0.0)])
                if current_vertex_total > 0 and len(current_vertices) >= current_vertex_total:
                    polygons.append({'polygon': current_vertices, 'inclusion': current_inclusion})
                    current_vertices = []
                    current_vertex_total = 0
                continue

            if command in (self.FENCE_CMD_CIRCLE_INCLUSION, self.FENCE_CMD_CIRCLE_EXCLUSION):
                circles.append({
                    'center': [float(item.get('lat', 0.0) or 0.0), float(item.get('lon', 0.0) or 0.0)],
                    'radius': float(item.get('param1', 0.0) or 0.0),
                    'inclusion': command == self.FENCE_CMD_CIRCLE_INCLUSION,
                })

        if current_vertices:
            polygons.append({'polygon': current_vertices, 'inclusion': current_inclusion})

        return {'version': 2, 'circles': circles, 'polygons': polygons}

    @staticmethod
    def _rally_to_mission_items(payload: dict) -> list[dict]:
        points = list((payload or {}).get('points', []))
        items = []
        for point in points:
            items.append({
                'frame': mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                'command': int(getattr(mavutil.mavlink, 'MAV_CMD_NAV_RALLY_POINT', 5100)),
                'param1': 0.0,
                'param2': 0.0,
                'param3': 0.0,
                'param4': 0.0,
                'lat': float(point.get('lat', 0.0) or 0.0),
                'lon': float(point.get('lon', 0.0) or 0.0),
                'alt': float(point.get('alt', 0.0) or 0.0),
            })
        return items

    def _mission_items_to_rally(self, items: list[dict]) -> dict:
        points = []
        for item in items:
            command = int(item.get('command', 0) or 0)
            if command != self.RALLY_CMD_NAV_POINT:
                continue
            points.append({
                'lat': float(item.get('lat', 0.0) or 0.0),
                'lon': float(item.get('lon', 0.0) or 0.0),
                'alt': float(item.get('alt', 0.0) or 0.0),
            })
        return {'version': 2, 'points': points}

    def upload_geofence(self, payload: dict):
        with self._mission_session():
            items = self._geofence_to_mission_items(payload)
            self._upload_raw_items(items, mission_type=self.MISSION_TYPE_FENCE, operation_label='围栏')

    def download_geofence(self) -> dict:
        with self._mission_session():
            items = self._download_raw_items(mission_type=self.MISSION_TYPE_FENCE, operation_label='围栏')
            return self._mission_items_to_geofence(items)

    def upload_rally_points(self, payload: dict):
        with self._mission_session():
            items = self._rally_to_mission_items(payload)
            self._upload_raw_items(items, mission_type=self.MISSION_TYPE_RALLY, operation_label='备降点')

    def download_rally_points(self) -> dict:
        with self._mission_session():
            items = self._download_raw_items(mission_type=self.MISSION_TYPE_RALLY, operation_label='备降点')
            return self._mission_items_to_rally(items)

    def _mission_item_to_waypoint(self, item) -> dict:
        msg_type = item.get_type()
        command = int(getattr(item, 'command', mavutil.mavlink.MAV_CMD_NAV_WAYPOINT))
        frame = int(getattr(item, 'frame', self.DEFAULT_MISSION_FRAME) or self.DEFAULT_MISSION_FRAME)
        if msg_type == 'MISSION_ITEM_INT':
            lat = float(getattr(item, 'x', 0)) / 1e7
            lon = float(getattr(item, 'y', 0)) / 1e7
        else:
            lat = float(getattr(item, 'x', 0.0))
            lon = float(getattr(item, 'y', 0.0))

        # QGC-style loading: keep mission altitude as transmitted by FC and preserve
        # original MAV_FRAME, instead of forcing a global relative conversion.
        raw_altitude = float(getattr(item, 'z', 0.0) or 0.0)
        altitude = raw_altitude
        param1 = float(getattr(item, 'param1', 0.0) or 0.0)
        param2 = float(getattr(item, 'param2', 0.0) or 0.0)
        param3 = float(getattr(item, 'param3', 0.0) or 0.0)
        param4 = float(getattr(item, 'param4', 0.0) or 0.0)
        loiter_radius = param2 if command == self.LOITER_TO_ALT_COMMAND else param3
        if command == mavutil.mavlink.MAV_CMD_NAV_LOITER_TIME:
            loiter_time = max(0.0, param1) / 60.0
        elif command == mavutil.mavlink.MAV_CMD_NAV_LOITER_TURNS:
            loiter_time = max(0.0, param1)
        else:
            loiter_time = 0.0
        return {
            'lat': lat,
            'lon': lon,
            'alt': altitude,
            'seq': int(getattr(item, 'seq', 0) or 0),
            'type': self.COMMAND_TO_MISSION_TYPE.get(command, 'WAYPOINT'),
            'loiter': command in self.LOITER_COMMANDS,
            'loiter_radius': float(loiter_radius or 60.0),
            'loiter_time': loiter_time,
            'command': command,
            'frame': frame,
            'source_frame': frame,
            'source_alt': raw_altitude,
            'current': int(getattr(item, 'current', 0) or 0),
            'autocontinue': int(getattr(item, 'autocontinue', 1) or 1),
            'param1': param1,
            'param2': param2,
            'param3': param3,
            'param4': param4,
        }

    def _ensure_home_altitude(self, target_system: int, target_component: int):
        if self.telemetry.get('home_alt_abs') is not None:
            return
        try:
            self.master.mav.command_long_send(
                target_system,
                target_component,
                mavutil.mavlink.MAV_CMD_GET_HOME_POSITION,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
            )
            message = self._wait_for_message({'HOME_POSITION'}, timeout=2.0)
            if message is not None:
                self._update_telemetry(message)
        except Exception:
            pass
        if self.telemetry.get('home_alt_abs') is None and self.telemetry.get('alt_abs'):
            self.telemetry['home_alt_abs'] = float(self.telemetry['alt_abs'])

    def _to_relative_mission_altitude(self, frame: int, altitude: float) -> float:
        relative_frames = {
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
        }
        if frame in relative_frames:
            return altitude

        absolute_frames = {
            mavutil.mavlink.MAV_FRAME_GLOBAL,
            mavutil.mavlink.MAV_FRAME_GLOBAL_INT,
        }
        if frame in absolute_frames:
            home_altitude = self.telemetry.get('home_alt_abs')
            if home_altitude is not None:
                return altitude - float(home_altitude)

        return altitude

    def _log_downloaded_mission_heights(self, mission_items: list[dict]):
        if not mission_items:
            logger.info('mission_download_heights: []')
            return
        rows = []
        for index, waypoint in enumerate(mission_items, start=1):
            source_frame = int(waypoint.get('source_frame', waypoint.get('frame', self.DEFAULT_MISSION_FRAME)))
            rows.append({
                'seq': index,
                'type': waypoint.get('type', 'WAYPOINT'),
                'frame': source_frame,
                'frame_label': self.FRAME_LABELS.get(source_frame, f'FRAME_{source_frame}'),
                'raw_alt': round(float(waypoint.get('source_alt', waypoint.get('alt', 0.0))), 3),
                'loaded_alt': round(float(waypoint.get('alt', 0.0)), 3),
                'home_alt_abs': round(float(self.telemetry.get('home_alt_abs', 0.0) or 0.0), 3),
            })
        logger.info('mission_download_heights: %s', rows)

    def _wait_for_message(self, message_types: set[str], timeout: float, predicate=None):
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = max(0.1, deadline - time.time())
            message = self._recv_match_safe(message_types=message_types, blocking=True, timeout=remaining)
            if message is None:
                continue
            if predicate is None or predicate(message):
                return message
        return None

    def _emit_mission_progress(self, operation: str, current: int, total: int, message: str, active: bool):
        percent = 0
        if total > 0:
            percent = int((max(0, min(current, total)) / total) * 100)
        self.mission_progress.emit({
            'operation': operation,
            'current': current,
            'total': total,
            'percent': percent,
            'message': message,
            'active': active,
        })

    def _mission_session(self):
        class MissionContext:
            def __init__(self, thread):
                self.thread = thread

            def __enter__(self):
                self.thread._mission_guard.acquire()
                self.thread._mission_active = True
                # Drain stale mission messages (e.g. old MISSION_ACK/NACK from a
                # previous failed session) so they cannot corrupt the new session.
                _stale_types = frozenset([
                    'MISSION_ACK', 'MISSION_REQUEST_INT', 'MISSION_REQUEST',
                    'MISSION_COUNT', 'MISSION_ITEM_INT', 'MISSION_ITEM',
                ])
                drained = 0
                for _ in range(80):
                    try:
                        msg = self.thread._recv_match_safe(blocking=False)
                    except ConnectionError:
                        raise
                    except Exception:
                        break
                    if msg is None:
                        break
                    if msg.get_type() in _stale_types:
                        self.thread._log_mission_trace('drain', 'session_start', msg.get_type(), message=msg)
                        logger.debug("mission buffer drain: discarded stale %s", msg.get_type())
                        drained += 1
                if drained:
                    logger.info("mission session: cleared %d stale buffer message(s)", drained)
                time.sleep(0.15)
                return self.thread

            def __exit__(self, exc_type, exc_val, exc_tb):
                self.thread._mission_active = False
                self.thread._mission_guard.release()

        return MissionContext(self)

    def stop_thread(self):
        self.running = False
        self.requestInterruption()
        try:
            self.master.close()
        except Exception:
            pass
        if not self.wait(1500):
            self.terminate()
            self.wait(500)

    def _resolve_mode_id(self, mode_name: str):
        mapping = None
        try:
            mapping = self.master.mode_mapping()
        except Exception:
            mapping = None
        if not isinstance(mapping, dict):
            return None
        wanted = str(mode_name or "").strip().upper()
        for key, value in mapping.items():
            if str(key).upper() == wanted:
                try:
                    return int(value)
                except Exception:
                    return None
        return None

    def set_mode(self, mode_name: str):
        mode_id = self._resolve_mode_id(mode_name)
        if mode_id is None:
            raise ValueError(f"飞控不支持模式: {mode_name}")
        self.master.mav.set_mode_send(
            self.master.target_system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mode_id,
        )

    def arm(self):
        self.master.arducopter_arm()

    def disarm(self):
        self.master.arducopter_disarm()

    def vtol_takeoff(self, height=30):
        target_system, target_component = self._mission_target()
        self.master.mav.command_long_send(
            target_system,
            target_component,
            mavutil.mavlink.MAV_CMD_NAV_VTOL_TAKEOFF,
            0,
            0,
            0,
            0,
            float('nan'),
            0,
            0,
            float(height),
        )

    def qland(self):
        self.set_mode("QLAND")

    def qrtl(self):
        self.set_mode("QRTL")

    def takeoff(self, height=30):
        self.vtol_takeoff(height)

    def land(self):
        self.qland()

    def return_home(self):
        self.qrtl()

    def set_home_position(self, lat: float, lon: float, alt: float = 0.0):
        target_system, target_component = self._mission_target()
        self.master.mav.command_long_send(
            target_system,
            target_component,
            mavutil.mavlink.MAV_CMD_DO_SET_HOME,
            0,
            0,
            0,
            0,
            0,
            float(lat),
            float(lon),
            float(alt),
        )

    def request_home_position(self, timeout: float = 2.0):
        target_system, target_component = self._mission_target()
        self.master.mav.command_long_send(
            target_system,
            target_component,
            mavutil.mavlink.MAV_CMD_GET_HOME_POSITION,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        )
        message = self._wait_for_message({'HOME_POSITION'}, timeout=max(0.5, float(timeout)))
        if message is None:
            return None
        self._update_telemetry(message)
        self.status_updated.emit(self.telemetry.copy())
        if self.telemetry.get('home_lat') is None or self.telemetry.get('home_lon') is None:
            return None
        return {
            'lat': float(self.telemetry.get('home_lat') or 0.0),
            'lon': float(self.telemetry.get('home_lon') or 0.0),
            'alt': float(self.telemetry.get('home_alt_abs') or 0.0),
        }

    def fly_to_waypoint(self, lat: float, lon: float, alt: float):
        target_system, target_component = self._mission_target()
        self.master.mav.command_int_send(
            target_system,
            target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            mavutil.mavlink.MAV_CMD_DO_REPOSITION,
            0,
            0,
            -1,
            0,
            0,
            float('nan'),
            int(round(float(lat) * 1e7)),
            int(round(float(lon) * 1e7)),
            float(alt),
        )

    def reboot_to_bootloader(self):
        """Request autopilot reboot into bootloader mode before firmware flashing."""
        target_system, target_component = self._mission_target()
        self.master.mav.command_long_send(
            target_system,
            target_component,
            mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN,
            0,
            3,  # autopilot: reboot to bootloader
            0,
            0,
            0,
            0,
            0,
            0,
        )

    @staticmethod
    def _decode_param_id(param_id) -> str:
        if isinstance(param_id, bytes):
            return param_id.decode('utf-8', errors='ignore').replace('\x00', '').strip()
        return str(param_id or '').replace('\x00', '').strip()

    def request_all_parameters(self, timeout: float = 12.0) -> dict[str, float]:
        with self._mission_session():
            deadline = time.time() + max(2.0, float(timeout))
            params: dict[str, float] = {}
            expected_count = None
            target_system, target_component = self._mission_target()

            self.master.mav.param_request_list_send(target_system, target_component)
            while time.time() < deadline:
                remaining = max(0.1, deadline - time.time())
                message = self._recv_match_safe(message_types={'PARAM_VALUE'}, blocking=True, timeout=remaining)
                if message is None:
                    continue

                name = self._decode_param_id(getattr(message, 'param_id', ''))
                if not name:
                    continue
                value = float(getattr(message, 'param_value', 0.0) or 0.0)
                params[name] = value

                count_value = getattr(message, 'param_count', None)
                if count_value is not None:
                    expected_count = int(count_value or 0)

                if expected_count is not None and expected_count > 0 and len(params) >= expected_count:
                    break

            return params

    def set_parameter(self, name: str, value: float, timeout: float = 2.0) -> float:
        param_name = str(name or '').strip()
        if not param_name:
            raise ValueError('参数名不能为空')

        target_system, target_component = self._mission_target()
        self.master.mav.param_set_send(
            target_system,
            target_component,
            param_name.encode('utf-8'),
            float(value),
            mavutil.mavlink.MAV_PARAM_TYPE_REAL32,
        )

        deadline = time.time() + max(0.5, float(timeout))
        while time.time() < deadline:
            remaining = max(0.1, deadline - time.time())
            message = self._recv_match_safe(message_types={'PARAM_VALUE'}, blocking=True, timeout=remaining)
            if message is None:
                continue
            msg_name = self._decode_param_id(getattr(message, 'param_id', ''))
            if msg_name != param_name:
                continue
            return float(getattr(message, 'param_value', value) or value)

        raise TimeoutError(f'设置参数超时: {param_name}')

    def set_parameters(self, values: dict[str, float], timeout_per_param: float = 2.0) -> dict[str, float]:
        with self._mission_session():
            applied: dict[str, float] = {}
            for name, value in (values or {}).items():
                applied[str(name)] = self.set_parameter(str(name), float(value), timeout=timeout_per_param)
            return applied

    def export_parameters_to_file(self, file_path: str, parameters: dict[str, float]):
        with open(file_path, 'w', encoding='utf-8') as file_obj:
            json.dump(parameters or {}, file_obj, indent=2, ensure_ascii=False)

    def import_parameters_from_file(self, file_path: str) -> dict[str, float]:
        with open(file_path, 'r', encoding='utf-8') as file_obj:
            data = json.load(file_obj)
        if not isinstance(data, dict):
            return {}
        result = {}
        for key, value in data.items():
            try:
                result[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        return result