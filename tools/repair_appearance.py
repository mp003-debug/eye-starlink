"""Reproducible development-only comparison; never installs/enables a model."""
from pathlib import Path
import sys,json,hashlib,collections
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/deps/opencv'),str(ROOT/'src')]
import numpy as np,cv2
from PIL import Image,ImageDraw
from eye_tracker.appearance_diagnostic import AppearanceDiagnostic
from eye_tracker.appearance import appearance_feature,CoarseAppearanceModel
OUT=ROOT/'data/private/analysis/appearance_repair';OUT.mkdir(exist_ok=True)
STAGES=('appearance_calibration_20261025','appearance_check_20261025','appearance_center_check_20261025','appearance_relocated_check_20261025','invalid_input_20261025')
PACK=ROOT/'data/private/analysis/appearance_calibration_20261025/diagnostic_model.npz'
if not (OUT/'aligned.npz').exists():
 rows=[];patches=[];sources={}
 for stage in STAGES:
  src=ROOT/'data/private/bringup'/stage/'targets';manifest=src/'manifest.json';entries=json.loads(manifest.read_text())['samples_detail'];sources[stage]=hashlib.sha256(manifest.read_bytes()).hexdigest();eng=AppearanceDiagnostic(PACK)
  first=next(e for e in entries if e['target']=='center');im=np.frombuffer((src/first['raw']).read_bytes(),np.uint8).reshape(480,640)
  eng.anchor.acquire(im)
  for i,e in enumerate(entries):
   raw=(src/e['raw']).read_bytes();assert hashlib.sha256(raw).hexdigest()==e['sha256'];im=np.frombuffer(raw,np.uint8).reshape(480,640)
   row=dict(stage=stage,sample=i,frame_index=e['frame_index'],target=e['target'],visit=e['visit'],raw_sha256=e['sha256'],patch_index=None)
   try:
    patch,metrics=eng.anchor.align(im);row.update(patch_index=len(patches),metrics=metrics);patches.append(patch)
   except ValueError as exc:row['rejection']=str(exc)
   rows.append(row)
 np.savez_compressed(OUT/'aligned.npz',patches=np.asarray(patches),rows=np.array(json.dumps(rows)),sources=np.array(json.dumps(sources)))
with np.load(OUT/'aligned.npz',allow_pickle=False) as a:patches=a['patches'].copy();rows=json.loads(str(a['rows'].item()));sources=json.loads(str(a['sources'].item()))
# Crop anatomical eye support using the two already established reference corners,
# not a parameter chosen on the checking target: patch coordinates x38..238,y52.
# Keep upper/lower iris and lids, remove distant skin/nose.
def feature(patch,mode):
 if mode=='eye_crop':patch=patch[12:108,28:248]
 return appearance_feature(patch)
results={}
for mode in ('original','eye_crop','fisher_weight'):
 F={j:feature(patches[r['patch_index']],mode) for j,r in enumerate(rows) if r['patch_index'] is not None}
 train=[j for j,r in enumerate(rows) if r['stage']==STAGES[0] and r['visit'].startswith('fit_') and j in F]
 templates={k:np.array([np.median([F[j] for j in train if rows[j]['target']==k and rows[j]['visit']==v],axis=0) for v in ('fit_a','fit_b')]) for k in CoarseAppearanceModel.LABELS}
 weights=np.ones(1152)
 if mode=='fisher_weight':
  means={k:np.median(np.array([F[j] for j in train if rows[j]['target']==k]),axis=0) for k in templates}
  between=np.var(np.array(list(means.values())),axis=0);within=np.mean(np.array([(F[j]-means[rows[j]['target']])**2 for j in train]),axis=0)
  importance=cv2.GaussianBlur((between/(within+.0025)).reshape(24,48),(5,5),0).ravel()
  weights=np.clip(importance,.1,3);weights/=weights.mean()
 def propose(f):
  ds=sorted((float(np.min(np.sqrt(np.mean(weights*(t-f)**2,axis=1)))),k) for k,t in templates.items());(best,k),(runner,_)=ds[:2]
  valid=best<=.09 and best/max(runner,1e-9)<=.75 and runner-best>=.015
  return k if valid else None,dict(best=best,runner=runner,ratio=best/max(runner,1e-9),margin=runner-best,nearest=k)
 per=[];offsets={}
 for stage in STAGES:
  center=[j for j,r in enumerate(rows) if r['stage']==stage and r['target']=='center' and (r['visit']=='session_reference' or stage==STAGES[1] and r['visit']=='new_check') and j in F]
  if stage==STAGES[0]:offsets[stage]=np.zeros(1152)
  elif len(center)>=3:offsets[stage]=np.median([F[j] for j in center[:5]],axis=0)-np.median(templates['center'],axis=0)
  else:
   center=[j for j,r in enumerate(rows) if r['stage']==stage and r['target']=='center' and j in F][:5]
   offsets[stage]=np.median([F[j] for j in center],axis=0)-np.median(templates['center'],axis=0)
 for j,r in enumerate(rows):
  v=dict(stage=r['stage'],sample=r['sample'],visit=r['visit'],target=r['target'],frame_index=r['frame_index'],candidate=None)
  if j in F:v['candidate'],v['metrics']=propose(np.clip(F[j]-offsets[r['stage']],0,1))
  else:v['rejection']=r['rejection']
  per.append(v)
 counts={}
 for stage in STAGES:
  part=[x for x in per if x['stage']==stage and x['visit']!='session_reference' and not x['visit'].startswith('challenge')];c=collections.Counter('reject' if x['candidate'] is None else 'match' if x['candidate']==x['target'] else 'wrong' for x in part)
  c['wrong_ids']=[(x['sample'],x['target'],x['candidate']) for x in part if x['candidate'] not in (None,x['target'])];counts[stage]=dict(c)
 results[mode]={'counts':counts,'training_wrong':[v for v in per[:50] if v['candidate'] not in (None,v['target'])],'last_open_more':per[-5:],'rows':per,'weight_range':[float(weights.min()),float(weights.max())]}
 selected=[j for j,r in enumerate(rows) if r['stage']==STAGES[0] and r['sample'] in (0,5,10,15,20,40,42,45) or r['stage']==STAGES[-1] and r['sample']>=60]
 canvas=Image.new('RGB',(604,155*((len(selected)+1)//2)),'white');draw=ImageDraw.Draw(canvas)
 for k,j in enumerate(selected):
  row=rows[j];x=k%2*302;y=k//2*155;canvas.paste(Image.fromarray(patches[row['patch_index']]).convert('RGB'),(x,y+20));draw.text((x,y),str(j)+' '+row['target']+' '+str(row['sample']),fill='black')
 canvas.save(OUT/'aligned_review.png')
report={'scope':'All listed source captures are now DEVELOPMENT data. No independent acceptance and no board/runtime/model edits. Candidate comparisons use first50 fitting samples only.','sources':sources,'results':results}
(OUT/'comparison.json').write_text(json.dumps(report,indent=2))
print(json.dumps({k:{kk:vv for kk,vv in v.items() if kk in ('counts','training_wrong','last_open_more','weight_range')} for k,v in results.items()},indent=2))
