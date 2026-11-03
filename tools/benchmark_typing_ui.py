"""CPU-only page cache benchmark. No camera, MMIO, DMA, audio or overlay load."""
import argparse,json,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from eye_tracker.daily_tools import DailyTools
from eye_tracker.composer import Favorites
from eye_tracker.ui import BoardRenderer
from eye_tracker.interaction import DwellController
from eye_tracker.calibration import Context


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',default='build/typing_ui_20261101/pc_cpu.json')
    p.add_argument('--pastimes',action='store_true')
    args=p.parse_args();out=(ROOT/args.output).resolve();out.relative_to((ROOT/'build').resolve())
    start=time.perf_counter();d=DailyTools.from_root(ROOT,local_video=True,pastimes=args.pastimes)
    d.composer.favorites=Favorites(d.composer.lexicon)  # Never mutate or benchmark-save personal phrases.
    r=BoardRenderer();r.bind_daily_tools(d)
    c=DwellController(Context('cpu-file-benchmark','four','simulated'),'synthetic',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=d)
    c.page='local_tools';startup=time.perf_counter()-start;rows=[]
    states=('compose','keyboard','candidates','suggestions','phrases','album','photo_view','video','present','display','input_methods','word_keyboard','word_candidates','word_actions')
    if args.pastimes:d.game.start('match');states+=('pastimes','games','game','game_done','book','book_options','book_chapters')
    for state in states:
        d.state=state;d.composer.pinyin='ni' if state=='candidates' else '';d.composer.text='我' if state=='suggestions' else '你好';d.display_text='我想喝水，谢谢你。'
        d.initials='jt' if state=='word_candidates' else 'j' if state=='word_keyboard' else ''
        r.daily_renderer._key=None;start=time.perf_counter();r.rgb565(c,'guide_ready');cold=(time.perf_counter()-start)*1000
        count=r.daily_renderer.cache_builds;times=[]
        for i in range(40):
            c.target_key='tool_slot_'+str(i%4);c.progress=(i%20)/20
            start=time.perf_counter();raw=r.rgb565(c,'guide_ready');times.append((time.perf_counter()-start)*1000)
            assert len(raw)==614400
        assert r.daily_renderer.cache_builds==count
        rows.append(dict(page=state,cold_ms=cold,warm_median_ms=float(np.median(times)),warm_p95_ms=float(np.percentile(times,95))))
    result=dict(scope='CPU file/render benchmark only; no eye frame processing, DMA, audio or constant frame-rate claim',
        hardware_loaded=False,personal_files_written=False,startup_seconds=startup,pages=rows,warm_frames=40*len(rows),
        warm_p95_under_40ms=all(x['warm_p95_ms']<40 for x in rows))
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':main()
