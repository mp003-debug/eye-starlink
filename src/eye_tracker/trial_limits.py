"""Explicit finite long-run policy and bounded event histories."""
import math
from collections import Counter


def validate_trial_duration(seconds, long_run=False, demo_window=False):
    if demo_window and not long_run:
        raise ValueError('demo_window_requires_bounded_long_run')
    maximum = 3600 if demo_window else 1200 if long_run else 90
    if not math.isfinite(seconds) or not 10 <= seconds <= maximum:
        raise ValueError('visual_trial_duration_10_to_%d' % maximum)


class EventHistory(list):
    """JSON-compatible trailing event window, with full-run event totals."""
    def __init__(self, limit=4096):
        if type(limit) is not int or limit <= 0:
            raise ValueError('positive_event_limit_required')
        super().__init__()
        self.limit = limit
        self.total = 0
        self.counts = Counter()

    def append(self, event):
        self.total += 1
        self.counts[str(event.get('event', event.get('command', event.get('key', 'unknown'))))] += 1
        if len(self) == self.limit:
            del self[0]
        super().append(event)

    def summary(self):
        return dict(limit=self.limit, total=self.total, retained=len(self),
                    discarded=self.total-len(self), counts=dict(self.counts))
