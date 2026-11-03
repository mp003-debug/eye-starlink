"""Offline RGB565 music page storyboard, without audio or hardware access."""
from pathlib import Path
import sys,argparse
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from eye_tracker.ui import BoardRenderer
from eye_tracker.framebuffer import unpack_rgb565
from eye_tracker.calibration import Context
from eye_tracker.interaction import DwellController
from eye_tracker.music import MusicLibrary

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir',default='build/music_controls_20261031')
args=parser.parse_args();out=(ROOT/args.output_dir).resolve();out.relative_to(ROOT/'build')
out.mkdir(parents=True,exist_ok=True)
c=DwellController(Context('music-preview','fixture','simulated'),'fixture',music_enabled=True)
r=BoardRenderer();font=ImageFont.truetype('assets/fonts/noto_sans_cjk_sc.otf',18)
lib=MusicLibrary(ROOT/'assets/music');r.bind_music(lib)
sheet=Image.new('RGB',(1328,1680),'#E5ECE8');d=ImageDraw.Draw(sheet)
d.text((20,12),'本地音乐 · 离线合成状态，非真人/听音/板测证据',font=font,fill='#183B3D')
scenes=[('music_hub','music_hub_hint',0,0,5,'音乐入口'),
        ('music','music_playing',0,.42,5,'曲名与播放进度'),
        ('music','music_paused',1,.5,3,'暂停，进度保留'),
        ('music','music_ended',2,1.,3,'第三首自然结束'),
        ('music_volume','music_volume_hint',0,0,1,'音乐音量设置'),
        ('music','music_empty',-1,0,5,'空曲库提示')]
for i,(page,key,index,fraction,level,label) in enumerate(scenes):
    c.page=page;c.reason='tracking';c.target_key=None;c.progress=0
    c.music_track_index=index;c.music_volume_level=level
    c.music_total_samples=lib.tracks[index]['frames'] if index>=0 else 0
    c.music_position_samples=int(c.music_total_samples*fraction)
    if i==1:c.target_key='music_toggle';c.progress=.55
    raw=r.rgb565(c,key);pic=Image.fromarray(unpack_rgb565(np.frombuffer(raw,dtype='<u2').reshape(480,640)))
    pic.save(out/f'music_{i+1}.png');x=16+(i%2)*656;y=64+(i//2)*530
    d.text((x,y),label,font=font,fill='#183B3D');sheet.paste(pic,(x,y+28))
sheet.save(out/'music_preview.png');print(out/'music_preview.png')
