"""CPU-only page/communication scheduling check using an in-memory TEST peer.

No serial/MMIO, overlay, capture, display DMA or playback. This is never a
wireless-link or live-eye result, including when executed on PYNQ.
"""
import argparse,json,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from eye_tracker.daily_tools import DailyTools
from eye_tracker.composer import Favorites
from eye_tracker.calibration import Context
from eye_tracker.interaction import Action,DwellController
from eye_tracker.event_link import EventLink
from eye_tracker.event_protocol import Packet,Receiver
from eye_tracker.trial_events import TrialEvents
from eye_tracker.ui import BoardRenderer

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='build/wireless_upgrade_20261101/pc_coexistence.json')
    opt=parser.parse_args();out=(ROOT/opt.output).resolve();out.relative_to(ROOT/'build')
    now=lambda:time.perf_counter()*1000  # High resolution also on Windows.
    class MemoryPeer:
        def __init__(self):self.receiver=Receiver(allow_test=True);self.rx=bytearray()
        def reset(self):self.rx.clear()
        def read(self):data=bytes(self.rx[:16]);del self.rx[:16];return data
        def try_write(self,raw):
            reply,_=self.receiver.receive(Packet.decode(raw),now())
            if reply:self.rx.extend(reply.encode())
            return True
    d=DailyTools.from_root(ROOT,local_video=True,pastimes=True)
    d.composer.favorites=Favorites(d.composer.lexicon)  # No personal writes.
    c=DwellController(Context('CPU_fixture_not_camera','four','live'),'fixture',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=d)
    c.page='local_tools';r=BoardRenderer();r.bind_daily_tools(d);d.game.start('match')
    link=EventLink(MemoryPeer(),simulation=False,wire_test=True,session_factory=iter(range(1,10000)).__next__)
    wireless=TrialEvents(link,c);rows=[]
    states=('compose','keyboard','candidates','suggestions','phrases','album','photo_view','video','present','display',
            'input_methods','word_keyboard','word_candidates','word_actions','pastimes','games','game','game_done',
            'book','book_options','book_chapters','word_actions_pending','display_64')
    for state in states:
        wireless.suspend(now(),'cpu_fixture_between_pages')
        d.state='word_actions' if state=='word_actions_pending' else 'display' if state=='display_64' else state
        d.composer.pinyin='ni' if state=='candidates' else '';d.composer.text='我' if state=='suggestions' else '你好'
        d.display_text='国'*64 if state=='display_64' else '我想喝水，谢谢你。'
        d.initials='jt' if state in ('word_candidates','word_actions_pending') else 'j' if state=='word_keyboard' else ''
        r.daily_renderer.atlas.service=None;r.daily_renderer._key=None;c.target_key=None;c.progress=0
        plain=r.rgb565(c,'guide_ready')
        # A separate fresh TEST fixture session per page; no waiting or real radio.
        link.retry_after=0;wireless.resume(c,now())
        for _ in range(3):wireless.update(now())
        assert link.ready
        stamp=now();assert wireless.update(stamp,Action('help','','live',stamp),0),(state,link.snapshot())
        ticks=[now()]
        def service():ticks.append(now());wireless.update(ticks[-1])
        r.daily_renderer.atlas.service=service;r.daily_renderer._key=None
        start=now();frame=r.rgb565(c,'guide_ready');service();cold=now()-start
        assert frame==plain,'service callback changed pixels: '+state
        cold_gap=max(b-a for a,b in zip(ticks,ticks[1:]));calls=len(ticks)-1
        builds=r.daily_renderer.cache_builds;warm=[]
        for i in range(40):
            c.target_key='tool_slot_'+str(i%4);c.progress=(i%20)/20
            start=now();r.rgb565(c,'guide_ready');service();warm.append(now()-start)
        assert builds==r.daily_renderer.cache_builds
        rows.append(dict(page=state,cold_ms=cold,cold_service_gap_ms=cold_gap,cold_service_calls=calls,warm_p95_ms=float(np.percentile(warm,95))))
        wireless.suspend(now(),'cpu_fixture_page_done')
    r.daily_renderer.atlas.service=None;wireless.close(now())
    accepted=link.counts.get('remote_accepted',0)
    passed=accepted==len(states) and all(x['cold_service_gap_ms']<200 and x['warm_p95_ms']<40 for x in rows)
    result=dict(scope=__doc__,hardware_loaded=False,personal_files_written=False,source='CPU fixture only',passed=passed,
                pages=rows,pixels_identical=len(states),warm_frames=len(states)*40,memory_TEST_acceptances=accepted,
                limits='CPU render-only. Capture/inference/DMA/media scheduling and real all-peer ACKs require separate board checks.')
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=passed,pages=len(rows),memory_TEST_acceptances=accepted,max_cold_service_gap_ms=max(x['cold_service_gap_ms'] for x in rows))))
    return 0 if passed else 1
if __name__=='__main__':sys.exit(main())
