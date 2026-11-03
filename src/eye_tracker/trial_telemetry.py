"""Bounded observation-only telemetry for long live-eye trials.

Rows retain their original identity so the caller can add presentation timing.
Only aggregate statistics cover the complete run; retained rows and images are
explicitly a tail/sample and must never be reported as complete-run percentiles
or accuracy. This module neither changes recognition nor produces actions.
"""
from collections import Counter, deque
import math
from pathlib import Path
import time


_LABELS = frozenset(('center', 'water', 'rest', 'help', 'more'))
_MEMORY_KEYS = ('VmRSS', 'VmHWM', 'MemAvailable', 'CmaFree', 'CmaTotal')


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) and value >= 0 else None


def read_process_resources(proc_root='/proc'):
    """Return Linux proc values in KiB; absent/invalid fields remain None."""
    values = dict.fromkeys(_MEMORY_KEYS)
    root = Path(proc_root)
    for path, wanted in ((root/'self'/'status', ('VmRSS', 'VmHWM')),
                         (root/'meminfo', ('MemAvailable', 'CmaFree', 'CmaTotal'))):
        try:
            lines = path.read_text(encoding='ascii').splitlines()
        except (OSError, UnicodeError):
            continue
        for line in lines:
            key, separator, tail = line.partition(':')
            if separator and key in wanted:
                parts = tail.split()
                if len(parts) == 2 and parts[1] == 'kB':
                    value = _number(parts[0])
                    if value is not None and value.is_integer():
                        values[key] = int(value)
    return values


class _Metric:
    def __init__(self):
        self.count = 0
        self.missing_or_invalid = 0
        self.total = 0.
        self.maximum = None

    def add(self, value):
        value = _number(value)
        if value is None:
            self.missing_or_invalid += 1
            return
        self.count += 1
        self.total += value
        self.maximum = value if self.maximum is None else max(self.maximum, value)

    def summary(self):
        return dict(count=self.count, missing_or_invalid=self.missing_or_invalid,
                    sum_ms=self.total, mean_ms=self.total/self.count if self.count else None,
                    max_ms=self.maximum, scope='all observed frames with finite nonnegative values')


