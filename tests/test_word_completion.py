"""Explicit word completion must reduce choices without inventing/auto-committing text."""
import unittest
from pathlib import Path
from eye_tracker.daily_tools import DailyTools
from eye_tracker.composer import Favorites
from eye_tracker.interaction import DwellController,GazeSample
from eye_tracker.calibration import Context
from test_typing_efficiency import enter_letter

ROOT=Path(__file__).resolve().parents[1]


def fixture():
    d=DailyTools.from_root(ROOT);d.composer.favorites=Favorites(d.composer.lexicon);return d


def word_route(d,pinyin,text):
    steps=0
    def choose(i):
        nonlocal steps
        d.select(i);steps+=1
    choose(0);choose(1)
    for ch in pinyin:enter_letter(d,ch,choose)
    while text not in [c.label for c in d.view().choices[:2] if c]:choose(2)
    choose(next(i for i,c in enumerate(d.view().choices[:2]) if c and c.label==text))
    return steps


class WordCompletionTests(unittest.TestCase):
    def test_first_syllable_can_explicitly_commit_whole_phrase(self):
        for py,text,limit in [('ni','你好',8),('wo','我想喝水',8),('xie','谢谢',13)]:
            d=fixture();count=word_route(d,py,text)
            self.assertLessEqual(count,limit);self.assertEqual(d.composer.text,text)
            self.assertEqual(d.composer.pinyin,'');self.assertEqual(d.state,'present')
            self.assertEqual(d.display_text,'');self.assertIsNone(d.video_command)
            self.assertNotIn(text,repr(d.last_event));self.assertEqual(d.composer.favorites.items,[])

    def test_continuation_is_visible_but_never_added_without_selection(self):
        d=fixture();d.composer.pinyin='wo';d.state='candidates';d.select(0)
        self.assertEqual(d.composer.text,'我');self.assertEqual(d.state,'suggestions')
        self.assertEqual(d.view().choices[0].label,'想喝水')
        for _ in range(20):d.view()
        self.assertEqual(d.composer.text,'我');d.select(0)
        self.assertEqual(d.composer.text,'我想喝水');self.assertEqual(d.state,'present')

    def test_plain_pinyin_is_one_explicit_action_away_from_suggestions(self):
        d=fixture();d.composer.text='你';d.state='suggestions';d.select(2)
        self.assertEqual(d.state,'keyboard');self.assertEqual(d.composer.text,'你')
        self.assertEqual(d.composer.pinyin,'')

    def test_all_characters_stay_reachable_and_no_duplicate_word_choices(self):
        d=fixture();d.composer.favorites.items=['你好','你好吗'];d.composer.pinyin='ni'
        items=d.candidate_choices();characters=[x.label for x in items if x.command=='candidate']
        words=[x.label for x in items if x.command=='phrase_candidate']
        self.assertEqual(characters,list(d.composer.candidates()));self.assertEqual(len(words),len(set(words)))
        self.assertLessEqual(len(words),3);self.assertEqual(items[0].command,'candidate')

    def test_limits_never_truncate_phrase_or_consume_pending_pinyin(self):
        d=fixture();c=d.composer;c.text='我'*63;c.pinyin='ni'
        self.assertEqual(c.phrase_candidates(),());self.assertEqual(c.continuations(),())
        with self.assertRaises(ValueError):c.phrase_candidate('你好')
        self.assertEqual((c.text,c.pinyin),('我'*63,'ni'))
        c.pinyin='';c.text='我'*64;self.assertEqual(c.continuations(),())

    def test_same_target_hold_cannot_commit_a_whole_phrase_after_new_page(self):
        d=fixture();d.composer.pinyin='wo';d.state='candidates'
        c=DwellController(Context('word-test','four','live'),'checked',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=d);c.page='local_tools'
        actions=[]
        for i in range(45):
            a=c.feed(GazeSample(c.context,'checked',i,i*100,'valid',(.2625,.38)),i*100)
            if a:actions.append(a)
        self.assertEqual(len(actions),1);self.assertEqual(d.composer.text,'我');self.assertEqual(d.state,'suggestions')
        for i in range(45,50):c.feed(GazeSample(c.context,'checked',i,i*100,'valid',(.5,.55)),i*100)
        for i in range(50,64):c.feed(GazeSample(c.context,'checked',i,i*100,'valid',(.2625,.38)),i*100)
        self.assertEqual(d.composer.text,'我想喝水')
