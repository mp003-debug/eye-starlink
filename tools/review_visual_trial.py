"""Private visual feedback audit; program labels never label gaze truth."""
from pathlib import Path
import argparse,json,hashlib,math
from PIL import Image,ImageDraw
p=argparse.ArgumentParser();p.add_argument('stage',type=Path);args=p.parse_args();root=args.stage
report=json.loads((root/'visual_trial.json').read_text(encoding='utf8'))
rows=report['rows'];images={x['frame_index']:x for x in report['images']};selected=set()
for i,row in enumerate(rows):
 if row['visual_selection']:
  selected.update(range(max(0,i-2),min(len(rows),i+3)))
# Locate long rejected stretches for review; do not call these closed eyes.
segments=[];start=None
for i,row in enumerate(rows+[{'stable_candidate':'end'}]):
 if row['stable_candidate'] is None:
  if start is None:start=i
 elif start is not None:
  end=i-1
  if rows[end]['copied_monotonic']-rows[start]['copied_monotonic']>=.8:
   segments.append([rows[start]['frame_index'],rows[end]['frame_index']])
   selected.update([start,(start+end)//2,end])
  start=None
out=root/'review';out.mkdir(exist_ok=True)
indices=sorted(selected)
for page in range(math.ceil(len(indices)/20)):
 group=indices[page*20:(page+1)*20];canvas=Image.new('RGB',(1280,math.ceil(len(group)/4)*268),'white');draw=ImageDraw.Draw(canvas)
 for j,i in enumerate(group):
  row=rows[i];image=images[row['frame_index']];path=root/'interaction'/image['png']
  assert hashlib.sha256(path.read_bytes()).hexdigest()==image['sha256']
  x=j%4*320;y=j//4*268;canvas.paste(Image.open(path).convert('RGB'),(x,y+28))
  draw.text((x+2,y+2),str(row['frame_index'])+' '+str(row['candidate'])+'/'+str(row['stable_candidate'])+' '+row['page']+' '+str(row['visual_selection']),fill='black')
 canvas.save(out/('events_%02d.png'%page))
print(json.dumps(dict(selections=report['visual_selections'],frames=len(rows),long_rejected_segments=segments,sheets=math.ceil(len(indices)/20)),indent=2))
