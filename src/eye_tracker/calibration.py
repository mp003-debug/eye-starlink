"""PCCR coordinate mathematics. No detector or optical validity is implied.

All coordinates come from one native-resolution ROI with fixed geometry.
Independent check frames are never used to fit coefficients.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import numpy as np


def pair(value):
    if len(value) != 2 or any(isinstance(x, bool) for x in value):
        raise ValueError("expected coordinate pair")
    result = tuple(float(x) for x in value)
    if not all(math.isfinite(x) for x in result):
        raise ValueError("nonfinite coordinate")
    return result


@dataclass(frozen=True)
class Context:
    session_id: str
    geometry_id: str
    source: str

    def __post_init__(self):
        if not self.session_id or not self.geometry_id:
            raise ValueError("missing session or geometry")
        if self.source not in ("simulated", "replay", "live"):
            raise ValueError("unknown source")


@dataclass(frozen=True)
class Observation:
    frame_id: str
    context: Context
    pupil: tuple
    glint: tuple
    roi_size: tuple

    def feature(self):
        p, c = pair(self.pupil), pair(self.glint)
        w, h = pair(self.roi_size)
        if w <= 0 or h <= 0 or not self.frame_id:
            raise ValueError("invalid frame geometry or identity")
        for x, y in (p, c):
            if not (0 <= x < w and 0 <= y < h):
                raise ValueError("feature outside native ROI")
        return ((p[0] - c[0]) / w, (p[1] - c[1]) / h)


@dataclass(frozen=True)
class CalibrationPoint:
    observation: Observation
    target: tuple


def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def convex_hull(points):
    points = sorted(set(tuple(p) for p in points))
    chains = []
    for order in (points, list(reversed(points))):
        chain = []
        for p in order:
            while len(chain) > 1 and cross(chain[-2], chain[-1], p) <= 0:
                chain.pop()
            chain.append(p)
        chains.append(chain[:-1])
    return tuple(chains[0] + chains[1])


class AffineCalibration:
    """Five-target affine baseline with separate checks; not full head-pose correction."""
    def __init__(self, context, roi_size, origin, scale, coefficients, hull, metrics):
        self.context = context
        self.roi_size = tuple(roi_size)
        self.origin, self.scale, self.coefficients = origin, scale, coefficients
        self.hull, self.metrics = hull, metrics
        payload = [context.__dict__, list(roi_size), coefficients.tolist(), origin.tolist(), scale.tolist()]
        self.calibration_id = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]
        for a in (origin, scale, coefficients):
            a.setflags(write=False)

    @classmethod
    def fit(cls, training, checks, max_fit_error=.08, max_check_error=.10):
        if any(not math.isfinite(v) or v <= 0 for v in (max_fit_error, max_check_error)):
            raise ValueError("invalid error budget")
        training, checks = list(training), list(checks)
        if len(training) < 5 or len(checks) < 4:
            raise ValueError("need five fit and four independent check observations")
        all_points = training + checks
        context = training[0].observation.context
        size = pair(training[0].observation.roi_size)
        ids = [p.observation.frame_id for p in all_points]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate frame or calibration/check leakage")
        for p in all_points:
            if p.observation.context != context or pair(p.observation.roi_size) != size:
                raise ValueError("mixed source, session or geometry")
            if not all(0 <= v <= 1 for v in pair(p.target)):
                raise ValueError("target outside screen")
        if len(set(pair(p.target) for p in training)) < 5 or len(set(pair(p.target) for p in checks)) < 4:
            raise ValueError("insufficient distinct targets")
        features = np.asarray([p.observation.feature() for p in training], dtype=float)
        targets = np.asarray([pair(p.target) for p in training], dtype=float)
        origin, scale = features.mean(axis=0), features.std(axis=0)
        if np.any(scale < 1e-6):
            raise ValueError("insufficient feature variation")
        design = np.column_stack(((features-origin)/scale, np.ones(len(features))))
        condition = float(np.linalg.cond(design))
        if not math.isfinite(condition) or condition > 20:
            raise ValueError("degenerate calibration geometry")
        coefficients, _, rank, _ = np.linalg.lstsq(design, targets, rcond=None)
        if rank != 3:
            raise ValueError("rank deficient calibration")
        error = np.linalg.norm(design @ coefficients - targets, axis=1)
        if float(error.max()) > max_fit_error:
            raise ValueError("fit error exceeds budget")
        model = cls(context, size, origin, scale, coefficients, convex_hull(features), {})
        check_error = np.asarray([np.linalg.norm(np.asarray(model.project(p.observation))-pair(p.target)) for p in checks])
        if float(check_error.max()) > max_check_error:
            raise ValueError("independent check failed")
        model.metrics.update(fit_max=float(error.max()), check_max=float(check_error.max()),
                             check_mean=float(check_error.mean()), condition=condition,
                             fit_count=len(training), check_count=len(checks),
                             source=context.source, optical_acceptance=False)
        return model

    def project(self, observation):
        if observation.context != self.context or pair(observation.roi_size) != self.roi_size:
            raise ValueError("calibration context changed")
        feature = observation.feature()
        if any(cross(a, b, feature) < -1e-12 for a, b in zip(self.hull, self.hull[1:]+self.hull[:1])):
            raise ValueError("outside calibrated feature region")
        row = np.append((np.asarray(feature)-self.origin)/self.scale, 1.)
        result = row @ self.coefficients
        if not np.isfinite(result).all() or np.any(result < 0) or np.any(result > 1):
            raise ValueError("projected point outside screen")
        return tuple(float(x) for x in result)
