# CLAUDE.md

@AGENTS.md

`AGENTS.md` (imported above) is upstream's main guide covering architecture, plugins, commands and conventions. This file adds notes specific to this fork.

## Purpose of this fork

This is DavidLDawes' fork of meerk40t/meerk40t. Work here focuses on the
**Ruida driver** (`meerk40t/ruida/`), fixing the issues listed in `PLAN.md`.
Read `PLAN.md` before starting work and tick off items as they are completed.

Keep changes small and self-contained so each fix can go upstream as its own
pull request. Don't reformat or refactor code you aren't changing.

## Ruida module map

| File | Role |
|------|------|
| `ruidasession.py` | Handshake thread: send, wait for ACK/NAK, wait for reply, retries and timeouts |
| `udp_transport.py`, `usb_transport.py`, `ruidatransport.py` | Raw I/O. UDP sends to port 50200 and listens on 40200. USB gets no ACKs |
| `controller.py` | Splits jobs into packets, polls status, switches timeouts |
| `driver.py` | Turns MeerK40t cutcode into Ruida commands; handles jog, home, pause, etc. |
| `rdjob.py` | Command encode/decode, swizzle tables, .rd parsing |
| `emulator.py`, `control.py` | Pretend to be a Ruida (for LightBurn/RDWorks) and man-in-the-middle mode |
| `README.md` | Note that the sections from "Overview" onwards are partly stale (see PLAN.md) |

## Protocol facts relied on

- UDP packet = 2-byte big-endian checksum (sum of swizzled bytes & 0xFFFF) + swizzled data.
- A one-byte reply is a status code: ACK, NAK (resend) or ENQ. Longer replies are data.
- USB/serial sends no checksum and gets no ACKs.
- The packet-size limit is not documented by Ruida. LibLaserCut uses 998 data
  bytes. Treat anything above that as unverified.

## Rules

- **Never send anything to a real laser controller** (no UDP to a real IP, no
  opening serial ports) unless the user explicitly asks in that session. A laser
  is a fire and eye hazard. Use fake transports in tests.
- Stay compatible with **Python 3.6** as AGENTS.md says: no walrus operator, no
  `match`, no 3.8+-only stdlib features.
- Every bug fix gets a unit test in `test/` that fails before the fix and passes
  after. `RuidaSession` starts a thread in `__init__`, so tests should give it a
  minimal fake service and a fake transport with scripted replies, and wait on
  conditions with timeouts rather than fixed sleeps.
- Before finishing, run `python -m unittest discover test -v` (this is what CI
  runs) and the formatting and lint checks listed in AGENTS.md.
- Only one hardware setup has ever been tested (RDC6442S, Linux). Don't claim
  that a change works on other controllers or on Windows.
