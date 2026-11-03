"""Private challenge review: every challenge frame; never infer gaze from prompts."""
from pathlib import Path
from collections import Counter
import argparse,json,hashlib,math
from PIL import Image,ImageDraw
p=argparse.ArgumentParser();p.add_argument('stage',type=Path);args=p.parse_args();root=args.stage
report=json.loads((root/'visual_trial.json').read_text(encoding='utf8'));rows=report['rows'];images={x['frame_index']:x for x in report['images']}
out=root/'review';out.mkdir(exist_ok=True);index=[];counts={}
def sheets(name,chosen):
 for page in range(math.ceil(len(chosen)/30)):
  group=chosen[page*30:(page+1)*30];canvas=Image.new('RGB',(1600,math.ceil(len(group)/5)*262),'white');draw=ImageDraw.Draw(canvas)
  for j,row in enumerate(group):
   meta=images[row['frame_index']];path=root/'interaction'/meta['png'];assert hashlib.sha256(path.read_bytes()).hexdigest()==meta['sha256']
   x=j%5*320;y=j//5*262;canvas.paste(Image.open(path).convert('RGB'),(x,y+22));text=str(row['frame_index'])+' '+str(row['candidate'])+'/'+str(row['stable_candidate'])+' p='+format(row['progress'],'.2f')+' '+str(row['visual_selection']);draw.text((x+2,y+2),text,fill='#b00020' if row['stable_candidate'] is not None else 'black')
  file=name+'_'+str(page)+'.png';canvas.save(out/file);index.append(dict(file=file,frames=[x['frame_index'] for x in group]))
for phase in dict.fromkeys(row['prompt_phase'] for row in rows):
 current=[row for row in rows if row['prompt_phase']==phase];counts[phase]=dict(frames=len(current),raw=dict(Counter(x['candidate'] or 'null' for x in current)),stable=dict(Counter(x['stable_candidate'] or 'null' for x in current)))
 if phase.startswith('challenge_'):sheets(phase,current)
selected=set()
for i,row in enumerate(rows):
 if row['visual_selection']:selected.update(range(max(0,i-1),min(len(rows),i+2)))
sheets('events',[rows[i] for i in sorted(selected)])
(out/'sheets.json').write_text(json.dumps(index,indent=2)+'\n');print(json.dumps(dict(sheets=index,counts=counts,events=report['visual_selections']),indent=2))
