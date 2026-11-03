import hashlib,json,tempfile,unittest,wave
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from eye_tracker.music import MusicLibrary,StreamAudioDevice,MusicPlayer,BANK_SAMPLES
from eye_tracker.audio import AudioDevice,AudioError
from eye_tracker.interaction import DwellController,GazeSample
from eye_tracker.calibration import Context


class StreamMMIO:
    """Register-level device fixture; pin-level sample order tested by XSim."""
    def __init__(self):
        self.array=np.zeros(0x20000//4,dtype='<u4');self.ready={};self.busy=False
        self.paused=False;self.done=False;self.fault=0;self.consumed=0;self.bank=0;self.pos=0
        self.played=[];self.mode=0;self.ignore_pause=False
    def read(self,r):
        return {0:0x41554431,4:0x00020000,0xc:8|int(self.busy)|int(self.done)*2|int(self.paused)*16|self.fault,
                0x34:sum(1<<b for b in self.ready),0x40:self.consumed}.get(r,0)
    def write(self,r,v):
        if r==8:
            if v==2:self.busy=False;self.paused=False;self.ready={}
            elif v==4:self.done=False;self.fault=0
            elif v==1:
                self.busy=True;self.bank=0;self.pos=0;self.consumed=0;self.done=False
            elif v==8 and not self.ignore_pause:self.paused=True
            elif v==16:self.paused=False
        elif r==0x30:self.mode=v;self.ready={}
        elif r in (0x38,0x3c):
            b=(r-0x38)//4;n=v&0x7fff;start=(0x10000+b*0x8000)//4
            if b in self.ready:raise RuntimeError('overwrite')
            self.ready[b]=(self.array[start:start+(n+1)//2].view('<i2')[:n].copy(),bool(v>>31))
    def consume(self,n):
        for _ in range(n):
            if not self.busy or self.paused:break
            data,last=self.ready[self.bank];self.played.append(int(data[self.pos]));self.pos+=1;self.consumed+=1
            if self.pos==len(data):
                del self.ready[self.bank];self.pos=0;self.bank^=1
                if last:self.busy=False;self.done=True
                elif self.bank not in self.ready:self.busy=False;self.fault=36


class MusicTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.clock=0.
        self.values=((np.arange(64007)%12000)-6000).astype('<i2')
        self.make_library(self.values)
        self.mmio=StreamMMIO();self.device=StreamAudioDevice(self.mmio)
        self.player=MusicPlayer(self.device,MusicLibrary(self.root),lambda:self.clock)
    def make_library(self,values,name='song.wav'):
        path=self.root/name
        with wave.open(str(path),'wb') as w:
            w.setparams((1,2,16000,len(values),'NONE',''));w.writeframes(values.tobytes())
        self.manifest={'version':1,'tracks':[dict(id='one',title='测试音乐',file=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest())]}
        self.save_manifest()
    def save_manifest(self):(self.root/'playlist.json').write_text(json.dumps(self.manifest),encoding='utf-8')
    def finish(self):
        for _ in range(200):
            self.mmio.consume(1000);self.clock+=.06;self.player.poll()
            if self.player.state=='ended':return
        self.fail('did not finish')
    def test_long_music_crosses_reused_banks_in_order_and_finishes_once(self):
        self.player.play();self.assertFalse(self.player.play())
        self.finish()
        np.testing.assert_array_equal(self.mmio.played,self.values)
        self.assertFalse(self.player.live);self.assertIsNone(self.player.reader)
        self.player.poll();self.assertEqual(len(self.mmio.played),len(self.values))
    def test_pause_resume_keeps_cursor_and_no_audio_during_pause(self):
        self.player.play();self.mmio.consume(17001);self.player.poll();self.player.pause();self.player.poll()
        self.assertEqual(self.player.state,'paused');self.mmio.consume(99999)
        self.assertEqual(len(self.mmio.played),17001)
        self.player.play();self.finish();np.testing.assert_array_equal(self.mmio.played,self.values)
    def test_help_suspend_releases_hardware_and_explicit_resume_restarts_at_cursor(self):
        self.player.play();self.mmio.consume(10101);self.player.suspend()
        self.assertEqual(self.player.offset,10101);self.assertFalse(self.mmio.busy)
        self.player.poll();self.assertEqual(len(self.mmio.played),10101)
        self.player.play();self.finish();np.testing.assert_array_equal(self.mmio.played,self.values)
    def test_underflow_stops_closes_and_never_repeats_old_data(self):
        self.player.play();self.mmio.consume(40000)
        with self.assertRaisesRegex(AudioError,'underrun'):self.player.poll()
        self.assertFalse(self.mmio.busy);self.assertIsNone(self.player.reader)
        self.assertEqual(self.player.state,'fault');self.assertEqual(len(self.mmio.played),32768)
        self.player.poll();self.assertEqual(len(self.mmio.played),32768)
    def test_pause_ack_timeout_is_bounded(self):
        self.player.play();self.mmio.ignore_pause=True;self.player.pause();self.clock=1
        with self.assertRaisesRegex(AudioError,'pause timeout'):self.player.poll()
        self.assertFalse(self.mmio.busy);self.assertIsNone(self.player.reader)
    def test_clock_fault_does_not_trigger_resume_or_retry(self):
        self.player.play();self.mmio.fault=4
        with self.assertRaisesRegex(AudioError,'clock fault'):self.player.poll()
        self.assertFalse(self.player.live);self.assertIsNone(self.player.reader)
    def test_alive_bclk_without_sample_progress_has_bounded_timeout(self):
        self.player.play();self.clock=2
        with self.assertRaisesRegex(AudioError,'progress timeout'):self.player.poll()
        self.assertFalse(self.mmio.busy)
    def test_changed_music_is_not_played_using_old_validation(self):
        path=self.root/'song.wav';path.write_bytes(path.read_bytes()+b'changed')
        with self.assertRaisesRegex(AudioError,'changed'):self.player.play()
        self.assertFalse(self.mmio.busy)
    def test_next_wraps_and_return_discards_resume_position(self):
        self.player.play();self.mmio.consume(42);self.player.next()
        self.assertEqual(self.player.index,0);self.assertEqual(self.player.state,'playing')
        self.player.action('music_back');self.assertEqual(self.player.offset,0)
        self.assertFalse(self.mmio.busy);self.assertIsNone(self.player.reader)
    def test_empty_playlist_never_starts_audio(self):
        self.manifest['tracks']=[];self.save_manifest()
        p=MusicPlayer(self.device,MusicLibrary(self.root));self.assertFalse(p.play());p.next()
        self.assertFalse(self.mmio.busy);self.assertEqual(p.feedback(),'music_empty')
    def test_legacy_ip_is_rejected_before_stream_register_writes(self):
        m=SimpleNamespace(read=lambda r:0x41554431 if r==0 else 0x10000)
        with self.assertRaisesRegex(AudioError,'IP v2'):StreamAudioDevice(m)
    def test_committed_bank_cannot_be_overwritten_by_driver(self):
        self.device.prepare();self.device.submit(0,self.values[:11],False)
        before=self.mmio.array.copy()
        with self.assertRaisesRegex(AudioError,'owned'):self.device.submit(0,self.values[:3],True)
        np.testing.assert_array_equal(before,self.mmio.array)
    def test_legacy_phrase_device_selects_legacy_mode_on_v2(self):
        self.mmio.mode=1
        a=AudioDevice(self.mmio,lambda:0);a.play(self.values[:12])
        self.assertEqual(self.mmio.mode,0);a.stop()
    def test_manifest_path_escape_and_hash_mismatch_are_rejected(self):
        for field,value in [('file','../song.wav'),('sha256','0'*64)]:
            old=self.manifest['tracks'][0][field];self.manifest['tracks'][0][field]=value;self.save_manifest()
            with self.assertRaises(ValueError):MusicLibrary(self.root)
            self.manifest['tracks'][0][field]=old
    def test_peak_and_bad_wav_are_rejected_before_play(self):
        self.make_library(np.array([9000],dtype='<i2'))
        with self.assertRaisesRegex(ValueError,'peak'):MusicLibrary(self.root)
        self.make_library(self.values)
        path=self.root/'song.wav';path.write_bytes(path.read_bytes()[:-8])
        self.manifest['tracks'][0]['sha256']=hashlib.sha256(path.read_bytes()).hexdigest();self.save_manifest()
        with self.assertRaisesRegex(ValueError,'truncated'):MusicLibrary(self.root)


class MusicNavigationTests(unittest.TestCase):
    def setUp(self):
        self.c=DwellController(Context('s','g','live'),'model',music_enabled=True);self.seq=0;self.t=0
    def feed(self,point,n=15,status='valid'):
        events=[]
        for _ in range(n):
            self.seq+=1;self.t+=100
            a=self.c.feed(GazeSample(self.c.context,'model',self.seq,self.t,status,point),self.t)
            if a:events.append(a.key)
        return events
    def test_new_page_requires_release_and_new_full_dwell(self):
        self.assertEqual(self.feed((.75,.7)),['more']);self.assertEqual(self.c.page,'menu')
        self.assertEqual(self.feed((.75,.7),40),[])
        self.assertEqual(self.feed((.25,.38),18),['music_open']);self.assertEqual(self.c.page,'music_hub')
        self.assertEqual(self.feed((.25,.38),40),[])
        self.feed(None,5,'unknown');self.assertEqual(self.feed((.25,.38),20),[])
        self.feed((.5,.55),5)
        self.assertEqual(self.feed((.25,.38)),['music_player_open']);self.assertEqual(self.c.page,'music')
        self.assertEqual(self.feed((.25,.38),40),[])
        self.feed((.5,.55),5)
        self.assertEqual(self.feed((.25,.38)),['music_toggle'])
        self.assertEqual(self.feed((.25,.38),40),[])
    def test_pause_and_clear_still_block_music_actions(self):
        self.c.page='music';self.c.pause(0)
        self.assertEqual(self.feed((.25,.38)),[])
        self.c.invalidate_calibration();self.c.resume(self.t)
        self.assertEqual(self.feed((.25,.38)),[])


class ImportTests(unittest.TestCase):
    def test_import_scales_peak_binds_hash_and_refuses_overwrite(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('import_music',Path(__file__).resolve().parents[1]/'tools/import_music.py')
        tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);music=root/'assets/music';music.mkdir(parents=True)
            (music/'playlist.json').write_text('{"version":1,"tracks":[]}')
            source=root/'original.wav'
            with wave.open(str(source),'wb') as w:
                w.setparams((1,2,16000,2,'NONE',''));w.writeframes(np.array([-32768,32767],dtype='<i2').tobytes())
            result=tool.import_track(source,'sample','示例曲目',root)
            self.assertLess(result['gain'],1)
            library=MusicLibrary(music);self.assertEqual(library.tracks[0]['title'],'示例曲目')
            with self.assertRaises(ValueError):tool.import_track(source,'sample','重复',root)
