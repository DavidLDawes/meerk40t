# PLAN.md: Ruida driver fixes

Issues come from a code review of upstream commit `d511944` (25 September 2026).
Line numbers refer to that commit. Do the items in order. Each one is its own
branch and its own upstream pull request.

Status key: [ ] to do, [~] in progress, [x] done

---

## 0. [x] Test scaffolding

There is currently only one Ruida test (`test/test_ruida.py`, which checks the
magic-key table). Fixes 1 and 2 need test helpers first.

- Add test helpers (in `test/test_ruida.py` or a helper module beside it):
  - `FakeService`: has `interface`, `safe_label`, `address`, `set_timeout`,
    `signal`, and `channel()` returning a recorder callable.
  - `FakeTransport(RuidaTransport)`: records `write()` calls; `read()` pops the
    next scripted reply or raises `TransportTimeout`.
  - Identity `swizzle`/`unswizzle` functions so the bytes are easy to read.
- Make sure tests never touch real sockets or serial ports, and that every test
  shuts down the session thread.

**Done when:** a smoke test can send one packet through `RuidaSession` with a
scripted ACK and check `acks == 1`.

---

## 1. [x] Packets can exceed the size limit (`controller.py:83`, `divide_data_into_queue`)

**Bug:** after a split, `total` is reset to `0` rather than to the length of the
command that started the new chunk. That command's bytes are never counted, so
a chunk can be up to 1000 bytes plus one command. Each chunk then also gets a
2-byte checksum.

**Fix:**
- Add a module constant, `MAX_PACKET_DATA = 998`, to match LibLaserCut. This
  value is conservative: Ruida's real limit is unknown, so add a comment saying
  that.
- Rewrite the loop so a chunk is flushed *before* adding a command that would
  push it over the limit. Never split a single command across packets.
- If one command on its own is bigger than the limit, send it alone and log a
  warning through `self.events`.
- Remove the `if last != len(data)` tail check (it is always true) and avoid
  queueing an empty final chunk.

**Tests:**
- No chunk is longer than `MAX_PACKET_DATA` for a buffer of many small commands.
- Joining all the chunks gives back the original buffer exactly.
- Command boundaries are kept.
- A single command over the limit is sent alone.
- An empty buffer queues nothing.

---

## 2. [x] A NAK can cause an endless resend loop (`ruidasession.py:377`)

**Bug:** in the ACK_PENDING loop, a NAK resends the packet without counting the
attempt. Only timeouts count against `_tries`, so a controller that keeps
sending NAK (for example, after a checksum mismatch it keeps reproducing) traps
the handshake thread forever.

**Fix:**
- Add `self._max_nak_resends = 3` (adjustable).
- Count NAK resends per packet. When the limit is passed, treat it like a comms
  failure: set `_responding = False`, clear `_ack_pending` and `_reply_pending`,
  call `self.events('Too many NAKs; packet dropped.')`, and break.
- Keep the existing `self.naks` statistics counter as it is.

**Tests:**
- One NAK followed by an ACK: the packet is written twice, `acks == 1`, and
  `_responding` stays True.
- Endless NAKs: there are exactly 1 + `_max_nak_resends` writes, then the
  thread moves on and `_responding` is False.
- The next queued packet is still sent after a failure.

---

## 3. [x] Check the short normal timeout (investigate before changing anything)

**Concern:** the normal timeout is 0.25 s per try with 4 tries (about 1 s in
total). Only `physical_home()` (`driver.py:398`) switches to the 40 s "gross"
timeout. Other long silences from the controller, such as a long Z move, the
controller processing a large upload, or the controller's own keypad homing,
might be treated as a comms failure. **This hasn't been confirmed; it's only an
inference from reading the code.**

**Steps:**
- Search the issue tracker and the git history for "not responding" or timeout
  reports on Ruida.
- If a laser is available and the user agrees: log `sends`, `acks`, `naks` and
  timeouts during a long job and during a keypad home.
- Only change the code if there's evidence. The likely fix would be to use the
  gross timeout around other known long operations, not to raise the global
  timeout.

**Done when:** the findings are written here, and either a fix with tests
exists or this item is closed as "not a problem".

### Findings (2 October 2026)

Closed as "no evidence, no change". Hardware measurements were not taken (no
laser was connected, and none may be used without the user's say-so).

- **Issue tracker** (`meerk40t/meerk40t`, all states, searched "ruida",
  "ruida timeout", "ruida not responding", "ruida disconnect", "ruida home"):
  no report of the controller being wrongly declared unresponsive. The only
  nearby one is #3272 ("job completed ... communication error"), but it was
  filed against 0.9.4040, which predates the new session/handshake code, so it
  says nothing about this timeout.
- **Git history** (`meerk40t/ruida`): the short normal timeout and the gross
  timeout were introduced together in 311fcbfb5 / dfb834e62 (2-3 November 2025,
  PR #3085/#3090) to survive `physical_home()`, where the commit message says the
  controller "goes completely silent". PR #3090 describes the design and says
  power-cycling and cable-pull recovery were tested; it reports no long-silence
  cases beyond homing.
- **Code reading** (inference only): the session only waits on the timeout while
  an ACK or reply is pending. Silence from a keypad home (or any other long
  silent operation) would make the poll time out after about 1 s,
  set `_responding` False and send the session into `connect()`, which retries an
  ENQ every second and sends nothing else until the controller answers. So the
  likely effect is a temporary "Connecting" status, not lost data. Not verified.
- **Reopen if** a user reports spurious "Connecting"/"not responding" during a
  long Z move, a large upload, or a keypad home. The fix would then be to wrap
  those operations in `gross_timeout()` / `normal_timeout()`, as
  `physical_home()` does, with tests. Hardware logging of `sends`, `acks`,
  `naks` and timeouts during a keypad home would settle it.

---

## 4. [ ] Correct the out-of-date README (`meerk40t/ruida/README.md`)

**Problem:** the opening note correctly says direct control has been tested on
an RDC6442S. But "Overview", "Limitations" (lines 291 onwards) and "Known
Issues" say "Emulation Only" and "Direct hardware control not implemented",
which the code contradicts. Some claims are also unverified, such as "Full
compatibility" with RDWorks and support for the Ruida Android app.

**Fix:**
- Describe the module as it actually is: direct UDP/USB control (job sending,
  jog, home, pause/resume/abort, status polling), plus the emulator and the .rd
  loader.
- Keep the "tested only on RDC6442S + Monport MP-570, Linux" warning and the
  Flip X and overscan-0 requirements.
- Label unverified compatibility claims as untested rather than deleting them.
- Add the 998-byte packet limit and the NAK limit to "Protocol Details" once
  items 1 and 2 are merged.

---

## Upstreaming

- Open one pull request per item against `meerk40t/meerk40t` `main`. Each pull
  request should describe the bug, the fix and the tests, and state that it has
  not been tested on hardware unless it has.
- Run `python -m unittest discover test -v` and the AGENTS.md lint and format
  checks before every push.
- Rebase on upstream before opening a pull request, because the Ruida code
  changes often (about 100 commits since January 2025).
