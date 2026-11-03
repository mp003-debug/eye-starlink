import unittest
from types import SimpleNamespace
from eye_tracker.appearance_trial import VisualTrial,positive_entry
from eye_tracker.appearance_diagnostic import StableCandidate
from eye_tracker.calibration import Context
from eye_tracker.interaction import DwellController
from eye_tracker.fixation import POINTS

class VisualTrialTests(unittest.TestCase):
 def setUp(self):
  self.trial=VisualTrial.__new__(VisualTrial)
  self.trial.token='visual-trial-only:test'
  self.trial.controller=DwellController(Context('test','geometry','live'),self.trial.token)
  self.trial.selections=[];self.trial.commands=[]
  self.trial.reference_history=[];self.trial.setup_attempts=0
  self.trial.engine=SimpleNamespace(gate=StableCandidate(),model=SimpleNamespace(enabled=False))
  self.index=0;self.time=0.
 def feed(self,key,n=1):
  result=None
  for _ in range(n):
   self.index+=1;self.time+=.1
   result=self.trial.feed({'candidate':key,'stable_candidate':key},self.index,self.time,self.time+.01) or result
  return result
 def test_real_region_drives_one_visual_selection_and_held_target_locks(self):
  self.assertEqual(self.feed('water',14).key,'water')
  self.assertIsNone(self.feed('water',30));self.assertEqual(len(self.trial.selections),1)
  self.assertEqual(self.trial.selections[0]['kind'],'visual_only')
  self.assertFalse(self.trial.engine.model.enabled)
  self.feed('center',5);self.assertEqual(self.feed('water',14).key,'water')
 def test_invalid_current_frame_cannot_reuse_stable_candidate(self):
  self.feed('water',8);self.index+=1;self.time+=.1
  self.trial.feed({'candidate':None,'stable_candidate':'water'},self.index,self.time,self.time+.01)
  self.assertEqual(self.trial.controller.progress,0)
  self.assertIsNone(self.feed('water',8));self.assertEqual(self.trial.selections,[])
 def test_more_requires_center_and_holding_more_cannot_trigger_return(self):
  self.assertEqual(self.feed('more',14).key,'more');self.assertEqual(self.trial.controller.page,'more')
  self.assertIsNone(self.feed('more',25));self.assertEqual(self.trial.controller.page,'more')
  self.assertEqual(self.feed('center',14).key,'back');self.assertEqual(self.trial.controller.page,'main')
  self.assertIsNone(self.feed('center',14));self.assertEqual([x['key'] for x in self.trial.selections],['more','back'])
 def test_return_rearms_each_visit_without_held_more_auto_return(self):
  for visit in range(3):
   self.assertEqual(self.feed('more',14).key,'more')
   if visit==0:self.assertIsNone(self.feed('more',15))
   self.assertIsNone(self.feed(None,5))
   self.assertIsNone(self.feed('center',5))
   self.assertEqual(self.feed('center',9).key,'back')
   self.assertIsNone(self.feed('center',5))
  self.assertEqual([e['key'] for e in self.trial.selections],['more','back']*3)
 def test_pause_cancel_and_clear_remove_dwell_without_clock_trigger(self):
  self.feed('help',8);self.trial.command('cancel',self.time+.02)
  self.assertEqual(self.trial.controller.progress,0);self.assertIsNone(self.feed('help',8))
  self.trial.command('toggle_pause',self.time+.02);self.assertIsNone(self.feed('help',20))
  self.trial.command('toggle_pause',self.time+.02);self.assertIsNone(self.feed('help',8))
  self.trial.command('invalidate_calibration',self.time+.02);self.assertIsNone(self.feed('help',20))
  self.assertIsNone(self.trial.controller.calibration_id);self.assertEqual(self.trial.selections,[])
 def test_stale_or_duplicate_frames_cannot_complete_dwell(self):
  self.feed('rest',9)
  obs={'candidate':'rest','stable_candidate':'rest'}
  self.trial.feed(obs,self.index,self.time,self.time+.02)
  self.assertEqual(self.trial.controller.progress,0)
  self.index+=1;self.time+=.1;self.trial.feed(obs,self.index,self.time,self.time+.2)
  self.assertEqual(self.trial.controller.progress,0);self.assertEqual(self.trial.selections,[])
 def test_center_reference_required_before_screen_trial(self):
  self.trial.engine.baseline=SimpleNamespace(finish=lambda:{'ready':False})
  with self.assertRaisesRegex(ValueError,'current_center'):self.trial.begin_visual()
 def evidence(self):
  rows=[]
  for i,key in enumerate(POINTS):
   for j in range(16):rows.append(dict(scored=True,instructed_target=key,candidate=key,stable_candidate=key,copied_monotonic=i*10+j*.1))
  return {'completed':True,'actions_enabled':False,'frames':rows}
 def test_entry_requires_every_target_and_sustained_fresh_evidence(self):
  d=self.evidence();self.assertEqual(set(positive_entry(d)),set(POINTS))
  d['frames']=[r for r in d['frames'] if r['instructed_target']!='help']
  with self.assertRaises(ValueError):positive_entry(d)
  d=self.evidence()
  for row in d['frames'][::3]:row['stable_candidate']=None
  with self.assertRaisesRegex(ValueError,'discontinuous'):positive_entry(d)
 def test_any_positive_wrong_or_incomplete_stage_blocks_entry(self):
  d=self.evidence();d['frames'][3]['candidate']='water'
  with self.assertRaisesRegex(ValueError,'wrong_positive'):positive_entry(d)
  d=self.evidence();d['completed']=False
  with self.assertRaises(ValueError):positive_entry(d)

 def run_loop(self,fail=False,challenges=None,audible=False,command_mask=0,codec_fail=False,auto_controls=False,long_run=False,incremental_setup=False,setup_fail=False,music_mode=False,quick_mode=False,assist=False,assist_fail=False,volume_mode=False,emotion_mode=False,daily_mode=False,video_mode=False,book_mode=False,wireless_mode=None,drop_ack=False,demo_window=False,demo_seconds=2400):
  from unittest.mock import patch
  import numpy as np
  from eye_tracker.appearance_trial import run_visual_trial
  daily_mode=daily_mode or video_mode or book_mode
  emotion_mode=emotion_mode or daily_mode
  music_mode=music_mode or volume_mode or emotion_mode
  quick_mode=quick_mode or emotion_mode
  clock=[1.];now=lambda:clock[0];stops=[];plays=[];codec_log=[];active=[None];first_start=[None]
  link=None
  if wireless_mode is not None:
   from test_events import Transport
   from eye_tracker.event_link import EventLink
   from eye_tracker.event_protocol import Receiver
   class TimedTransport(Transport):
    def try_write(self,raw):self.time=now()*1000;return super().try_write(raw)
   self.wire=TimedTransport(Receiver(allow_test=wireless_mode=='log'));self.wire.drop_ack=drop_ack
   link=EventLink(self.wire,simulation=False,wire_test=wireless_mode=='log',session_factory=iter(range(100,10000)).__next__)
   self.event_link=link
  self.music_calls=[];music_calls=self.music_calls
  class Books:
   def __init__(self,device,library,marks,clock):self.state='stopped';self.index=0;self.position=0;self.save_failed=False
   def poll(self):pass
   def suspend(self):music_calls.append('book_suspend');self.state='paused'
   def action(self,key):
    music_calls.append(key)
    if key=='book_toggle':self.state='paused' if self.state=='playing' else 'playing'
    else:self.state='paused'
    if key=='book_next':self.index=1
   def snapshot(self):return dict(state=self.state,chapter_index=self.index,position_samples=self.position,total_samples=160000,bookmark_warning=False)
   def close(self):music_calls.append('book_close');self.suspend()
  class Video:
   def __init__(self,library,device,clock):self.state='stopped';self.index=0
   def poll(self):pass
   def action(self,key):music_calls.append(key);self.state='playing' if key=='video_toggle' else 'paused' if key=='video_controls' else 'stopped'
   def suspend(self):music_calls.append('video_suspend');self.state='paused'
   def stop(self):music_calls.append('video_stop');self.state='stopped'
   def snapshot(self):return dict(state=self.state,index=self.index,frame_index=-1)
   def close(self):music_calls.append('video_close');self.stop()
  class Music:
   def __init__(self,device,library,clock):self.library=library;self.state='stopped';self.index=0;self.offset=0;self.volume=SimpleNamespace(level=5)
   def sync_display(self,c):c.music_track_index=self.index;c.music_volume_level=self.volume.level
   def poll(self):pass
   def suspend(self):music_calls.append('suspend');self.state='paused'
   def stop(self):music_calls.append('stop');self.state='stopped'
   def action(self,key):
    music_calls.append(key)
    if key=='music_toggle':self.state='playing'
    if key=='music_back':self.stop()
    if key=='music_volume_down':self.volume.level=max(1,self.volume.level-1)
    if key=='music_volume_up':self.volume.level=min(5,self.volume.level+1)
   def feedback(self):return 'music_playing' if self.state=='playing' else 'music_paused'
  class Audio:
   def __init__(self,*args):pass
   def stop(self):stops.append(now());active[0]=None
   def status(self):return int(active[0] is not None)
   def play(self,samples):
    music_calls.append('speech')
    plays.append(now());active[0]=now()+1.5
    if first_start[0] is None:first_start[0]=now()
   def poll(self):
    if active[0] is not None and now()>=active[0]:active[0]=None;return 'done'
    return 'busy' if active[0] is not None else 'idle'
  class Codec:
   output_enabled=False;core_ready=True
   def __init__(self,*args):pass
   def configure_muted(self):
    codec_log.append('configure')
    if codec_fail:raise RuntimeError('codec failed')
    return {'pll_locked':True}
   def enable_output(self):codec_log.append('enable');self.output_enabled=True
   def mute(self):codec_log.append('mute');self.output_enabled=False
  class MMIO:
   def read(self,*args):
    if first_start[0] is None:return 0
    dt=now()-first_start[0]
    return command_mask if .2<dt<.7 or (command_mask==1 and 1.5<dt<2.) else 0
  class Session:
   capture_index=0;present_count=0
   def wait_native_frames(self,n):return {'bad_lines':1,'bad_frames':1}
   def present(self,frame):
    self.present_count+=1;clock[0]+=.01
    if fail and self.present_count==5:raise RuntimeError('display failure')
   def capture_once(self):
    req=now();clock[0]+=.06;self.capture_index+=1
    self.last_capture={'requested_at_monotonic':req,'copied_at_monotonic':now()}
    return np.zeros((480,640),np.uint8)
  self.setup_frames=[];self.feedbacks=[]
  setup_frames=self.setup_frames;feedbacks=self.feedbacks
  class Renderer:
   def setup_frame(self,count=0,failed=False):
    setup_frames.append((count,failed,now()));return bytes(640*480*2)
   def rgb565(self,c,feedback):
    feedbacks.append(feedback)
    if feedback.startswith('speaking_'):assert c.reason=='speaking'
    return bytes(640*480*2)
  self.trial.reference=SimpleNamespace(observe=lambda *args:None,rows=[dict(frame_index=i,reference_sample=True,translation=[0,0]) for i in range(1,6)])
  self.trial.engine.anchor=SimpleNamespace(origin_shift=np.zeros(2),box=(0,0,200,200));self.trial.engine.relocation={}
  self.trial.engine.baseline=SimpleNamespace(samples=[] if incremental_setup else [1]*5,ids=set(range(1,6)),summary={'ready':not setup_fail},finish=lambda:{'ready':not setup_fail})
  if incremental_setup:
   def collect(*args):
    samples=self.trial.engine.baseline.samples
    if len(samples)<5 and now()>3+len(samples)*.6:samples.append(1)
   self.trial.reference.observe=collect
  def observation(*args):
   clock[0]+=.03
   key='help' if auto_controls and first_start[0] is not None and now()-first_start[0]>3 else 'water'
   if music_mode:
    key=('more' if now()<9 else 'center' if now()<9.6 else 'water' if now()<11.6 else
         'center' if now()<12.2 else 'water' if now()<14.2 else 'center' if now()<14.8 else
         'water' if now()<16.8 else 'help' if now()<18.8 else 'more')
   if quick_mode:
    plan=((9,'more'),(9.6,'center'),(11.6,'rest'),(12.2,'center'),
          (15.5,'water'),(19,'rest'),(22.5,'help'),(24.5,'more'),(25.1,'center'),
          (27.1,'help'),(27.7,'center'),(31,'water'),(34.5,'rest'),(38,'help'),
          (40,'more'),(40.6,'center'),(42.6,'more'))
    key=next((k for end,k in plan if now()<end),'center')
   if volume_mode:
    plan=((9,'more'),(9.6,'center'),(11.6,'water'),(12.2,'center'),
          (14.2,'rest'),(14.8,'center'),(16.8,'water'),(18.8,'rest'),
          (20.8,'help'),(23.5,'more'),(24.1,'center'),(26.1,'water'),
          (26.7,'center'),(28.7,'water'),(30.7,'more'),(31.3,'center'),
          (33.3,'more'),(33.9,'center'),(35.9,'more'))
    key=next((k for end,k in plan if now()<end),'center')
   if emotion_mode:
    # Four-region input sequence crosses both expression pages and speaks help.
    plan=((9,'more'),(9.6,'center'),(11.6,'help'),(12.2,'center'),
          (14.2,'water'),(14.8,'center'),(16.8,'water'),(18.8,'rest'),
          (22.8,'help'),(24.8,'more'),(25.4,'center'),(27.4,'more'),
          (28,'center'),(30,'rest'),(30.6,'center'),(32.6,'rest'),
          (34.6,'more'),(35.2,'center'),(37.2,'more'),(37.8,'center'),
          (39.8,'more'),(40.4,'center'),(42.4,'more'))
    key=next((k for end,k in plan if now()<end),'center')
   if daily_mode:
    # Full camera-loop routing: ni -> character -> save/show/help -> album.
    slots=['more', 'rest', 'help', 'water', 'rest', 'rest', 'rest', 'rest', 'rest', 'water', 'water', 'more', 'help', 'rest', 'water', 'help', 'more', 'more', 'more', 'more', 'more', 'help', 'rest', 'help', 'more', 'rest', 'help']
    elapsed=now()-7
    visit=max(0,int(elapsed/2.6));within=elapsed%2.6
    key=slots[visit] if visit<len(slots) and within<2 else 'center'
   if video_mode:
    slots=['more','help','rest','rest','water','help','more','water','more','rest','more','more','more']
    elapsed=now()-7;visit=max(0,int(elapsed/2.6));within=elapsed%2.6
    key=slots[visit] if visit<len(slots) and within<2 else 'center'
   if book_mode:
    slots=['more','help','rest','rest','water','help','water','rest','water','rest','more','water','more','more','more']
    elapsed=now()-7;visit=max(0,int(elapsed/3.2));within=elapsed%3.2
    key=slots[visit] if visit<len(slots) and within<2.6 else 'center'
   return {'candidate':key,'stable_candidate':key}
  self.trial.engine.observe=observation;self.trial.rows=[];self.trial.audit=[];self.trial.summary={}
  self.assist_checks=[]
  def assisted(*args):
   self.trial.controller.invalidate_calibration()
   self.assist_checks.append(dict(audio_idle=active[0] is None,muted=codec_log[-1] in ('configure','mute'),time=now()))
   self.assertIsNone(self.trial.controller.calibration_id)
   self.assertEqual(self.trial.controller.progress,0)
   clock[0]+=6.01
   if assist_fail and len(self.assist_checks)>1:return False
   self.trial.begin_visual();return True
  def reset_reference():
   old=self.trial.controller
   self.trial.controller=DwellController(Context('fresh-reference','geometry','live'),music_enabled=old.music_enabled,quick_phrases=old.quick_phrases,emotion_cards=old.emotion_cards)
   self.trial.token='fresh-reference-token';self.trial.last_action=None
   self.trial.summary.pop('current_neighborhood',None)
  if long_run:self.trial.configure_long_run()
  from eye_tracker.audio import PhraseBank
  daily=None
  if daily_mode:
   from test_daily_tools import fixture
   daily=fixture()
   if video_mode:daily.video_library=SimpleNamespace(clips=[dict(title='测试短片')])
   if book_mode:
    daily.pastimes=True;daily.audiobook_library=SimpleNamespace(tracks=[dict(title='第一篇',frames=160000),dict(title='第二篇',frames=160000)])
    daily.bookmarks=SimpleNamespace(selected=0,warning=False,position=lambda i:0)
  with patch('eye_tracker.audiobook.AudioBookPlayer',Books),patch('eye_tracker.video.VideoPlayer',Video),patch('eye_tracker.audio.AudioDevice',Audio),patch('eye_tracker.audio.Codec',Codec),patch('eye_tracker.music.StreamAudioDevice'),patch('eye_tracker.music.MusicPlayer',Music),patch('eye_tracker.phrase_audio.PhraseAudioDevice',side_effect=lambda short,stream,clock:short),patch('eye_tracker.reposition.assisted_reference',side_effect=assisted),patch.object(self.trial,'reset_reference',side_effect=reset_reference):
   try:return run_visual_trial(Session(),Renderer(),self.trial,MMIO(),demo_seconds if demo_window else 300 if long_run else 90 if daily_mode else 80 if challenges is not None else 44 if emotion_mode else 38 if quick_mode or volume_mode else 18 if music_mode else 20 if assist else 10,clock=now,challenges=challenges,bank=PhraseBank(include_quick=quick_mode) if audible else None,auto_controls=auto_controls,event_link=link,music_library=SimpleNamespace(tracks=[{}]) if music_mode else None,quick_phrases=quick_mode,reposition_assist=assist,emotion_cards=emotion_mode,daily_tools=daily,demo_window=demo_window),stops
   finally:self.stops=stops;self.plays=plays;self.codec_log=codec_log

 def test_wireless_media_and_typing_only_original_actions_send_once(self):
  from eye_tracker.event_protocol import EVENTS,TEST
  for feature in ('music_mode','video_mode','book_mode','daily_mode','emotion_mode','quick_mode'):
   for mode in ('log','live'):
    with self.subTest(feature=feature,mode=mode):
     self.setUp();result,_=self.run_loop(audible=True,wireless_mode=mode,**{feature:True})
     expected=[EVENTS[e['key']] for e in self.trial.selections if e['key'] in EVENTS]
     self.assertEqual([p.code for p in self.wire.delivered],expected)
     self.assertTrue(all(p.detail==(TEST if mode=='log' else 0) for p in self.wire.delivered))
     self.assertEqual(result['communication']['counts'].get('remote_accepted',0),len(expected))
     if feature!='quick_mode':self.assertTrue(any(x==3 for x in expected))
     self.assertEqual(self.event_link.state,'disabled')
     self.assertLess(result['communication']['max_service_gap_ms'],250)

 def test_wireless_reference_rebind_and_failed_retry_cannot_restore_old_request(self):
  result,_=self.run_loop(audible=True,command_mask=4,assist=True,wireless_mode='live')
  self.assertEqual(result['communication']['controller_bindings'],2)
  self.assertEqual(len(self.assist_checks),2);self.assertEqual(len(self.wire.delivered),2)
  self.assertNotEqual(self.wire.delivered[0].session,self.wire.delivered[1].session)
  self.assertGreater(self.plays[1]-self.assist_checks[1]['time'],7.)
  self.setUp()
  with self.assertRaisesRegex(ValueError,'assisted_reference_not_completed'):
   self.run_loop(audible=True,command_mask=4,assist=True,assist_fail=True,wireless_mode='live')
  self.assertEqual(len(self.wire.delivered),1);self.assertEqual(self.event_link.state,'disabled')

 def test_wireless_missing_receivers_does_not_block_local_media_or_typing(self):
  for feature in ('music_mode','video_mode','book_mode','daily_mode'):
   self.setUp();result,_=self.run_loop(audible=True,wireless_mode='live',drop_ack=True,**{feature:True})
   self.assertGreater(len(self.plays),0);self.assertEqual(result['communication']['counts'].get('remote_accepted',0),0)
   self.assertGreater(len(self.trial.selections),5);self.assertEqual(self.event_link.state,'disabled')
   self.assertTrue(result['output_muted_on_exit'])
 def test_audiobook_camera_loop_help_priority_chapter_and_exit(self):
  result,_=self.run_loop(audible=True,book_mode=True)
  calls=self.music_calls
  self.assertEqual(calls.count('book_toggle'),3)
  self.assertIn('book_next',calls);self.assertIn('book_exit',calls);self.assertIn('book_close',calls)
  speech=calls.index('speech');self.assertIn('book_suspend',calls[speech-4:speech])
  self.assertEqual(calls[speech-1],'suspend')
  for i,key in enumerate(calls):
   if key=='book_toggle':self.assertEqual(calls[i-1],'stop')
  self.assertEqual(result['book_final']['state'],'paused');self.assertFalse(result['bookmark_save_failed'])
 def test_video_camera_loop_routes_controls_and_stops_before_help_speech(self):
  result,_=self.run_loop(audible=True,video_mode=True)
  calls=self.music_calls
  self.assertEqual(calls.count('video_toggle'),2)
  for key in ('video_controls','video_next','video_exit','video_close'):self.assertIn(key,calls)
  speech=calls.index('speech');self.assertIn('video_suspend',calls[speech-3:speech])
  for i,key in enumerate(calls):
   if key=='video_toggle':self.assertEqual(calls[i-1],'stop')
  self.assertEqual(len(self.plays),1);self.assertFalse(result['uart_enabled']);self.assertTrue(result['local_video_enabled'])
  self.assertTrue(all('camera_frame_index' in e and 'frame_index' in e for e in result['video_actions']))
 def test_video_decoder_cleanup_runs_even_when_display_raises(self):
  with self.assertRaisesRegex(RuntimeError,'display failure'):self.run_loop(audible=True,video_mode=True,fail=True)
  self.assertIn('video_close',self.music_calls)
 def test_daily_tools_camera_loop_composes_saves_displays_and_views_album(self):
  self.run_loop(audible=True,daily_mode=True)
  d=self.trial.controller.daily_tools
  self.assertEqual(d.composer.text,'你');self.assertEqual(d.composer.favorites.items,['你'])
  self.assertEqual(d.state,'photo_view');self.assertEqual(d.photo_index,1)
  self.assertEqual(len(self.plays),1)
  events=[r['local_action']['action'] for r in self.trial.rows if r.get('local_action')]
  for action in ('letters','candidate','save','show_draft','help','photo_view','photo_next'):self.assertIn(action,events)
  self.assertFalse(self.trial.uart_enabled)
 def test_assisted_retry_stops_audio_mutes_and_requires_fresh_dwell(self):
  self.run_loop(audible=True,command_mask=4,assist=True)
  self.assertEqual(len(self.assist_checks),2)
  self.assertTrue(all(x['audio_idle'] and x['muted'] for x in self.assist_checks))
  self.assertEqual(len(self.plays),2)
  self.assertGreater(self.plays[1]-self.assist_checks[1]['time'],7.)
  self.assertEqual(self.trial.controller.calibration_id,'fresh-reference-token')
  self.assertEqual([e['event'] for e in self.trial.summary['speech_events']],['started','interrupted','started','completed'])
 def test_emotions_use_camera_loop_without_speech_except_explicit_help(self):
  result,stops=self.run_loop(audible=True,emotion_mode=True)
  self.assertEqual([e['key'] for e in self.trial.selections],
      ['more','emotion_open','emotion_mood_open','emotion_happy','help','emotion_close',
       'emotion_mood_back','emotion_affection_open','emotion_thanks','emotion_close',
       'emotion_affection_back','emotion_menu_back','menu_back'])
  self.assertTrue(result['emotion_cards_enabled']);self.assertFalse(result['uart_enabled'])
  self.assertEqual(len(self.plays),1)
  self.assertEqual([(e['event'],e['key']) for e in result['speech_events']],[('started','help'),('completed','help')])
  self.assertIn('emotion_display_hint',self.feedbacks)
  self.assertIn('emotion_happy',{r['emotion_card'] for r in self.trial.rows})
  self.assertIn('emotion_thanks',{r['emotion_card'] for r in self.trial.rows})
  self.assertEqual(self.trial.controller.page,'main')
 def test_real_reference_reset_retains_opt_in_but_clears_displayed_expression(self):
  from unittest.mock import patch
  self.trial.controller.music_enabled=True;self.trial.controller.quick_phrases=True
  self.trial.controller.emotion_cards=True;self.trial.controller.page='emotion_display'
  self.trial.controller.emotion_key='emotion_sad'
  self.trial.reference_inputs=('model','evidence','root')
  self.trial.reference=SimpleNamespace();self.trial.summary={}
  fresh=SimpleNamespace(controller=DwellController(self.trial.controller.context),
      engine=SimpleNamespace(),reference=SimpleNamespace(),token='new-reference')
  with patch('eye_tracker.appearance_trial.VisualTrial',return_value=fresh):self.trial.reset_reference()
  self.assertTrue(self.trial.controller.emotion_cards)
  self.assertEqual(self.trial.controller.page,'main');self.assertIsNone(self.trial.controller.emotion_key)
  self.assertIsNone(self.trial.controller.calibration_id)
 def test_assisted_retry_failure_cleans_up_without_resuming_old_speech(self):
  with self.assertRaisesRegex(ValueError,'assisted_reference_not_completed'):
   self.run_loop(audible=True,command_mask=4,assist=True,assist_fail=True)
  self.assertEqual(len(self.plays),1)
  self.assertIsNone(self.trial.controller.calibration_id)
  self.assertTrue(self.trial.summary['output_muted_on_exit'])
  self.assertEqual([e['event'] for e in self.trial.summary['speech_events']],['started','interrupted'])
 def test_long_run_exceeds_short_audit_limit_without_repeating_held_speech(self):
  result,stops=self.run_loop(audible=True,long_run=True)
  self.assertGreater(result['telemetry']['total_frames'],1800)
  self.assertLessEqual(len(self.trial.rows),1800)
  self.assertLessEqual(len(self.trial.audit),120)
  self.assertEqual(len(self.plays),1)
  self.assertEqual(self.trial.event_total('selections'),1)
  self.assertFalse(result['uart_enabled'])
  self.assertTrue(result['output_muted_on_exit'])
  self.assertFalse(result['audio_busy_on_exit'])
  import json
  json.dumps(result)

 def test_forty_minute_demo_fake_clock_exits_and_keeps_bounded_records(self):
  result,stops=self.run_loop(audible=True,long_run=True,demo_window=True)
  self.assertEqual(result['exit_reason'],'duration')
  self.assertGreaterEqual(result['interaction_seconds'],2400)
  self.assertLess(result['interaction_seconds'],2401)
  self.assertLessEqual(len(self.trial.rows),1800)
  self.assertLessEqual(len(self.trial.audit),120)
  self.assertEqual(len(self.plays),1)
  self.assertTrue(result['output_muted_on_exit'])
  self.assertFalse(result['audio_busy_on_exit'])

 def test_one_hour_demo_fake_clock_stops_audio_and_keeps_bounded_records(self):
  result,stops=self.run_loop(audible=True,long_run=True,demo_window=True,demo_seconds=3600)
  self.assertEqual(result['exit_reason'],'duration')
  self.assertGreaterEqual(result['interaction_seconds'],3600)
  self.assertLess(result['interaction_seconds'],3601)
  self.assertLessEqual(len(self.trial.rows),1800)
  self.assertLessEqual(len(self.trial.audit),120)
  self.assertEqual(len(self.plays),1)
  self.assertTrue(result['output_muted_on_exit'])
  self.assertFalse(result['audio_busy_on_exit'])

 def test_setup_progress_never_starts_speech_before_reference_validation(self):
  self.run_loop(audible=True,incremental_setup=True)
  self.assertEqual([n for n,failed,t in self.setup_frames],[0,1,2,3,4,5])
  self.assertGreater(self.plays[0],self.setup_frames[-1][2])
  self.assertIn('guide_ready',self.feedbacks)
  self.assertTrue(all('usage_feedback' in r for r in self.trial.rows))

 def test_music_navigation_uses_real_dwell_and_help_suspends_before_speech(self):
  self.run_loop(audible=True,music_mode=True)
  keys=[e['key'] for e in self.trial.selections]
  self.assertEqual(keys,['more','music_open','music_player_open','music_toggle','help','music_back'])
  self.assertEqual(len(self.plays),1)
  pos=self.music_calls.index('speech')
  self.assertEqual(self.music_calls[pos-1],'suspend')
  self.assertIn('music_playing',self.feedbacks)
  self.assertIn('music_back',self.music_calls)
  self.assertEqual(self.music_calls[-1],'stop')

 def test_both_quick_pages_use_camera_loop_dwell_and_single_speech(self):
  from eye_tracker.phrases import QUICK_KEYS
  result,stops=self.run_loop(audible=True,quick_mode=True,music_mode=True)
  self.assertEqual([r['key'] for r in self.trial.selections],
      ['more','quick_open','yes','no','please_stop','quick_back','care_open','reposition','toilet','unwell','care_back','menu_back'])
  events=self.trial.summary['speech_events']
  self.assertEqual([e['key'] for e in events if e['event']=='started'],list(QUICK_KEYS))
  self.assertEqual(len([e for e in events if e['event']=='completed']),6)
  self.assertEqual(len(self.plays),6)
  for i,call in enumerate(self.music_calls):
   if call=='speech':self.assertEqual(self.music_calls[i-1],'suspend')
  self.assertTrue(result['quick_phrases_enabled']);self.assertFalse(result['uart_enabled'])
  self.assertTrue(result['output_muted_on_exit']);self.assertEqual(self.trial.controller.page,'main')

 def test_volume_page_routes_real_dwell_once_and_keeps_help_and_cleanup(self):
  result,stops=self.run_loop(audible=True,volume_mode=True)
  self.assertEqual([e['key'] for e in self.trial.selections],
      ['more','music_open','music_volume_open','music_volume_down','music_volume_up','help',
       'music_volume_back','music_player_open','music_toggle','music_back','music_menu_back','menu_back'])
  actions=self.trial.summary['music_actions']
  self.assertEqual([e['volume_level'] for e in actions if e['key'].startswith('music_volume_')],[5,4,5,5])
  self.assertEqual(len(self.plays),1);self.assertEqual(self.trial.controller.page,'main')
  self.assertIn('music_volume_hint',self.feedbacks)
  self.assertIn('music_hub_hint',self.feedbacks)
  self.assertEqual(result['music_final']['volume_level'],5)
  self.assertTrue(result['output_muted_on_exit']);self.assertFalse(result['uart_enabled'])

 def test_quick_pages_require_checked_audible_bank_before_actions(self):
  with self.assertRaisesRegex(ValueError,'checked speech bank'):
   self.run_loop(quick_mode=True,audible=False)
  self.assertEqual(self.plays,[])

 def test_failed_reference_shows_failure_and_never_starts_actions(self):
  with self.assertRaisesRegex(ValueError,'current_center_reference'):
   self.run_loop(audible=True,setup_fail=True)
  self.assertTrue(self.setup_frames[-1][1])
  self.assertEqual(self.plays,[]);self.assertEqual(self.trial.selections,[])
  self.assertEqual(self.codec_log,['configure','mute'])
 def test_short_mode_still_refuses_recording_overflow(self):
  self.trial.rows=[];self.trial.audit=[None]*1200
  with self.assertRaisesRegex(ValueError,'recording_full'):
   self.trial.observe(None,1,1.)

 def test_automatic_helper_test_cancels_and_pauses_only_real_selections(self):
  self.run_loop(audible=True,auto_controls=True)
  self.assertEqual([e['key'] for e in self.trial.summary['speech_events'] if e['event']=='started'],['water','help'])
  self.assertEqual([c['command'] for c in self.trial.commands],['cancel','toggle_pause','toggle_pause'])
  self.assertTrue(all(c['source']=='automatic_test' and not c['audio_busy_after'] for c in self.trial.commands))
  self.assertFalse(self.trial.controller.paused)
  self.assertEqual([e['event'] for e in self.trial.summary['speech_events']],['started','interrupted','started','interrupted'])
 def test_live_speech_once_and_no_held_target_repeat_or_queue(self):
  result,stops=self.run_loop(audible=True)
  self.assertTrue(result['audio_enabled']);self.assertFalse(result['uart_enabled'])
  self.assertEqual(len(self.plays),1);self.assertEqual(len(self.trial.selections),1)
  events=self.trial.summary['speech_events'];self.assertEqual([e['event'] for e in events],['started','completed'])
  self.assertEqual(events[0]['source'],'live')
  blocked=[r for r in self.trial.rows if r['reason']=='speaking']
  self.assertTrue(blocked);self.assertTrue(all(r['progress']==0 and r['visual_selection'] is None for r in blocked))
  self.assertEqual(self.codec_log,['configure','enable','mute'])
  self.assertTrue(self.trial.summary['output_muted_on_exit']);self.assertFalse(self.trial.summary['audio_busy_on_exit'])
 def test_live_helpers_stop_active_phrase_and_never_resume_it(self):
  for mask in (1,2,4,8):
   with self.subTest(mask=mask):
    self.setUp();self.run_loop(audible=True,command_mask=mask)
    self.assertEqual(len(self.plays),1)
    self.assertEqual([e['event'] for e in self.trial.summary['speech_events']],['started','interrupted'])
    self.assertTrue(all(not c['audio_busy_after'] for c in self.trial.commands))
    self.assertTrue(self.trial.summary['output_muted_on_exit'])
    if mask==4:self.assertIsNone(self.trial.controller.calibration_id)
    if mask==8:self.assertTrue(self.trial.controller.closed)
 def test_live_setup_and_display_failures_always_stop_and_mute(self):
  for codec_fail in (False,True):
   with self.subTest(codec_fail=codec_fail):
    self.setUp()
    with self.assertRaises(RuntimeError):self.run_loop(fail=True,audible=True,codec_fail=codec_fail)
    self.assertEqual(self.codec_log[-1],'mute');self.assertGreaterEqual(len(self.stops),2)
    self.assertFalse(self.trial.summary['audio_busy_on_exit'])
    self.assertFalse(any(failed for count,failed,t in self.setup_frames))

 def test_runtime_camera_frames_drive_ui_but_no_audio_play_path(self):
  result,stops=self.run_loop()
  self.assertEqual(len(self.trial.selections),1)
  self.assertFalse(result['audio_enabled']);self.assertFalse(result['uart_enabled'])
  self.assertEqual(len(stops),2);self.assertGreater(len(self.trial.rows),50)
 def test_challenge_prompts_do_not_override_candidate_dwell_or_locks(self):
  from eye_tracker.trial_challenges import TrialChallenges,PLAN
  schedule=TrialChallenges();result,stops=self.run_loop(challenges=schedule)
  self.assertEqual(len(self.trial.selections),1)
  self.assertEqual(self.trial.selections[0]['key'],'water')
  self.assertEqual({x['prompt_phase'] for x in self.trial.rows},{x['phase'] for x in PLAN})
  self.assertTrue(all(x['candidate']=='water' and x['stable_candidate']=='water' for x in self.trial.rows))
  self.assertEqual(len(self.trial.summary['challenge_schedule']['presentations']),len(PLAN))
  self.assertFalse(result['audio_enabled']);self.assertFalse(result['uart_enabled'])
  self.assertEqual(len(stops),2)
 def test_display_failure_stops_audio_and_keeps_observations(self):
  with self.assertRaisesRegex(RuntimeError,'display failure'):self.run_loop(True)
  self.assertEqual(len(self.stops),2);self.assertGreater(len(self.trial.rows),0)

 def test_previous_seed_preserves_fresh_center_requirement_and_bounds(self):
  import numpy as np
  from eye_tracker.appearance_trial import seed_previous_eye
  e=SimpleNamespace(anchor=SimpleNamespace(origin_shift=np.zeros(2)),baseline=SimpleNamespace(offset=None))
  d={'reference_relocation':{'origin_shift':[-56,52],'score':.939,'margin':.054},'center_reference':{'ready':True}}
  seed_previous_eye(e,d);np.testing.assert_allclose(e.anchor.origin_shift,[-56,52])
  self.assertIsNone(e.baseline.offset)
  d['reference_relocation']['margin']=.03
  with self.assertRaises(ValueError):seed_previous_eye(e,d)

 def test_reference_retries_rejected_blink_without_reusing_old_offset(self):
  import numpy as np
  from eye_tracker.appearance_trial import TrialReference
  class Engine:
   def __init__(self):self.baseline=SimpleNamespace(samples=[]);self.attempts=0
   def observe_reference(self,pixels,index,copied,eligible,clock):
    accepted=False
    if eligible:
     self.attempts+=1
     if self.attempts!=2:self.baseline.samples.append(index);accepted=True
    return dict(candidate=None,stable_candidate=None,reference_sample=accepted,processing_ms=1)
  engine=Engine();record=TrialReference(engine,lambda:0)
  pixels=np.zeros((480,640),np.uint8)
  for i in range(1,91):record.observe(pixels,i,i*.1,i*.1+.01,0,0)
  self.assertEqual(engine.attempts,6);self.assertEqual(len(engine.baseline.samples),5)
  self.assertEqual(sum(x[0]['reference_sample'] for x in record.samples),5)


