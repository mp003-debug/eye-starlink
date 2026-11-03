"""Synthetic video/clock/priority checks; no board or live eye claims."""
import copy,json,tempfile,unittest,wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from eye_tracker.video_library import VideoLibrary,sha,stamp
from eye_tracker.video import VideoPlayer,STARTUP_TIMEOUT
from eye_tracker.music import StreamAudioDevice
from test_music import StreamMMIO
from test_daily_tools import fixture
from eye_tracker.interaction import DwellController,GazeSample
from eye_tracker.calibration import Context

class InstantDecoder:
    def __init__(self,clip):self.index=None;self.stopped=False;self.reaped=False;self.fail=False;self.stall=False
    def request(self,index):self.index=index
    def poll(self):
        if self.fail:raise ValueError('decode failed')
        if self.stall:return None
        return self.index,np.full((198,352),self.index,dtype='<u2')
    def stop(self):self.stopped=True
    def reap(self,timeout=0):self.reaped=True;return True

class VideoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.time=0.;self.mmio=StreamMMIO();self.device=StreamAudioDevice(self.mmio)
        p=self.root/'test.mp4';p.write_bytes(b'placeholder for catalogue-only tests')
        self.row=dict(id='test',title='测试短片',width=320,height=180,fps=8,frames=32,file=p.name,sha256=sha(p),audio=None)
        self.values=((np.arange(64000)%12000)-6000).astype('<i2')
        wav=self.root/'test.wav'
        with wave.open(str(wav),'wb') as w:w.setparams((1,2,16000,0,'NONE',''));w.writeframes(self.values.tobytes())
        self.audio=dict(file=wav.name,sha256=sha(wav))
    def library(self,row=None):
        (self.root/'playlist.json').write_text(json.dumps(dict(version=1,clips=[row or self.row])),encoding='utf-8')
        return VideoLibrary(self.root)
    def player(self,audio=False):
        if audio:self.row['audio']=self.audio
        p=VideoPlayer(self.library(),self.device,lambda:self.time,InstantDecoder);self.addCleanup(p.close);return p
    def test_catalogue_rejects_traversal_bad_hash_duration_shape_and_duplicates(self):
        for field,value in [('file','../test.mp4'),('file','C:\\test.mp4'),('sha256','0'*64),('frames',481),('frames',True),('fps',12),('width',480),('title','bad\n')]:
            with self.subTest(field=field):
                row=copy.deepcopy(self.row);row[field]=value
                with self.assertRaises(ValueError):self.library(row)
        (self.root/'playlist.json').write_text(json.dumps(dict(version=1,clips=[self.row]*2)))
        with self.assertRaises(ValueError):VideoLibrary(self.root)
    def test_audio_sample_count_and_peak_checked_before_play(self):
        self.row['audio']=self.audio;self.assertEqual(self.library().clips[0]['audio']['frames'],64000)
        self.row['frames']=31
        with self.assertRaisesRegex(ValueError,'matching'):self.library()
        self.row['frames']=32
        with wave.open(str(self.root/'test.wav'),'wb') as w:w.setparams((1,2,16000,0,'NONE',''));w.writeframes(np.full(64000,9000,dtype='<i2').tobytes())
        self.row['audio']['sha256']=sha(self.root/'test.wav')
        with self.assertRaisesRegex(ValueError,'peak'):self.library()
    def test_empty_library_never_starts_worker_or_audio(self):
        p=VideoPlayer(SimpleNamespace(clips=[]),self.device,decoder_factory=lambda _:self.fail('worker on empty library'))
        p.play();p.next();p.poll();p.close();self.assertFalse(self.mmio.busy)
    def test_silent_pause_freezes_clock_and_picture_then_resumes_explicitly(self):
        p=self.player();p.play();self.assertEqual(p.state,'loading');self.time=1.;p.poll()
        self.assertEqual(p.position,0);self.time=1.51;p.poll();self.assertEqual(p.frame_index,4)
        p.suspend();f=p.frame.copy();pos=p.position;self.time=80;p.poll()
        self.assertEqual(p.position,pos);np.testing.assert_array_equal(f,p.frame)
        p.play();p.poll();self.time+=.25;p.poll();self.assertAlmostEqual(p.position,pos+.25)
    def test_audio_clock_uses_consumed_samples_and_help_resume_keeps_sample_order(self):
        p=self.player(True);p.play();p.poll();self.mmio.consume(10101);self.time=.01;p.poll()
        self.assertAlmostEqual(p.position,10101/16000);self.assertEqual(p.frame_index,5)
        p.suspend();self.assertFalse(self.mmio.busy);self.time=50;p.poll();self.assertEqual(len(self.mmio.played),10101)
        p.play();p.poll()
        for _ in range(60):
            self.mmio.consume(1000);self.time+=.06;p.poll()
            if p.state=='ended':break
        self.assertEqual(p.state,'ended');self.assertEqual(p.stats['ends'],1)
        np.testing.assert_array_equal(self.mmio.played,self.values);self.assertFalse(self.mmio.busy)
    def test_decode_fault_stops_audio_and_never_automatically_restarts(self):
        p=self.player(True);p.play();p.poll();p.decoder.fail=True;p.poll()
        self.assertEqual(p.state,'fault');self.assertFalse(self.mmio.busy);p.poll();self.assertEqual(p.stats['starts'],1)
    def test_startup_and_decode_lag_have_bounded_timeouts(self):
        p=self.player();p.play();p.decoder.stall=True;self.time=STARTUP_TIMEOUT+.1;p.poll();self.assertEqual(p.state,'fault')
        p.poll();p.play();p.poll();p.decoder.stall=True;self.time+=1.;p.poll();self.assertEqual(p.state,'fault')
    def test_return_next_and_exit_discard_old_decode_frames(self):
        p=self.player(True);p.play();p.poll();old=p.decoder;p.action('video_controls')
        self.assertEqual(p.state,'paused');self.assertFalse(self.mmio.busy)
        p.action('video_next');self.assertTrue(old.stopped);self.assertIsNone(p.frame);self.assertEqual(p.offset,0)
        p.poll();p.play();p.poll();self.assertIsNot(p.decoder,old);p.action('video_exit');self.assertIsNone(p.frame)
    def test_paused_video_cleanup_does_not_stop_a_later_speech_owner(self):
        p=self.player(True);p.play();p.poll();p.suspend()
        self.mmio.busy=True;p.stop();self.assertTrue(self.mmio.busy);self.mmio.busy=False
    def test_busy_retired_process_blocks_new_worker(self):
        p=self.player();p.play();p.poll();old=p.decoder;old.reap=lambda timeout=0:False
        p.stop();p.play();self.assertEqual(p.state,'fault');self.assertIsNone(p.decoder)
        old.reap=lambda timeout=0:True

