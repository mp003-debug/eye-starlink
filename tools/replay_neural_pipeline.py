"""Saved-image + simulated-clock replay of the existing dwell pipeline, no I/O."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/deps/opencv'),str(ROOT/'src')]
import numpy as np
from eye_tracker.neural import attach_neural,NeuralModel
from eye_tracker.appearance_diagnostic import AppearanceDiagnostic
from eye_tracker.appearance_trial import VisualTrial
from eye_tracker.interaction import DwellController
from eye_tracker.calibration import Context

def main():
    base=ROOT/'build/fixed_camera_calibration_20261103';out=ROOT/'build/neural_upgrade_20261103'
    model=NeuralModel(out/'model/model.npz');folder=base/'positive_01/targets'
    entries=json.loads((folder/'manifest.json').read_text())['samples_detail']
    def image(e):
        raw=(folder/e['raw']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==e['sha256']
        return np.frombuffer(raw,np.uint8).reshape(480,640)
    e=AppearanceDiagnostic(base/'candidate_01/model.npz')
    attach_neural(e,out/'model/model.npz',model.sha256)
    e.anchor.acquire(image(entries[0]))
    for i,r in enumerate(entries[:5]):f,_=e.feature(image(r));e.baseline.add(f,i+1)
    assert e.baseline.finish()['ready']
    t=VisualTrial.__new__(VisualTrial);t.token='offline-neural-replay'
    t.controller=DwellController(Context('offline','geometry','live'),t.token)
    t.selections=[];t.commands=[];t.audio_enabled=False;t.engine=e
    index=0;time=0.;records=[]
    for target in ('water','center','rest','center','help','center','more'):
        candidates=[r for r in entries[5:] if r['target']==target]
        # Repetition is deliberate behavioral simulation, not new eye evidence.
        for i in range(40 if target!='center' else 8):
            index+=1;time+=.1
            observation=e.observe(image(candidates[i%len(candidates)]),index,time,lambda:time+.01)
            action=t.feed(observation,index,time,time+.01)
            if action:records.append(dict(frame=index,key=action.key))
    assert [r['key'] for r in records]==['water','rest','help','more'],records
    # Neural failure during an unfinished dwell must not borrow old candidates.
    e.model.neural.guarded=lambda *args: (_ for _ in ()).throw(TimeoutError('injected'))
    index+=1;time+=.1
    observation=e.observe(image(entries[5]),index,time,lambda:time+.01)
    assert observation['candidate'] is None and observation['stable_candidate'] is None
    assert t.feed(observation,index,time,time+.01) is None
    result=dict(passed=True,frames_replayed=index,simulated_selections=records,
                source_unique_frames=30,simulated_clock=True,repeated_images=True,
                active_audio=False,active_wireless=False,board_tested=False,
                verifies=['explicit neural adapter','unchanged temporal and dwell gates','held-target lock','center release','neural failure rejects current frame'],
                not_evidence_of='human selection accuracy or runtime latency')
    (out/'pipeline_replay.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))

if __name__=='__main__':main()
