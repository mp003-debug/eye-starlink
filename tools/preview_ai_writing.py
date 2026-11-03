"""Offline RGB565 previews of every AI/speech confirmation state."""
from pathlib import Path
from types import SimpleNamespace
import sys,json
import numpy as np
from PIL import Image,ImageDraw
R=Path(__file__).resolve().parents[1];S=R/'build/ai_integration_20261103';sys.path.insert(0,str(R/'src'))
from eye_tracker.daily_tools import DailyTools
from eye_tracker.ai_writing import AIWriting
from eye_tracker.ui import BoardRenderer
from eye_tracker.interaction import DwellController
from eye_tracker.calibration import Context

def main():
    tools=DailyTools.from_root(R);tools.ai=AIWriting(None,S/'preview_work');tools.composer.load('今天下午我想去公园散步。')
    tools.state='ai';a=tools.ai;a.frozen=tools.composer.text;a.candidate='今天下午，我想去公园散步。'
    c=DwellController(Context('preview','fixed','simulated'),'checked',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=tools);c.page='local_tools'
    renderer=BoardRenderer();renderer.bind_daily_tools(tools);out=S/'previews';out.mkdir(exist_ok=True)
    names=['home','generating','preview','confirm','synthesizing','speech_ready','speaking'];images=[]
    for name in names:
        a.page=name;words=np.frombuffer(renderer.rgb565(c),'<u2').reshape(480,640)
        rgb=np.stack([((words>>11)&31)*255//31,((words>>5)&63)*255//63,(words&31)*255//31],2).astype('uint8')
        im=Image.fromarray(rgb);im.save(out/(name+'.png'));images.append(im)
    a.page='preview';a.candidate='今天下午我想去公园散步。'*5+'你好你好'
    a.candidate=a.candidate[:64]
    assert len(a.candidate)==64
    renderer.rgb565(c)
    montage=Image.new('RGB',(1280,480*4),'white')
    for i,im in enumerate(images):montage.paste(im,(i%2*640,i//2*480))
    montage.save(out/'overview.png');print(json.dumps(dict(pages=len(images),full_64_character_rendered=True)))
if __name__=='__main__':main()
