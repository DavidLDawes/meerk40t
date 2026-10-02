import unittest

state = 0


class TestRuida(unittest.TestCase):
    def test_magic_keys(self):
        from meerk40t.ruida.rdjob import magic_keys

        keys = magic_keys()
        self.assertEqual(keys[b"\xd4\x89\r\xf7"], 0x88)
        self.assertEqual(keys[b"\xd9\x84\x08\xfe"], 0x83)
        self.assertEqual(keys[b"i4\xb8N"], 0x33)
        self.assertEqual(keys[b"I\x14\x98n"], 0x13)
        self.assertEqual(keys[b"z#\xa7]"], 0x22)
        self.assertEqual(keys[b"K\x12\x96p"], 0x11)
        self.assertEqual(keys[b"-x\xf4\n"], 0x77)
        self.assertEqual(keys[b"\xb6\xefk\x91"], 0xEE)


class TestRuidaSession(unittest.TestCase):
    """Smoke tests for the session handshake using a fake transport."""

    def setUp(self):
        self.session = None

    def tearDown(self):
        if self.session is not None:
            self.session.shutdown()

    def test_send_one_packet_acked(self):
        import struct

        from test.ruida_helpers import make_session, wait_for

        self.session, transport, _ = make_session()
        transport.script(b"\xcc")
        self.session.write(b"\x01\x02\x03")
        self.assertTrue(wait_for(lambda: self.session.acks == 1))
        self.assertEqual(self.session.sends, 1)
        self.assertEqual(self.session.naks, 0)
        # UDP packet is a 2-byte checksum followed by the (identity) data.
        self.assertEqual(
            transport.writes, [struct.pack(">H", 0x01 + 0x02 + 0x03) + b"\x01\x02\x03"]
        )
        self.assertTrue(self.session._responding)


class TestRuidaDivideData(unittest.TestCase):
    """RuidaController.divide_data_into_queue splits jobs into packets."""

    def make_controller(self, commands):
        from meerk40t.ruida.controller import RuidaController
        from test.ruida_helpers import Recorder

        # Skip __init__: it starts a status thread which polls the service.
        controller = RuidaController.__new__(RuidaController)
        controller.job = type("Job", (), {})()
        controller.job.buffer = list(commands)
        controller.job.get_contents = lambda first=None, last=None: b"".join(
            controller.job.buffer[first:last]
        )
        controller.events = Recorder()
        controller._send_queue = []
        return controller

    def test_chunks_within_limit(self):
        from meerk40t.ruida.controller import MAX_PACKET_DATA

        # 7 byte commands do not divide 998 evenly, so splits land mid-stream.
        commands = [bytes([i % 256]) * 7 for i in range(1000)]
        controller = self.make_controller(commands)
        controller.divide_data_into_queue()
        self.assertGreater(len(controller._send_queue), 1)
        for chunk in controller._send_queue:
            self.assertLessEqual(len(chunk), MAX_PACKET_DATA)

    def test_chunks_rejoin_to_original(self):
        commands = [bytes([i % 256]) * (1 + i % 40) for i in range(500)]
        controller = self.make_controller(commands)
        controller.divide_data_into_queue()
        self.assertEqual(b"".join(controller._send_queue), b"".join(commands))

    def test_command_boundaries_kept(self):
        commands = [bytes([i % 256]) * (1 + i % 40) for i in range(500)]
        controller = self.make_controller(commands)
        controller.divide_data_into_queue()
        boundaries = set()
        position = 0
        for command in commands:
            boundaries.add(position)
            position += len(command)
        boundaries.add(position)
        position = 0
        for chunk in controller._send_queue:
            self.assertIn(position, boundaries)
            position += len(chunk)
        self.assertEqual(position, sum(len(c) for c in commands))

    def test_oversized_command_sent_alone(self):
        from meerk40t.ruida.controller import MAX_PACKET_DATA

        big = b"\xAB" * (MAX_PACKET_DATA + 50)
        commands = [b"\x01" * 10, b"\x02" * 10, big, b"\x03" * 10]
        controller = self.make_controller(commands)
        controller.divide_data_into_queue()
        self.assertEqual(
            controller._send_queue, [b"\x01" * 10 + b"\x02" * 10, big, b"\x03" * 10]
        )
        self.assertEqual(len(controller.events.calls), 1)
        self.assertIn("WARNING", controller.events.calls[0][0])

    def test_empty_buffer_queues_nothing(self):
        controller = self.make_controller([])
        controller.divide_data_into_queue()
        self.assertEqual(controller._send_queue, [])

    def test_exact_fit_is_one_chunk(self):
        from meerk40t.ruida.controller import MAX_PACKET_DATA

        commands = [b"\x01" * (MAX_PACKET_DATA // 2)] * 2
        controller = self.make_controller(commands)
        controller.divide_data_into_queue()
        self.assertEqual(len(controller._send_queue), 1)
