"""Bake only challenge banners; retain live UI geometry and state feedback."""
from pathlib import Path
import sys,json
import numpy as np
from PIL import Image,ImageDraw,ImageFont
r=Path(__file__).resolve().parents[1];sys.path.insert(0,str(r/'src'))
from eye_tracker.trial_challenges import PLAN,ASSET
from eye_tracker.framebuffer import pack_rgb565
font=ImageFont.truetype('assets/fonts/noto_sans_cjk_sc.otf',22)
small=ImageFont.truetype('assets/fonts/noto_sans_cjk_sc.otf',18)
labels={'water':'喝水','rest':'休息','help':'需要帮助'}
actions={'close':'轻闭双眼，数3秒后睁开','cover':'手掌挡镜头约3秒，再移开（不碰镜头）',
         'leave':'头部移出画面，约3秒后回来','blink':'自然眨眼几次，不需要用力闭眼'}
frames={}
for i,p in enumerate(PLAN):
 im=Image.new('RGB',(640,72),'#e8f2ef');d=ImageDraw.Draw(im);phase=p['phase'];target=labels[p['target']]
 if phase.startswith('challenge_'):
  lines=(actions[phase.split('_',1)[1]],'动作后继续看“'+target+'”；识别和进度照常运行')
 elif phase.startswith('after_'):
  lines=('请看“'+target+'”，尝试选中','恢复检查 · 保持舒服坐姿，正常眨眼')
 else:lines=('请看“'+target+'”，尝试选中','稍后按提示做动作 · 本轮静音')
 for y,line,f in ((6,lines[0],font),(40,lines[1],small)):
  assert d.textbbox((14,y),line,font=f)[2]<625
  d.text((14,y),line,font=f,fill='#153f3b')
 frames[phase]=pack_rgb565(np.asarray(im))
 if phase=='challenge_cover':im.save(r/'build/previews/trial_challenge_banner.png')
frames['metadata']=np.frombuffer(json.dumps({'plan':list(PLAN),'font_not_distributed':True}).encode(),np.uint8)
np.savez_compressed(ASSET,**frames);print(ASSET)
