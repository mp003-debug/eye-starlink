"""Native RGB565 previews and deterministic effort report; never touches hardware."""
import json,sys,time,hashlib
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'tests'))
from eye_tracker.daily_tools import DailyTools
from eye_tracker.composer import Favorites
from eye_tracker.ui import BoardRenderer
from eye_tracker.interaction import DwellController,PAGE_TARGETS
from eye_tracker.calibration import Context
from eye_tracker.framebuffer import unpack_rgb565
from test_typing_efficiency import type_text


def main():
    out=ROOT/'build/typing_ui_20261101';out.mkdir(exist_ok=True)
    d=DailyTools.from_root(ROOT,local_video=True);d.composer.favorites=Favorites(d.composer.lexicon)
    c=DwellController(Context('offline-artwork','four','simulated'),'offline',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=d)
    r=BoardRenderer();r.bind_daily_tools(d)
    frames={}
    def save(name):
        raw=r.rgb565(c,'guide_ready');im=Image.fromarray(unpack_rgb565(np.frombuffer(raw,dtype='<u2').reshape(480,640)))
        im.save(out/(name+'.png'));frames[name]=im
    for page in PAGE_TARGETS:
        if page=='local_tools':continue
        c.page=page;c.target_key=None;c.progress=0;c.emotion_key='emotion_happy'
        c.music_position_samples=16000*32;c.music_total_samples=1413538
        save(page)
    c.page='main';c.target_key='water';c.progress=.6;c.reason='tracking';save('main_progress')
    c.target_key=None;c.progress=0;c.reason='waiting';c.page='local_tools'
    d.composer.text='你好';d.composer.favorites.items=['你','我想喝水'];d.favorite_index=0;d.display_text='我想和你聊天，谢谢你陪着我。'
    for state in ('album','photo_view','media','video','compose','keyboard','keyboard_actions','candidates','expressions','phrases','edit','present','display','favorites','favorite','clear_confirm','load_confirm','delete_confirm','symbols'):
        d.state=state;d.composer.pinyin='ni' if state=='candidates' else 'n' if state=='keyboard' else ''
        save('local_'+state)
    d.state='candidates';d.composer.pinyin='ni';c.target_key='tool_slot_0';c.progress=.65;save('typing_progress')
    c.locks={'tool_slot_0'};c.target_key=None;c.progress=0;save('typing_locked');c.locks=set()
    # Actual first decoded frame, fixed offline snapshot, not a running video.
    import sys as _sys
    _sys.path.insert(0,str(ROOT/'tools/deps/opencv'))
    import cv2
    from eye_tracker.framebuffer import pack_rgb565
    capture=cv2.VideoCapture(str(ROOT/'assets/video/amd_b1_cinematic.mp4'));ok,rgb=capture.read();capture.release();assert ok
    rgb=cv2.cvtColor(cv2.resize(rgb,(352,198),interpolation=cv2.INTER_NEAREST),cv2.COLOR_BGR2RGB)
    d.video_player=SimpleNamespace(index=0,state='paused',frame=pack_rgb565(rgb),duration=45,position=0)
    d.state='video_view';save('local_video_view')
    for filename,names in [('overview',('main_progress','music','emotion_mood','local_album')),
                           ('typing_overview',('local_compose','local_keyboard','typing_progress','local_phrases')),
                           ('media_overview',('local_video','local_video_view','local_photo_view','local_display'))]:
        sheet=Image.new('RGB',(1280,960))
        for i,name in enumerate(names):sheet.paste(frames[name],((i%2)*640,(i//2)*480))
        sheet.save(out/(filename+'.png'))
    baseline=json.loads((out/'baseline_effort.json').read_text(encoding='utf-8'));effort=[]
    for case in baseline['cases']:
        tool=DailyTools.from_root(ROOT);tool.composer.favorites=Favorites(tool.composer.lexicon)
        count=type_text(tool,case['text'],case['pinyin'])
        assert tool.composer.text==case['text']
        effort.append(dict(text=case['text'],before=case['selections'],after=count,
                           reduction_percent=round(100*(case['selections']-count)/case['selections'],1)))
    d.state='keyboard';d.composer.pinyin='n';r.rgb565(c,'guide_ready');times=[]
    builds=r.daily_renderer.cache_builds
    for i in range(100):
        c.target_key='tool_slot_'+str(i%4);c.progress=(i%20)/20
        start=time.perf_counter();r.rgb565(c,'guide_ready');times.append((time.perf_counter()-start)*1000)
    assert r.daily_renderer.cache_builds==builds
    result=dict(scope='PC native RGB565 artwork and deterministic button counts only, not board latency or real-eye speed',
        preview_frames=len(frames),selection_counts=effort,
        pc_warm_render_median_ms=float(np.median(times)),pc_warm_render_p95_ms=float(np.percentile(times,95)),
        warm_frames_without_glyph_rebuild=100,ui_uncompressed_bytes=sum(t.nbytes for t in r.tiles.values()),
        glyph_uncompressed_bytes=sum(t.nbytes for t in r.daily_renderer.atlas.glyphs.values()),
        preview_sha256={n:hashlib.sha256((out/(n+'.png')).read_bytes()).hexdigest() for n in frames})
    (out/'offline_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='preview_sha256'},ensure_ascii=True))


if __name__=='__main__':main()
