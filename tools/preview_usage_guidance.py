"""Offline storyboard from the exact RGB565 assets used by the board UI."""
from pathlib import Path
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from eye_tracker.ui import BoardRenderer
from eye_tracker.framebuffer import unpack_rgb565
from eye_tracker.interaction import DwellController
from eye_tracker.calibration import Context
from eye_tracker.usage_guidance import UsageGuidance


def main():
    out=ROOT/'build/upgrade_20261029'
    out.mkdir(parents=True,exist_ok=True)
    board=BoardRenderer()
    shots=[('启动：等待参考',board.setup_frame(0)),
           ('启动：采集进度',board.setup_frame(3)),
           ('启动：未通过检查',board.setup_frame(3,failed=True))]
    c=DwellController(Context('offline-preview','geometry','simulated'),'fixture')
    c.reason='tracking';c.target_key='water';c.progress=.6
    shots.append(('交互：有效停留',board.rgb565(c,UsageGuidance().feedback(c,{},0))))
    c.reason='unknown';c.target_key=None;c.progress=0
    guide=UsageGuidance();guide.feedback(c,{},0)
    shots.append(('交互：持续定位失败',board.rgb565(c,guide.feedback(c,{'rejection':'motion_envelope'},3))))
    c.invalidate_calibration()
    shots.append(('交互：清除校准后',board.rgb565(c,guide.feedback(c,{},4))))
    sheet=Image.new('RGB',(1328,1660),'#E5ECE8');draw=ImageDraw.Draw(sheet)
    font=ImageFont.truetype('assets/fonts/noto_sans_cjk_sc.otf',20)
    small=ImageFont.truetype('assets/fonts/noto_sans_cjk_sc.otf',16)
    draw.text((24,16),'升级阶段一 · 使用引导与状态提示',font=font,fill='#183B3D')
    draw.text((24,49),'离线合成状态，使用实际 RGB565 渲染结果；不是板测或真人眼控证据。',font=small,fill='#526F73')
    for i,(label,raw) in enumerate(shots):
        image=Image.fromarray(unpack_rgb565(np.frombuffer(raw,dtype='<u2').reshape(480,640)))
        image.save(out/('guidance_%d.png'%(i+1)))
        x=16+(i%2)*656;y=92+(i//2)*520
        draw.text((x,y),label,font=small,fill='#183B3D')
        sheet.paste(image,(x,y+28))
    sheet.save(out/'guidance_preview.png')
    print(out/'guidance_preview.png')


if __name__=='__main__':main()
