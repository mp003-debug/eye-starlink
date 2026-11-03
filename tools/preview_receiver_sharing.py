"""Preview actual RGB565 UI and C-rendered EPD bytes; no hardware."""
from pathlib import Path
import sys,json
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from eye_tracker.daily_tools import DailyTools
from eye_tracker.sharing_ui import SharingUI
from eye_tracker.ui import BoardRenderer
from eye_tracker.text_ui import DailyRenderer
OUT=ROOT/'build/receiver_sharing_20261102/previews';OUT.mkdir(parents=True,exist_ok=True)
d=DailyTools.from_root(ROOT);d.sharing=SharingUI();d.state='share';d.composer.text='今天下午我想听音乐然后看相册'*4
d.composer.text=d.composer.text[:64];d.sharing.frozen=(3,d.composer.text)
r=BoardRenderer();local=DailyRenderer(d,tiles=r.tiles)
class Controller:
    target_key='tool_slot_0';locks=set();progress=.65
images=[]
for page in ('home','list','text','preview','confirm','activity','activity_confirm','activity_info','status'):
    d.sharing.page=page
    words=r.tiles['base_local_tools'].copy();local.overlay(words,Controller(),None)
    v=words.astype(np.uint32)
    rgb=np.stack((((v>>11)&31)*255//31,((v>>5)&63)*255//63,(v&31)*255//31),axis=-1).astype(np.uint8)
    im=Image.fromarray(rgb);im.save(OUT/('pynq_'+page+'.png'));images.append((page,im))
sheet=Image.new('RGB',(960,750),'white');draw=ImageDraw.Draw(sheet)
for i,(page,im) in enumerate(images):
    x=(i%3)*320;y=(i//3)*250;sheet.paste(im.resize((320,240)),(x,y));draw.text((x+4,y+239),page,fill='black')
sheet.save(OUT/'pynq_contact.png')
epd=[]
for p in sorted((ROOT/'build/receiver_sharing_20261102/host').glob('epd_*.bin')):
    raw=np.unpackbits(np.frombuffer(p.read_bytes(),dtype=np.uint8)).reshape(480,800)*255
    im=Image.fromarray(raw).transpose(Image.Transpose.ROTATE_90);im.save(OUT/(p.stem+'.png'));epd.append(im)
sheet=Image.new('L',(240*len(epd),400),255)
for i,im in enumerate(epd):sheet.paste(im.resize((240,400)),(i*240,0))
sheet.save(OUT/'epd_contact.png')
(OUT/'result.json').write_text(json.dumps(dict(pynq_pages=len(images),epd_frames=len(epd),hardware_tested=False)),encoding='utf-8')
print(OUT)
