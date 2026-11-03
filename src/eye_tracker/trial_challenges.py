"""Display-only challenge schedule; predictions never receive phase labels."""
from pathlib import Path
import json,math
import numpy as np

# Distinct post-action target tests recovery without clearing existing locks.
PLAN=tuple(dict(phase=phase,target=target,seconds=duration) for action,before,after in
           (("close","water","help"),("cover","rest","water"),
            ("leave","help","rest"),("blink","water","help"))
           for phase,target,duration in (("before_"+action,before,6.),
                                        ("challenge_"+action,before,8.),
                                        ("after_"+action,after,6.)))
DURATION=sum(p['seconds'] for p in PLAN)
ASSET=Path(__file__).resolve().parents[2]/'assets/trial_challenge_prompts.npz'

class TrialChallenges:
    def __init__(self,path=ASSET):
        with np.load(path,allow_pickle=False) as a:
            meta=json.loads(a['metadata'].tobytes().decode('utf8'))
            if meta['plan']!=list(PLAN):raise ValueError('challenge_plan_mismatch')
            self.tiles={p['phase']:a[p['phase']].copy() for p in PLAN}
        if any(x.shape!=(72,640) or x.dtype!=np.dtype('<u2') for x in self.tiles.values()):
            raise ValueError('challenge_tile_geometry')
        self.current=None;self.shown=None;self.presentations=[]
    def due(self,elapsed):
        if not math.isfinite(elapsed) or elapsed<0:raise ValueError('challenge_clock')
        end=0.
        for step,p in enumerate(PLAN):
            end+=p['seconds']
            if elapsed<end:return step
        return len(PLAN)-1
    def decorate(self,frame,step):
        if type(step) is not int or not 0<=step<len(PLAN):raise ValueError('challenge_step')
        words=np.frombuffer(frame,dtype='<u2').reshape(480,640).copy()
        words[:72]=self.tiles[PLAN[step]['phase']]
        return words.tobytes()
    def presented(self,step,now):
        if not math.isfinite(now):raise ValueError('challenge_clock')
        if step==self.current:return
        if step!=(0 if self.current is None else self.current+1):raise ValueError('challenge_step_skipped')
        if self.shown is not None and now<self.shown:raise ValueError('challenge_clock')
        self.current,self.shown=step,now
        self.presentations.append(dict(step=step,phase=PLAN[step]['phase'],shown_monotonic=now))
    def annotate(self,row,requested):
        if self.current is None or requested<self.shown:raise ValueError('challenge_capture_before_prompt')
        # The call occurs AFTER the real classifier/controller consumed the frame.
        row.update(prompt_phase=PLAN[self.current]['phase'],
                   instructed_target=PLAN[self.current]['target'],
                   requested_monotonic=requested,after_prompt_s=row['copied_monotonic']-self.shown,
                   action_label_verified=False)
    def report(self):
        return dict(plan=list(PLAN),presentations=self.presentations,
                    prompt_labels_are_ground_truth=False,prompts_modify_predictions=False,
                    prompt_scope='Top banner only; real buttons, dwell, locks and invalid handling unchanged.')
