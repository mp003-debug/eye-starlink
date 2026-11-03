"""Native display review and deterministic choice counts, without hardware."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/free_text_20261101'
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from eye_tracker.daily_tools import DailyTools
from eye_tracker.composer import Favorites
from eye_tracker.interaction import DwellController
from eye_tracker.calibration import Context
from eye_tracker.ui import BoardRenderer
from eye_tracker.framebuffer import unpack_rgb565
from test_free_text import compose_chunks

def main():
    out=OUT/'previews';out.mkdir(exist_ok=True)
    d=DailyTools.from_root(ROOT,local_video=True,pastimes=True);d.composer.favorites=Favorites(d.composer.lexicon)
    c=DwellController(Context('offline','four','simulated'),'offline',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=d);c.page='local_tools'
    r=BoardRenderer();r.bind_daily_tools(d);frames={}
    def save(name,state,prefix='',text='今天下午',progress=False):
        d.state=state;d.initials=prefix;d.word_groups=[];d.word_offset=0;d.composer.text=text;d.display_text=text;d.notice=''
        c.target_key='tool_slot_0' if progress else None;c.progress=.65 if progress else 0
        raw=r.rgb565(c,'guide_ready');im=Image.fromarray(unpack_rgb565(np.frombuffer(raw,dtype='<u2').reshape(480,640)))
        im.save(out/(name+'.png'));frames[name]=im
    save('01_compose','compose');save('02_methods','input_methods');save('03_initials','word_keyboard')
    save('04_single_j','word_candidates','j');save('05_continue_j','word_keyboard','j')
    save('06_words_jt','word_candidates','jt',progress=True);save('07_words_xw','word_candidates','xw')
    save('08_words_yy','word_candidates','yy');save('09_prefix_edit','word_actions','jt')
    d.composer.text='';d.composer._edits=[];d.composer.append_text('今天');d.composer.append_text('下午')
    save('10_undo','word_actions');save('11_symbols','symbols')
    save('12_full_pinyin','keyboard');d.composer.pinyin='ni';save('13_full_candidates','candidates');d.composer.pinyin=''
    text='今天下午我想和你一起听音乐，听完后我们聊聊明天的安排。'
    save('14_long_draft','display',text=text);save('15_sixty_four','display',text='国'*64)
    save('16_word_full','word_candidates','jt',text='我'*63)
    for i in range(0,len(frames),4):
        sheet=Image.new('RGB',(1280,960),'white')
        for j,name in enumerate(list(frames)[i:i+4]):sheet.paste(frames[name],((j%2)*640,(j//2)*480))
        sheet.save(out/('sheet_%02d.png'%(i//4)))
    overview=Image.new('RGB',(1280,960))
    for i,n in enumerate(('02_methods','06_words_jt','10_undo','14_long_draft')):overview.paste(frames[n],((i%2)*640,(i//2)*480))
    overview.save(OUT/'overview.png')
    cases=json.loads((OUT/'baseline_effort.json').read_text(encoding='utf-8'))['cases'];effort=[]
    for case in cases:
        tool=DailyTools.from_root(ROOT);tool.composer.favorites=Favorites(tool.composer.lexicon)
        vocabulary={s for s,_ in tool.words.words}
        chunks=[part for s in case['chunks'] for part in ([s] if s in vocabulary else list(s))]
        count=compose_chunks(tool,chunks);assert tool.composer.text==case['text']
        effort.append(dict(text=case['text'],chunks=chunks,before=case['selections'],after=count,reduction_percent=round(100*(1-count/case['selections']),1)))
    protected=json.loads((OUT/'protected_before.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in protected.items())
    d.state='word_candidates';d.initials='jt';r.rgb565(c,'guide_ready');builds=r.daily_renderer.cache_builds
    for i in range(100):c.progress=(i%20)/20;r.rgb565(c,'guide_ready')
    assert builds==r.daily_renderer.cache_builds
    result=dict(scope='Deterministic UI choices from compose page to body ready; no physical gaze time, correction or accuracy',
        native_pages=len(frames),effort=effort,cache_frames_without_glyph_rebuild=100,protected_hashes=len(protected),
        words_bytes=(ROOT/'assets/typing/words.json').stat().st_size,word_entries=len(d.words.words))
    (OUT/'offline_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))
if __name__=='__main__':main()
