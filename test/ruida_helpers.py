"""
Test helpers for the Ruida driver.

These let tests drive RuidaSession with a fake service and a fake transport so
nothing ever touches a real socket or serial port.
"""

import threading
import time

from meerk40t.ruida.rdjob import ACK
from meerk40t.ruida.ruidasession import RuidaSession
from meerk40t.ruida.ruidatransport import RuidaTransport, TransportTimeout


class Recorder:
    """Callable that records everything it is called with."""

    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append(args)

    def messages(self):
        return [call[0] if len(call) == 1 else call for call in self.calls]


class FakeService:
    """The minimum of a RuidaDevice that RuidaSession and the transports use."""

    def __init__(self, interface="udp"):
        self.interface = interface
        self.name = "fake-ruida"
        self.safe_label = "fake_ruida"
        self.address = "127.0.0.1"
        self.timeout_values = []
        self.signals = []
        self.channels = {}

    def set_timeout(self, seconds):
        self.timeout_values.append(seconds)

    def signal(self, *args, **kwargs):
        self.signals.append(args)

    def channel(self, name, *args, **kwargs):
        if name not in self.channels:
            self.channels[name] = Recorder()
        return self.channels[name]


class FakeTransport(RuidaTransport):
    """Transport which records writes and answers reads from a script.

    Each item in the script is returned by one read(). When the script is empty
    read() waits briefly and then raises TransportTimeout, like a silent
    controller would.
    """

    def __init__(self, service, replies=(), read_wait=0.01):
        super().__init__(service)
        self.writes = []
        self.read_wait = read_wait
        self._replies = list(replies)
        self._lock = threading.Lock()
        self._open = False

    def script(self, *replies):
        """Queue more replies for upcoming reads."""
        with self._lock:
            self._replies.extend(replies)

    def open(self):
        self._open = True

    def close(self):
        self._open = False

    def read(self, n):
        with self._lock:
            if self._replies:
                return self._replies.pop(0)
        time.sleep(self.read_wait)
        raise TransportTimeout()

    def write(self, data):
        with self._lock:
            self.writes.append(bytes(data))

    def purge(self):
        return b""

    def location(self):
        return "fake"

    @property
    def is_open(self):
        return self._open

    @property
    def connected(self):
        return self._open


def identity(data):
    """Swizzle/unswizzle stand-in so test bytes stay readable."""
    return bytes(data)


def wait_for(condition, timeout=5.0, interval=0.005):
    """Poll condition() until it is true or the timeout expires."""
    end = time.time() + timeout
    while time.time() < end:
        if condition():
            return True
        time.sleep(interval)
    return bool(condition())


def make_session(interface="udp", replies=()):
    """Build a connected RuidaSession wired to a FakeTransport.

    The connect handshake consumes one scripted ACK for the initial ENQ and
    another for the ENQ the session queues to prime the pump. Both are supplied
    here, and the statistics and recorded writes are cleared afterwards so a
    test starts from zero. Any `replies` are queued after the handshake.

    Callers must call session.shutdown() (see RuidaSessionTestCase).
    """
    service = FakeService(interface)
    transport = FakeTransport(service, replies=[ACK, ACK])
    session = RuidaSession(service)
    session.transport = transport
    session.set_swizzles(identity, identity)
    if not wait_for(lambda: session.acks == 1 and not session.is_busy):
        session.shutdown()
        raise RuntimeError("Fake Ruida session failed to complete the handshake.")
    session.sends = session.acks = session.naks = 0
    session.replies = session.enqs = session.dropped_packets = 0
    transport.writes.clear()
    transport.script(*replies)
    return session, transport, service
