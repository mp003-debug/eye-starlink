"""One fixed utterance, using audio v2 banks only when it exceeds short RAM.

No queue, pause or resume: helper interruption discards the utterance.
"""
import time
import numpy as np
from .audio import AudioError
from .music import BANK_SAMPLES


class PhraseAudioDevice:
    def __init__(self,short_device,stream_device,clock=time.monotonic):
        self.short,self.stream,self.clock=short_device,stream_device,clock
        self.streaming=False;self.samples=None;self.position=0;self.next_bank=0;self.deadline=None

    def status(self):return self.short.status()

    def stop(self):
        try:
            if self.streaming:self.stream.stop()
            else:self.short.stop()
        finally:
            self.streaming=False;self.samples=None;self.deadline=None

    def _fill(self):
        for _ in range(2):
            if self.position==len(self.samples) or self.stream.snapshot()['banks']&(1<<self.next_bank):return
            end=min(self.position+BANK_SAMPLES,len(self.samples))
            self.stream.submit(self.next_bank,self.samples[self.position:end],end==len(self.samples))
            self.position=end;self.next_bank^=1

    def play(self,samples):
        if not isinstance(samples,np.ndarray) or samples.dtype!=np.dtype('<i2') or samples.ndim!=1 or not 0<len(samples)<=128000:
            raise ValueError('fixed phrase requires bounded PCM16 up to 8 seconds')
        if self.streaming or self.status()&1:raise AudioError('audio busy; no phrase queue')
        if len(samples)<=32768:
            self.short.play(samples);return
        try:
            self.stream.prepare();self.streaming=True;self.samples=samples
            self.position=0;self.next_bank=0;self._fill();self.stream.start()
            self.deadline=self.clock()+len(samples)/16000+.25
        except BaseException:
            try:self.stop()
            except Exception:pass
            raise

    def poll(self):
        if not self.streaming:return self.short.poll()
        try:
            state=self.stream.snapshot()
            if state['done']:
                if state['consumed']!=len(self.samples):raise AudioError('incomplete streamed phrase')
                self.streaming=False;self.samples=None;self.deadline=None
                return 'done'
            if not state['busy']:raise AudioError('phrase stopped without completion')
            if self.clock()>self.deadline:raise AudioError('bounded phrase playback timeout')
            self._fill();return 'busy'
        except BaseException:
            try:self.stop()
            except Exception:pass
            raise