class VideoNavigationTests(unittest.TestCase):
    def setUp(self):
        self.d=fixture();self.d.video_library=SimpleNamespace(clips=[dict(title='测试短片')])
        self.c=DwellController(Context('test','four','live'),'checked',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=self.d)
        self.c.page='local_tools';self.seq=0;self.t=0
    def feed(self,point,n=15):
        events=[]
        for _ in range(n):
            self.seq+=1;self.t+=100
            a=self.c.feed(GazeSample(self.c.context,'checked',self.seq,self.t,'valid',point),self.t)
            if a:events.append(a.key)
        return events
    def test_media_branch_preserves_old_album_and_no_hardware_action_on_selection(self):
        self.d.open('album');self.assertEqual(self.d.state,'media');self.d.select(0);self.assertEqual(self.d.state,'album')
        self.d.select(3);self.assertEqual(self.d.state,'media');self.d.select(1);self.d.select(0)
        self.assertEqual(self.d.state,'video_view');self.assertEqual(self.d.video_command,'video_toggle');self.assertIsNone(self.d.video_player)
        self.d.reset_navigation();self.assertIsNone(self.d.video_command)
    def test_watch_upper_targets_cannot_select_and_lower_help_control_need_new_dwell(self):
        self.d.state='video';self.assertEqual(self.feed((.25,.38)),['tool_slot_0'])
        self.assertEqual(self.feed((.25,.38),35),[]);self.assertEqual(self.feed((.75,.38),20),[])
        self.assertEqual(self.feed((.75,.70)),['tool_slot_3']);self.assertEqual(self.d.state,'video')
        self.assertEqual(self.feed((.75,.70),20),[])
    def test_watch_renderer_reuses_cache_while_progress_and_frames_change(self):
        from eye_tracker.ui import BoardRenderer
        self.d.state='video_view';self.d.video_player=SimpleNamespace(index=0,state='playing',frame=np.zeros((198,352),dtype='<u2'),position=.2,duration=4.)
        r=BoardRenderer();r.bind_daily_tools(self.d);first=r.rgb565(self.c,'guide_ready');builds=r.daily_renderer.cache_builds
        with patch.object(r.daily_renderer.atlas,'draw',side_effect=AssertionError('per-frame text rebuild')):
            self.d.video_player.position=.5;self.d.video_player.frame.fill(65535);other=r.rgb565(self.c,'guide_ready')
        self.assertNotEqual(first,other);self.assertEqual(r.daily_renderer.cache_builds,builds)
        self.assertEqual([t.key for t in self.c.targets],['help','tool_slot_3'])
        self.c.target_key='tool_slot_3';self.c.progress=.6
        words=np.frombuffer(r.rgb565(self.c),dtype='<u2').reshape(480,640)
        self.assertGreater(np.count_nonzero(((words[322:352,410:534]>>11)&31)<16),400)
    def test_video_launch_requires_explicit_local_dependencies(self):
        from eye_tracker.launch import prepare_launch
        with self.assertRaisesRegex(ValueError,'daily tools'):prepare_launch('not-read.json',local_video=True)
