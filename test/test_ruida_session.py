import struct
import unittest

from test.ruida_helpers import make_session, wait_for

ACK = b"\xcc"
NAK = b"\xcf"


def udp_packet(data):
    """What RuidaSession sends for data with the identity swizzle."""
    return struct.pack(">H", sum(data) & 0xFFFF) + data


class TestRuidaSessionNak(unittest.TestCase):
    def setUp(self):
        self.session = None

    def tearDown(self):
        if self.session is not None:
            self.session.shutdown()

    def test_nak_then_ack_resends_once(self):
        self.session, transport, _ = make_session()
        packet = udp_packet(b"\x01\x02")
        transport.script(NAK, ACK)
        self.session.write(b"\x01\x02")
        self.assertTrue(wait_for(lambda: self.session.acks == 1))
        self.assertEqual(transport.writes, [packet, packet])
        self.assertEqual(self.session.naks, 1)
        self.assertTrue(self.session._responding)

    def test_endless_naks_give_up(self):
        self.session, transport, service = make_session()
        packet = udp_packet(b"\x01\x02")
        limit = self.session._max_nak_resends
        transport.script(*[NAK] * (limit + 1))
        self.session.write(b"\x01\x02")
        events = service.channels["fake_ruida/events"]
        self.assertTrue(
            wait_for(lambda: "Too many NAKs; packet dropped." in events.messages())
        )
        self.assertFalse(self.session._responding)
        self.assertFalse(self.session._reply_pending)
        self.assertEqual(transport.writes.count(packet), 1 + limit)
        self.assertEqual(self.session.naks, limit + 1)
        self.assertEqual(self.session.acks, 0)

    def test_next_packet_sent_after_failure(self):
        self.session, transport, _ = make_session()
        limit = self.session._max_nak_resends
        first = udp_packet(b"\x01\x02")
        second = udp_packet(b"\x03\x04")
        # NAKs for the first packet, then ACKs for the reconnect ENQ (read by
        # connect(), so not counted in acks), the second packet and the ENQ
        # which primes the pump after reconnecting.
        transport.script(*[NAK] * (limit + 1), ACK, ACK, ACK)
        # Queue both directly: write() refuses once comms has failed.
        self.session.send_q.put(b"\x01\x02")
        self.session.send_q.put(b"\x03\x04")
        self.assertTrue(wait_for(lambda: second in transport.writes))
        self.assertEqual(transport.writes.count(first), 1 + limit)
        self.assertTrue(wait_for(lambda: self.session.acks == 2))
        self.assertTrue(self.session._responding)


if __name__ == "__main__":
    unittest.main()
