"""Native preview and bounded local checks for explicit phrase shortcuts."""
import hashlib,json,sys,time
from pathlib import Path
from PIL import Image
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT/'tests'))
from test_word_completion import fixture,word_route
from test_typing_efficiency import enter_letter
from eye_tracker.ui import BoardRenderer
from eye_tracker.interaction import DwellController
from eye_tracker.calibration import Context
from eye_tracker.framebuffer import unpack_rgb565


def main():
    out=ROOT/'build/typing_words_20261101';out.mkdir(exist_ok=True)
    d=fixture();c=DwellController(Context('word-preview','four','simulated'),'synthetic',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=d);c.page='local_tools'
    renderer=BoardRenderer();renderer.bind_daily_tools(d);images=[];cases=[]
    for name,state,body,py in [('ni_words','candidates','','ni'),('wo_words','candidates','','wo'),
                             ('continue_wo','suggestions','我',''),('word_added','present','你好','')]:
        d.state=state;d.composer.text=body;d.composer.pinyin=py
        frame=renderer.rgb565(c,'guide_ready')
        im=Image.fromarray(unpack_rgb565(np.frombuffer(frame,dtype='<u2').reshape(480,640)));im.save(out/(name+'.png'));images.append(im)
    sheet=Image.new('RGB',(1280,960))
    for i,im in enumerate(images):sheet.paste(im,((i%2)*640,(i//2)*480))
    sheet.save(out/'word_completion_preview.png')
    for py,text,v9 in [('ni','你好',15),('wo','我想喝水',35),('xie','谢谢',18),('qing','请帮我换个姿势',58)]:
        tool=fixture();count=word_route(tool,py,text);assert tool.composer.text==text
        cases.append(dict(text=text,pinyin_prefix=py,v9_free_pinyin_selections=v9,known_phrase_selections=count))
    d.composer.text='我';d.composer.pinyin='';d.state='suggestions';renderer.rgb565(c,'guide_ready');builds=renderer.daily_renderer.cache_builds;times=[]
    for i in range(100):
        c.target_key='tool_slot_'+str(i%4);c.progress=(i%20)/20
        start=time.perf_counter();renderer.rgb565(c,'guide_ready');times.append((time.perf_counter()-start)*1000)
    assert renderer.daily_renderer.cache_builds==builds
    guard=json.loads((ROOT/'build/typing_ui_20261101/protected_before.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in guard.items())
    result=dict(scope='PC native previews and deterministic known-phrase paths; no live speed claim',cases=cases,
        warm_render_median_ms=float(np.median(times)),warm_render_p95_ms=float(np.percentile(times,95)),
        warm_frames_without_glyph_rebuild=100,protected_files_verified=len(guard),board_operations=False)
    (out/'offline_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__':main()
