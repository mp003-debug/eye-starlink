"""Nonblocking local video control, with PL-consumed audio as the A/V clock."""
import time
from types import SimpleNamespace
from .video_library import FPS
from .video_decode import Decoder
from .music import MusicPlayer

# PYNQ cold interpreter/OpenCV spawn measured 8.743 s (CPU-only, 2026-11-01).
# This bounds media startup only; the UI/helper loop keeps polling throughout.
STARTUP_TIMEOUT=15.

class VideoPlayer:
    def __init__(self,library,device,clock=time.monotonic,decoder_factory=Decoder):
        self.library,self.device,self.clock,self.factory=library,device,clock,decoder_factory
        self.index=0;self.state='stopped';self.offset=0.;self.anchor=clock()
        self.frame=None;self.frame_index=-1;self.decoder=None;self.retired=None;self.audio=None
        self.error=None;self.started=clock();self.last_frame_at=clock();self.pending=None
        self.stats=dict(starts=0,pauses=0,ends=0,faults=0,decoded_frames=0,skipped_frames=0)

    @property
    def clip(self):return self.library.clips[self.index] if self.library.clips else None
    @property
    def duration(self):return self.clip['frames']/FPS if self.clip else 0.
    @property
    def position(self):
        if self.audio is not None:return min(self.duration,self.audio.offset/16000)
        return min(self.duration,self.offset+(self.clock()-self.anchor if self.state=='playing' else 0.))

    def _retire(self):
        if self.decoder is not None:
            self.decoder.stop();self.retired=self.decoder;self.decoder=None
    def _reap(self):
        if self.retired is not None and self.retired.reap():self.retired=None

    def play(self):
        if not self.clip or self.state in ('playing','loading'):return
        if self.state=='paused' and self.decoder is not None:
            # Resume first refreshes the frozen frame, then restarts the clock/audio.
            self.state='loading';self.started=self.clock();return
        self.stop();self._reap()
        if self.retired is not None:
            self.error='decoder_cleanup_pending';self.state='fault';return
        try:
            self.decoder=self.factory(self.clip);self.decoder.request(0)
            if self.clip['audio'] is not None:
                library=SimpleNamespace(tracks=[self.clip['audio']],volume=SimpleNamespace(percent=100))
                self.audio=MusicPlayer(self.device,library,self.clock)
            self.state='loading';self.started=self.clock();self.error=None;self.stats['starts']+=1
        except Exception as exc:self._fault(exc)

    def suspend(self):
        if self.state in ('playing','loading'):
            position=self.position
            if self.audio is not None:self.audio.suspend();position=self.audio.offset/16000
            self.offset=position;self.state='paused';self.stats['pauses']+=1

    def stop(self):
        if self.audio is not None:self.audio.stop();self.audio=None
        self._retire();self.state='stopped';self.offset=0.;self.frame=None;self.frame_index=-1;self.pending=None

    def next(self):
        self.stop()
        if self.library.clips:self.index=(self.index+1)%len(self.library.clips)

    def _fault(self,exc):
        # Propagate an audio STOP failure: hardware cleanup is not a UI-only fault.
        position=self.position
        if self.audio is not None:self.audio.stop()
        self.audio=None;self.offset=position;self._retire();self.state='fault';self.error=str(exc);self.stats['faults']+=1

    def poll(self):
        self._reap()
        if self.state not in ('playing','loading'):return
        try:
            if self.audio is not None:self.audio.poll()
            now=self.clock();wanted=min(self.clip['frames']-1,int(self.position*FPS))
            self.decoder.request(wanted)
            result=self.decoder.poll()
            if result is not None:self.pending=result
            if self.pending is not None and self.pending[0]<=wanted:
                index,frame=self.pending;self.pending=None
                if index>self.frame_index:
                    self.stats['skipped_frames']+=max(0,index-self.frame_index-1)
                    self.frame_index=index;self.frame=frame;self.stats['decoded_frames']+=1;self.last_frame_at=now
            if self.state=='loading':
                if self.frame_index>=wanted:
                    if self.audio is not None:self.audio.play()
                    self.anchor=now;self.last_frame_at=now;self.state='playing'
                elif now-self.started>STARTUP_TIMEOUT:raise ValueError('video startup timeout')
                return
            if self.position>=self.duration:
                self.offset=self.duration
                if self.audio is not None:self.audio.stop();self.audio=None
                self.state='ended';self.stats['ends']+=1;self._retire();return
            if wanted-self.frame_index>FPS*.75 and now-self.last_frame_at>.75:raise ValueError('video decode fell behind')
        except Exception as exc:self._fault(exc)

    def action(self,command):
        if command=='video_toggle':
            if self.state in ('playing','loading'):self.suspend()
            else:self.play()
        elif command=='video_next':self.next()
        elif command in ('video_exit','video_controls'):self.suspend() if command=='video_controls' else self.stop()

    def snapshot(self):
        return dict(state=self.state,index=self.index,position_seconds=round(self.position,3),frame_index=self.frame_index,
                    error=self.error,**self.stats)

    def close(self):
        try:self.stop()
        finally:
            if self.retired is not None:
                if not self.retired.reap(1.):raise RuntimeError('video decoder cleanup failed')
                self.retired=None