class CurrentNeighborhoodTests(unittest.TestCase):
 def fixture(self):
  import numpy as np
  e=SimpleNamespace(anchor=SimpleNamespace(origin_shift=np.array([-56.,52.]),box=(138,76,362,300)),
      baseline=SimpleNamespace(summary={'ready':True},ids=set(range(1,6))),relocation={})
  rows=[dict(frame_index=i,reference_sample=True,translation=[-40,120+d]) for i,d in enumerate((-2,-1,0,1,2),1)]
  return e,rows
 def test_only_fresh_accepted_setup_moves_frozen_search_origin(self):
  from eye_tracker.appearance_trial import freeze_current_neighborhood
  import numpy as np
  e,rows=self.fixture();rows.append(dict(frame_index=6,reference_sample=False,translation=[999,999]))
  result=freeze_current_neighborhood(e,rows)
  np.testing.assert_allclose(e.anchor.origin_shift,[-40,120]);self.assertAlmostEqual(result['radius_pixels'],78.4)
  self.assertEqual(result['frame_ids'],list(range(1,6)))
 def test_missing_duplicate_or_foreign_setup_never_moves_origin(self):
  from eye_tracker.appearance_trial import freeze_current_neighborhood
  import numpy as np
  for kind in ('missing','duplicate','foreign'):
   e,rows=self.fixture()
   if kind=='missing':rows.pop()
   elif kind=='duplicate':rows[-1]['frame_index']=1
   else:rows[-1]['frame_index']=100
   with self.assertRaises(ValueError):freeze_current_neighborhood(e,rows)
   np.testing.assert_array_equal(e.anchor.origin_shift,[-56,52])
 def test_unverified_or_outside_origin_rejected_without_relaxation(self):
  from eye_tracker.appearance_trial import freeze_current_neighborhood
  import numpy as np
  for kind in ('unready','outside','nan'):
   e,rows=self.fixture()
   if kind=='unready':e.baseline.summary={'ready':False}
   elif kind=='outside':rows[0]['translation']=[400,400]
   else:rows[0]['translation']=[float('nan'),0]
   with self.assertRaises(ValueError):freeze_current_neighborhood(e,rows)
   np.testing.assert_array_equal(e.anchor.origin_shift,[-56,52])
 def test_recentered_matcher_accepts_local_motion_but_still_rejects_escape_and_blank(self):
  import sys,numpy as np
  from pathlib import Path
  sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools/deps/opencv'))
  import cv2
  from eye_tracker.appearance_diagnostic import TranslationMatcher
  from eye_tracker.appearance_trial import freeze_current_neighborhood
  from eye_tracker.appearance import AlignmentFailure
  rng=np.random.default_rng(53);ref=cv2.GaussianBlur(rng.integers(0,256,(480,640),dtype=np.uint8),(11,11),3)
  matcher=TranslationMatcher(ref,(160,100,360,300))
  image=lambda dx:cv2.warpAffine(ref,np.float32([[1,0,dx],[0,1,0]]),(640,480))
  with self.assertRaises(AlignmentFailure):matcher.align(image(84))
  e=SimpleNamespace(anchor=matcher,baseline=SimpleNamespace(summary={'ready':True},ids=set(range(1,6))),relocation={})
  rows=[dict(frame_index=i,reference_sample=True,translation=[60,0]) for i in range(1,6)]
  freeze_current_neighborhood(e,rows);patch,metrics=matcher.align(image(84))
  np.testing.assert_allclose(metrics['translation'],[84,0],atol=.5)
  for pixels in (image(140),np.zeros_like(ref)):
   with self.assertRaises(AlignmentFailure):matcher.align(pixels)
  np.testing.assert_array_equal(matcher.origin_shift,[60,0])