class BoundedTrialTelemetry:
    MAX_ROWS = 1800
    MAX_AUDIT = 120
    MAX_RESOURCES = 128
    MAX_REASON_CATEGORIES = 64
    PERIOD_SECONDS = 10.
    MIN_AUDIT_GAP_SECONDS = 1.

    def __init__(self, proc_root='/proc', process_clock=None, resource_clock=None):
        self.rows = deque(maxlen=self.MAX_ROWS)
        self.audit = deque(maxlen=self.MAX_AUDIT)
        self.audit_metadata = deque(maxlen=self.MAX_AUDIT)
        self.resources = deque(maxlen=self.MAX_RESOURCES)
        self._proc_root = proc_root
        self._process_clock = process_clock or time.process_time
        self._resource_clock = resource_clock or time.monotonic
        self.total_frames = 0
        self.total_selections = 0
        self.valid_frames = 0
        self.invalid_frames = 0
        self.selection_counts = Counter()
        self.reason_counts = Counter()
        self.rejection_counts = Counter()
        self.processing = _Metric()
        self.copy_to_result = _Metric()
        self.max_inter_frame_gap_seconds = 0.
        self.validity_transitions = 0
        self.audit_samples_total = 0
        self.audit_requested_frames = 0
        self.audit_rate_limited_frames = 0
        self.audit_pixels_bytes_total = 0
        self.resource_samples_total = 0
        self._started = None
        self._last_copied = None
        self._last_index = None
        self._last_valid = None
        self._last_audit_time = None
        self._audit_period_bin = -1
        self._resource_period_bin = -1
        self._last_resource_copied = None
        self._resource_cpu_previous = None
        self._resource_start = None

    @classmethod
    def _count_reason(cls, counter, value):
        label = str(value)[:160] if value is not None else 'unspecified'
        if label not in counter and len(counter) >= cls.MAX_REASON_CATEGORIES-1:
            label = '__other__'
        counter[label] += 1

    def _sample_resources(self, copied):
        wall = _number(self._resource_clock())
        cpu = _number(self._process_clock())
        percent = None
        previous = self._resource_cpu_previous
        if previous is not None and wall is not None and cpu is not None:
            old_wall, old_cpu = previous
            if wall > old_wall and cpu >= old_cpu:
                percent = 100.*(cpu-old_cpu)/(wall-old_wall)
        self._resource_cpu_previous = (wall, cpu) if wall is not None and cpu is not None else None
        sample = dict(elapsed=copied-self._started,
                      memory_kib=read_process_resources(self._proc_root),
                      cpu_percent_single_core=percent)
        self.resources.append(sample)
        self.resource_samples_total += 1
        self._last_resource_copied = copied
        if self._resource_start is None:
            self._resource_start = sample

    def observe(self, pixels, row, action):
        """Record one frame; no row copy, no borrowed image buffer, no action side effects."""
        copied = _number(row.get('copied_monotonic'))
        index = row.get('frame_index')
        if (copied is None or type(index) is not int or index <= 0
                or self._last_index is not None and index <= self._last_index
                or self._last_copied is not None and copied <= self._last_copied):
            raise ValueError('telemetry_requires_fresh_frame_identity')
        if self._started is None:
            self._started = copied
        elapsed = copied-self._started
        period_bin = int(elapsed/self.PERIOD_SECONDS)
        candidate = row.get('candidate')
        stable = row.get('stable_candidate')
        valid = isinstance(candidate, str) and candidate in _LABELS and candidate == stable
        changed = self._last_valid is not None and valid != self._last_valid
        if self._last_copied is not None:
            self.max_inter_frame_gap_seconds = max(self.max_inter_frame_gap_seconds,
                                                  copied-self._last_copied)
        self._last_copied, self._last_index, self._last_valid = copied, index, valid
        self.total_frames += 1
        self.valid_frames += int(valid)
        self.invalid_frames += int(not valid)
        self.validity_transitions += int(changed)
        self.rows.append(row)
        self._count_reason(self.reason_counts, row.get('reason'))
        if row.get('rejection') is not None:
            self._count_reason(self.rejection_counts, row['rejection'])
        self.processing.add(row.get('processing_ms'))
        self.copy_to_result.add(row.get('copy_to_result_ms'))
        if action is not None:
            self.total_selections += 1
            key = action.get('key') if isinstance(action, dict) else getattr(action, 'key', None)
            self.selection_counts[key if key in _LABELS or key == 'back' else '__other__'] += 1

        triggers = []
        if period_bin > self._audit_period_bin:
            triggers.append('periodic')
        if action is not None:
            triggers.append('selection')
        if changed:
            triggers.append('validity_changed')
        if triggers:
            self.audit_requested_frames += 1
            if self._last_audit_time is None or copied-self._last_audit_time >= self.MIN_AUDIT_GAP_SECONDS:
                if getattr(pixels, 'ndim', None) != 2 or str(getattr(pixels, 'dtype', None)) != 'uint8':
                    raise ValueError('telemetry_audit_requires_gray8')
                sample = pixels[::2, ::2].copy()
                self.audit.append((index, sample))
                self.audit_metadata.append(dict(frame_index=index, elapsed=elapsed,
                                                candidate=candidate, stable=stable,
                                                reason=row.get('reason'), triggers=triggers))
                self.audit_samples_total += 1
                self.audit_pixels_bytes_total += int(sample.nbytes)
                self._last_audit_time = copied
                self._audit_period_bin = period_bin
            else:
                self.audit_rate_limited_frames += 1
        if period_bin > self._resource_period_bin:
            self._sample_resources(copied)
            self._resource_period_bin = period_bin

    def summary(self):
        """JSON-safe snapshot, adding at most one final resource sample per frame."""
        if self._last_copied is not None and self._last_resource_copied != self._last_copied:
            self._sample_resources(self._last_copied)
        retained_bytes = sum(int(pixels.nbytes) for _, pixels in self.audit)
        return dict(
            scope='full-run counters; bounded row tail and sparse image samples; no gaze accuracy claim',
            total_frames=self.total_frames, total_selections=self.total_selections,
            valid_frames=self.valid_frames, invalid_frames=self.invalid_frames,
            valid_definition='current candidate equals stable_candidate in the five known regions',
            selection_counts=dict(self.selection_counts), reason_counts=dict(self.reason_counts),
            rejection_counts=dict(self.rejection_counts), validity_transitions=self.validity_transitions,
            started_monotonic=self._started, ended_monotonic=self._last_copied,
            duration_seconds=self._last_copied-self._started if self._started is not None else 0.,
            max_inter_frame_gap_seconds=self.max_inter_frame_gap_seconds,
            processing=self.processing.summary(), copy_to_result=self.copy_to_result.summary(),
            retention=dict(
                row_limit=self.MAX_ROWS, rows_retained=len(self.rows),
                rows_discarded=self.total_frames-len(self.rows),
                audit_limit=self.MAX_AUDIT, audit_retained=len(self.audit),
                audit_samples_total=self.audit_samples_total,
                audit_discarded=self.audit_samples_total-len(self.audit),
                audit_requested_frames=self.audit_requested_frames,
                audit_rate_limited_frames=self.audit_rate_limited_frames,
                audit_period_seconds=self.PERIOD_SECONDS,
                audit_min_gap_seconds=self.MIN_AUDIT_GAP_SECONDS,
                audit_pixels_bytes_retained=retained_bytes,
                audit_pixels_bytes_total=self.audit_pixels_bytes_total,
                resource_limit=self.MAX_RESOURCES, resources_retained=len(self.resources),
                resource_samples_total=self.resource_samples_total,
                resources_discarded=self.resource_samples_total-len(self.resources),
                reason_category_limit=self.MAX_REASON_CATEGORIES,
                reason_overflow_bucket='__other__'),
            resource_start=self._resource_start,
            resource_end=self.resources[-1] if self.resources else None,
            resources=list(self.resources),
            resource_scope='process RSS/HWM and system available/CMA in KiB; CPU100% equals one core, not whole system')

