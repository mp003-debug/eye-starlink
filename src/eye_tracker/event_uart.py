"""Bounded polling driver for PG142 AXI UART Lite, 115200/8N1 at 50MHz.

Only the owning UI thread accesses MMIO. No sleep, spin-until-ready, IRQ or USB.
Exactly one 16-byte request is outstanding; the remote sends one 16-byte reply.
"""
from .event_protocol import FRAME_SIZE


class UartError(RuntimeError):
    pass


class AxiUartLite:
    def __init__(self, mmio):
        self.mmio = mmio
        self.reset()

    def reset(self):
        self.mmio.write(0x0c, 3)  # clear FIFOs, disable interrupts
        self.mmio.read(0x08)     # clear latched RX error flags

    def _status(self):
        status = int(self.mmio.read(0x08))
        if status & 0xe0:
            self.reset()
            raise UartError("UART receive error flags 0x%02x" % (status & 0xe0))
        return status

    def read(self):
        data = bytearray()
        for _ in range(FRAME_SIZE):
            if not self._status() & 1:
                break
            data.append(int(self.mmio.read(0x00)) & 255)
        return bytes(data)

    def try_write(self, frame):
        if len(frame) != FRAME_SIZE:
            raise ValueError("UART requires one complete 16-byte frame")
        if not self._status() & 4:  # wait for FIFO empty; never block the UI
            return False
        for byte in frame:
            if self._status() & 8:
                self.reset()
                raise UartError("unexpected TX FIFO full during single-owner write")
            self.mmio.write(0x04, byte)
        return True
