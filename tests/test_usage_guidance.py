import unittest
from eye_tracker.calibration import Context
from eye_tracker.interaction import DwellController, GazeSample
from eye_tracker.usage_guidance import UsageGuidance


class GuidanceTests(unittest.TestCase):
    def setUp(self):
        self.c = DwellController(Context('test', 'geometry', 'live'), 'current')
        self.g = UsageGuidance()

    def test_prolonged_loss_is_only_a_hint_and_new_dwell_is_still_required(self):
        for seq in range(8):
            self.assertIsNone(self.c.feed(GazeSample(self.c.context, 'current', seq,
                seq*100, 'valid', (.25,.37)), seq*100))
        self.assertGreater(self.c.progress, .5)
        self.c.feed(GazeSample(self.c.context, 'current', 8, 800, 'unknown'), 800)
        self.assertEqual(self.c.progress, 0)
        before = repr(vars(self.c))
        row = {'rejection':'motion_envelope'}
        self.assertEqual(self.g.feedback(self.c,row,.8), 'guide_unavailable')
        self.assertEqual(self.g.feedback(self.c,row,2.81), 'guide_reposition')
        self.assertEqual(repr(vars(self.c)), before)
        for seq in range(9,17):
            self.assertIsNone(self.c.feed(GazeSample(self.c.context,'current',seq,
                3000+(seq-9)*100,'valid',(.25,.37)),3000+(seq-9)*100))
        self.assertEqual(self.g.feedback(self.c,{},3.71),'guide_ready')
        self.c.feed(GazeSample(self.c.context,'current',17,3800,'unknown'),3800)
        self.assertEqual(self.g.feedback(self.c,row,3.8),'guide_unavailable')

    def test_rejection_never_claims_closed_eyes_or_recalibrates(self):
        self.c.reason='unknown'
        for row,expected in (({'classification':{'reason':'ambiguous_appearance'}},'guide_appearance'),
                             ({'candidate':None},'guide_unavailable_long')):
            g=UsageGuidance()
            self.assertEqual(g.feedback(self.c,row,1),'guide_unavailable')
            self.assertEqual(g.feedback(self.c,row,4),expected)
            self.assertEqual(self.c.calibration_id,'current')

    def test_helper_states_override_old_observation_and_do_not_authorize_input(self):
        self.c.reason='tracking';row={'candidate':'water','stable_candidate':'water'}
        self.c.pause(0)
        self.assertEqual(self.g.feedback(self.c,row,1),'guide_paused')
        self.c.invalidate_calibration()
        self.assertEqual(self.g.feedback(self.c,row,2),'guide_uncalibrated')
        self.c.resume(2000)
        self.assertEqual(self.g.feedback(self.c,row,3),'guide_uncalibrated')
        self.assertIsNone(self.c.feed(GazeSample(self.c.context,'current',1,3000,
                                                'valid',(.25,.37)),3000))
        self.c.stop(3100)
        self.assertEqual(self.g.feedback(self.c,row,3.1),'guide_stopped')

    def test_stale_frame_and_time_fault_cannot_show_ready(self):
        self.c.reason='tracking'
        self.c.last_source=1000
        self.c.tick(1200)
        self.assertEqual(self.g.feedback(self.c,{'candidate':'water'},1.2),'guide_input')
        self.assertEqual(self.g.feedback(self.c,{},1),'guide_input')
        self.assertEqual(self.g.feedback(self.c,{},float('nan')),'guide_input')

    def test_held_selection_stays_locked_and_more_has_return_instruction(self):
        self.c.reason='locked';self.c.locks={'water'}
        self.assertEqual(self.g.feedback(self.c,{},1),'guide_release')
        self.assertEqual(self.c.locks,{'water'})
        self.c.page='more';self.c.reason='selected'
        self.assertEqual(self.g.feedback(self.c,{},2),'guide_back')

