import unittest
from types import SimpleNamespace
from eye_tracker.audio import AudioError,PhraseBank
from eye_tracker.calibration import Context
from eye_tracker.interaction import DwellController,Action,GazeSample,MAIN_TARGETS
from eye_tracker.trial_speech import TrialSpeech


class SpeechBoundaryTests(unittest.TestCase):
 def setUp(self):
  self.t=1.;self.played=[];self.stopped=[]
  self.c=DwellController(Context('session','geo','live'),'current')
  self.device=SimpleNamespace(play=lambda s:self.played.append(s),stop=lambda:self.stopped.append(self.t),poll=lambda:'done')
  self.s=TrialSpeech(self.device,PhraseBank(),self.c,lambda:self.t)
 def action(self,key='water',source='live',stamp=1000,phrase=None):
  text=next(t.phrase for t in MAIN_TARGETS if t.key==key)
  return Action(key,text if phrase is None else phrase,source,stamp)
 def test_reject_stale_future_replay_wrong_phrase_or_uncalibrated(self):
  for kind in ('stale','future','replay','wrong','uncalibrated','paused','closed','nan'):
   with self.subTest(kind=kind):
    self.setUp();a=self.action()
    if kind=='stale':self.t=1.151
    if kind=='future':self.t=.99
    if kind=='replay':a=self.action(source='replay')
    if kind=='wrong':a=self.action(phrase='not the phrase')
    if kind=='uncalibrated':self.c.invalidate_calibration()
    if kind=='paused':self.c.pause(1000)
    if kind=='closed':self.c.stop(1000)
    if kind=='nan':a=self.action(stamp=float('nan'))
    with self.assertRaises(AudioError):self.s.start(a,12)
    self.assertEqual(self.played,[])
 def test_no_busy_queue_no_duplicate_after_completion(self):
  a=self.action();self.s.start(a,12)
  with self.assertRaises(AudioError):self.s.start(self.action('help'),13)
  self.s.poll()
  with self.assertRaises(AudioError):self.s.start(a,12)
  self.assertEqual(len(self.played),1)
 def test_bounded_speech_high_watermark_rejects_replay_and_reordering(self):
  self.s=TrialSpeech(self.device,PhraseBank(),self.c,lambda:self.t,bounded=True)
  for i in range(2200):
   self.t=1+i*.05
   self.s.start(self.action(stamp=self.t*1000),i+1);self.s.poll()
  self.assertIsNone(self.s.spoken_times)
  self.assertEqual(self.s.events.total,4400)
  self.assertEqual(len(self.s.events),4096)
  for stamp in (self.t*1000,self.t*1000-20):
   with self.assertRaises(AudioError):self.s.start(self.action(stamp=stamp),2201)
  self.assertEqual(len(self.played),2200)
 def test_more_and_back_are_silent(self):
  self.s.start(self.action('more'),10);self.s.start(Action('back','','live',1000),11)
  self.assertEqual(self.played,[]);self.assertEqual(self.s.events,[])
 def test_partial_dwell_invalid_clears_and_cannot_speak_until_new_full_dwell(self):
  seq=0
  def feed(status):
   nonlocal seq
   seq+=1;self.t+=.1
   return self.c.feed(GazeSample(self.c.context,'current',seq,self.t*1000,status,(.25,.37)),self.t*1000)
  for _ in range(8):self.s.start(feed('valid'),seq)
  self.assertGreater(self.c.progress,.5)
  self.s.start(feed('unknown'),seq);self.assertEqual(self.c.progress,0)
  for _ in range(8):self.s.start(feed('valid'),seq)
  self.assertEqual(self.played,[])
  for _ in range(5):self.s.start(feed('valid'),seq)
  self.assertEqual(len(self.played),1)


class AutomaticControlsTests(unittest.TestCase):
 def test_no_command_until_real_utterance_and_bounded_one_shot_schedule(self):
  from eye_tracker.trial_speech import AutomaticTrialControls
  a=AutomaticTrialControls();s=SimpleNamespace(active=None,events=[])
  self.assertIsNone(a.update(s,100))
  s.active='water';s.events=[dict(event='started',key='water',monotonic=101)]
  self.assertIsNone(a.update(s,101.5));self.assertEqual(a.update(s,101.7),'cancel')
  s.active=None;self.assertIsNone(a.update(s,110))
  s.active='help';s.events.append(dict(event='started',key='help',monotonic=111))
  self.assertEqual(a.update(s,111.7),'toggle_pause');s.active=None
  self.assertIsNone(a.update(s,113.6));self.assertEqual(a.update(s,113.8),'toggle_pause')
  self.assertIsNone(a.update(s,120));self.assertEqual(a.stage,'complete')
