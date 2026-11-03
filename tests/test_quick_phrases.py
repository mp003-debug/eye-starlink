"""Approved phrases, fresh dwell, local-only meaning and bounded audio tests."""
import hashlib,json,shutil,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from eye_tracker.audio import AudioDevice,AudioError,PhraseBank,ROOT
from eye_tracker.music import StreamAudioDevice
from eye_tracker.phrase_audio import PhraseAudioDevice
from eye_tracker.phrases import PHRASE_TEXT,QUICK_KEYS
from eye_tracker.interaction import DwellController,GazeSample,Action,PAGE_TARGETS
from eye_tracker.calibration import Context
from eye_tracker.trial_speech import TrialSpeech
from test_music import StreamMMIO


class QuickInteractionTests(unittest.TestCase):
    def setUp(self):
        self.c=DwellController(Context('fixture','four-region','live'),'checked',quick_phrases=True)
        self.t=0;self.seq=0;self.actions=[]
    def feed(self,point,n=1,status='valid'):
        for _ in range(n):
            self.t+=100;self.seq+=1
            a=self.c.feed(GazeSample(self.c.context,'checked',self.seq,self.t,status,point),self.t)
            if a:self.actions.append(a)
    def select(self,key):
        self.feed((.5,.55),5)
        target=next(t for t in self.c.targets if t.key==key)
        l,t,r,b=target.rect;self.feed(((l+r)/2,(t+b)/2),12)
        self.assertEqual(self.actions[-1].key,key)
    def test_two_pages_all_phrases_and_repeated_visits(self):
        self.select('more');self.select('quick_open')
        for key in ('yes','no','please_stop'):self.select(key)
        self.assertFalse(self.c.closed);self.assertFalse(self.c.paused)
        self.select('quick_back');self.select('care_open')
        for key in ('reposition','toilet','unwell'):self.select(key)
        self.select('care_back');self.select('menu_back')
        self.select('more');self.select('quick_open');self.select('yes')
        spoken=[a.phrase for a in self.actions if a.phrase]
        self.assertEqual(spoken,[PHRASE_TEXT[k] for k in QUICK_KEYS]+['是'])
    def test_held_menu_gaze_and_invalid_frames_cannot_choose_child(self):
        self.select('more');self.select('quick_open')
        self.feed((.75,.37),35);self.assertEqual(self.actions[-1].key,'quick_open')
        self.feed((.5,.55),10,status='unknown')
        self.feed((.75,.37),20);self.assertEqual(self.actions[-1].key,'quick_open')
        self.select('no');self.assertEqual(self.actions[-1].phrase,'不是')
    def test_partial_dwell_and_cleared_calibration_do_not_emit(self):
        self.select('more');self.select('care_open');self.feed((.5,.55),5)
        self.feed((.25,.37),8);count=len(self.actions);self.assertGreater(self.c.progress,.5)
        self.feed((.25,.37),1,status='closed');self.assertEqual(self.c.progress,0)
        self.feed((.25,.37),8);self.assertEqual(len(self.actions),count)
        self.c.invalidate_calibration();self.feed((.25,.37),25)
        self.assertEqual(len(self.actions),count)
    def test_feature_flags_only_expose_available_menu_entries(self):
        for music,quick,page,keys in [(False,False,'more',{'back'}),
                (True,False,'menu',{'music_open','menu_back'}),
                (False,True,'quick_menu',{'quick_open','care_open','menu_back'}),
                (True,True,'full_menu',{'music_open','quick_open','care_open','menu_back'})]:
            self.setUp();self.c.music_enabled=music;self.c.quick_phrases=quick;self.select('more')
            self.assertEqual(self.c.page,page);self.assertEqual({t.key for t in self.c.targets},keys)


