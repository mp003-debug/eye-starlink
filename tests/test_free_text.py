"""Behavioral checks for explicit initials composition, recovery and long display."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from eye_tracker.daily_tools import DailyTools
from eye_tracker.composer import Composer,Favorites,MAX_TEXT
from eye_tracker.word_input import WordLexicon
from eye_tracker.interaction import DwellController,GazeSample,MAIN_TARGETS
from eye_tracker.calibration import Context
from eye_tracker.ui import BoardRenderer
ROOT=Path(__file__).resolve().parents[1]

def initials_for(d,text):
    # Use a dictionary-provided alias, not invented spelling in the test driver.
    if text=='音乐':return 'yy'
    return next(key for key,ids in d.words.index.items() if any(d.words.words[i][0]==text for i in ids))

def add_initial(d,letter,choose):
    if d.state=='word_candidates':choose(3)
    assert d.state=='word_keyboard'
    while True:
        i=next(i for i,c in enumerate(d.view().choices[:3]) if c and letter in c.value)
        leaf=len(d.view().choices[i].value)==1;choose(i)
        if leaf:return

def compose_chunks(d,chunks):
    steps=0
    def choose(i):
        nonlocal steps
        d.select(i);steps+=1
    choose(0);choose(0)
    for word in chunks:
        for letter in initials_for(d,word):add_initial(d,letter,choose)
        assert d.state=='word_candidates'
        for _ in range(len(d.word_choices())//2+1):
            choices=d.view().choices
            match=next((i for i,c in enumerate(choices[:2]) if c and c.value==word),None)
            if match is not None:choose(match);break
            choose(2)
        else:raise AssertionError('unreachable word')
    return steps

class FreeTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.sample=DailyTools.from_root(ROOT)
    def setUp(self):self.d=DailyTools.from_root(ROOT);self.d.composer.favorites=Favorites(self.d.composer.lexicon)

    def test_new_sentence_composes_multiple_words_without_finish_detours(self):
        d=self.d;chunks=['今天','下午','我想','和','你','一起','听','音乐']
        steps=compose_chunks(d,chunks)
        self.assertEqual(d.composer.text,''.join(chunks));self.assertEqual(d.state,'word_keyboard')
        self.assertEqual(d.initials,'');self.assertEqual(d.display_text,'');self.assertLess(steps,112)
        self.assertNotIn(d.composer.text,repr(d.last_event));self.assertIsNone(d.video_command);self.assertIsNone(d.book_command)

    def test_every_compiled_entry_has_reachable_alias_and_every_character_is_retained(self):
        w=self.d.words;seen=set();chars=set()
        for key,ids in w.index.items():
            for i in ids:
                text=w.words[i][0];seen.add(text)
                if len(text)==1:chars.add(text)
            for pos,letter in enumerate(key):self.assertIn(letter,w.next_letters(key[:pos]))
        self.assertEqual(len(seen),len(w.words));self.assertEqual(chars,set(self.d.composer.lexicon.characters))
        self.assertIn('音乐',w.lookup('yy'));self.assertIn('音乐',w.lookup('yl'))
        self.assertEqual(len(w.lookup('jt')),len(set(w.lookup('jt'))))

    def test_page_navigation_wraps_and_never_commits_or_loses_initials(self):
        d=self.d;d.initials='jt';d.state='word_candidates';expected=list(d.word_choices());seen=[]
        for _ in range((len(expected)+1)//2):
            seen.extend(c.value for c in d.view().choices[:2] if c);d.select(2)
        self.assertEqual(seen,expected);self.assertEqual(d.word_offset,0)
        self.assertEqual(d.composer.text,'');d.select(3);self.assertEqual(d.initials,'jt')
        d.select(3);d.select(0);self.assertEqual(d.initials,'j');self.assertEqual(d.composer.text,'')

    def test_full_buffer_rejects_whole_word_without_consuming_it(self):
        d=self.d;d.composer.text='我'*63;d.initials='jt';d.state='word_candidates'
        self.assertGreaterEqual(len(d.view().choices[0].value),2)
        d.select(0);self.assertEqual(d.composer.text,'我'*63);self.assertEqual(d.initials,'jt')
        self.assertIn('未加入',d.notice);self.assertEqual(d.state,'word_candidates')

    def test_initials_candidate_return_preserves_page_and_separates_full_pinyin(self):
        d=self.d;d.initials='xw';d.state='word_candidates';d.word_offset=2
        offered=[c.value for c in d.view().choices[:2]]
        d.select(3);d.select(3);d.select(2)
        self.assertEqual(d.state,'word_candidates');self.assertEqual(d.initials,'xw')
        self.assertEqual(d.word_offset,2);self.assertEqual([c.value for c in d.view().choices[:2]],offered)
        self.assertEqual(d.composer.text,'');self.assertEqual(d.composer.pinyin,'')
        d.select(3);d.select(3);d.select(1);d.select(1)
        self.assertEqual(d.state,'keyboard');self.assertEqual(d.initials,'xw')
        self.assertTrue(d.composer.letter('w'));self.assertTrue(d.composer.letter('u'))
        self.assertIn('午',d.composer.lexicon.candidates(d.composer.pinyin))

    def test_common_readings_rank_before_rare_aliases_and_favorites_refresh_cache(self):
        d=self.d;d.initials='jt';self.assertEqual(d.word_choices()[0],'今天')
        d.initials='t';self.assertEqual(d.word_choices()[0],'听')
        d.initials='yy';self.assertEqual(d.word_choices()[0],'音乐')
        d.initials='xw';before=d.word_choices();self.assertNotEqual(before[0],'下午')
        d.composer.favorites.items=['今天下午'];self.assertEqual(d.word_choices()[0],'下午')
        self.assertEqual(set(before),set(d.word_choices()))

    def test_punctuation_return_and_confirmed_load_keep_navigation_consistent(self):
        d=self.d;d.composer.append_text('今天');d.state='input_methods';d.select(2)
        while True:
            i=next(i for i,c in enumerate(d.view().choices[:3]) if c and '，' in c.value)
            leaf=len(d.view().choices[i].value)==1;d.select(i)
            if leaf:break
        self.assertEqual(d.composer.text,'今天，');d.select(3);self.assertEqual(d.state,'input_methods')
        d.initials='xw';d.composer.pinyin='ni';d.composer.favorites.items=['你好'];d.favorite_index=0;d.state='load_confirm'
        d.select(0);self.assertEqual(d.composer.text,'你好');self.assertEqual((d.initials,d.composer.pinyin),('',''))
        self.assertTrue(d.composer.undo());self.assertEqual(d.composer.text,'今天，');self.assertEqual(d.composer.favorites.items,['你好'])

    def test_undo_removes_last_word_only_and_can_restore_deleted_text(self):
        c=self.d.composer;c.append_text('今天');c.append_text('下午');c.favorites.items=['你好']
        self.assertTrue(c.undo());self.assertEqual(c.text,'今天');self.assertTrue(c.undo());self.assertEqual(c.text,'')
        self.assertFalse(c.undo());c.append_text('你好');c.erase();self.assertEqual(c.text,'你')
        self.assertTrue(c.undo());self.assertEqual(c.text,'你好');self.assertEqual(c.favorites.items,['你好'])
        c.clear();self.assertTrue(c.undo());self.assertEqual(c.text,'你好')
        c.text='另一个草稿';self.assertFalse(c.can_undo());c.append('好');self.assertTrue(c.undo());self.assertEqual(c.text,'另一个草稿')

    def test_undo_history_is_bounded_and_pending_full_pinyin_is_preserved(self):
        c=self.d.composer
        for _ in range(40):c.append('我')
        self.assertEqual(len(c._edits),16);c.pinyin='ha';c.undo();self.assertEqual(c.pinyin,'ha')
        self.d.initials='jt';self.d.state='word_actions';self.d.select(1);self.d.select(1)
        self.assertEqual(self.d.state,'keyboard');self.assertEqual(self.d.initials,'jt');self.assertEqual(c.pinyin,'ha')

    def test_long_favorites_roundtrip_and_old_phrases_are_compatible(self):
        c=self.d.composer;text='今天下午我想和你一起听音乐。'*4
        self.assertLessEqual(len(text),MAX_TEXT)
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'favorites.json';f=Favorites(c.lexicon,path)
            f.save('你');f.save(text);loaded=Favorites(c.lexicon,path)
            self.assertEqual(loaded.items,['你',text]);self.assertFalse(c.lexicon.valid_text('我'*65))

    def test_long_display_fits_four_lines_and_reuses_cache_for_dwell(self):
        d=self.d;d.composer.text='国'*64;d.display_text=d.composer.text;d.state='display'
        c=DwellController(Context('offline','four','simulated'),'offline',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=d);c.page='local_tools'
        renderer=BoardRenderer();renderer.bind_daily_tools(d);raw=renderer.rgb565(c,'guide_ready')
        self.assertEqual(len(raw),640*480*2);body=renderer.daily_renderer.cache['body']
        self.assertEqual(body.shape,(147,576));self.assertGreater(np.count_nonzero(body[110:140]!=body[0,0]),100)
        with patch.object(renderer.daily_renderer.atlas,'draw',side_effect=AssertionError('uncached')):
            c.target_key='help';c.progress=.5;renderer.rgb565(c,'guide_ready')
        self.assertEqual([t.rect for t in c.targets],[MAIN_TARGETS[2].rect,MAIN_TARGETS[3].rect])

    def test_dictionary_rejects_malformed_or_mismatched_aliases(self):
        lex=self.d.composer.lexicon
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'words.json'
            for rows in ([['今天',1,['xx']]],[['今天',True,['jt']]],[['今天',1,[[]]]],[['今天',1,['jt']],['今天',1,['jt']]]):
                p.write_text(json.dumps(dict(version=1,character_dictionary_sha256=lex.sha256,entries=rows)),encoding='utf-8')
                with self.assertRaises(ValueError):WordLexicon(p,lex)

    def test_same_target_hold_and_invalid_input_cannot_append_a_second_word(self):
        d=self.d;d.initials='jt';d.state='word_candidates'
        c=DwellController(Context('live','four','live'),'checked',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=d);c.page='local_tools'
        chosen=d.view().choices[0].value
        for i in range(50):c.feed(GazeSample(c.context,'checked',i,i*100,'valid',(.2625,.38)),i*100)
        self.assertEqual(d.composer.text,chosen);self.assertEqual(d.initials,'')
        for i in range(50,55):c.feed(GazeSample(c.context,'checked',i,i*100,'closed',None),i*100)
        for i in range(55,90):c.feed(GazeSample(c.context,'checked',i,i*100,'valid',(.2625,.38)),i*100)
        self.assertEqual(d.initials,'');self.assertEqual(d.composer.text,chosen)
