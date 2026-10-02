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
