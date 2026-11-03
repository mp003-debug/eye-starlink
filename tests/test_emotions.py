"""Local expression behavior; deterministic input is not gaze validation."""
import unittest
from pathlib import Path
import numpy as np
from eye_tracker.calibration import Context
from eye_tracker.interaction import DwellController,GazeSample,PAGE_TARGETS,MAIN_TARGETS
from eye_tracker.emotions import CARDS,MOOD_KEYS,AFFECTION_KEYS,PANEL_BOX,validate_options


class EmotionNavigationTests(unittest.TestCase):
    def setUp(self):
        self.c=DwellController(Context('fixture','four-region','live'),'checked',
            music_enabled=True,quick_phrases=True,emotion_cards=True)
        self.seq=0;self.time=0
    def feed(self,point,n=15,status='valid'):
        actions=[]
        for _ in range(n):
            self.seq+=1;self.time+=100
            action=self.c.feed(GazeSample(self.c.context,'checked',self.seq,self.time,status,point),self.time)
            if action:actions.append(action)
        return actions
    def choose(self,key):
        self.feed((.5,.55),5)
        target=next(t for t in self.c.targets if t.key==key)
        l,t,r,b=target.rect
        actions=self.feed(((l+r)/2,(t+b)/2))
        self.assertEqual([a.key for a in actions],[key])
        return actions[0]
    def test_six_cards_and_repeated_return_stay_visual_and_restore_source_page(self):
        self.choose('more');self.choose('emotion_open')
        for opener,keys in (('emotion_mood_open',MOOD_KEYS),('emotion_affection_open',AFFECTION_KEYS)):
            self.choose(opener)
            for key in keys:
                source=self.c.page
                self.assertEqual(self.choose(key).phrase,'')
                self.assertEqual(self.c.page,'emotion_display');self.assertEqual(self.c.emotion_key,key)
                self.assertEqual(self.feed((.25,.38),40),[])
                self.assertEqual(self.feed((.75,.38),40),[])
                self.assertEqual(self.c.emotion_key,key)
                self.choose('emotion_close')
                self.assertEqual(self.c.page,source);self.assertIsNone(self.c.emotion_key)
            self.choose('emotion_mood_back' if keys==MOOD_KEYS else 'emotion_affection_back')
        self.choose('emotion_menu_back');self.choose('menu_back');self.assertEqual(self.c.page,'main')
    def test_bottom_left_expression_cannot_immediately_trigger_help_on_display(self):
        self.c.page='emotion_mood'
        self.assertEqual([a.key for a in self.feed((.25,.7))],['emotion_worried'])
        self.assertEqual(self.feed((.25,.7),40),[])
        self.feed(None,5,'lost');self.assertEqual(self.feed((.25,.7),20),[])
        self.feed((.5,.55),4)
        self.assertEqual(self.feed((.25,.7),9),[])
        self.assertEqual([a.key for a in self.feed((.25,.7),3)],['help'])
        self.assertEqual(self.c.emotion_key,'emotion_worried')
        self.assertEqual(self.c.page,'emotion_display')
    def test_lost_pause_cancel_and_invalid_calibration_prevent_expression_selection(self):
        self.c.page='emotion_mood'
        self.feed((.25,.38),8);self.feed(None,2,'closed')
        self.assertEqual(self.feed((.25,.38),8),[])
        self.c.cancel(self.time);self.assertEqual(self.feed((.25,.38),8),[])
        self.c.pause(self.time);self.assertEqual(self.feed((.25,.38),20),[])
        self.c.resume(self.time);self.assertEqual(self.feed((.25,.38),8),[])
        self.c.invalidate_calibration();self.assertEqual(self.feed((.25,.38),20),[])
        self.assertIsNone(self.c.emotion_key)
    def test_communication_and_music_return_to_new_menu_without_changing_original_phrases(self):
        self.choose('more');self.choose('communication_open')
        self.choose('response_open');self.assertEqual(self.choose('yes').phrase,'是')
        self.choose('quick_back');self.assertEqual(self.c.page,'communication_menu')
        self.choose('caring_open');self.assertEqual(self.choose('unwell').phrase,'我不舒服')
        self.choose('care_back');self.choose('communication_back')
        self.choose('music_open');self.choose('music_menu_back')
        self.assertEqual(self.c.page,'extended_menu')
    def test_new_pages_keep_original_regions_and_large_display_is_not_a_target(self):
        for page in ('extended_menu','communication_menu','emotion_hub','emotion_mood','emotion_affection'):
            self.assertEqual([t.rect for t in PAGE_TARGETS[page]],[t.rect for t in MAIN_TARGETS])
        self.assertEqual([t.key for t in PAGE_TARGETS['emotion_display']],['help','emotion_close'])
        for targets in PAGE_TARGETS.values():
            for target in targets:
                same=[t for page in PAGE_TARGETS.values() for t in page if t.key==target.key]
                self.assertTrue(all(t==target for t in same))
    def test_explicit_local_option_does_not_change_old_menu_and_rejects_partial_enable(self):
        c=DwellController(self.c.context,'checked',music_enabled=True,quick_phrases=True)
        self.assertEqual(c.menu_page,'full_menu')
        validate_options(True,True,True,True)
        for music,quick,wireless in ((False,True,False),(True,False,False),(False,True,True)):
            with self.assertRaises(ValueError):validate_options(True,music,quick,wireless)


class EmotionDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from eye_tracker.ui import BoardRenderer
        from eye_tracker.render import Renderer
        cls.board=BoardRenderer();cls.reference=Renderer(Path('assets/fonts/noto_sans_cjk_sc.otf'))
    def test_six_compiled_panels_and_feedback_match_actual_rgb565_artwork(self):
        from eye_tracker.framebuffer import encode_frame
        from eye_tracker.render import feedback_message
        c=DwellController(Context('fixture','four-region','live'),'checked')
        c.page='emotion_display'
        for key in CARDS:
            c.emotion_key=key
            for target,progress in ((None,0),('help',.6),('emotion_close',.95)):
                c.target_key=target;c.progress=progress
                before=repr(vars(c))
                expected=encode_frame(np.asarray(self.reference.frame(c,feedback_message('live','emotion_display_hint'))))
                self.assertEqual(self.board.rgb565(c,'emotion_display_hint'),expected,(key,target))
                self.assertEqual(repr(vars(c)),before)
    def test_missing_or_unknown_expression_is_not_silently_displayed(self):
        c=DwellController(Context('fixture','four-region','live'),'checked');c.page='emotion_display'
        for key in (None,'unknown'):
            c.emotion_key=key
            with self.assertRaisesRegex(ValueError,'explicitly selected'):self.board.rgb565(c)
    def test_panels_are_distinct_bounded_and_all_six_labels_are_present(self):
        tiles=[self.board.tiles['panel_'+k] for k in CARDS]
        self.assertEqual(len({t.tobytes() for t in tiles}),6)
        self.assertTrue(all(t.shape==(145,576) for t in tiles))
        self.assertEqual([v[0] for v in CARDS.values()],['开心','难过','担心','喜欢','谢谢','想你'])