class SeedEvidenceTests(unittest.TestCase):
 evidence=VisualTrialTests.evidence
 def test_seed_is_only_position_and_checks_pack_and_positive_record(self):
  import tempfile,json,numpy as np
  from pathlib import Path
  from eye_tracker.appearance_trial import load_verified_setup_seed
  e=SimpleNamespace(pack_sha256='test-pack',anchor=SimpleNamespace(origin_shift=np.zeros(2)),baseline=SimpleNamespace(offset=None))
  d=self.evidence();d.update(model_pack_sha256='test-pack',reference_relocation={'origin_shift':[-56,52],'score':.939,'margin':.054},center_reference={'ready':True})
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'diagnostic.json';p.write_text(json.dumps(d));load_verified_setup_seed(e,folder)
   self.assertIsNone(e.baseline.offset);self.assertIn('seed_evidence_sha256',e.relocation)
   d['model_pack_sha256']='different';p.write_text(json.dumps(d))
   with self.assertRaisesRegex(ValueError,'model_mismatch'):load_verified_setup_seed(e,folder)

 def test_seeded_check_needs_positive_current_results_and_identity_provenance(self):
  import numpy as np
  from eye_tracker.appearance_trial import seed_previous_eye
  e=SimpleNamespace(anchor=SimpleNamespace(origin_shift=np.zeros(2)))
  d=self.evidence();d.update(reference_relocation=dict(origin_shift=[-56,52],previous_score=.939,previous_margin=.054,seed_evidence_sha256='a'*64),center_reference={'ready':True})
  seed_previous_eye(e,d);np.testing.assert_array_equal(e.anchor.origin_shift,[-56,52])
  d['frames'][0]['candidate']='water'
  with self.assertRaises(ValueError):seed_previous_eye(e,d)
  d['reference_relocation']['seed_evidence_sha256']='bad'
  with self.assertRaisesRegex(ValueError,'provenance'):seed_previous_eye(e,d)

 def test_feature_revision_can_reuse_only_exact_same_eye_position(self):
  import tempfile,json,numpy as np
  from pathlib import Path
  from unittest.mock import patch
  from eye_tracker.appearance_trial import load_verified_setup_seed
  def engine(h):
   return SimpleNamespace(pack_sha256=h,reference=np.zeros((480,640),np.uint8),box=(100,100,300,300),
      anchor=SimpleNamespace(corners=np.array([[120,200],[280,200]]),origin_shift=np.zeros(2)),baseline=SimpleNamespace(offset=None))
  old,new=engine('old'),engine('new')
  d=self.evidence();d.update(model_pack_sha256='old',reference_relocation=dict(origin_shift=[-56,52],score=.939,margin=.054),center_reference={'ready':True})
  with tempfile.TemporaryDirectory() as folder,patch('eye_tracker.appearance_trial.AppearanceDiagnostic',return_value=old):
   (Path(folder)/'diagnostic.json').write_text(json.dumps(d))
   load_verified_setup_seed(new,folder,'original-pack')
   np.testing.assert_array_equal(new.anchor.origin_shift,[-56,52])
   self.assertIsNone(new.baseline.offset)
   self.assertEqual(new.relocation['seed_model_pack_sha256'],'old')
   for change in ('hash','reference','box','corners'):
    old,new=engine('old'),engine('new')
    if change=='hash':old.pack_sha256='not-the-evidence'
    elif change=='reference':old.reference[0,0]=1
    elif change=='box':old.box=(101,100,301,300)
    else:old.anchor.corners[0,0]+=1
    with patch('eye_tracker.appearance_trial.AppearanceDiagnostic',return_value=old):
     with self.assertRaises(ValueError):load_verified_setup_seed(new,folder,'original-pack')
    np.testing.assert_array_equal(new.anchor.origin_shift,[0,0])
    self.assertIsNone(new.baseline.offset)


