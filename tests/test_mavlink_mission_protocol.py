import unittest

from core.mavlink_comms import MavlinkThread


class _FakeMessage:
    def __init__(self, msg_type, **fields):
        self._msg_type = msg_type
        for key, value in fields.items():
            setattr(self, key, value)

    def get_type(self):
        return self._msg_type


class _FakeMav:
    def __init__(self, master):
        self.master = master
        self.request_list_calls = []
        self.request_int_calls = []
        self.request_calls = []
        self.ack_calls = []
        self.command_long_calls = []
        self.param_request_list_calls = []
        self.param_set_calls = []

    def mission_request_list_send(self, target_system, target_component, mission_type=0):
        self.request_list_calls.append((target_system, target_component, mission_type))
        self.master.queue.append(
            _FakeMessage('MISSION_COUNT', count=self.master.mission_count, mission_type=mission_type)
        )

    def mission_request_int_send(self, target_system, target_component, seq, mission_type=0):
        self.request_int_calls.append((target_system, target_component, seq, mission_type))
        if not self.master.legacy_only:
            self.master.queue.append(self.master.make_item(seq, mission_type))

    def mission_request_send(self, target_system, target_component, seq, mission_type=0):
        self.request_calls.append((target_system, target_component, seq, mission_type))
        self.master.queue.append(self.master.make_item(seq, mission_type))

    def mission_ack_send(self, target_system, target_component, ack_type, mission_type=0):
        self.ack_calls.append((target_system, target_component, ack_type, mission_type))

    def command_long_send(self, *args):
        self.command_long_calls.append(args)

    def param_request_list_send(self, target_system, target_component):
        self.param_request_list_calls.append((target_system, target_component))
        total = len(self.master.param_values)
        for index, (name, value) in enumerate(self.master.param_values.items()):
            self.master.queue.append(
                _FakeMessage(
                    'PARAM_VALUE',
                    param_id=name.encode('utf-8'),
                    param_value=value,
                    param_count=total,
                    param_index=index,
                )
            )

    def param_set_send(self, target_system, target_component, param_name, value, param_type):
        self.param_set_calls.append((target_system, target_component, param_name, value, param_type))
        name = param_name.decode('utf-8') if isinstance(param_name, bytes) else str(param_name)
        self.master.queue.append(
            _FakeMessage(
                'PARAM_VALUE',
                param_id=name.encode('utf-8'),
                param_value=float(value),
                param_count=max(1, len(self.master.param_values)),
                param_index=0,
            )
        )


class _FakeMaster:
    def __init__(self, *, mission_count=1, legacy_only=True, target_component=0, param_values=None):
        self.target_system = 1
        self.target_component = target_component
        self.flightmode = 'AUTO'
        self.mission_count = mission_count
        self.legacy_only = legacy_only
        self.param_values = dict(param_values or {"WPNAV_SPEED": 500.0, "RTL_ALT": 1500.0})
        self.queue = []
        self.mav = _FakeMav(self)

    def recv_match(self, type=None, blocking=True, timeout=None):
        if type is None:
            allowed = None
        elif isinstance(type, (list, tuple, set, frozenset)):
            allowed = set(type)
        else:
            allowed = {type}

        for index, message in enumerate(self.queue):
            if allowed is None or message.get_type() in allowed:
                return self.queue.pop(index)
        return None

    @staticmethod
    def make_item(seq, mission_type=0):
        return _FakeMessage(
            'MISSION_ITEM',
            seq=seq,
            mission_type=mission_type,
            frame=3,
            command=16,
            current=0,
            autocontinue=1,
            x=24.2 + seq * 0.001,
            y=54.7 + seq * 0.001,
            z=50.0 + seq,
            param1=0.0,
            param2=0.0,
            param3=0.0,
            param4=0.0,
        )


class MavlinkMissionProtocolTests(unittest.TestCase):
    def test_download_mission_falls_back_to_legacy_request_when_int_times_out(self):
        master = _FakeMaster(mission_count=2, legacy_only=True)
        thread = MavlinkThread(master)
        thread.telemetry['home_alt_abs'] = 0.0  # skip home query delay in tests

        items = thread.download_mission()

        self.assertEqual(len(items), 2)
        self.assertGreaterEqual(len(master.mav.request_int_calls), 1)
        self.assertGreaterEqual(len(master.mav.request_calls), 1)
        self.assertEqual([item['seq'] for item in items], [0, 1])

    def test_mission_target_prefers_last_heartbeat_component(self):
        master = _FakeMaster(target_component=0)
        thread = MavlinkThread(master)
        thread._last_heartbeat_component = 1

        target_system, target_component = thread._mission_target()

        self.assertEqual(target_system, 1)
        self.assertEqual(target_component, 1)

    def test_request_all_parameters_uses_resolved_target_component(self):
        master = _FakeMaster(target_component=0, param_values={"WPNAV_SPEED": 800.0, "RTL_ALT": 1200.0})
        thread = MavlinkThread(master)
        thread._last_heartbeat_component = 1

        params = thread.request_all_parameters(timeout=1.0)

        self.assertEqual(master.mav.param_request_list_calls, [(1, 1)])
        self.assertEqual(params["WPNAV_SPEED"], 800.0)
        self.assertEqual(params["RTL_ALT"], 1200.0)


if __name__ == '__main__':
    unittest.main()
