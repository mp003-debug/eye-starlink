"""Strictly fit a private candidate pack; never enable actions from training."""
from pathlib import Path
import sys,json,hashlib,argparse
r=Path(__file__).resolve().parents[1];sys.path[:0]=[str(r/'tools/deps/opencv'),str(r/'src')]
import cv2,numpy as np
from eye_tracker.appearance import CoarseAppearanceModel,appearance_feature
from eye_tracker.appearance_diagnostic import AppearanceDiagnostic,CornerMatcher
parser=argparse.ArgumentParser()
parser.add_argument('--feature-crop',choices=('legacy','eye_support_v1'),default='legacy')
parser.add_argument('--output',type=Path)
args=parser.parse_args()
src=r/'data/private/bringup/appearance_calibration_20261025/targets';entries=json.loads((src/'manifest.json').read_text())['samples_detail']
reference=np.frombuffer((src/entries[0]['raw']).read_bytes(),np.uint8).reshape(480,640).copy();box=(138,76,362,300)
corners=np.array([[154,184],[354,186]]);anchor=CornerMatcher(reference,box,corners,args.feature_crop);observations=[]
for i,e in enumerate(entries[:50]):
 raw=(src/e['raw']).read_bytes();assert hashlib.sha256(raw).hexdigest()==e['sha256'];im=np.frombuffer(raw,np.uint8).reshape(480,640)
 patch,_=anchor.align(im);observations.append(dict(frame_id=e['sha256'],target=e['target'],visit=e['visit'],feature=appearance_feature(patch)))
geometry=hashlib.sha256(reference.tobytes()).hexdigest()
model=CoarseAppearanceModel.fit(observations,geometry,discriminative=True)
rows=[]
for i,e in enumerate(observations):
 guess=model.propose(e['feature'],geometry);rows.append(dict(sample=i,instructed=e['target'],candidate=guess['target'],reason=guess['reason'],distance=guess['distance'],ratio=guess['ratio']))
meta={'feature_crop_mode':args.feature_crop,'reference_feature_crop':list(anchor.crop),'alignment':'corners_and_session_reference','feature_metric':'training_fisher_v1','strict_training_passed':True,'diagnostic_only':True,'actions_enabled':False,'calibration_passed':False,'source_manifest_sha256':hashlib.sha256((src/'manifest.json').read_bytes()).hexdigest(),'training_ids':[x['frame_id'] for x in observations],'training_conflicts':[x for x in rows if x['candidate'] not in (None,x['instructed'])],'training_rejections':[x for x in rows if x['candidate'] is None],'seed_policy':'helper-marked first fitting image, known subject geometry','metric_policy':'between/within variation; variance floor .0025; 5x5 smoothing; clip .1..3 then mean-one. Fitting images only. Gates .09/.75/.015 and temporal filter unchanged.','protocol':'Candidate-only. All prior captures now development data. Fresh positive and negative checks required before actions.'}
assert not model.enabled and not meta['training_conflicts']
out=args.output or r/'data/private/analysis/appearance_calibration_20261025';out.mkdir(parents=True,exist_ok=True);path=out/'diagnostic_model.npz'
np.savez_compressed(path,reference=reference,box=np.array(box),corners=corners,metric_weights=model.metric_weights,metadata=np.array(json.dumps(meta)),**{'template_'+k:v for k,v in model.templates.items()})
engine=AppearanceDiagnostic(path)
report=dict(meta,pack_sha256=engine.pack_sha256,training_rows=rows,weight_min=float(model.metric_weights.min()),weight_max=float(model.metric_weights.max()))
(out/'diagnostic_pack.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('training_ids','training_rows')},indent=2))
