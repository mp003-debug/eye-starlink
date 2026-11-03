"""Show the actual compiled RGB565 expression pages; no hardware or gaze input."""
import sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from eye_tracker.calibration import Context
from eye_tracker.interaction import DwellController
from eye_tracker.ui import BoardRenderer
from eye_tracker.emotions import CARDS
from eye_tracker.framebuffer import unpack_rgb565


def main():
    out=ROOT/'build/emotion_cards_20261031';out.mkdir(parents=True,exist_ok=True)
    controller=DwellController(Context('offline-preview','four-region','simulated'),'fixture',
        music_enabled=True,quick_phrases=True,emotion_cards=True)
    renderer=BoardRenderer();font=ImageFont.truetype('assets/fonts/noto_sans_cjk_sc.otf',18)
    def picture(page,key=None):
        controller.page=page;controller.emotion_key=key;controller.reason='tracking'
        feedback='emotion_display_hint' if key else 'emotion_hint' if page.startswith('emotion') else 'guide_communication' if page=='communication_menu' else 'guide_menu'
        raw=renderer.rgb565(controller,feedback)
        return Image.fromarray(unpack_rgb565(np.frombuffer(raw,dtype='<u2').reshape(480,640)))
    pages=('extended_menu','communication_menu','emotion_hub','emotion_mood','emotion_affection')
    for page in pages:picture(page).save(out/(page+'.png'))
    for key in CARDS:picture('emotion_display',key).save(out/(key+'.png'))
    for filename,items in [('navigation_preview.png',[(p,picture(p)) for p in pages]),
                           ('six_cards_preview.png',[(v[0],picture('emotion_display',k)) for k,v in CARDS.items()])]:
        sheet=Image.new('RGB',(1328,1660),'#E5ECE8');d=ImageDraw.Draw(sheet)
        d.text((16,12),'六张本地表情卡 · 实际RGB565素材预览，非真人或板测证据',font=font,fill='#183B3D')
        for i,(label,pic) in enumerate(items):
            x=16+i%2*656;y=56+i//2*532
            d.text((x,y),label,font=font,fill='#183B3D');sheet.paste(pic,(x,y+26))
        sheet.save(out/filename)
    print(out/'six_cards_preview.png')


if __name__=='__main__':main()
