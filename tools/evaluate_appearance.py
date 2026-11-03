"""Frozen appearance prototype evaluation; instructed targets are not measured gaze."""
from pathlib import Path
import sys,json,hashlib,time,argparse
r=Path(__file__).resolve().parents[1];sys.path[:0]=[str(r/'tools/deps/opencv'),str(r/'src')]
import numpy as np
from PIL import Image,ImageDraw
from eye_tracker.appearance import EyeAnchor,AlignmentFailure,appearance_feature,CoarseAppearanceModel
from eye_tracker.eye_region import CascadeEyes,normalize_boxes
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source',type=Path,default=r/'data/private/bringup/fixation/targets')
parser.add_argument('--output',type=Path,default=r/'data/private/analysis/appearance')
parser.add_argument('--fresh-checks',action='store_true')
parser.add_argument('--seed-box',type=int,nargs=4,metavar=('X0','Y0','X1','Y1'),help='helper-marked eye box from first training frame only')
args=parser.parse_args();src=args.source;out=args.output;out.mkdir(parents=True,exist_ok=True)
m=json.loads((src/'manifest.json').read_text());entries=m['samples_detail'];images=[]
for e in entries:
 raw=(src/e['raw']).read_bytes();assert hashlib.sha256(raw).hexdigest()==e['sha256'];images.append(np.frombuffer(raw,np.uint8).reshape(480,640))
if not images or entries[0]['target']!='center':raise ValueError('center reference required')
source_hash=hashlib.sha256((r/'src/eye_tracker/appearance.py').read_bytes()).hexdigest()
if args.fresh_checks:
 frozen=json.loads((r/'config/appearance_evaluation.json').read_text())
 if hashlib.sha256((src/'manifest.json').read_bytes()).hexdigest() in frozen.get('development_manifest_sha256',[]):raise ValueError('development data cannot be presented as fresh checks')
 if source_hash!=frozen['source_sha256']:raise ValueError('algorithm changed since protocol freeze')
 if hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=frozen['evaluation_script_sha256']:raise ValueError('evaluator changed since protocol freeze')
 if args.seed_box:
  setup=frozen['setup_override']
  if args.seed_box!=setup['seed_box'] or hashlib.sha256(images[0].tobytes()).hexdigest()!=setup['reference_sha256']:raise ValueError('setup differs from recorded training-only choice')
seed_boxes=normalize_boxes([args.seed_box]) if args.seed_box else normalize_boxes(CascadeEyes()(images[0],None))
if not seed_boxes:raise ValueError('no initial eye region; inspect reference, do not guess')
seed=seed_boxes[0];anchor=EyeAnchor(images[0],seed);geometry=hashlib.sha256(images[0].tobytes()).hexdigest()
rows=[];features={};steps=max(x['step'] for x in entries)+1
canvas=Image.new('RGB',(1000,steps*150),'#eee');draw=ImageDraw.Draw(canvas)
for i,(e,a) in enumerate(zip(entries,images)):
 t=time.perf_counter();row={'sample':i,'frame_id':e['raw'],'target':e['target'],'visit':e['visit'],'step':e['step']}
 try:
  patch,metrics=anchor.align(a);features[i]=appearance_feature(patch);row.update(aligned=True,metrics=metrics)
  tile=Image.fromarray(patch).resize((190,100));canvas.paste(tile,(e['slot']*200,e['step']*150+35))
 except (ValueError,AlignmentFailure) as exc:row.update(aligned=False,error=str(exc))
 row['local_ms']=(time.perf_counter()-t)*1000;rows.append(row)
 draw.text((e['slot']*200+2,e['step']*150+3),str(i)+' '+e['target']+' '+e['visit'],fill='black')
training=[dict(frame_id=entries[i]['raw'],target=entries[i]['target'],visit=entries[i]['visit'],feature=f) for i,f in features.items() if entries[i]['visit'] in ('first','fit_a','fit_b')]
try:
 model=CoarseAppearanceModel.fit(training,geometry)
 for row in rows:
  if row['sample'] in features:row['gated']=model.propose(features[row['sample']],geometry)
 checks=[dict(frame_id=x['frame_id'],target=x['target'],feature=features.get(x['sample'])) for x in rows if x['visit'] in ('repeat','check')]
 validation=model.validate(checks,geometry)
 positives=validation['counts'];ready=all(positives[k]['total']>=5 and positives[k]['correct']>=.6*positives[k]['total'] and positives[k]['wrong']==0 for k in model.LABELS)
 model_state={'constructed':True,'enabled':model.enabled,'training_support':model.training_support,'validation':validation,'positive_check_passed':ready,'invalid_input_trials_complete':False}
except ValueError as exc:model_state={'constructed':False,'enabled':False,'reason':str(exc)}
result={'scope':'Offline feasibility; instructions are labels, not measured gaze; no buttons or PCCR','source_manifest_sha256':hashlib.sha256((src/'manifest.json').read_bytes()).hexdigest(),'seed_box':seed,'seed_method':'helper-marked first training frame' if args.seed_box else 'automatic cascade','evaluation_status':('new checks with frozen classifier; setup amendment recorded before check inspection' if args.seed_box else 'new data checked with frozen code') if args.fresh_checks else 'development data already inspected; not independent acceptance','aligned':sum(x['aligned'] for x in rows),'samples':len(rows),'model':model_state,'rows':rows,'runtime_source_sha256':source_hash}
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');canvas.save(out/'aligned.png')
print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