class QuickSpeechTests(unittest.TestCase):
    def test_catalog_targets_pcm_and_manifest_agree(self):
        bank=PhraseBank(include_quick=True)
        self.assertEqual(set(bank.samples),set(PHRASE_TEXT))
        self.assertEqual(set(PhraseBank().samples),{'water','rest','help'})
        for page in ('quick','care'):
            for target in PAGE_TARGETS[page]:
                if target.phrase:self.assertEqual(bank.text[target.key],target.phrase)
        self.assertGreater(len(bank.samples['reposition']),32768)
        self.assertGreater(len(bank.samples['toilet']),32768)
        for samples in bank.samples.values():self.assertLessEqual(np.abs(samples.astype(np.int32)).max(),8191)
    def test_changed_text_or_audio_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            dst=Path(folder)/'speech';shutil.copytree(ROOT/'assets/speech',dst)
            p=dst/'manifest.json';original=p.read_bytes();m=json.loads(original)
            m['phrases']['yes']['text']='不是';p.write_text(json.dumps(m),encoding='utf-8')
            with self.assertRaisesRegex(AudioError,'identity/hash'):PhraseBank(dst,include_quick=True)
            p.write_bytes(original);f=dst/'yes.wav';f.write_bytes(f.read_bytes()[:-2])
            with self.assertRaisesRegex(AudioError,'identity/hash'):PhraseBank(dst,include_quick=True)
    def test_oversized_asset_is_rejected_before_audio_read(self):
        with tempfile.TemporaryDirectory() as folder:
            dst=Path(folder)/'speech';shutil.copytree(ROOT/'assets/speech',dst)
            (dst/'yes.wav').write_bytes(bytes(128000*2+65537))
            with self.assertRaisesRegex(AudioError,'bounded size'):PhraseBank(dst,include_quick=True)
    def test_new_utterances_keep_live_identity_freshness_and_no_queue(self):
        bank=PhraseBank(include_quick=True)
        for key in QUICK_KEYS:
            c=DwellController(Context('fixture','four','live'),'checked',quick_phrases=True)
            calls=[];device=SimpleNamespace(play=lambda s:calls.append(s),stop=lambda:None,poll=lambda:'done')
            speech=TrialSpeech(device,bank,c,lambda:1.)
            for a in (Action(key,PHRASE_TEXT[key],'replay',1000),Action(key,PHRASE_TEXT[key],'live',700),Action(key,'wrong','live',1000)):
                with self.assertRaises(AudioError):speech.start(a,1)
            speech.start(Action(key,PHRASE_TEXT[key],'live',1000),1)
            with self.assertRaises(AudioError):speech.start(Action(key,PHRASE_TEXT[key],'live',1000),1)
            self.assertEqual(len(calls),1)
            speech.interrupt('cancel');self.assertIsNone(speech.active)
            with self.assertRaises(AudioError):speech.start(Action(key,PHRASE_TEXT[key],'live',1000),1)


class StreamedPhraseTests(unittest.TestCase):
    def setUp(self):
        self.mmio=StreamMMIO();self.t=0.
        self.device=PhraseAudioDevice(AudioDevice(self.mmio,lambda:self.t),StreamAudioDevice(self.mmio),lambda:self.t)
    def test_complete_long_pcm_order_and_final_sample(self):
        for key in ('reposition','toilet'):
            self.setUp();pcm=PhraseBank(include_quick=True).samples[key]
            self.device.play(pcm)
            for _ in range(130):
                self.mmio.consume(1024);self.t+=1024/16000
                if self.device.poll()=='done':break
            np.testing.assert_array_equal(np.asarray(self.mmio.played,dtype='<i2'),pcm)
            self.assertFalse(self.device.streaming);self.assertIsNone(self.device.samples)
    def test_stop_discards_tail_and_does_not_resume_on_poll(self):
        pcm=PhraseBank(include_quick=True).samples['reposition'];self.device.play(pcm)
        self.mmio.consume(1000);self.device.stop();self.mmio.consume(5000)
        self.assertEqual(self.device.poll(),'idle');self.assertEqual(len(self.mmio.played),1000)
        self.assertEqual(self.mmio.ready,{});self.assertIsNone(self.device.samples)
        self.device.play(pcm[:100]);self.assertEqual(self.mmio.mode,0)
    def test_busy_queue_fault_timeout_and_incomplete_completion_fail_closed(self):
        pcm=PhraseBank(include_quick=True).samples['reposition']
        for failure in ('fault','timeout','incomplete','stopped'):
            self.setUp();self.device.play(pcm)
            with self.assertRaisesRegex(AudioError,'busy'):self.device.play(pcm)
            if failure=='fault':self.mmio.fault=36
            elif failure=='timeout':self.t=9
            elif failure=='incomplete':self.mmio.busy=False;self.mmio.done=True
            else:self.mmio.busy=False
            with self.assertRaises(AudioError):self.device.poll()
            self.assertFalse(self.mmio.busy);self.assertIsNone(self.device.samples)
    def test_two_consecutive_long_utterances_start_from_sample_zero(self):
        pcm=PhraseBank(include_quick=True).samples['toilet']
        for _ in range(2):
            self.device.play(pcm)
            while True:
                self.mmio.consume(1000);self.t+=.0625
                if self.device.poll()=='done':break
        np.testing.assert_array_equal(np.asarray(self.mmio.played,dtype='<i2'),np.tile(pcm,2))
