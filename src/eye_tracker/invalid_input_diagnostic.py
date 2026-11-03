"""Bounded invalid-input evidence capture with a frozen candidate engine.

Prompts NEVER mark predictions invalid or enter the classifier. Challenge frames
include action transitions and returns, so inspection is required for labels.
"""
import hashlib,json,time
from pathlib import Path
import numpy as np
from PIL import Image
from .fixation import FixationRecording,POINTS,checked_plan

CHALLENGES=(('water','close'),('help','cover'),('rest','leave'),('more','blink'))
PLAN=checked_plan([('center',POINTS['center'],'session_reference')]+[
    (target,POINTS[target],visit)
    for target,action in CHALLENGES
    for visit in ('before_'+action,'challenge_'+action,'after_'+action)])
DURATIONS=tuple(8. if visit.startswith('challenge_') else 6. for _,_,visit in PLAN)
ASSET=Path(__file__).resolve().parents[2]/'assets/invalid_input_prompts.npz'

class InvalidInputRenderer:
    def __init__(self):
        self.plan=PLAN
        with np.load(ASSET,allow_pickle=False) as data:
            self.frames={key:data[key].copy() for key in data.files if key!='metadata'}
            meta=json.loads(data['metadata'].tobytes().decode('utf8'))
        if meta['plan']!=[list((n,list(p),v)) for n,p,v in PLAN]:raise ValueError('prompt plan mismatch')
        if set(self.frames)!=set(['intro']+[v for _,_,v in PLAN]):raise ValueError('missing prompt frames')
        if any(a.shape!=(480,640) or a.dtype!=np.dtype('uint16') for a in self.frames.values()):raise ValueError('RGB565 prompt geometry')
    def frame(self,step=None):
        return self.frames['intro' if step is None else self.plan[step][2]].astype('<u2',copy=False).tobytes()

class InvalidInputRecording(FixationRecording):
    MAX_ROWS=2400
    MAX_AUDIT=720
    def __init__(self,engine,clock=time.monotonic):
        super().__init__(PLAN);self.engine=engine;self.clock=clock;self.rows=[];self.audit=[]
    def observe(self,pixels,index,requested,copied,presented,step):
        before=len(self.samples);super().observe(pixels,index,requested,copied,presented,step)
        if len(self.rows)>=self.MAX_ROWS:raise ValueError('bounded diagnostic capacity exceeded')
        phase=self.plan[step][2];reference=phase=='session_reference'
        if reference:
            value=self.engine.observe_reference(pixels,index,copied,len(self.samples)>before,self.clock)
        else:
            self.engine.baseline.finish()
            value=self.engine.observe(pixels,index,copied,self.clock)
        # Attach instructions after prediction. In particular, never substitute
        # None because the prompt says "close", "cover" or "leave".
        row=dict(value,frame_index=index,requested_monotonic=requested,copied_monotonic=copied,
                 phase=phase,instructed_target=self.plan[step][0],step=step,
                 after_present_s=copied-presented,
                 scored_positive=not reference and not phase.startswith('challenge_') and requested-presented>=2.,
                 action_label_verified=False)
        if phase.startswith('challenge_'):
            if len(self.audit)>=self.MAX_AUDIT:raise ValueError('bounded audit image capacity exceeded')
            name='frame_%06d.png'%index
            row['audit_png']=name
            self.audit.append((dict(frame_index=index,phase=phase,copied_monotonic=copied,
                                    after_present_s=copied-presented,png=name),
                               pixels[::2,::2].copy()))
        self.rows.append(row)
    def save(self,output,completed):
        result=super().save(output,completed);root=Path(output);dest=root/'audit';dest.mkdir(exist_ok=False)
        details=[]
        for meta,pixels in self.audit:
            p=dest/meta['png'];Image.fromarray(pixels).save(p)
            details.append(dict(meta,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
        (dest/'manifest.json').write_text(json.dumps({'format':'320x240 GRAY8, every captured challenge frame, nearest factor2',
            'labels_verified':False,'frames':details},indent=2)+'\n')
        counts={}
        for row in self.rows:
            p=row['phase']
            c=counts.setdefault(p,dict(frames=0,raw_accepted=0,stable_accepted=0,
                settled_positive_frames=0,settled_raw_wrong=0,settled_stable_matching=0,
                settled_stable_wrong=0,settled_rejected=0))
            c['frames']+=1;c['raw_accepted']+=row['candidate'] is not None;c['stable_accepted']+=row['stable_candidate'] is not None
            if row['scored_positive']:
                c['settled_positive_frames']+=1
                c['settled_raw_wrong']+=row['candidate'] not in (None,row['instructed_target'])
                c['settled_stable_matching']+=row['stable_candidate']==row['instructed_target']
                c['settled_stable_wrong']+=row['stable_candidate'] not in (None,row['instructed_target'])
                c['settled_rejected']+=row['stable_candidate'] is None
        summary={'completed':bool(completed),'scope':'Frozen candidate-only challenge observation; no actions; inspect image evidence before labeling invalid periods',
            'model_pack_sha256':self.engine.pack_sha256,'center_reference':self.engine.baseline.summary,
            'reference_relocation':self.engine.relocation,'rows':len(self.rows),'audit_images':len(details),
            'counts':counts,'actions_enabled':False,'invalid_input_verified':False,'calibration_enabled':False,
            'prompt_labels_are_ground_truth':False,'post_return_reference_updated':False}
        (root/'invalid_input.json').write_text(json.dumps(dict(summary,frames=self.rows),indent=2)+'\n')
        result['invalid_input_diagnostic']=summary
        return result

def run_invalid_input(session,renderer,recording,clock=time.monotonic,sleep=time.sleep):
    if renderer.plan!=recording.plan or recording.plan!=PLAN:raise ValueError('prompt/recording plan mismatch')
    started=clock()
    while clock()-started<6.:session.display_health();sleep(.02)
    before=session.wait_native_frames(2);presentations=[]
    for step,duration in enumerate(DURATIONS):
        session.present(renderer.frame(step));shown=clock()
        presentations.append(dict(step=step,phase=PLAN[step][2],confirmed_elapsed_s=shown-started,duration_s=duration))
        while clock()-shown<duration:
            pixels=session.capture_once();info=session.last_capture
            recording.observe(pixels,session.capture_index,info['requested_at_monotonic'],
                info['copied_at_monotonic'],shown,step)
    after=session.wait_native_frames(1)
    if any(after[k]!=before[k] for k in ('bad_lines','bad_frames')):raise RuntimeError('camera errors increased during challenge')
    return dict(elapsed_seconds=clock()-started,camera_frames=recording.frames,presentations=presentations,
                diagnostic_before=before,diagnostic_after=after,calibration_fitted=False,gaze_and_speech_enabled=False)

