"""Create private chronological review sheets; prompts are not truth labels."""
from pathlib import Path
import argparse,json,hashlib,math
from PIL import Image,ImageDraw
p=argparse.ArgumentParser();p.add_argument('stage',type=Path);args=p.parse_args()
root=args.stage;d=json.loads((root/'invalid_input.json').read_text());rows={r['frame_index']:r for r in d['frames']}
audit=json.loads((root/'audit/manifest.json').read_text())['frames']
out=root/'review';out.mkdir(exist_ok=True)
phases=list(dict.fromkeys(a['phase'] for a in audit));summaries={}
for phase in phases:
    images=[a for a in audit if a['phase']==phase]
    for page in range(math.ceil(len(images)/30)):
        batch=images[page*30:(page+1)*30];canvas=Image.new('RGB',(1200,math.ceil(len(batch)/5)*205),'#f4f4f4');draw=ImageDraw.Draw(canvas)
        for j,a in enumerate(batch):
            source=root/'audit'/a['png'];assert hashlib.sha256(source.read_bytes()).hexdigest()==a['sha256']
            im=Image.open(source).convert('RGB').resize((240,180))
            x=j%5*240;y=j//5*205;canvas.paste(im,(x,y+25));v=rows[a['frame_index']]
            draw.text((x+3,y+2),str(a['frame_index'])+' '+('%.2fs'%a['after_present_s'])+' '+str(v['candidate'])+'/'+str(v['stable_candidate']),fill='black')
        canvas.save(out/(phase+'_%02d.png'%page))
    summaries[phase]={'audit_frames':len(images),'pages':math.ceil(len(images)/30)}
print(json.dumps(dict(center_reference=d['center_reference'],counts=d['counts'],review=summaries),indent=2))