class SetupReacquisitionTests(unittest.TestCase):
 def fixture(self,fail=False):
  import numpy as np
  from eye_tracker.appearance_trial import TrialReference
  class Engine:
   def __init__(self):
    self.baseline=SimpleNamespace(samples=[])
    self.anchor=SimpleNamespace(origin_shift=np.array([-56.,52.]),acquire=self.acquire)
    self.relocation={'previous_score':.94,'previous_margin':.05}
    self.calls=[];self.gate=StableCandidate();self.cv=SimpleNamespace(error=RuntimeError)
   def acquire(self,pixels):
    self.anchor.origin_shift=np.array([80.,10.])
    if fail:raise ValueError('setup_identity_ambiguous')
    return {'score':.95,'margin':.06,'origin_shift':[80.,10.]}
   def observe_reference(self,pixels,index,copied,eligible,clock):
    self.gate.update(None,index,copied,clock())
    self.calls.append((index,eligible))
    if not eligible:return {'reference_sample':False}
    if self.relocation.get('setup_reacquired_before_first_reference'):
     self.baseline.samples.append(index)
     return {'reference_sample':True,'translation':[80.,10.]}
    return {'reference_sample':False,'rejection':'neighborhood_not_matched'}
  e=Engine();return e,TrialReference(e,lambda:20.),np.zeros((480,640),np.uint8)
 def test_stale_seed_reacquires_position_then_uses_a_new_capture(self):
  e,r,p=self.fixture();r.observe(p,1,2.1,2.2,0,0)
  self.assertEqual(e.calls,[(1,True)]);self.assertEqual(e.baseline.samples,[])
  self.assertTrue(e.relocation['setup_reacquired_before_first_reference'])
  self.assertTrue(r.rows[-1]['setup_reacquisition_deferred_to_next_frame'])
  self.assertFalse(r.rows[-1]['reference_sample'])
  r.observe(p,2,3.,3.1,0,0)
  self.assertEqual(e.calls,[(1,True),(2,True)])
  self.assertEqual(e.baseline.samples,[2]);self.assertEqual(r.reacquire_attempts,1)
  self.assertEqual(e.gate.last_index,2)
 def test_ambiguous_reacquisition_restores_seed_and_is_bounded(self):
  import numpy as np
  e,r,p=self.fixture(fail=True)
  for i in range(1,7):r.observe(p,i,i+1.,i+1.1,0,0)
  np.testing.assert_array_equal(e.anchor.origin_shift,[-56.,52.])
  self.assertEqual(r.reacquire_attempts,3);self.assertEqual(e.baseline.samples,[])
  self.assertEqual(len(e.calls),6);self.assertEqual(e.gate.last_index,6)
  self.assertFalse(any(row['reference_sample'] for row in r.rows))
  self.assertEqual(e.relocation['previous_score'],.94)


