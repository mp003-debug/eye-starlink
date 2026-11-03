"""Bounded bring-up for the project's fixed VDMA topology.

Static or parked triple-buffer RGB565 display and frame-bounded GRAY8 captures. Each DMA
write halts before CPU ownership; this is transport, not a gaze driver. DMA buffers are never freed until BOTH channels halt.
Register meanings: AMD PG020; cache ownership: PYNQ allocate documentation.
"""
import math
import time
import numpy as np
from .framebuffer import CAPTURE, DISPLAY

MM2S, S2MM = 0x00, 0x30
REGIONS = {MM2S: 0x50, S2MM: 0xA0}
RUN, RESET, HALTED, FRAME_DONE = 1, 4, 1, 0x1000
ERRORS = 0xC9F0  # bus, SOF/EOL size errors, and error IRQ; excludes normal frame IRQ


class HardwareFault(RuntimeError):
    pass


class UnsafeShutdown(HardwareFault):
    """Caller MUST retain this session and its buffers until hardware recovery."""


class VideoIO:
    def __init__(self, vdma, gpio, diag, allocate, timeout=1.0,
                 now=time.monotonic, sleep=time.sleep):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("positive finite timeout required")
        self.vdma, self.gpio, self.diag = vdma, gpio, diag
        self.allocate, self.timeout = allocate, timeout
        self.now, self.sleep = now, sleep
        self.buffers = {}
        self.prepared = False
        self.closed = False
        self.control = 0
        self.capture_faulted = False
        self.capture_index = 0
        self.last_capture = None
        self.display_started = False
        self.display_slots = []
        self.display_slot = 0
        self.display_faulted = False
        self.present_count = 0
        self.reset_recovery_used = False

    def _wait(self, poll, description):
        deadline = self.now() + self.timeout
        while True:
            result = poll()
            if result:
                return result
            if self.now() >= deadline:
                raise HardwareFault("timeout: " + description)
            self.sleep(0.001)

    def _halted(self, channel):
        return (bool(self.vdma.read(channel + 4) & HALTED)
                and not (self.vdma.read(channel) & (RUN | RESET)))

    def _both_halted(self):
        # Read both even if the first is not yet halted.
        states = [self._halted(ch) for ch in (MM2S, S2MM)]
        return all(states)

    def prepare(self):
        if self.prepared or self.closed:
            raise HardwareFault("session cannot be prepared twice")
        if not self._both_halted():
            raise HardwareFault("VDMA already active; do not take ownership from another process")
        if self.diag.read(0) != 0x45594531 or self.diag.read(4) != 0x00010003:
            raise HardwareFault("unexpected diagnostic hardware identity/version")
        self.prepared = True
        self.gpio.write(0, 0)
        if self.gpio.read(8) & 7:
            raise HardwareFault("latched PL fault; reload overlay after verifying DMA is stopped")

    def _ready(self):
        if not self.prepared or self.closed:
            raise HardwareFault("session is not prepared or is closed")

    def _gate(self, bits):
        self.gpio.write(0, bits)
        self.control = bits

    def _reset(self, channel):
        self.vdma.write(channel, RESET)
        self._wait(lambda: not (self.vdma.read(channel) & RESET), "VDMA reset")
        self._wait(lambda: self._halted(channel), "halt after reset")
        if self.vdma.read(channel + 4) & (ERRORS | FRAME_DONE):
            raise HardwareFault("VDMA reset left stale errors or completion status")

    def _buffer(self, channel, layout):
        buffer = self.allocate(shape=(layout.size_bytes,), dtype=np.uint8)
        # Retain immediately, including on validation/flush/programming failures.
        self.buffers[channel] = buffer
        address = int(buffer.device_address)
        if (buffer.nbytes != layout.size_bytes or buffer.dtype != np.uint8
                or not buffer.flags.c_contiguous):
            raise HardwareFault("allocator returned wrong buffer geometry")
        if address < 0 or address % 8 or address + buffer.nbytes > 0x20000000:
            raise HardwareFault("DMA address outside aligned HP0 DDR aperture")
        for other_channel, other in self.buffers.items():
            if other_channel == channel:
                continue
            other_address = int(other.device_address)
            if address < other_address + other.nbytes and other_address < address + buffer.nbytes:
                raise HardwareFault("capture/display physical buffers overlap")
        return buffer

    def _program(self, channel, layout, buffer, one_frame, slots=None):
        # PG020: RUN -> addresses -> stride -> HSIZE -> VSIZE LAST (kick).
        # Park on frame 0; static/capture slots share a buffer, dynamic slots do not.
        # Genlock is disabled because camera and UI have different buffers/rates.
        park_mask = 0x1F if channel == MM2S else 0x1F00
        park = self.vdma.read(0x28) & 0x1F1F
        self.vdma.write(0x28, park & ~park_mask)
        self.vdma.write(channel + 0x14, 0)
        self.vdma.write(channel, 0x10001 | (0x10 if one_frame else 0))
        region = REGIONS[channel]
        for slot in range(3):
            self.vdma.write(region + 0x0C + 4 * slot, int((slots[slot] if slots else buffer).device_address))
        self.vdma.write(region + 8, layout.stride_bytes)
        self.vdma.write(region + 4, layout.hsize_bytes)
        self.vdma.write(region, layout.height)

    def display_static(self, frame):
        self._start_display(frame, dynamic=False)

    def display_dynamic(self, frame):
        self._start_display(frame, dynamic=True)

    def _start_display(self, frame, dynamic):
        self._ready()
        if MM2S in self.buffers:
            raise HardwareFault("display already allocated; a new session is required")
        if not isinstance(frame, (bytes, bytearray)) or len(frame) != DISPLAY.size_bytes:
            raise ValueError("expected exactly 614400 bytes of RGB565 little-endian data")
        self._reset(MM2S)
        buffer = self._buffer(MM2S, DISPLAY)
        buffer[:] = np.frombuffer(frame, dtype=np.uint8)
        buffer.flush()
        if dynamic:
            self.display_slots = [buffer]
            for slot in (1, 2):
                other = self._buffer((MM2S, slot), DISPLAY)
                self.display_slots.append(other)
                other[:] = np.frombuffer(frame, dtype=np.uint8)
                other.flush()
        self._program(MM2S, DISPLAY, buffer, one_frame=False, slots=self.display_slots)
        # HALTED may take several AXI cycles to deassert after RUN/VSIZE.
        # Keep the sink disabled until the DMA has accepted the start.
        def running():
            sr = self.vdma.read(MM2S + 4)
            if sr & ERRORS:
                raise HardwareFault("display VDMA fault during startup: 0x%08x" % sr)
            return not (sr & HALTED) and bool(self.vdma.read(MM2S) & RUN)
        self._wait(running, "display DMA starting")
        self.display_started = True
        self._gate(self.control | 2)
        self._wait(lambda: bool(self.display_health() & 8), "display stream lock")

    def present(self, frame):
        """Synchronous park switch. Never overwrite the current DMA read buffer.

        PG020 PARK_PTR_REG: requested read slot bits 4:0, CURRENT slot 20:16.
        Flush a spare before requesting it; wait for the hardware current slot,
        not just register writeback. Three-way rotation leaves a guard slot.
        A timeout poisons the session: ownership is then uncertain until stop.
        Single caller only, like capture_once().
        """
        self._ready()
        if not self.display_started or len(self.display_slots) != 3:
            raise HardwareFault("dynamic display is not started")
        if self.display_faulted:
            raise HardwareFault("previous display switch failed; close and reload overlay")
        if not isinstance(frame, (bytes, bytearray)) or len(frame) != DISPLAY.size_bytes:
            raise ValueError("expected exactly 614400 bytes of RGB565 little-endian data")
        self.display_faulted = True
        self.display_health()
        park = self.vdma.read(0x28)
        if (park & 0x1F) != self.display_slot or ((park >> 16) & 0x1F) != self.display_slot:
            raise HardwareFault("display ownership changed outside this session")
        next_slot = (self.display_slot + 1) % 3
        buffer = self.display_slots[next_slot]
        buffer[:] = np.frombuffer(frame, dtype=np.uint8)
        buffer.flush()
        self.vdma.write(0x28, (park & 0x1F00) | next_slot)
        def switched():
            self.display_health()
            value = self.vdma.read(0x28)
            if (value & 0x1F) != next_slot:
                raise HardwareFault("display park request changed outside this session")
            return ((value >> 16) & 0x1F) == next_slot
        self._wait(switched, "display hardware frame switch")
        self.display_slot = next_slot
        self.present_count += 1
        self.display_faulted = False
        return next_slot

    def display_health(self):
        self._ready()
        sr = self.vdma.read(MM2S + 4)
        status = self.gpio.read(8)
        if sr & ERRORS or status & 6:
            raise HardwareFault("display fault: VDMA=0x%08x PL=0x%x" % (sr, status))
        if self.display_started and (sr & HALTED or not self.vdma.read(MM2S) & RUN):
            raise HardwareFault("display channel halted unexpectedly")
        return status

    def snapshot(self):
        self._ready()
        if self.diag.read(0x0C) & 1:
            raise HardwareFault("diagnostic mailbox is busy; another requester may own it")
        previous = self.diag.read(0x10)
        self.diag.write(0x08, 1)
        def fresh():
            flags = self.diag.read(0x0C)
            sequence = self.diag.read(0x10)
            return flags & 2 and not flags & 1 and sequence != previous
        self._wait(fresh, "fresh camera diagnostic mailbox (camera clock required)")
        packed = self.diag.read(0x20)
        return {
            "sequence": self.diag.read(0x10), "frame_count": self.diag.read(0x14),
            "frame_period_ticks": self.diag.read(0x18), "frame_pixels": self.diag.read(0x1C),
            "frame_lines": packed >> 16, "line_pixels": packed & 0xFFFF,
            "bad_lines": self.diag.read(0x24), "bad_frames": self.diag.read(0x28),
            "camera_ticks": self.diag.read(0x2C),
            "declared_pclk_hz_not_measured": self.diag.read(0x30),
        }

    def wait_native_frames(self, count=2):
        """Observe complete 752x480 sensor frames, independently of crop DMA.

        The crop ends before FV falls. Waiting AFTER capture for another native
        frame prevents accepting stale geometry/error counters for that capture.
        Startup partial-frame errors are allowed to settle before the baseline;
        callers compare error counters across the subsequent capture interval.
        """
        if type(count) is not int or not 1 <= count <= 10:
            raise ValueError("native frame count must be an integer from 1 to 10")
        initial = self.snapshot()
        def progressed():
            current = self.snapshot()
            delta = (current["frame_count"] - initial["frame_count"]) & 0xFFFFFFFF
            if self.display_started:
                self.display_health()
            if not count <= delta < 0x80000000:
                return False
            if (current["frame_pixels"] != 752 * 480
                    or current["frame_lines"] != 480 or current["line_pixels"] != 752
                    or current["frame_period_ticks"] == 0):
                raise HardwareFault("native camera geometry/period invalid: %s" % current)
            return current
        return self._wait(progressed, "complete native camera frames")

    def capture_once(self):
        """Request one new complete frame; repeat without reloading the overlay.

        PL accepts exactly one SOF..EOF window. The buffer is copied only after
        fresh DMA completion + halt + PL rearm acknowledgement + native geometry
        verification. Calls are serial; any failed request poisons this session.
        """
        self._ready()
        if self.capture_faulted:
            raise HardwareFault("previous capture failed; close and reload overlay")
        self.capture_faulted = True
        if not self._halted(S2MM):
            raise HardwareFault("capture channel is still active; buffer cannot be reused")
        def rearm():
            status = self.gpio.read(8)
            if status & 1:
                raise HardwareFault("capture FIFO/frame fault latched")
            if self.display_started:
                self.display_health()
            return bool(status & 16)
        self._gate(self.control & ~1)
        self._wait(rearm, "empty capture queue and low-request acknowledgement")
        before = self.snapshot()
        self._reset(S2MM)  # clears old completion event before every request
        if S2MM not in self.buffers:
            buffer = self._buffer(S2MM, CAPTURE)
            buffer.fill(0xA5)
            buffer.flush()  # no dirty CPU lines may survive into a DMA write
        else:
            buffer = self.buffers[S2MM]
        self._program(S2MM, CAPTURE, buffer, one_frame=True)
        requested_at = self.now()
        self._gate(self.control | 1)
        # Observe high request in the camera domain; prevents reusing an old
        # ready level when the request is lowered again later.
        self._wait(lambda: not (self.gpio.read(8) & 16), "capture request acknowledgement")
        def completed():
            sr = self.vdma.read(S2MM + 4)
            if sr & ERRORS:
                raise HardwareFault("capture VDMA fault: 0x%08x" % sr)
            if self.gpio.read(8) & 1:
                raise HardwareFault("capture FIFO/frame fault")
            if self.display_started:
                self.display_health()
            return bool(sr & FRAME_DONE) and self._halted(S2MM)
        self._wait(completed, "one complete captured frame and automatic halt")
        dma_completed_at = self.now()
        self._gate(self.control & ~1)
        self._wait(rearm, "capture queue drain before CPU ownership")
        # The crop ends before native FV falls. Wait for the final line/error
        # counters to be committed before accepting this image.
        after = self.wait_native_frames(1)
        if any(after[k] != before[k] for k in ("bad_lines", "bad_frames")):
            raise HardwareFault("camera link error counters increased during capture")
        buffer.invalidate()
        pixels = np.array(buffer, copy=True).reshape(CAPTURE.height, CAPTURE.stride_bytes)[:, :CAPTURE.width]
        self.capture_index += 1
        self.last_capture = {"index": self.capture_index,
                             "requested_at_monotonic": requested_at,
                             "dma_completed_at_monotonic": dma_completed_at,
                             "copied_at_monotonic": self.now(),
                             "diagnostic_after": after}
        self.capture_faulted = False
        return pixels

    def registers(self):
        return {"mm2s_cr": self.vdma.read(0), "mm2s_sr": self.vdma.read(4),
                "s2mm_cr": self.vdma.read(0x30), "s2mm_sr": self.vdma.read(0x34),
                "pl_status": self.gpio.read(8), "control": self.control}

    def close(self):
        if self.closed:
            return
        if not self.prepared:
            self.closed = True
            return
        try:
            # Keep producers/consumers alive while current transfers drain.
            for channel in (MM2S, S2MM):
                self.vdma.write(channel, self.vdma.read(channel) & ~RUN)
            try:
                self._wait(self._both_halted, "both DMA channels stopping")
            except HardwareFault:
                self.reset_recovery_used = True
                for channel in (MM2S, S2MM):
                    if not self._halted(channel):
                        self.vdma.write(channel, RESET)
                self._wait(self._both_halted, "both DMA channels reset and halted")
            self._gate(0)
        except BaseException as exc:
            # Do NOT free or drop the allocations on any uncertain shutdown.
            raise UnsafeShutdown("DMA halt not confirmed; retain buffers and recover board power") from exc
        for buffer in self.buffers.values():
            buffer.freebuffer()
        self.buffers.clear()
        self.closed = True
