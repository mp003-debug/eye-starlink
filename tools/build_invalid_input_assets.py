"""Bake Chinese challenge prompts into portable RGB565 assets; font not shipped."""
from pathlib import Path
import sys,json
import numpy as np
from PIL import Image,ImageDraw,ImageFont
r=Path(__file__).resolve().parents[1];sys.path.insert(0,str(r/'src'))
from eye_tracker.invalid_input_diagnostic import PLAN,ASSET
from eye_tracker.framebuffer import pack_rgb565
font=ImageFont.truetype('assets/fonts/noto_sans_cjk_sc.otf',24);small=ImageFont.truetype('assets/fonts/noto_sans_cjk_sc.otf',18)
titles={
 'close':('轻闭双眼，心中数3秒后睁开','睁开后继续看圆点'),
 'cover':('手掌挡住镜头约3秒，再移开','不碰镜头；移开后继续看圆点'),
 'leave':('头部移出画面，约3秒后回来','回来后继续看圆点'),
 'blink':('自然连续眨眼几次，再看圆点','不需要用力闭眼')
}
frames={}
for key,point,phase in [('center',(.5,.55),'intro')]+list(PLAN):
 im=Image.new('RGB',(640,480),'#edf4f2');d=ImageDraw.Draw(im)
 d.text((26,20),'眼语 · 状态检查',font=font,fill='#153f3b')
 d.text((26,57),'只记录识别结果，不触发按钮或声音',font=small,fill='#526963')
 cx,cy=round(point[0]*640),round(point[1]*480)
 d.ellipse((cx-23,cy-23,cx+23,cy+23),fill='white',outline='#12645c',width=3)
 d.ellipse((cx-8,cy-8,cx+8,cy+8),fill='#e67638')
 if phase=='intro':lines=('稍后按文字提示做小动作','每次动作后继续看圆点')
 elif phase=='session_reference':lines=('自然看中心圆点','保持舒服坐姿，正常眨眼')
 elif phase.startswith('challenge_'):lines=titles[phase.split('_',1)[1]]
 elif phase.startswith('after_'):lines=('动作结束，继续看圆点','不用调整相机或重新对焦')
 else:lines=('自然看圆点','正常眨眼，头部自然稳定')
 d.rounded_rectangle((15,360,625,466),radius=12,fill='white',outline='#bdcbc7',width=2)
 for y,line in zip((376,418),lines):d.text((28,y),line,font=font if y==376 else small,fill='#153f3b')
 d.text((550,22),'READY' if phase=='intro' else str([v for _,_,v in PLAN].index(phase)+1)+'/13',font=small,fill='#526963')
 frames[phase]=pack_rgb565(np.asarray(im))
 if phase in ('intro','challenge_close','challenge_cover'):im.save(r/'build/previews'/('invalid_'+phase+'.png'))
frames['metadata']=np.frombuffer(json.dumps({'plan':[[n,list(p),v] for n,p,v in PLAN],'font_not_distributed':True}).encode('utf8'),np.uint8)
np.savez_compressed(ASSET,**frames);print(ASSET)

