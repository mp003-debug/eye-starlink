"""Opt-in v2 sharing over the unchanged 16-byte UART/SLE transport.

V1 care packets are unchanged. V2 requires a successful CAPS in the current
v1 session; complete, bounded GB2312 messages are displayed only at COMMIT.
"""
from dataclasses import dataclass
import struct
from .event_protocol import MAGIC, FRAME_SIZE, ACK, crc16, Packet

CAPS, BEGIN, DATA, COMMIT = 32, 33, 34, 35
PHRASE, EMOTION, TEXT, ACTIVITY = 1, 2, 3, 4
BLOCKED, UNSUPPORTED = 7, 8
MAX_CHARS, MAX_BYTES = 64, 128

PHRASES = ('是', '不是', '请停一下', '请帮我换个姿势', '我要上厕所', '我不舒服')
EMOTIONS = ('我很开心', '我有些难过', '我有些担心', '我很喜欢', '谢谢你', '我想你了')
ACTIVITIES = ('使用菜单', '听音乐', '看视频', '听故事', '玩游戏', '看相册', '文字交流', '展示心意', '活动分享已关闭')


def message_bytes(category, text):
    if category not in (PHRASE, EMOTION, TEXT, ACTIVITY):
        raise ValueError('unknown sharing category')
    if not isinstance(text, str) or not 1 <= len(text) <= MAX_CHARS:
        raise ValueError('分享内容需为1至64字')
    if any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise ValueError('分享内容不能包含控制字符')
    if category in (PHRASE, EMOTION, ACTIVITY) and text not in {
            PHRASE: PHRASES, EMOTION: EMOTIONS, ACTIVITY: ACTIVITIES}[category]:
        raise ValueError('unknown fixed message')
    try:
        raw = text.encode('gb2312')
    except UnicodeEncodeError as exc:
        raise ValueError('接收屏暂不支持其中的生僻字或符号') from exc
    if len(raw) > MAX_BYTES:
        raise ValueError('分享内容过长')
    return raw


@dataclass(frozen=True)
class SharePacket:
    kind: int
    session: int
    sequence: int
    code: int = 0
    detail: int = 0
    version: int = 2

    def encode(self):
        if self.version != 2 or self.kind not in (CAPS, BEGIN, DATA, COMMIT, ACK):
            raise ValueError('invalid sharing packet')
        if not 1 <= self.session <= 0xffffffff or not 0 <= self.sequence <= 0xffffffff:
            raise ValueError('invalid sharing session/sequence')
        if not 0 <= self.code <= 255 or not 0 <= self.detail <= 255:
            raise ValueError('invalid sharing payload')
        raw = struct.pack('<2sBBIIBB', MAGIC, 2, self.kind, self.session,
                          self.sequence, self.code, self.detail)
        return raw + struct.pack('<H', crc16(raw))

    @classmethod
    def decode(cls, raw):
        if len(raw) != FRAME_SIZE or raw[:3] != MAGIC + b'\x02' or crc16(raw[:14]) != int.from_bytes(raw[14:], 'little'):
            raise ValueError('invalid sharing frame')
        _, _, kind, session, sequence, code, detail = struct.unpack('<2sBBIIBB', raw[:14])
        p = cls(kind, session, sequence, code, detail)
        p.encode()
        return p


class MixedDecoder:
    def __init__(self):
        self.buffer = bytearray()
        self.bad_frames = 0

    def feed(self, data):
        out = []
        for byte in data:
            self.buffer.append(byte)
            while len(self.buffer) >= 2 and self.buffer[:2] != MAGIC:
                del self.buffer[0]
            if len(self.buffer) == FRAME_SIZE:
                try:
                    out.append((SharePacket if self.buffer[2] == 2 else Packet).decode(bytes(self.buffer)))
                    self.buffer.clear()
                except ValueError:
                    self.bad_frames += 1
                    del self.buffer[0]
        return out


def fragments(category, text):
    raw = message_bytes(category, text)
    result = [(BEGIN, category, len(raw))]
    padded = raw + (b'\0' if len(raw) % 2 else b'')
    result += [(DATA, padded[i], padded[i + 1]) for i in range(0, len(padded), 2)]
    check = crc16(raw)
    result.append((COMMIT, check & 255, check >> 8))
    return result
