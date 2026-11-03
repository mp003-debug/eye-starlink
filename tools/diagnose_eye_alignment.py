"""Replay development captures; center-reference frames are excluded from checks."""
from pathlib import Path
import sys,json,collections,hashlib
r=Path(__file__).resolve().parents[1];sys.path[:0]=[str(r/'tools/deps/opencv'),str(r/'src')]
import numpy as np
from eye_tracker.appearance_diagnostic import AppearanceDiagnostic
eng=AppearanceDiagnostic(r/'data/private/analysis/appearance_calibration_20261025/diagnostic_model.npz')
rows=[];features={}
for stage in ('appearance_calibration_20261025','appearance_check_20261025'):
 s=r/'data/private/bringup'/stage/'targets';entries=json.loads((s/'manifest.json').read_text())['samples_detail']
 for i,e in enumerate(entries):
  raw=(s/e['raw']).read_bytes();assert hashlib.sha256(raw).hexdigest()==e['sha256'];im=np.frombuffer(raw,np.uint8).reshape(480,640)
  row=dict(stage=stage,sample=i,target=e['target'],visit=e['visit']);idx=len(rows)
  try:
   f,mt=eng.feature(im);features[idx]=f;row['metrics']=mt;row['uncorrected']=eng.model.propose(f,eng.geometry_id)
  except ValueError as exc:row['rejection']=str(exc)
  rows.append(row)
for i in range(85,90):
 if i in features:eng.baseline.add(features[i],i+1)
reference=eng.baseline.finish();counts=collections.Counter()
for i in range(75,100):
 row=rows[i];row['used_for_reference']=85<=i<90
 guess=eng.model.propose(eng.baseline.correct(features[i]),eng.geometry_id) if i in features else dict(target=None,reason=row['rejection']);row['corrected']=guess
 if row['used_for_reference']:continue
 counts['rejected' if guess['target'] is None else 'matched_instruction' if guess['target']==row['target'] else 'wrong']+=1
result={'scope':'development only; both captures inspected; no actions; reference center 5 images excluded from 20 non-center counts','reference':reference,'noncenter_counts':dict(counts),'model_sha256':eng.pack_sha256,'rows':rows}
out=r/'data/private/analysis/appearance_calibration_20261025/corner_alignment_development.json';out.write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
