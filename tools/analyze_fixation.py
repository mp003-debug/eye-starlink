"""Private offline inspection of instructed targets; no gaze or calibration decisions."""
from pathlib import Path
import hashlib,json,sys
r=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(r/'tools/deps/opencv'),str(r/'src')]
from PIL import Image,ImageDraw
import numpy as np
from eye_tracker.eye_region import CascadeEyes,normalize_boxes
src=r/'data/private/bringup/fixation';out=r/'data/private/analysis/fixation';out.mkdir(parents=True,exist_ok=True)
m=json.loads((src/'targets/manifest.json').read_text());det= CascadeEyes();rows=[]
canvas=Image.new('RGB',(1000,9*220),'#eeeeee');draw=ImageDraw.Draw(canvas)
for i,entry in enumerate(m['samples_detail']):
 raw=(src/'targets'/entry['raw']).read_bytes()
 assert hashlib.sha256(raw).hexdigest()==entry['sha256']
 a=np.frombuffer(raw,np.uint8).reshape(480,640)
 boxes=normalize_boxes(det(a,None)); row=dict(entry,eye_proposals=boxes);rows.append(row)
 if boxes:
  x0,y0,x1,y1=boxes[0];cx=(x0+x1)//2;cy=(y0+y1)//2
  x=max(0,min(460,cx-90));y=max(0,min(300,cy-90))
  tile=Image.fromarray(a[y:y+180,x:x+180]).convert('RGB')
  row['inspection_crop_xyxy']=[x,y,x+180,y+180]
 else:tile=Image.fromarray(a).resize((180,135)).convert('RGB')
 bx=entry['slot']*200;by=entry['step']*220
 canvas.paste(tile,(bx,by+30))
 draw.text((bx+2,by+2),str(i)+' '+entry['target']+' '+entry['visit'],fill='black')
canvas.save(out/'contact.png')
result={'scope':'unlabelled eye proposals and visual contact sheet; target instructions are not measured gaze','samples':len(rows),'with_eye_proposals':sum(bool(x['eye_proposals']) for x in rows),'entries':rows,'calibration_fitted':False}
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='entries'}))
