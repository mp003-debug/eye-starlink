"""Replay the current frozen candidate pack on already inspected native images."""
from pathlib import Path
import sys,json,hashlib,collections
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'tools/deps/opencv'),str(ROOT/'src')]
import numpy as np
from eye_tracker.appearance_diagnostic import AppearanceDiagnostic
PACK=ROOT/'data/private/analysis/appearance_calibration_20261025/diagnostic_model.npz'
STAGES=('appearance_check_20261025','appearance_center_check_20261025','appearance_relocated_check_20261025','invalid_input_20261025','appearance_weighted_check_20261025')
all_rows=[];summaries={}
for stage in STAGES:
 src=ROOT/'data/private/bringup'/stage/'targets';entries=json.loads((src/'manifest.json').read_text())['samples_detail'];eng=AppearanceDiagnostic(PACK)
 center=[(i,e) for i,e in enumerate(entries) if e['target']=='center'][:5];reference_ids={e['sha256'] for i,e in center}
 def image(e):
  raw=(src/e['raw']).read_bytes();assert hashlib.sha256(raw).hexdigest()==e['sha256'];return np.frombuffer(raw,np.uint8).reshape(480,640)
 eng.anchor.acquire(image(center[0][1]))
 for j,(i,e) in enumerate(center):
  try:f,_=eng.feature(image(e));eng.baseline.add(f,j+1)
  except ValueError:pass
 baseline=eng.baseline.finish();counts=collections.Counter();wrong=[];neg=collections.Counter();more=[]
 labels=[]
 if (src.parent/'review/image_annotations.json').exists():
  annotation=json.loads((src.parent/'review/image_annotations.json').read_text())
  labels=[(g['label'],g['inclusive_frame_intervals']) for g in annotation['groups'] if g['label'] in ('fully_closed','occluded','eye_absent')]
 for i,e in enumerate(entries):
  if e['sha256'] in reference_ids:continue
  row=dict(stage=stage,sample=i,frame_index=e['frame_index'],target=e['target'],phase=e['visit'],candidate=None)
  try:f,metrics=eng.feature(image(e));guess=eng.model.propose(eng.baseline.correct(f),eng.geometry_id);row.update(candidate=guess['target'],classification=guess)
  except ValueError as exc:row['rejection']=str(exc)
  is_negative=any(lo<=e['frame_index']<=hi for _,intervals in labels for lo,hi in intervals)
  if is_negative:
   row['image_verified_invalid']=True;neg['total']+=1;neg['accepted' if row['candidate'] else 'rejected']+=1
  elif not e['visit'].startswith('challenge'):
   counts['rejected' if row['candidate'] is None else 'matching' if row['candidate']==e['target'] else 'wrong']+=1
   if row['candidate'] not in (None,e['target']):wrong.append(row)
  if e['visit']=='after_blink':more.append(row)
  all_rows.append(row)
 summaries[stage]=dict(baseline=baseline,positive=dict(counts),negative=dict(neg),wrong=wrong,after_blink=more)
report={'scope':'Native image development replay. All datasets were previously inspected. Raw samples spaced ~0.8 seconds cannot prove stream continuity or real dwell.','pack_sha256':hashlib.sha256(PACK.read_bytes()).hexdigest(),'model_enabled':False,'summary':summaries,'rows':all_rows}
out=ROOT/'data/private/analysis/appearance_repair/current_replay.json';out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2))
