"""Fit explicitly instructed current-session native samples; never self-label or enable."""
from pathlib import Path
import argparse,hashlib,json,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/deps/opencv'),str(ROOT/'src')]
from eye_tracker.appearance_diagnostic import AppearanceDiagnostic
from eye_tracker.appearance import CoarseAppearanceModel
p=argparse.ArgumentParser()
p.add_argument('--stage',type=Path,required=True)
p.add_argument('--source-model',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
args=p.parse_args()
report=json.loads((args.stage/'diagnostic.json').read_text())
engine=AppearanceDiagnostic(args.source_model)
assert report['completed'] and report['actions_enabled'] is False
assert report['model_pack_sha256']==engine.pack_sha256
assert engine.metadata.get('feature_crop_mode')=='eye_support_v1'
engine.anchor.origin_shift=np.array(report['reference_relocation']['origin_shift'])
src=args.stage/'targets';manifest=src/'manifest.json'
entries=json.loads(manifest.read_text())['samples_detail']
assert len(entries)==30 and len({e['sha256']for e in entries})==30
assert all(e['target']=='center' and e['visit']=='session_reference' for e in entries[:5])
assert all(e['visit']=='new_check' for e in entries[5:])
assert {k:sum(e['target']==k for e in entries[5:])for k in engine.model.LABELS}=={k:5 for k in engine.model.LABELS}
observations=[]
for i,e in enumerate(entries):
 raw=(src/e['raw']).read_bytes();assert hashlib.sha256(raw).hexdigest()==e['sha256']
 feature,_=engine.feature(np.frombuffer(raw,np.uint8).reshape(480,640))
 if i<5:
  engine.baseline.add(feature,i+1)
  if i==4:assert engine.baseline.finish()['ready']
 else:
  observations.append(dict(frame_id=e['sha256'],target=e['target'],visit='current_fit',feature=engine.baseline.correct(feature)))
model=CoarseAppearanceModel.fit(observations,engine.geometry_id,discriminative=True)
meta=dict(engine.metadata)
meta.update(template_visit_count=1,training_protocol='current_session_25',
 training_ids=[e['frame_id']for e in observations],training_counts={k:5 for k in model.LABELS},
 source_manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
 source_pack_sha256=engine.pack_sha256,strict_training_passed=True,diagnostic_only=True,actions_enabled=False,
 calibration_passed=False,protocol='Current-session fit from25 instructed examples; five earlier center references excluded. No validation from this stage. Fresh independent positive and invalid-input checks required.',
 training_conflicts=[],training_rejections=[dict(frame_id=e['frame_id'],target=e['target'])for e in observations if model.propose(e['feature'],engine.geometry_id)['target']is None])
args.output.mkdir(parents=True,exist_ok=True)
dest=args.output/'diagnostic_model.npz'
np.savez_compressed(dest,reference=engine.reference,box=np.array(engine.box),corners=engine.anchor.corners,
 metric_weights=model.metric_weights,metadata=np.array(json.dumps(meta)),
 **{'template_'+k:v for k,v in model.templates.items()})
loaded=AppearanceDiagnostic(dest)
assert not loaded.model.enabled
(args.output/'diagnostic_pack.json').write_text(json.dumps(dict(meta,pack_sha256=loaded.pack_sha256),indent=2)+'\n')
print(json.dumps(dict(pack_sha256=loaded.pack_sha256,strict_fit=True,validation=False,enabled=False)))
