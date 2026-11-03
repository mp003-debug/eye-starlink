"""Single committed live-eye utterance, without an audio queue."""
import math
from .audio import AudioError


class TrialSpeech:
    def __init__(self,device,bank,controller,clock,bounded=False):
        self.device,self.bank,self.controller,self.clock=device,bank,controller,clock
        self.active=None
        self.bounded=bounded;self.last_spoken_time=-math.inf
        self.spoken_times=None if bounded else set()
        from .trial_limits import EventHistory
        self.events=EventHistory() if bounded else []

    def start(self,action,frame_index):
        if action is None or not action.phrase:return
        c=self.controller;now=self.clock();t=action.source_time_ms
        if (self.active is not None or c.paused or c.closed or not c.calibration_id
                or action.source!='live' or c.context.source!='live'
                or not math.isfinite(t) or not 0<=now*1000-t<=c.max_age_ms
                or (t<=self.last_spoken_time if self.bounded else t in self.spoken_times) or action.key not in self.bank.samples
                or action.phrase!=self.bank.text[action.key]):
            raise AudioError('invalid, stale or duplicate live speech action')
        self.device.play(self.bank.samples[action.key])
        self.active=action.key;self.last_spoken_time=t
        if self.spoken_times is not None:self.spoken_times.add(t)
        self.events.append(dict(event='started',key=self.active,monotonic=self.clock(),
                                source='live',source_time_ms=t,frame_index=frame_index))

    def poll(self):
        if self.active is not None and self.device.poll()=='done':
            self.events.append(dict(event='completed',key=self.active,monotonic=self.clock()))
            self.active=None

    def interrupt(self,command):
        self.device.stop()
        if self.active is not None:
            self.events.append(dict(event='interrupted',key=self.active,monotonic=self.clock(),command=command))
            self.active=None


class AutomaticTrialControls:
    """Explicit test helper; only cancels/pauses, never fabricates gaze/actions."""
    def __init__(self):
        self.stage='first';self.resume_at=None;self.resumed_at=None
    def update(self,speech,now):
        starts=[e for e in speech.events if e['event']=='started']
        if self.stage in ('first','second'):
            needed=1 if self.stage=='first' else 2
            if len(starts)>=needed and speech.active and now-starts[needed-1]['monotonic']>=.6:
                if self.stage=='first':self.stage='second';return 'cancel'
                self.stage='paused';self.resume_at=now+2.;return 'toggle_pause'
        elif self.stage=='paused' and now>=self.resume_at:
            self.stage='complete';self.resumed_at=now;return 'toggle_pause'
        return None
    def feedback(self,now):
        if self.stage=='complete':return 'eye_auto_resume' if now-self.resumed_at<3 else 'eye_speech'
        return {'first':'eye_auto_first','second':'eye_auto_second','paused':'eye_auto_pause'}.get(self.stage,'eye_speech')
