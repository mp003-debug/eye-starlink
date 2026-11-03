"""Fresh eye-region proposals for setup; never emits pupil, gaze or open-eye validity."""
import hashlib
import math
import time
from pathlib import Path
import numpy as np

MODEL = Path(__file__).resolve().parents[2] / "assets/haarcascade_eye.xml"
MODEL_SHA256 = "71cc64fc305a355dc60067880f6fbbd43dd155bd63ee3844661a1bda34b2fd8c"


def overlap(a, b):
    iw = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    ih = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    intersection = iw * ih
    area = lambda r: (r[2]-r[0]) * (r[3]-r[1])
    return intersection / max(1, area(a)+area(b)-intersection)


def normalize_boxes(boxes):
    candidates = []
    for box in boxes:
        if len(box) != 4 or any(not math.isfinite(float(x)) or float(x) != int(x) for x in box):
            continue
        b = tuple(int(x) for x in box)
        if not (0 <= b[0] < b[2] <= 640 and 0 <= b[1] < b[3] <= 480):
            continue
        if not (64 <= b[2]-b[0] <= 240 and 64 <= b[3]-b[1] <= 240):
            continue
        candidates.append(b)
    # Suppress overlapping duplicate detections, not independent eyes.
    kept = []
    for b in sorted(candidates, key=lambda r: (-(r[2]-r[0])*(r[3]-r[1]), r)):
        if not any(overlap(b, other) > .30 for other in kept):
            kept.append(b)
    return sorted(kept)


def display_crop(box):
    cx, cy = (box[0]+box[2])/2, (box[1]+box[3])/2
    side = min(256, max(128, round(max(box[2]-box[0], box[3]-box[1])*1.5)))
    x, y = min(640-side, max(0, round(cx-side/2))), min(480-side, max(0, round(cy-side/2)))
    return (x, y, x+side, y+side)


def compatible(a, b):
    aw, ah, bw, bh = a[2]-a[0], a[3]-a[1], b[2]-b[0], b[3]-b[1]
    shift = math.hypot((a[0]+a[2]-b[0]-b[2])/2, (a[1]+a[3]-b[1]-b[3])/2)
    return shift <= .65*max(aw, ah) and .5 <= bw*bh/(aw*ah) <= 2.


class CascadeEyes:
    """Quarter-size search, constrained local re-detection on every next frame."""
    def __init__(self, model=MODEL):
        data = Path(model).read_bytes()
        if hashlib.sha256(data).hexdigest() != MODEL_SHA256:
            raise ValueError("eye cascade hash mismatch")
        import cv2  # PYNQ uses its installed OpenCV; no PC dependency at runtime.
        self.cv = cv2
        cv2.setNumThreads(1)
        self.cascade = cv2.CascadeClassifier(str(model))
        if self.cascade.empty():
            raise ValueError("eye cascade did not load")

    def __call__(self, pixels, hint):
        cv = self.cv
        if hint is None:
            x0, y0, x1, y1 = 0, 0, 640, 480
            minimum, maximum = (20,20), (55,55)
        else:
            w, h = hint[2]-hint[0], hint[3]-hint[1]
            x0, y0 = max(0, hint[0]-round(w*.55)), max(0, hint[1]-round(h*.55))
            x1, y1 = min(640, hint[2]+round(w*.55)), min(480, hint[3]+round(h*.55))
            minimum = (max(20, round(w*.65/4)), max(20, round(h*.65/4)))
            maximum = (max(minimum[0], round(w*1.45/4)), max(minimum[1], round(h*1.45/4)))
        sw, sh = max(1,(x1-x0)//4), max(1,(y1-y0)//4)
        image = cv.resize(pixels[y0:y1,x0:x1], (sw,sh), interpolation=cv.INTER_AREA)
        boxes = self.cascade.detectMultiScale(cv.equalizeHist(image), scaleFactor=1.1,
                    minNeighbors=5, minSize=minimum, maxSize=maximum)
        sx, sy = (x1-x0)/sw, (y1-y0)/sh
        return [(round(x*sx)+x0, round(y*sy)+y0, round((x+w)*sx)+x0, round((y+h)*sy)+y0)
                for x,y,w,h in boxes]


class EyeRegionLocator:
    MAX_GAP = .5
    def __init__(self, detector=None):
        self.detector = detector if detector is not None else CascadeEyes()
        self.hint = None
        self.last_seen = None
        self.last_time = None
        self.last_index = 0
        self.streak = 0
        self.track_id = 0
        self.counts = {"searching":0, "confirming":0, "located":0}
        self.times_ms = []

    def update(self, pixels, frame_index, timestamp):
        if not isinstance(pixels,np.ndarray) or pixels.shape != (480,640) or pixels.dtype != np.uint8:
            raise ValueError("native640x480 uint8 required")
        if type(frame_index) is not int or frame_index <= self.last_index or not math.isfinite(timestamp) or timestamp < 0:
            raise ValueError("fresh frame identity/time required")
        if self.last_time is not None and timestamp <= self.last_time:
            raise ValueError("capture timestamps must increase")
        if len(self.times_ms) >= 20000:
            raise ValueError("bounded diagnostic capacity exceeded")
        if self.last_seen is not None and timestamp-self.last_seen > self.MAX_GAP:
            self.hint = None
            self.streak = 0
        previous = self.hint
        start = time.monotonic()
        boxes = normalize_boxes(self.detector(pixels, previous))
        elapsed = (time.monotonic()-start)*1000
        self.times_ms.append(elapsed)
        selected = None
        if previous is None:
            if boxes:
                selected = boxes[0]  # deterministic image-left preference, not anatomical identity
        else:
            matches = [b for b in boxes if compatible(previous, b)]
            if len(matches) == 1:
                selected = matches[0]
            # Ambiguous association never produces a current box.
        self.last_time, self.last_index = timestamp, frame_index
        if selected is None:
            self.streak = 0
            state, box, crop = "searching", None, None
        else:
            self.streak += 1
            self.hint, self.last_seen = selected, timestamp
            if self.streak == 2:
                self.track_id += 1  # discontinuity token; not persistent biological identity
            state = "located" if self.streak >= 2 else "confirming"
            box = selected if state == "located" else None
            crop = display_crop(box) if box else None
        self.counts[state] += 1
        return {"state":state, "box":box, "crop":crop, "track_id":self.track_id if box else None,
                "frame_index":frame_index, "copied_at":timestamp, "detector_ms":elapsed,
                "candidate_count":len(boxes), "gaze_validated":False}

    def summary(self):
        return {"scope":"eye-region proposals only; not pupil, gaze, blink validity or calibration",
                "model_sha256":MODEL_SHA256, "states":dict(self.counts), "track_segments":self.track_id,
                "p95_detector_ms":float(np.percentile(self.times_ms,95)) if self.times_ms else None,
                "max_detector_ms":max(self.times_ms,default=None), "max_confirmation_gap_s":self.MAX_GAP,
                "gaze_validated":False, "eye_open_validated":False}
