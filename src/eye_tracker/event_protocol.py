"""Version 1 wire format and a platform-independent receiver reference.

The receiver reference is for tests/teammate porting, not flashed BearPi code.
An ACK means the remote receiver accepted the event, not actuator completion.
"""
from dataclasses import dataclass
import math
import struct

MAGIC = b"\xa5\x5a"
VERSION = 1
FRAME_SIZE = 16
HELLO, PING, EVENT, ACK = 1, 2, 16, 128
OK, DUPLICATE, NO_SESSION, OLD_SEQUENCE, BAD_EVENT, BAD_MODE, BUSY = range(7)
EVENTS = {"water": 1, "rest": 2, "help": 3, "more": 4, "back": 5}
TEST = 1


def crc16(data):
    """CRC-16/CCITT-FALSE: poly1021, initFFFF, refin/out false, xorout0."""
    crc = 0xffff
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xffff
    return crc


@dataclass(frozen=True)
class Packet:
    kind: int
    session: int
    sequence: int
    code: int = 0
    detail: int = 0

    def encode(self):
        if self.kind not in (HELLO, PING, EVENT, ACK) or not 1 <= self.session <= 0xffffffff:
            raise ValueError("invalid packet kind/session")
        raw = struct.pack("<2sBBIIBB", MAGIC, VERSION, self.kind,
                          self.session, self.sequence, self.code, self.detail)
        return raw + struct.pack("<H", crc16(raw))

    @classmethod
    def decode(cls, raw):
        if len(raw) != FRAME_SIZE or raw[:2] != MAGIC or raw[2] != VERSION:
            raise ValueError("invalid frame header/size")
        if crc16(raw[:14]) != int.from_bytes(raw[14:], "little"):
            raise ValueError("CRC mismatch")
        _, _, kind, session, sequence, code, detail = struct.unpack("<2sBBIIBB", raw[:14])
        packet = cls(kind, session, sequence, code, detail)
        packet.encode()  # validate kind and session too
        return packet


class Decoder:
    """Resynchronizes after noise/bad CRC; retains at most 15 partial bytes."""
    def __init__(self):
        self.buffer = bytearray()
        self.bad_frames = 0

    def feed(self, data):
        result = []
        for byte in data:
            self.buffer.append(byte)
            while len(self.buffer) >= 2 and self.buffer[:2] != MAGIC:
                del self.buffer[0]
            if len(self.buffer) == FRAME_SIZE:
                try:
                    result.append(Packet.decode(bytes(self.buffer)))
                    self.buffer.clear()
                except ValueError:
                    self.bad_frames += 1
                    del self.buffer[0]
        return result


class Receiver:
    """Reference policy. Call disconnect() on SLE loss/reboot before reconnect.

    No persistent exactly-once guarantee across receiver power failure. A session
    expires after 2s without accepted traffic. Only a new HELLO can rearm it.
    Bridge queues MUST be discarded on disconnect; no offline store-and-forward.
    """
    def __init__(self, allow_test=False):
        self.allow_test = allow_test
        self.session = None
        self.mode = 0
        self.last = None
        self.last_time = -math.inf

    def disconnect(self):
        self.session = None
        self.last = None

    def receive(self, packet, now_ms):
        if not math.isfinite(now_ms) or now_ms < self.last_time:
            raise ValueError("receiver clock regressed")
        if now_ms - self.last_time > 2000:
            self.disconnect()
        status, deliver = OK, False
        if packet.kind == ACK:
            return None, False  # no ACK storms
        if packet.kind == HELLO:
            if packet.sequence or packet.code or packet.detail not in (0, TEST):
                status = BAD_EVENT
            elif packet.detail == TEST and not self.allow_test:
                status = BAD_MODE
            elif packet.session == self.session:
                if packet.detail != self.mode:
                    status = BAD_MODE
                # A retried HELLO must never clear duplicate suppression.
            else:
                self.session, self.mode, self.last = packet.session, packet.detail, packet
        elif self.session != packet.session:
            status = NO_SESSION
        elif packet.detail != self.mode:
            status = BAD_MODE
        elif packet.kind == EVENT and packet.code not in EVENTS.values():
            status = BAD_EVENT
        elif packet.kind == PING and packet.code != 0:
            status = BAD_EVENT
        elif packet.sequence == 0:
            status = OLD_SEQUENCE
        elif self.last and packet.sequence <= self.last.sequence:
            status = DUPLICATE if packet == self.last else OLD_SEQUENCE
        else:
            self.last = packet
            deliver = packet.kind == EVENT
        if status in (OK, DUPLICATE):
            self.last_time = now_ms
        return Packet(ACK, packet.session, packet.sequence, packet.code, status), deliver
