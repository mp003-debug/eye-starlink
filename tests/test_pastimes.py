"""Behavior and persistence checks for untimed games and isolated chapter audio."""
import hashlib,json,random,tempfile,unittest,wave
from pathlib import Path
from unittest.mock import patch
import numpy as np
from eye_tracker.pastimes import LeisureGame,SHAPES
from eye_tracker.audiobook import AudioBookPlayer,Bookmarks,MusicLibrary
from eye_tracker.music import StreamAudioDevice
from eye_tracker.audio import AudioError
from eye_tracker.daily_tools import DailyTools
from eye_tracker.interaction import DwellController,GazeSample
from eye_tracker.calibration import Context
from test_music import StreamMMIO
from test_daily_tools import fixture

class PastimeLaunchTests(unittest.TestCase):
    @unittest.skipUnless((Path(__file__).resolve().parents[1]/'data/private/profiles/current_eye.json').is_file(), 'requires optional local private profile or AI runtime bundle')
    def test_explicit_flag_and_wireless_isolation(self):
        from eye_tracker.launch import prepare_launch
        root=Path(__file__).resolve().parents[1];profile='data/private/profiles/current_eye.json'
        plain=prepare_launch(profile,root,music=True,quick_phrases=True,emotion_cards=True,daily_tools=True)
        self.assertNotIn('--pastimes',plain['board_arguments'])
        enabled=prepare_launch(profile,root,music=True,quick_phrases=True,emotion_cards=True,daily_tools=True,pastimes=True)
        self.assertIn('--pastimes',enabled['board_arguments']);self.assertFalse(enabled['hardware_loaded'])
        with self.assertRaises(ValueError):prepare_launch(profile,root,pastimes=True)
        for mode in ('log','live'):
            plan=prepare_launch(profile,root,music=True,quick_phrases=True,emotion_cards=True,daily_tools=True,pastimes=True,eye_events=mode)
            self.assertTrue(plan['uart_enabled']);self.assertIn('--pastimes',plan['board_arguments'])

class GameTests(unittest.TestCase):
    def test_five_untimed_rounds_require_explicit_correct_answer_and_next(self):
        for kind in ('match','quiz'):
            g=LeisureGame(random.Random(41));g.start(kind)
            self.assertEqual(len(g.rounds),5)
            for i in range(5):
                self.assertEqual(g.index,i);right=g.current.correct
                self.assertFalse(g.answer(1-right));self.assertFalse(g.solved)
                with self.assertRaises(ValueError):g.advance()
                self.assertTrue(g.answer(right));self.assertEqual(g.index,i)
                self.assertFalse(g.answer(right))
                if i<4:g.advance()
            self.assertTrue(g.finished)
            with self.assertRaises(ValueError):g.advance()

    def test_matching_has_one_correct_shape_and_restart_resets(self):
        g=LeisureGame(random.Random(2));g.start('match')
        self.assertEqual(len({r.shape for r in g.rounds}),5)
        for r in g.rounds:
            self.assertEqual(r.answers.count(r.shape),1);self.assertEqual(r.answers[r.correct],r.shape)
        g.answer(g.current.correct);g.advance();g.start('quiz');self.assertEqual(g.index,0);self.assertFalse(g.solved)

    def test_new_routes_and_game_answer_cannot_chain_on_held_gaze(self):
        d=fixture();d.pastimes=True
        c=DwellController(Context('game-test','four','live'),'current',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=d)
        seq=0;now=0
        def dwell(point,n=20):
            nonlocal seq,now
            result=[]
            for _ in range(n):
                seq+=1;now+=100;a=c.feed(GazeSample(c.context,'current',seq,now,'valid',point),now)
                if a:result.append(a.key)
            return result
        dwell((.75,.7));dwell((.25,.7));self.assertEqual(c.page,'pastimes_leisure')
        dwell((.75,.38));self.assertEqual(d.state,'pastimes');self.assertEqual(c.page,'local_tools')
        dwell((.25,.38));self.assertEqual(d.state,'games')
        self.assertEqual(dwell((.25,.38),40),[])
        dwell((.5,.55),5);dwell((.25,.38));self.assertEqual(d.state,'game')
        dwell((.5,.55),5);slot=d.game.current.correct
        dwell((.25 if slot==0 else .75,.38));self.assertTrue(d.game.solved)
        self.assertEqual(dwell((.25 if slot==0 else .75,.38),40),[]);self.assertEqual(d.game.index,0)
        self.assertEqual(d.view().choices[2].command,'help');self.assertEqual(d.view().choices[3].command,'games')

class BookTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name);self.now=0.
        rows=[]
        for i in range(2):
            p=self.root/('chapter%d.wav'%i);values=((np.arange(48000)%10000)-5000).astype('<i2')
            with wave.open(str(p),'wb') as w:w.setparams((1,2,16000,len(values),'NONE',''));w.writeframes(values.tobytes())
            rows.append(dict(id=str(i),title='故事'+str(i),file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
        (self.root/'playlist.json').write_text(json.dumps(dict(version=1,tracks=rows)),encoding='utf-8')
        self.library=MusicLibrary(self.root);self.path=self.root/'private/progress.json'
        self.mmio=StreamMMIO();self.player=AudioBookPlayer(StreamAudioDevice(self.mmio),self.library,Bookmarks(self.library,self.path),lambda:self.now)

    def test_pause_restart_instance_and_explicit_resume_keep_exact_cursor(self):
        p=self.player;p.action('book_toggle');self.mmio.consume(12001);p.poll();p.action('book_toggle')
        self.assertFalse(self.mmio.busy);self.assertEqual(p.position,12001)
        marks=Bookmarks(self.library,self.path);self.assertEqual(marks.position(0),12001)
        fresh=AudioBookPlayer(StreamAudioDevice(self.mmio),self.library,marks,lambda:self.now)
        self.assertFalse(self.mmio.busy);fresh.action('book_toggle');self.mmio.consume(1000);fresh.poll()
        self.assertEqual(fresh.position,13001);fresh.close();self.assertFalse(self.mmio.busy)

    def test_chapter_switch_preserves_each_cursor_without_autoplay(self):
        p=self.player;p.action('book_toggle');self.mmio.consume(1001);p.action('book_next')
        self.assertEqual((p.index,p.position),(1,0));self.assertFalse(self.mmio.busy)
        p.action('book_toggle');self.mmio.consume(2001);p.action('book_previous')
        self.assertEqual((p.index,p.position),(0,1001));self.assertFalse(self.mmio.busy)
        p.action('book_next');self.assertEqual(p.position,2001);p.action('book_restart');self.assertEqual(p.position,0)
        p.close()

    def test_help_suspend_releases_stream_and_does_not_autoresume(self):
        p=self.player;p.action('book_toggle');self.mmio.consume(4000);p.suspend()
        for _ in range(5):p.poll()
        self.assertEqual(p.state,'paused');self.assertFalse(self.mmio.busy);self.assertEqual(p.position,4000)
        self.assertEqual(Bookmarks(self.library,self.path).position(0),4000)

    def test_natural_end_does_not_play_next_chapter(self):
        p=self.player;p.action('book_toggle')
        for _ in range(48):self.mmio.consume(1000);self.now+=.0625;p.poll()
        self.assertEqual((p.state,p.ends,p.index,p.position),('ended',1,0,48000));self.assertFalse(self.mmio.busy)
        for _ in range(3):p.poll()
        self.assertEqual(p.ends,1);self.assertEqual(Bookmarks(self.library,self.path).position(0),48000)

    def test_corrupt_or_changed_bookmarks_never_resume_invalid_offset(self):
        self.path.parent.mkdir();self.path.write_text('broken')
        marks=Bookmarks(self.library,self.path);self.assertTrue(marks.warning);self.assertEqual(marks.position(0),0)
        marks.save(0,123);raw=json.loads(self.path.read_text());raw['chapters']['0']['sha256']='different';self.path.write_text(json.dumps(raw))
        self.assertEqual(Bookmarks(self.library,self.path).position(0),0)
        raw['chapters']['0']['samples']=-1;self.path.write_text(json.dumps(raw));self.assertTrue(Bookmarks(self.library,self.path).warning)

    def test_save_error_does_not_prevent_audio_stop_and_recovery(self):
        p=self.player;p.action('book_toggle');self.mmio.consume(1234)
        with patch.object(p.bookmarks,'save',side_effect=OSError('full')):p.suspend()
        self.assertTrue(p.save_failed);self.assertFalse(self.mmio.busy);self.assertEqual(p.position,1234)
        p.persist();self.assertFalse(p.save_failed);self.assertEqual(Bookmarks(self.library,self.path).position(0),1234)

    def test_audio_fault_preserves_last_known_cursor_and_releases(self):
        p=self.player;p.action('book_toggle');self.mmio.consume(2200);p.poll();self.mmio.fault=4
        with self.assertRaises(AudioError):p.poll()
        self.assertFalse(self.mmio.busy);self.assertEqual(p.position,2200)
        self.assertEqual(Bookmarks(self.library,self.path).position(0),2200)

    def test_empty_book_library_never_starts(self):
        (self.root/'playlist.json').write_text('{"version":1,"tracks":[]}')
        library=MusicLibrary(self.root);p=AudioBookPlayer(StreamAudioDevice(self.mmio),library,Bookmarks(library))
        p.action('book_toggle');p.action('book_next');p.close();self.assertFalse(self.mmio.busy)
