"""Reachability, atomic text edits and synthetic eye-navigation protection."""
import unittest
from pathlib import Path
from eye_tracker.daily_tools import DailyTools
from eye_tracker.composer import COMMON_EXPRESSIONS

ROOT=Path(__file__).resolve().parents[1]


def enter_letter(d,letter,choose):
    if d.state=='suggestions':choose(2)
    if d.state=='candidates':choose(3)
    assert d.state=='keyboard'
    while True:
        i=next(i for i,c in enumerate(d.view().choices[:3]) if c and letter in c.value)
        leaf=len(d.view().choices[i].value)==1
        choose(i)
        if leaf:return


def type_text(d,text,syllables):
    count=0
    def choose(i):
        nonlocal count
        d.select(i);count+=1
    choose(0);choose(1)
    for ch,py in zip(text,syllables):
        for letter in py:enter_letter(d,letter,choose)
        if d.state!='candidates':choose(3);choose(0)
        while ch not in [c.label for c in d.view().choices[:2] if c]:choose(2)
        choose(next(i for i,c in enumerate(d.view().choices[:2]) if c and c.label==ch))
    return count


class TypingEfficiencyTests(unittest.TestCase):
    def setUp(self):self.d=DailyTools.from_root(ROOT)

    def test_every_syllable_remains_reachable_including_early_candidates(self):
        d=self.d
        for py in d.composer.lexicon.entries:
            with self.subTest(pinyin=py):
                d.composer.clear();d.open('compose');d.select(0);d.select(1)
                for letter in py:enter_letter(d,letter,d.select)
                if d.state!='candidates':d.select(3);d.select(0)
                self.assertEqual(d.composer.pinyin,py)
                self.assertEqual(d.state,'candidates')
                expected=d.composer.candidates()[0];d.select(0)
                self.assertEqual(d.composer.text,expected)
                self.assertEqual(d.composer.pinyin,'')
                self.assertIn(d.state,('keyboard','suggestions'))

    def test_prefix_filter_excludes_impossible_letters(self):
        lex=self.d.composer.lexicon
        for prefix,letters in lex.continuations.items():
            self.assertEqual(set(letters),{s[len(prefix)] for s in lex.entries if s.startswith(prefix) and len(s)>len(prefix)})
        self.assertEqual(lex.next_letters('zz'),'')

    def test_free_pinyin_examples_need_fewer_selections(self):
        for text,pys,old in [('你好',['ni','hao'],23),('谢谢',['xie','xie'],28),
                            ('我想喝水',['wo','xiang','he','shui'],57),
                            ('请帮我换个姿势',['qing','bang','wo','huan','ge','zi','shi'],104)]:
            d=DailyTools.from_root(ROOT)
            count=type_text(d,text,pys)
            self.assertEqual(d.composer.text,text)
            self.assertLess(count,old)

    def test_phrase_appends_atomically_without_auto_display_or_discarding_pinyin(self):
        d=self.d;d.composer.text='你好，';d.composer.pinyin='n'
        d.select(1);d.select(0);d.select(0)
        self.assertEqual(d.composer.text,'你好，我想喝水')
        self.assertEqual(d.composer.pinyin,'n')
        self.assertEqual(d.state,'present');self.assertEqual(d.display_text,'')
        self.assertNotIn('我想喝水',repr(d.last_event));self.assertIsNone(d.video_command)
        d.composer.text='我'*62;d.state='phrases';d.select(0)
        self.assertEqual(d.composer.text,'我'*62);self.assertEqual(d.state,'phrases')
        self.assertIn('整句未加入',d.notice)

    def test_all_common_phrases_supported_and_paging_does_not_skip(self):
        d=self.d
        for group,(_,items) in enumerate(COMMON_EXPRESSIONS):
            self.assertTrue(all(d.composer.lexicon.valid_text(s) for s in items))
            d.phrase_group=group;d.phrase_offset=0;d.state='phrases';seen=[]
            for _ in range((len(items)+1)//2):
                seen.extend(c.value for c in d.view().choices[:2] if c);d.select(2)
            self.assertEqual(seen,list(items));self.assertEqual(d.phrase_offset,0)

    def test_candidate_ranking_uses_context_without_changing_dictionary_or_saving(self):
        c=self.d.composer;before=c.lexicon.candidates('hao');c.text='你';c.pinyin='hao'
        self.assertEqual(c.candidates()[0],'好');self.assertEqual(c.lexicon.candidates('hao'),before)
        self.assertEqual(set(c.candidates()),set(before));self.assertEqual(c.favorites.items,[])
        c.favorites.items=['你号'];self.assertEqual(c.candidates()[0],'号')
        c.candidate(0);self.assertEqual(c.text,'你号')

    def test_keyboard_delete_and_navigation_preserve_saved_phrases(self):
        d=self.d;d.composer.favorites.items=['你'];d.composer.text='你好';d.composer.pinyin='hao'
        d.open('compose');d.select(0);d.select(1);d.select(3);d.select(1)
        self.assertEqual(d.composer.pinyin,'ha');self.assertEqual(d.composer.text,'你好')
        self.assertEqual(d.composer.favorites.items,['你'])
        d.select(3);d.select(2);d.select(3)
        self.assertEqual(d.state,'keyboard_actions');d.select(3)
        self.assertEqual(d.state,'compose')
        d.select(1);d.select(2);d.select(3)
        self.assertEqual(d.state,'expressions')
