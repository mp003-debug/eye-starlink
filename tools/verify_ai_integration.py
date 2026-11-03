"""Replay actual CPU outputs through draft/audio state and three C receivers.

All devices and transport are simulated; this script never connects to a board.
"""
import array,ctypes,json,os,shutil,sys,tempfile,wave
from pathlib import Path
R=Path(__file__).resolve().parents[1];S=R/'build/ai_integration_20261103'
sys.path[:0]=[str(R/'src'),str(R/'tests')]
os.environ['EYE_SHARING_CHECK_OUTPUT']='build/ai_integration_20261103/chain'
import verify_sharing_chain as chain
from test_ai_writing import AIWritingTests
from eye_tracker.interaction import Action,DwellController
from eye_tracker.calibration import Context
from eye_tracker.trial_events import TrialEvents

def main():
    report=json.loads((S/'worker_result.json').read_text(encoding='utf-8'))
    assert len(report['rows'])==3 and all(r.get('result',{}).get('ok') for r in report['rows'])
    generated=next(r['result']['text'] for r in report['rows'] if r['kind']=='generate')
    # This recorded static CPU sample used the exact same sentence for TTS.
    assert generated=='今天下午我想去公园散步。'
    tempfile.tempdir=str(R/'build/test_tmp')
    fixture=AIWritingTests();fixture.setUp()
    try:
        ai,c,t=fixture.ai,fixture.c,fixture.tools
        w,link=chain.ready();controller=DwellController(Context('s','g','live'),'checked',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=t)
        controller.reason='selected';events=TrialEvents(link,controller)
        fixture.generate(generated)
        assert c.text=='今天下午' and all(chain.lib.chain_messages(i)==0 for i in range(3))
        ai.select('ai_reviewed',c);ai.select('ai_adopt',c);ai.service(c)
        assert c.text==generated and not fixture.mmio.busy
        ai.select('ai_speech',c);shutil.copyfile(S/'probe_speech.wav',fixture.path/'speech.wav')
        ai.job.result=dict(kind='synthesize');ai.service(c);assert ai.page=='speech_ready' and not fixture.mmio.busy
        ai.select('ai_play',c);ai.dispatch(Action('tool_slot_2','','live',200),200)
        for _ in range(1000):
            fixture.mmio.consume(1000);ai.service(c)
            if ai.page=='home':break
        with wave.open(str(S/'probe_speech.wav')) as wav:pcm=array.array('h',wav.readframes(wav.getnframes()))
        assert fixture.mmio.played==list(pcm) and not fixture.mmio.busy
        assert all(chain.lib.chain_messages(i)==0 for i in range(3))
        share=t.sharing;share.select('share_draft',None,c);share.select('share_reviewed',None,c)
        events.update(200,Action('tool_slot_2','','live',200))
        assert all(chain.lib.chain_messages(i)==0 for i in range(3))
        share.select('share_confirm',None,c);events.update(210,Action('tool_slot_0','','live',210))
        for now in range(220,8000,20):w.now=now;events.update(now)
        assert link.counts['share_accepted']==1
        for peer in range(3):
            raw=ctypes.create_string_buffer(128);n=chain.lib.chain_text(peer,raw)
            assert chain.lib.chain_messages(peer)==1 and raw.raw[:n].decode('gb2312')==generated
        result=dict(passed=True,hardware_tested=False,board_cpu_outputs_replayed=True,
                    explicit_draft_confirmation=True,explicit_speech_confirmation=True,
                    pcm_samples=len(pcm),explicit_wireless_confirmation=True,c_receiver_count=3,
                    no_auto_send=True,original_chain_cases=len(chain.cases))
        (S/'integration_replay.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    finally:fixture.doCleanups()
if __name__=='__main__':main()