class PairEvidenceHashTests(unittest.TestCase):
 def test_paired_matcher_cannot_borrow_evidence_from_changed_or_unrecorded_code(self):
  import tempfile,hashlib,json
  from pathlib import Path
  from unittest.mock import patch
  fake=SimpleNamespace(metadata={'strict_training_passed':True,'corner_search_mode':'paired_corners_v1'},pack_sha256='pack',geometry_id='geo')
  with tempfile.TemporaryDirectory() as folder,patch('eye_tracker.appearance_trial.AppearanceDiagnostic',return_value=fake),patch('eye_tracker.appearance_trial.positive_entry',return_value={}),patch('eye_tracker.appearance_trial.seed_previous_eye'):
   root=Path(folder);(root/'src/eye_tracker').mkdir(parents=True);hashes={}
   for n in ('appearance.py','appearance_diagnostic.py','corner_pair.py'):
    rel='src/eye_tracker/'+n;(root/rel).write_bytes(n.encode());hashes[rel]=hashlib.sha256(n.encode()).hexdigest()
   hashes['data/private/diagnostic/model.npz']='pack'
   (root/'diagnostic.json').write_text(json.dumps({'model_pack_sha256':'pack'}))
   for mode in ('missing','changed','matching'):
    h=dict(hashes)
    if mode=='missing':h.pop('src/eye_tracker/corner_pair.py')
    if mode=='changed':h['src/eye_tracker/corner_pair.py']='bad'
    (root/'runtime_manifest.json').write_text(json.dumps({'runtime_files':h}))
    if mode=='matching':VisualTrial('unused',root,root)
    else:
     with self.assertRaisesRegex(ValueError,'classifier_changed'):VisualTrial('unused',root,root)

