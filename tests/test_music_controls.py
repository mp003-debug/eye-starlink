import copy,json,tempfile,unittest,wave,hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from eye_tracker.music import MusicLibrary,MusicPlayer,StreamAudioDevice,BANK_SAMPLES
from eye_tracker.music_settings import MusicVolume
from eye_tracker.music_ui import display_values,MUSIC_BAR_BOX
from eye_tracker.audio import AudioError
from eye_tracker.calibration import Context
from eye_tracker.interaction import DwellController,GazeSample,MAIN_TARGETS,PAGE_TARGETS
from test_music import StreamMMIO


class MusicControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.clock=0.
        self.values=np.resize(np.array([-8191,-7,-1,0,1,7,8191],dtype='<i2'),BANK_SAMPLES*3+31)
        track=self.root/'song.wav'
        with wave.open(str(track),'wb') as w:
            w.setparams((1,2,16000,len(self.values),'NONE',''));w.writeframes(self.values.tobytes())
        (self.root/'playlist.json').write_text(json.dumps({'version':1,'tracks':[
            dict(id='one',title='曲名测试',file='song.wav',sha256=hashlib.sha256(track.read_bytes()).hexdigest())]}),encoding='utf-8')
        self.library=MusicLibrary(self.root,volume_path=self.root/'settings.json')
        self.mmio=StreamMMIO();self.player=MusicPlayer(StreamAudioDevice(self.mmio),self.library,lambda:self.clock)

    def finish(self):
        for _ in range(100):
            self.mmio.consume(4000);self.clock+=.2;self.player.poll()
            if self.player.state=='ended':return
        self.fail('stream did not end')

    def test_gain_is_bounded_symmetric_and_preserves_samples_across_banks(self):
        for level in (1,3,5):
            with self.subTest(level=level):
                self.player.stop();self.mmio.played=[]
                while self.player.volume.level>level:self.player.action('music_volume_down')
                while self.player.volume.level<level:self.player.action('music_volume_up')
                self.player.play();self.finish()
                expected=np.sign(self.values.astype(np.int32))*((np.abs(self.values.astype(np.int32))*level*20+50)//100)
                np.testing.assert_array_equal(self.mmio.played,expected)
                self.assertEqual(self.player.offset,len(self.values))
                self.assertLessEqual(max(map(abs,self.mmio.played)),8191)
        with wave.open(str(self.root/'song.wav'),'rb') as w:
            np.testing.assert_array_equal(np.frombuffer(w.readframes(len(self.values)),dtype='<i2'),self.values)

    def test_volume_is_remembered_and_clamped_without_wrapping(self):
        for _ in range(10):self.player.action('music_volume_down')
        self.assertEqual(self.player.volume.level,1)
        again=MusicPlayer(StreamAudioDevice(self.mmio),MusicLibrary(self.root,volume_path=self.root/'settings.json'))
        self.assertEqual(again.volume.percent,20)
        for _ in range(10):again.action('music_volume_up')
        self.assertEqual(again.volume.percent,100)
        self.assertFalse((self.root/'settings.json.pending').exists())

    def test_live_buffers_cannot_be_rewritten_by_volume_controls(self):
        self.player.play();before=self.mmio.array.copy()
        with self.assertRaisesRegex(AudioError,'stop music'):self.player.action('music_volume_down')
        self.assertEqual(self.player.volume.percent,100)
        np.testing.assert_array_equal(self.mmio.array,before)
        self.player.action('music_volume_open')
        self.assertFalse(self.mmio.busy);self.assertEqual(self.player.offset,0)
        self.player.action('music_volume_down');self.assertEqual(self.player.volume.percent,80)
        self.player.action('music_volume_back');self.assertFalse(self.mmio.busy)

    def test_paused_progress_tracks_consumption_and_end_then_return_resets(self):
        c=SimpleNamespace();self.player.play();self.mmio.consume(17001);self.player.poll()
        self.player.pause();self.player.poll();self.player.sync_display(c)
        self.assertEqual(c.music_position_samples,17001)
        self.clock+=10;self.player.poll();self.player.sync_display(c)
        self.assertEqual(c.music_position_samples,17001)
        self.assertTrue(display_values(c)[2].startswith('00:01'))
        self.player.play();self.finish();self.player.sync_display(c)
        self.assertEqual(display_values(c)[3],MUSIC_BAR_BOX[2]-MUSIC_BAR_BOX[0])
        self.player.action('music_back');self.player.sync_display(c)
        self.assertEqual(c.music_position_samples,0);self.assertEqual(display_values(c)[3],0)

    def test_save_failure_keeps_previous_volume_and_file(self):
        self.player.action('music_volume_down');before=(self.root/'settings.json').read_bytes()
        with patch.object(Path,'replace',side_effect=OSError('disk unavailable')):
            with self.assertRaisesRegex(AudioError,'could not be saved'):self.player.action('music_volume_down')
        self.assertEqual(self.player.volume.level,4)
        self.assertEqual((self.root/'settings.json').read_bytes(),before)
        self.assertFalse((self.root/'settings.json.pending').exists())

    def test_corrupt_or_unbounded_saved_volume_is_not_silently_accepted(self):
        p=self.root/'bad.json'
        for value in (-1,0,6,True,2.5,'3',None):
            p.write_text(json.dumps({'version':1,'level':value}),encoding='utf-8')
            with self.assertRaises(ValueError):MusicVolume(p)
        for text in ('{broken','[]','x'*1025):
            p.write_text(text,encoding='utf-8')
            with self.assertRaises(ValueError):MusicVolume(p)

    def test_display_empty_and_one_hour_bounds(self):
        self.assertEqual(display_values(SimpleNamespace(music_track_index=-1))[2],'--:-- / --:--')
        self.assertEqual(display_values(SimpleNamespace(music_position_samples=57600000,music_total_samples=57600000))[2],'60:00 / 60:00')
        for field,value in [('music_volume_level',0),('music_track_index',32),('music_position_samples',-1),('music_total_samples',True)]:
            with self.assertRaises(ValueError):display_values(SimpleNamespace(**{field:value}))

    def test_saved_volume_is_validated_before_library_is_usable(self):
        p=self.root/'bad.json';p.write_text('{"version":true,"level":3}',encoding='utf-8')
        with self.assertRaises(ValueError):MusicLibrary(self.root,volume_path=p)

    def test_multiline_titles_cannot_silently_overflow_display(self):
        p=self.root/'playlist.json';data=json.loads(p.read_text(encoding='utf-8'))
        data['tracks'][0]['title']='第一行\n第二行';p.write_text(json.dumps(data),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'entry'):MusicLibrary(self.root)


class MusicVolumeNavigationTests(unittest.TestCase):
    def setUp(self):
        self.c=DwellController(Context('s','g','live'),'m',music_enabled=True,quick_phrases=True)
        self.c.page='music_hub';self.t=0;self.seq=0
    def feed(self,point,n=15,status='valid'):
        result=[]
        for _ in range(n):
            self.seq+=1;self.t+=100
            a=self.c.feed(GazeSample(self.c.context,'m',self.seq,self.t,status,point),self.t)
            if a:result.append(a.key)
        return result
    def test_volume_entry_needs_release_and_each_step_needs_new_dwell(self):
        self.assertEqual(self.feed((.75,.38)),['music_volume_open'])
        self.assertEqual(self.c.page,'music_volume')
        self.assertEqual(self.feed((.75,.38),40),[])
        self.feed(None,5,'lost');self.assertEqual(self.feed((.75,.38),20),[])
        self.feed((.5,.55),5)
        self.assertEqual(self.feed((.75,.38)),['music_volume_up'])
        self.assertEqual(self.feed((.75,.38),50),[])
        self.assertEqual(self.feed((.25,.38)),['music_volume_down'])
        self.assertEqual(self.feed((.25,.7)),['help'])
        self.assertEqual(self.feed((.75,.7)),['music_volume_back'])
        self.assertEqual(self.c.page,'music_hub')
        self.assertEqual(self.feed((.75,.7),50),[])
        self.feed((.5,.55),5)
        self.assertEqual(self.feed((.75,.7)),['music_menu_back'])
        self.assertEqual(self.c.page,'full_menu')
    def test_music_pages_keep_same_large_regions_and_help_location(self):
        for page in ('music_hub','music','music_volume'):
            self.assertEqual([t.rect for t in PAGE_TARGETS[page]],[t.rect for t in MAIN_TARGETS])
            self.assertEqual(PAGE_TARGETS[page][2].key,'help')


class MusicDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from eye_tracker.ui import BoardRenderer
        cls.board=BoardRenderer()
    def test_playlist_titles_bind_order_text_audio_identity_and_duration(self):
        from eye_tracker.music import MusicLibrary
        lib=MusicLibrary(Path(__file__).resolve().parents[1]/'assets/music')
        self.board.bind_music(lib)
        original=lib.provenance()['tracks']
        for field,value in [('title','changed'),('frames',1),('sha256','0'*64),('id','different')]:
            changed=copy.deepcopy(original);changed[0][field]=value
            with self.assertRaisesRegex(ValueError,'rebuild UI'):
                self.board.bind_music(SimpleNamespace(provenance=lambda:{'tracks':changed}))
        with self.assertRaises(ValueError):
            self.board.bind_music(SimpleNamespace(provenance=lambda:{'tracks':original[::-1]}))
    def test_compiled_titles_progress_and_volumes_match_artwork(self):
        from eye_tracker.render import Renderer,feedback_message
        from eye_tracker.framebuffer import encode_frame
        reference=Renderer(Path('assets/fonts/noto_sans_cjk_sc.otf'))
        c=DwellController(Context('display','g','live'),'m',music_enabled=True)
        for page in ('music_hub','music','music_volume'):
            c.page=page
            for index in (-1,0,1,2):
                for level in (1,3,5):
                    c.music_track_index=index;c.music_volume_level=level
                    c.music_total_samples=0 if index<0 else reference.music_tracks[index]['frames']
                    for position in (0,c.music_total_samples//2,c.music_total_samples):
                        c.music_position_samples=position
                        expected=encode_frame(np.asarray(reference.frame(c,feedback_message('live','music_paused'))))
                        self.assertEqual(self.board.rgb565(c,'music_paused'),expected,(page,index,level,position))
