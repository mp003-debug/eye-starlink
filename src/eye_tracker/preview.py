"""Camera setup view. No pupil detector, gaze coordinates or interaction output."""
import math
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from .framebuffer import encode_frame, pack_rgb565

TEMPLATE = Path(__file__).resolve().parents[2] / "assets/preview_template.png"
CROP = (256, 176, 384, 304)  # center 128x128 in the acquired 640x480 frame


def frame_statistics(pixels):
    if not isinstance(pixels, np.ndarray) or pixels.shape != (480, 640) or pixels.dtype != np.uint8:
        raise ValueError("preview requires a 640x480 uint8 captured frame")
    # Full-frame distribution; no camera-dependent threshold is called a pupil.
    histogram = np.asarray(Image.fromarray(pixels, mode="L").histogram(), dtype=np.int64)
    return {"mean": float(np.dot(histogram, np.arange(256)) / pixels.size),
            "dark_percent": float(histogram[:3].sum() * 100 / pixels.size),
            "bright_percent": float(histogram[253:].sum() * 100 / pixels.size),
            "histogram": histogram}


class PreviewRenderer:
    def __init__(self, template=TEMPLATE):
        with Image.open(template) as image:
            if image.size != (640, 480):
                raise ValueError("preview template must be 640x480")
            self.base = image.convert("RGB")
        # Chinese labels are baked into the supplied image at build time.
        # Runtime uses Pillow's bundled ASCII bitmap font, no PC font dependency.
        self.font = ImageFont.load_default()
        self.base_words = np.frombuffer(encode_frame(np.asarray(self.base)), dtype="<u2").reshape(480, 640)
        levels = np.arange(256, dtype=np.uint16)
        self.gray_words = ((levels >> 3) << 11) | ((levels >> 2) << 5) | (levels >> 3)
        self.colors = {c: pack_rgb565(np.array([[tuple(bytes.fromhex(c))]], dtype=np.uint8))[0,0]
                       for c in ("f2c66c", "496d70", "3b9a92", "20a38e")}
        self.crop = CROP
        self.region_mode = False
        self.crop_box = tuple(round(v * .6) + (20 if i % 2 == 0 else 104) for i, v in enumerate(CROP))

    def set_region(self, observation):
        state = observation["state"]
        crop = observation["crop"]
        if state not in ("searching", "confirming", "located"):
            raise ValueError("unknown eye region state")
        if state != "located" and crop is not None:
            raise ValueError("unconfirmed region must not be shown")
        if state == "located":
            if crop is None or len(crop) != 4 or any(type(v) is not int for v in crop):
                raise ValueError("integer crop required")
            x0,y0,x1,y1=crop
            if not (0<=x0<x1<=640 and 0<=y0<y1<=480 and x1-x0==y1-y0):
                raise ValueError("native square crop required")
        self.region_mode = True
        self.crop = crop

    @lru_cache(maxsize=128)
    def _number_image(self, text):
        if hasattr(self.font, "getbbox"):
            bounds = self.font.getbbox(text)
        else:  # Pillow 9.0.1 bundled bitmap font on the deployed PYNQ image
            width, height = self.font.getsize(text)
            bounds = (0, 0, width, height)
        tile = Image.new("RGB", (bounds[2] - bounds[0] + 2, 12), (255,255,255))
        ImageDraw.Draw(tile).text((-bounds[0], -bounds[1]), text, font=self.font, fill=(23,75,73))
        return tile.resize((tile.width * 2, 24), Image.NEAREST)

    def _number(self, image, xy, text):
        image.paste(self._number_image(text), xy)

    @lru_cache(maxsize=128)
    def _number_words(self, text):
        return pack_rgb565(np.asarray(self._number_image(text)))

    def frame(self, pixels, index, elapsed):
        if type(index) is not int or index < 1 or not math.isfinite(elapsed) or elapsed <= 0:
            raise ValueError("positive accepted-frame index and elapsed time required")
        stats = frame_statistics(pixels)
        image = self.base.copy()
        camera = Image.fromarray(pixels, mode="L")
        image.paste(camera.resize((384, 288), Image.NEAREST), (20, 104))
        zoom = camera.crop(self.crop).resize((192,192), Image.NEAREST) if self.crop else Image.new("L",(192,192),0)
        image.paste(zoom, (424,104))
        draw = ImageDraw.Draw(image)
        # Marks the enlarged region, not a detected eye or feature.
        if self.crop:
            box = tuple(round(v * .6) + (20 if i % 2 == 0 else 104) for i, v in enumerate(self.crop))
            draw.rectangle(box, outline="#20a38e" if self.region_mode else "#f2c66c", width=1)
        draw.rectangle((19, 103, 404, 392), outline="#496d70", width=1)
        self._number(image, (474, 310), str(index))
        self._number(image, (474, 338), "%.1f fps" % (index / elapsed))
        self._number(image, (474, 366), "%.1f" % stats["mean"])
        bins = stats["histogram"].reshape(64, 4).sum(axis=1)
        scale = 26 / max(1, int(bins.max()))
        for i, value in enumerate(bins):
            x = 20 + i * 6
            draw.rectangle((x, 444 - round(value * scale), x + 4, 444), fill="#3b9a92")
        self._number(image, (450, 404), "%.1f%%" % stats["bright_percent"])
        # Progress marker lets the user distinguish repeated/frozen screen content.
        draw.rectangle((20, 70, 20 + (index % 120) * 3, 72), fill="#20a38e")
        return image, {key: value for key, value in stats.items() if key != "histogram"}

    def rgb565(self, pixels, index, elapsed):
        # Direct pixel sampling for the reduced setup view avoids ~20ms/frame
        # bilinear resize on Cortex-A9. Sensor pixels/center magnification are
        # unchanged. Cache numeric tiles, not captured images or statistics.
        if type(index) is not int or index < 1 or not math.isfinite(elapsed) or elapsed <= 0:
            raise ValueError("positive accepted-frame index and elapsed time required")
        stats = frame_statistics(pixels)
        words = self.base_words.copy()
        camera = Image.fromarray(pixels, mode="L")
        main = camera.resize((384, 288), Image.NEAREST)
        zoom = camera.crop(self.crop).resize((192,192), Image.NEAREST) if self.crop else Image.new("L",(192,192),0)
        words[104:392, 20:404] = self.gray_words[np.frombuffer(main.tobytes(), dtype=np.uint8).reshape(288, 384)]
        words[104:296, 424:616] = self.gray_words[np.frombuffer(zoom.tobytes(), dtype=np.uint8).reshape(192, 192)]
        def rectangle(box, value):
            x0, y0, x1, y1 = box
            words[y0, x0:x1+1] = words[y1, x0:x1+1] = value
            words[y0:y1+1, x0] = words[y0:y1+1, x1] = value
        if self.crop:
            box = tuple(round(v * .6) + (20 if i % 2 == 0 else 104) for i, v in enumerate(self.crop))
            rectangle(box, self.colors["20a38e" if self.region_mode else "f2c66c"])
        rectangle((19, 103, 404, 392), self.colors["496d70"])
        for x,y,text in ((474,310,str(index)), (474,338,"%.1f fps" % (index / elapsed)),
                         (474,366,"%.1f" % stats["mean"]), (450,404,"%.1f%%" % stats["bright_percent"])):
            tile=self._number_words(text)
            height,width=tile.shape
            words[y:y+height,x:x+width]=tile
        bins = stats["histogram"].reshape(64, 4).sum(axis=1)
        scale = 26 / max(1, int(bins.max()))
        fill = self.colors["3b9a92"]
        for i, value in enumerate(bins):
            x = 20 + i * 6
            words[444-round(value*scale):445, x:x+5] = fill
        words[70:73, 20:21+(index%120)*3] = self.colors["20a38e"]
        return words.tobytes(), {key: value for key, value in stats.items() if key != "histogram"}
