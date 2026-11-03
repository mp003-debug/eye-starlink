"""Offline actual RGB565 pages; no eye, audio or board session is started."""
from pathlib import Path
import sys
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from eye_tracker.ui import BoardRenderer
from eye_tracker.framebuffer import unpack_rgb565
from eye_tracker.calibration import Context
from eye_tracker.interaction import DwellController

out=ROOT/'build/phrases_upgrade_20261029';out.mkdir(parents=True,exist_ok=True)
c=DwellController(Context('phrase-preview','fixture','simulated'),'fixture',music_enabled=True,quick_phrases=True)
r=BoardRenderer();font=ImageFont.truetype('assets/fonts/noto_sans_cjk_sc.otf',18)
sheet=Image.new('RGB',(1328,1140),'#E5ECE8');d=ImageDraw.Draw(sheet)
d.text((20,12),'双页快捷交流 · 离线合成状态，非真人/听音/板测证据',font=font,fill='#183B3D')
scenes=[('full_menu','guide_menu','更多功能',None),('quick','guide_quick','回应交流',None),
        ('care','guide_care','日常照护',None),('care','speaking_reposition','完整语音播报状态','reposition')]
for i,(page,feedback,label,selected) in enumerate(scenes):
    c.page=page;c.reason='speaking' if selected else 'tracking';c.target_key=selected
    c.locks={selected} if selected else set();c.progress=0
    raw=r.rgb565(c,feedback);pic=Image.fromarray(unpack_rgb565(np.frombuffer(raw,dtype='<u2').reshape(480,640)))
    pic.save(out/('quick_page_%d.png'%(i+1)))
    x=16+(i%2)*656;y=64+(i//2)*530
    d.text((x,y),label,font=font,fill='#183B3D');sheet.paste(pic,(x,y+28))
sheet.save(out/'quick_phrases_preview.png')
print(out/'quick_phrases_preview.png')
