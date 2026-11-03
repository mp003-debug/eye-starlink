import array,json,tempfile,unittest,wave
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
from eye_tracker.ai_writing import AIWriting
from eye_tracker.ai_worker import normalize_wav
from eye_tracker.daily_tools import DailyTools
from eye_tracker.composer import Favorites
from eye_tracker.interaction import Action,DwellController,GazeSample,MAIN_TARGETS
from eye_tracker.calibration import Context
from eye_tracker.music import StreamAudioDevice
from eye_tracker.sharing_ui import SharingUI
from eye_tracker.share_protocol import TEXT
from test_music import StreamMMIO

ROOT=Path(__file__).resolve().parents[1]

class FakeJob:
    def __init__(self,bundle,folder,kind,text,clock):
        self.kind=kind;self.text=text;self.path=Path(folder);self.result=None;self.cancelled=False;self.reaped=False
    def poll(self):return self.result
    def cancel(self):self.cancelled=True
    def reap(self,wait=0):self.reaped=True;return True

class AIWritingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.path=Path(self.temp.name)
        self.tools=DailyTools.from_root(ROOT);self.c=self.tools.composer;self.c.favorites=Favorites(self.c.lexicon);self.c.load('今天下午')
        self.ai=AIWriting(None,self.path,FakeJob,lambda:1);self.tools.ai=self.ai;self.tools.sharing=SharingUI();self.tools.state='ai'
        self.mmio=StreamMMIO();self.ai.bind_audio(StreamAudioDevice(self.mmio));self.addCleanup(self.ai.close)
    def generate(self,text='今天下午我想去公园散步。'):
        self.ai.select('ai_generate',self.c);self.job=self.ai.job;self.job.result=dict(kind='generate',text=text);self.ai.service(self.c)
    def speech(self):
        self.ai.select('ai_speech',self.c);self.job=self.ai.job
        samples=array.array('h',((i%8000)-4000 for i in range(40001)))
        with wave.open(str(self.path/'speech.wav'),'wb') as w:w.setparams((1,2,16000,len(samples),'NONE',''));w.writeframes(samples.tobytes())
        self.job.result=dict(kind='synthesize',frames=len(samples));self.ai.service(self.c)
        return samples
    def test_generated_text_never_auto_adopted_or_shared(self):
        self.generate();self.assertEqual(self.c.text,'今天下午');self.assertEqual(self.ai.page,'preview')
        self.assertIsNone(self.tools.sharing.request);self.assertFalse(self.mmio.busy);self.assertEqual(self.c.favorites.items,[])
    def test_candidate_requires_review_and_second_confirmation(self):
        self.generate()
        with self.assertRaises(ValueError):self.ai.select('ai_adopt',self.c)
        self.ai.select('ai_reviewed',self.c);self.assertEqual(self.c.text,'今天下午')
        self.ai.select('ai_adopt',self.c);self.assertEqual(self.c.text,'今天下午我想去公园散步。')
        self.assertTrue(self.c.undo());self.assertEqual(self.c.text,'今天下午');self.assertIsNone(self.tools.sharing.request)
    def test_candidate_cancel_keeps_text_and_favorites(self):
        self.c.favorites.save('你好');self.generate();self.ai.select('ai_cancel',self.c)
        self.assertEqual(self.c.text,'今天下午');self.assertEqual(self.c.favorites.items,['你好'])
    def test_late_result_after_cancel_is_not_reused(self):
        self.ai.select('ai_generate',self.c);job=self.ai.job;self.ai.cancel();job.result=dict(kind='generate',text='你好')
        self.ai.service(self.c);self.assertEqual(self.ai.candidate,'');self.assertEqual(self.c.text,'今天下午')
    def test_changing_draft_invalidates_generation(self):
        self.ai.select('ai_generate',self.c);self.ai.job.result=dict(kind='generate',text='你好');self.c.load('我想喝水')
        self.ai.service(self.c);self.assertEqual(self.ai.page,'home');self.assertEqual(self.c.text,'我想喝水')
    def test_unknown_glyph_and_overlong_candidates_rejected_without_truncation(self):
        for text in ['你好🙂','你'*65,'', 'hello']:
            self.generate(text);self.assertEqual(self.ai.page,'home');self.assertEqual(self.c.text,'今天下午');self.ai.service(self.c)
    def test_partial_pinyin_cannot_be_discarded_by_AI(self):
        self.c.pinyin='ni'
        with self.assertRaises(ValueError):self.ai.select('ai_generate',self.c)
        self.assertEqual(self.c.pinyin,'ni')
    def test_voice_ready_never_autoplays(self):
        self.speech();self.assertEqual(self.ai.page,'speech_ready');self.assertFalse(self.mmio.busy)
        self.ai.select('ai_play',self.c);self.assertFalse(self.mmio.busy)
    def test_play_uses_fresh_live_confirmation_and_streams_complete_pcm(self):
        samples=self.speech();self.ai.select('ai_play',self.c);self.ai.dispatch(Action('tool_slot_2','','live',1000),1000)
        self.assertTrue(self.mmio.busy)
        for _ in range(100):
            self.mmio.consume(1000);self.ai.service(self.c)
            if self.ai.page=='home':break
        self.assertEqual(self.mmio.played,list(samples));self.assertFalse(self.mmio.busy)
    def test_expired_or_replay_speech_confirmation_cannot_start(self):
        for source,stamp in [('live',0),('replay',1000)]:
            self.speech();self.ai.select('ai_play',self.c);self.ai.dispatch(Action('tool_slot_2','',source,stamp),1000)
            self.assertFalse(self.mmio.busy);self.ai.service(self.c)
    def test_help_stops_speech_and_cancels_worker_without_restart(self):
        self.speech();self.ai.select('ai_play',self.c);self.ai.dispatch(Action('tool_slot_2','','live',1000),1000)
        self.assertEqual(self.tools.select(2),'help');self.assertFalse(self.mmio.busy);self.assertTrue(self.job.cancelled)
        self.ai.service(self.c);self.assertFalse(self.mmio.busy)
    def test_reposition_discards_result_and_pending_voice_but_preserves_draft(self):
        self.speech();self.ai.select('ai_play',self.c);self.tools.reset_navigation()
        self.ai.dispatch(Action('tool_slot_2','','live',1000),1000);self.assertFalse(self.mmio.busy)
        self.assertEqual(self.c.text,'今天下午');self.assertFalse(self.ai.play_requested)
    def test_adopted_text_uses_existing_wireless_preview_confirm(self):
        self.generate('我想喝水');self.ai.select('ai_reviewed',self.c);self.ai.select('ai_adopt',self.c)
        s=self.tools.sharing;s.select('share_draft',None,self.c);self.assertIsNone(s.request)
        s.select('share_reviewed',None,self.c);self.assertIsNone(s.request)
        s.select('share_confirm',None,self.c);self.assertEqual(s.request,(TEXT,'我想喝水'))
    def test_speech_file_corruption_is_rejected(self):
        self.ai.select('ai_speech',self.c);self.ai.job.result=dict(kind='synthesize',frames=2)
        (self.path/'speech.wav').write_bytes(b'bad');self.ai.service(self.c);self.assertEqual(self.ai.page,'home');self.assertFalse(self.mmio.busy)
    def test_async_page_change_resets_existing_dwell_and_requires_release(self):
        context=Context('s','g','live');controller=DwellController(context,'checked',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=self.tools)
        controller.page='local_tools';self.ai.select('ai_generate',self.c)
        target=controller.targets[1];controller.cursor=((target.rect[0]+target.rect[2])/2,(target.rect[1]+target.rect[3])/2)
        controller.progress=.95;controller.target_key=target.key;controller.start_time=0
        self.ai.job.result=dict(kind='generate',text='你好');self.ai.poll_controller(controller,self.tools)
        self.assertEqual(controller.progress,0);self.assertIsNotNone(controller.navigation_block)
    def test_wave_resample_limits_and_peak(self):
        raw=self.path/'raw.wav';out=self.path/'out.wav'
        with wave.open(str(raw),'wb') as w:w.setparams((1,2,22050,22050,'NONE',''));w.writeframes(array.array('h',[30000,-30000]*11025).tobytes())
        self.assertEqual(normalize_wav(raw,out),16000)
        with wave.open(str(out),'rb') as w:
            self.assertEqual(w.getframerate(),16000);self.assertLessEqual(max(abs(x) for x in array.array('h',w.readframes(16000))),8191)
    def test_silence_rejected_instead_of_claiming_speech(self):
        raw=self.path/'silent.wav'
        with wave.open(str(raw),'wb') as w:w.setparams((1,2,16000,100,'NONE',''));w.writeframes(b'\0'*200)
        with self.assertRaises(ValueError):normalize_wav(raw,self.path/'out.wav')
    def test_only_explicit_share_confirmation_reaches_wire_commit(self):
        from test_receiver_sharing import Transport
        from eye_tracker.share_link import SharingEventLink
        from eye_tracker.share_protocol import DATA,COMMIT
        from eye_tracker.trial_events import TrialEvents
        wire=Transport();link=SharingEventLink(wire,session_factory=lambda:123)
        controller=DwellController(Context('s','g','live'),'checked',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=self.tools)
        controller.reason='selected';events=TrialEvents(link,controller)
        for now in range(0,100,5):events.update(now)
        self.generate('我想喝水');self.ai.select('ai_reviewed',self.c);self.ai.select('ai_adopt',self.c)
        events.update(100,Action('tool_slot_0','','live',100))
        self.assertFalse(any(p.kind in (DATA,COMMIT) for p in wire.sent))
        s=self.tools.sharing;s.select('share_draft',None,self.c);s.select('share_reviewed',None,self.c)
        events.update(105,Action('tool_slot_2','','live',105));self.assertFalse(any(p.kind==COMMIT for p in wire.sent))
        s.select('share_confirm',None,self.c);events.update(110,Action('tool_slot_0','','live',110))
        for now in range(115,2000,5):events.update(now)
        self.assertEqual(link.counts['share_accepted'],1);self.assertEqual(sum(p.kind==COMMIT for p in wire.sent),1)
    def test_feature_off_keeps_original_pages(self):
        self.tools.ai=None;self.tools.state='more'
        self.assertEqual(self.tools.view().choices[1].command,'present')
    def test_enabled_entry_preserves_access_to_display_and_favorites(self):
        self.tools.state='more';self.tools.select(1);self.assertEqual(self.tools.state,'ai')
        self.tools.select(2);self.assertEqual(self.tools.state,'present')
        self.tools.select(1);self.assertEqual(self.c.favorites.items,['今天下午'])
    @unittest.skipUnless((Path(__file__).resolve().parents[1]/'assets/ai/manifest.json').is_file(), 'requires optional local private profile or AI runtime bundle')
    def test_launch_requires_explicit_opt_in_and_checks_complete_local_bundle(self):
        from eye_tracker.launch import prepare_launch
        from eye_tracker.ai_bundle import AIBundle
        from test_launch import LaunchTests
        fixture=LaunchTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        from eye_tracker.phrases import QUICK_KEYS
        for name in ['assets/speech/'+n for n in ['manifest.json']+[k+'.wav' for k in QUICK_KEYS]]+['assets/music/playlist.json','assets/photos/album.json','assets/typing/pinyin.json','assets/typing/glyphs.npz']:
            p=fixture.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'fixture')
        options=dict(music=True,quick_phrases=True,emotion_cards=True,daily_tools=True)
        with patch('eye_tracker.launch.verify_artifacts',return_value={'audio_ip_version':'0x00020000'}):
            plan=prepare_launch(fixture.path,fixture.root,**options)
            self.assertFalse(plan['ai_writing_enabled']);self.assertNotIn('--ai-writing',plan['board_arguments'])
            with self.assertRaises(FileNotFoundError):prepare_launch(fixture.path,fixture.root,ai_writing=True,**options)
            bundle=AIBundle(ROOT/'assets/ai')
            with patch('eye_tracker.ai_bundle.AIBundle',return_value=bundle):
                plan=prepare_launch(fixture.path,fixture.root,ai_writing=True,**options)
            self.assertIn('--ai-writing',plan['board_arguments']);self.assertFalse(plan['uart_enabled'])
            self.assertFalse(plan['hardware_loaded']);self.assertFalse((fixture.root/'data').exists())

if __name__=='__main__':unittest.main()
