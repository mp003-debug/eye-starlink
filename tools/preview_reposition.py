"""Offline RGB565 preview, using a clearly labeled recorded eye image."""
from pathlib import Path
import sys
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from eye_tracker.ui import BoardRenderer
from eye_tracker.framebuffer import unpack_rgb565

out=ROOT/'build/reposition_upgrade_20261031';out.mkdir(exist_ok=True)
pixels=np.asarray(Image.open(ROOT/'build/music_endurance_20261031/reseated_capture.png').convert('L'))
ui=BoardRenderer();sheet=Image.new('RGB',(1320,1100),'#DBE6E2');draw=ImageDraw.Draw(sheet)
font=ImageFont.truetype('assets/fonts/noto_sans_cjk_sc.otf',18)
for i,state in enumerate(('preview','collecting','failed','limit')):
    raw=ui.position_frame(pixels,state,3 if state=='collecting' else 0)
    im=Image.fromarray(unpack_rgb565(np.frombuffer(raw,dtype='<u2').reshape(480,640)))
    x=10+(i%2)*660;y=40+(i//2)*530
    sheet.paste(im,(x,y));draw.text((x,y-28),'离线素材预览（历史图像） · '+state,font=font,fill='#183B3D')
sheet.save(out/'preview.png')
print(out/'preview.png')
