"""Explicit camera/display formats. No MMIO, allocation or DMA side effects."""
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class FrameLayout:
    width: int
    height: int
    format: str
    stride_bytes: int

    def __post_init__(self):
        if self.format not in ("GRAY8", "RGB565_LE"):
            raise ValueError("unsupported pixel format")
        if any(type(v) is not int or v <= 0 for v in (self.width,self.height,self.stride_bytes)):
            raise ValueError("positive integer geometry required")
        if self.stride_bytes < self.hsize_bytes or self.stride_bytes % 8:
            raise ValueError("stride must contain a line and align to the 64-bit memory bus")
        if self.hsize_bytes > 65535 or self.stride_bytes > 65535 or self.height > 8191:
            raise ValueError("geometry exceeds this VDMA register layout")

    @property
    def hsize_bytes(self):
        return self.width * (1 if self.format == "GRAY8" else 2)

    @property
    def size_bytes(self):
        return self.stride_bytes * self.height

CAPTURE = FrameLayout(640,480,"GRAY8",640)
DISPLAY = FrameLayout(640,480,"RGB565_LE",1280)

def pack_rgb565(rgb):
    """Pack RGB uint8 as little-endian uint16. R at bit15, B at bit0."""
    a=np.asarray(rgb)
    if a.dtype != np.uint8 or a.ndim != 3 or a.shape[2] != 3:
        raise ValueError("expected HxWx3 RGB uint8")
    words=((a[...,0].astype(np.uint16)>>3)<<11) | ((a[...,1].astype(np.uint16)>>2)<<5) | (a[...,2].astype(np.uint16)>>3)
    return np.ascontiguousarray(words,dtype="<u2")

def unpack_rgb565(words):
    """Preview the exact bit replication used by the FPGA color converter."""
    w=np.asarray(words)
    if w.ndim != 2 or w.dtype.kind != "u" or w.dtype.itemsize != 2:
        raise ValueError("expected HxW unsigned 16-bit words")
    r=(w>>11)&31;g=(w>>5)&63;b=w&31
    return np.stack(((r<<3)|(r>>2),(g<<2)|(g>>4),(b<<3)|(b>>2)),axis=-1).astype(np.uint8)

def encode_frame(rgb, layout=DISPLAY):
    if layout.format != "RGB565_LE":
        raise ValueError("RGB frame cannot be sent using a camera GRAY8 layout")
    words=pack_rgb565(rgb)
    if words.shape != (layout.height,layout.width):
        raise ValueError("frame geometry differs from display layout")
    rows=np.zeros((layout.height,layout.stride_bytes),dtype=np.uint8)
    rows[:,:layout.hsize_bytes]=words.view(np.uint8).reshape(layout.height,layout.hsize_bytes)
    return rows.tobytes()
