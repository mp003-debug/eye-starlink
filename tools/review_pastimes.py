"""Review native RGB565 game/book pages without hardware or personal writes."""
import hashlib,json,math,sys,time,zipfile
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from eye_tracker.daily_tools import DailyTools
from eye_tracker.pastimes import Round,SHAPES,QUESTIONS
from eye_tracker.ui import BoardRenderer
from eye_tracker.interaction import DwellController
from eye_tracker.calibration import Context
from eye_tracker.framebuffer import unpack_rgb565

def main():
    out=ROOT/'build/pastimes_20261101';views=out/'previews';views.mkdir(exist_ok=True)
    d=DailyTools.from_root(ROOT,local_video=True,pastimes=True);r=BoardRenderer();r.bind_daily_tools(d)
    c=DwellController(Context('offline','four','simulated'),'test',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=d)
    pages=[]
    def save(name):
        raw=r.rgb565(c,'guide_ready');im=Image.fromarray(unpack_rgb565(np.frombuffer(raw,dtype='<u2').reshape(480,640)))
        im.save(views/(name+'.png'));pages.append((name,im))
    for state in ('pastimes_leisure','leisure'):
        c.page=state;save(state)
    c.page='local_tools'
    for state in ('pastimes','games'):
        d.state=state;save(state)
    d.game.start('match');d.state='game'
    for i,shape in enumerate(SHAPES):
        d.game.rounds[0]=Round('找到相同的图形',(shape,SHAPES[(i+1)%6]),0,shape)
        for target,progress in ((None,0),('tool_slot_0',.65)):
            c.target_key=target;c.progress=progress;save('shape_%d_%d'%(i,int(progress*100)))
    c.target_key=None;c.progress=0;d.game.notice='再看看 · 可以慢慢选';save('match_retry')
    d.game.solved=True;save('match_solved')
    d.game.start('quiz');d.state='game';save('quiz')
    d.state='game_done';save('game_done')
    p=SimpleNamespace(index=0,state='paused',position=16000*42)
    p.snapshot=lambda:dict(bookmark_warning=False);d.book_player=p
    for i in range(3):
        p.index=i;d.state='book';save('book_%d'%i)
    p.index=0
    for state in ('book_options','book_chapters'):
        d.state=state;save(state)
    d.state='book';p.state='playing';save('book_playing');builds=r.daily_renderer.cache_builds
    for i in range(100):p.position=16000*(i%80);r.rgb565(c,'guide_ready')
    assert r.daily_renderer.cache_builds==builds,'progress must not rebuild glyphs'
    p.state='ended';p.position=d.audiobook_library.tracks[0]['frames'];save('book_ended')
    p.snapshot=lambda:dict(bookmark_warning=True);save('book_save_warning')
    for first,name in ((0,'games_overview'),(20,'books_overview')):
        group=pages[first:first+8];canvas=Image.new('RGB',(1280,math.ceil(len(group)/2)*480))
        for i,(_,im) in enumerate(group):canvas.paste(im,(i%2*640,i//2*480))
        canvas.save(out/(name+'.png'))
    for first in range(0,len(pages),6):
        group=pages[first:first+6];canvas=Image.new('RGB',(1280,math.ceil(len(group)/2)*480))
        for i,(_,im) in enumerate(group):canvas.paste(im,(i%2*640,i//2*480))
        canvas.save(views/('sheet_%02d.png'%(first//6)))
    protected=json.loads((out/'protected_before.json').read_text())
    assert all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in protected.items())
    with zipfile.ZipFile(out/'before_pastimes.zip') as z:old=z.read('src/eye_tracker/interaction.py').decode('utf-8')
    new=(ROOT/'src/eye_tracker/interaction.py').read_text(encoding='utf-8')
    def gates(s):return s.replace('\r\n','\n').split('class DwellController:',1)[1].split('        previous_page=self.page',1)[0]
    assert gates(old)==gates(new),'recognition/dwell/invalid/release gates changed'
    result=dict(native_pages=len(pages),warm_progress_frames_without_rebuild=100,protected_hashes_verified=18,
                dwell_and_invalid_gate_source_unchanged=True,board_operations=False,
                audio=d.audiobook_library.provenance())
    (out/'offline_review.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');print(json.dumps(result))

if __name__=='__main__':main()
