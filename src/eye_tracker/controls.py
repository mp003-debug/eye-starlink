"""Debounced physical helper controls; never create gaze or selection events."""
import math

class HelperButtons:
    def __init__(self,debounce_ms=30,max_gap_ms=250):
        self.debounce_ms=debounce_ms;self.max_gap_ms=max_gap_ms
        self.last_time=None;self.stable=0;self.candidate=0;self.since=[0.]*4;self.armed=0
    def update(self,raw,now):
        if type(raw) is not int or not 0<=raw<16 or not math.isfinite(now) or now<0:
            raise ValueError('invalid button sample')
        if self.last_time is not None and now<self.last_time:raise ValueError('button clock regressed')
        if self.last_time is None or now-self.last_time>self.max_gap_ms:
            self.last_time=now;self.stable=raw;self.candidate=raw;self.since=[now]*4;self.armed=(~raw)&15
            return None
        self.last_time=now;rising=0
        for i in range(4):
            mask=1<<i
            if (raw^self.candidate)&mask:
                self.candidate^=mask;self.since[i]=now
            if (self.candidate^self.stable)&mask and now-self.since[i]>=self.debounce_ms:
                self.stable^=mask
                if self.stable&mask:
                    if self.armed&mask:rising|=mask
                    self.armed&=~mask
                else:self.armed|=mask
        for bit,name in ((3,'stop'),(2,'invalidate_calibration'),(0,'toggle_pause'),(1,'cancel')):
            if rising&(1<<bit):return name
        return None

def apply_command(controller,command,now):
    if command=='toggle_pause':
        (controller.resume if controller.paused else controller.pause)(now)
    elif command=='invalidate_calibration':controller.invalidate_calibration()
    elif command in ('cancel','stop'):getattr(controller,command)(now)
    else:raise ValueError('unknown helper command')