class NamedModelEvidenceTests(unittest.TestCase):
 def test_fresh_session_candidate_requires_its_own_evidence_hash(self):
  import tempfile,hashlib,json
  from pathlib import Path
  from unittest.mock import patch
  fake=SimpleNamespace(metadata={'strict_training_passed':True,'corner_search_mode':'paired_corners_v1'},pack_sha256='newpack',geometry_id='geo')
  with tempfile.TemporaryDirectory() as folder,patch('eye_tracker.appearance_trial.AppearanceDiagnostic',return_value=fake),patch('eye_tracker.appearance_trial.positive_entry',return_value={}),patch('eye_tracker.appearance_trial.seed_previous_eye'):
   root=Path(folder);(root/'src/eye_tracker').mkdir(parents=True);hashes={}
   for name in ('appearance.py','appearance_diagnostic.py','corner_pair.py'):
    rel='src/eye_tracker/'+name;(root/rel).write_bytes(name.encode());hashes[rel]=hashlib.sha256(name.encode()).hexdigest()
   hashes['data/private/diagnostic/model.npz']='oldpack'
   model_file='data/private/bringup/current/session_calibration/model.npz'
   (root/'diagnostic.json').write_text(json.dumps({'model_pack_sha256':'newpack'}))
   for declared in ('missing','oldpack','newpack'):
    h=dict(hashes)
    if declared!='missing':h[model_file]=declared
    (root/'runtime_manifest.json').write_text(json.dumps({'runtime_files':h,'model_file':model_file}))
    if declared=='newpack':VisualTrial('unused',root,root)
    else:
     with self.assertRaisesRegex(ValueError,'model_changed_after_positive'):VisualTrial('unused',root,root)
