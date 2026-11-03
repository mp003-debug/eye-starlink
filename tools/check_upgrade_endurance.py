"""Observe a 20-minute real-eye run; never generates input or playback actions."""
import argparse,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools')]
from eye_tracker.trial_limits import EventHistory

class Observer:
    def __init__(self,clock=time.monotonic,emit=None):
        self.clock=clock;self.emit=emit;self.started=clock();self.last_emit=self.started
        self.events=EventHistory(256);self.previous=None;self.last_poll=None
        self.max_poll_gap=0.;self.playing_observed_seconds=0.
    def observe(self,player,before):
        now=self.clock();state=(player.index,player.state)
        if self.last_poll is not None:
            gap=now-self.last_poll
            self.max_poll_gap=max(self.max_poll_gap,gap)
            if self.previous and self.previous[1]=='playing':self.playing_observed_seconds+=gap
        self.last_poll=now
        track=player.library.tracks[player.index]
        row=dict(elapsed_seconds=now-self.started,track_index=player.index,track_id=track['id'],
                 state=player.state,position_samples=player.offset,total_samples=track['frames'])
        if state!=self.previous:
            self.events.append(dict(row,event='state'))
        if player.state=='ended' and before!='ended':
            self.events.append(dict(row,event='natural_end',sample_count_matches=player.offset==track['frames']))
        changed=state!=self.previous
        self.previous=state
        if self.emit and (changed or now-self.last_emit>=30):
            self.last_emit=now;self.emit(dict(row,event='progress'))
    def summary(self):
        return dict(events=list(self.events),retention=self.events.summary(),max_poll_gap_seconds=self.max_poll_gap,
                    playing_observed_seconds=self.playing_observed_seconds,
                    playing_time_scope='poll-interval approximation, not measured analog output duration')

def observed_player(base,observer):
    class ObservedPlayer(base):
        def poll(self):
            before=self.state
            result=super().poll()
            observer.observe(self,before)
            return result
    return ObservedPlayer

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--reposition-assist',action='store_true',help='use verified explicit helper-confirmed reference workflow')
    a=p.parse_args()
    output=a.output.resolve();output.relative_to(ROOT)
    if output.exists():raise ValueError('refuse to overwrite prior evidence')
    from upgrade_preflight import owners
    owners()
    from eye_tracker import launch,music
    plan=launch.prepare_launch('data/private/profiles/current_eye.json',ROOT,music=True,quick_phrases=True,reposition_assist=a.reposition_assist)
    if plan['profile_values']['duration_seconds']!=1200:raise ValueError('requires explicit 1200-second profile')
    output.mkdir(parents=True)
    observer=Observer(emit=lambda row:print(json.dumps(row),flush=True))
    original=music.MusicPlayer;music.MusicPlayer=observed_player(original,observer)
    code=None
    try:
        print(json.dumps(dict(event='launch',output=plan['output'],duration=1200,wireless=False,reposition_assist=a.reposition_assist)),flush=True)
        code=launch._invoke_board(plan['board_arguments'])
        return code
    finally:
        music.MusicPlayer=original
        run=Path(plan['output'])
        if run.is_dir():
            (run/'launch_profile.json').write_text(json.dumps(dict(plan,scope='observed real-eye launch; see result.json'),indent=2)+'\n')
        report=dict(observer.summary(),exit_code=code,run=plan['output'],scope='Observer only; original player poll called once; no generated gaze or controls.',
                    reposition_assist=a.reposition_assist,
                    gap_scope='Poll gaps and approximate playing time can include manual setup; natural_end sample counts are the full-track evidence.',
                    observer_file_sha256=__import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest())
        (output/'music_observation.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(dict(event='finished',exit_code=code,run=plan['output'])),flush=True)

if __name__=='__main__':sys.exit(main())
