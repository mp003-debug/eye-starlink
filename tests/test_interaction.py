import unittest
from eye_tracker.calibration import Context
from eye_tracker.interaction import DwellController,GazeSample


class DwellTests(unittest.TestCase):
    def setUp(self):
        self.context=Context('session','geometry','simulated')
        self.control=DwellController(self.context,'calibration')
        self.seq=0

    def feed(self,t,screen=(.25,.37),status='valid',now=None):
        self.seq+=1
        return self.control.feed(GazeSample(self.context,'calibration',self.seq,t,status,screen),t if now is None else now)

    def dwell(self,start=0,screen=(.25,.37),duration=1000):
        return [e for t in range(start,start+duration+1,50) if (e:=self.feed(t,screen))]

    def test_exact_dwell_once_and_no_repeat(self):
        actions=self.dwell(duration=2000)
        self.assertEqual([a.key for a in actions],['water'])
        self.assertEqual(actions[0].source_time_ms,1000)
        self.assertEqual(actions[0].source,'simulated')

    def test_pause_status_survives_timer(self):
        self.feed(0)
        self.control.pause(50)
        self.control.tick(1000)
        self.assertEqual(self.control.reason,"paused")

    def test_tick_never_selects(self):
        self.feed(0)
        self.control.tick(1000)
        self.assertEqual(self.control.progress,0)
        self.assertEqual(self.control.locks,set())

    def test_lost_closed_unknown_clear_progress(self):
        for status in ('lost','closed','unknown'):
            with self.subTest(status=status):
                self.setUp();self.dwell(duration=600)
                self.feed(650,status=status)
                self.assertEqual(self.control.progress,0)
                self.assertEqual(self.dwell(start=700,duration=600),[])

    def test_invalid_input_cannot_unlock(self):
        self.dwell()
        self.feed(1100,status='lost')
        self.feed(1500,status='closed')
        self.assertEqual(self.dwell(start=1600,duration=1200),[])
        self.assertIn('water',self.control.locks)

    def test_valid_exit_rearms(self):
        self.dwell()
        for t in range(1050,1351,50):self.feed(t,(.5,.5))
        self.assertNotIn('water',self.control.locks)
        self.assertEqual(len(self.dwell(start=1400)),1)

    def test_short_exit_does_not_rearm(self):
        self.dwell()
        for t in range(1050,1301,50):self.feed(t,(.5,.5))
        self.assertEqual(self.dwell(start=1350,duration=1100),[])

    def test_pause_clears_progress_and_preserves_locks(self):
        self.dwell(duration=600)
        self.control.pause(650);self.feed(700)
        self.assertEqual(self.control.progress,0)
        self.control.resume(750)
        self.assertEqual(len(self.dwell(start=800)),1)
        self.control.pause(1850);self.control.resume(1900)
        self.assertEqual(self.dwell(start=1950),[])

    def test_cancel_requires_new_dwell(self):
        self.dwell(duration=600);self.control.cancel(650)
        self.assertEqual(self.dwell(start=700,duration=600),[])

    def test_changed_context_invalidates_calibration(self):
        self.feed(0)
        wrong=GazeSample(Context('session','moved','simulated'),'calibration',2,50,'valid',(.25,.37))
        self.control.feed(wrong,50)
        self.assertIsNone(self.control.calibration_id)
        self.assertEqual(self.dwell(start=100),[])

    def test_duplicate_reorder_future_stale_and_nonfinite_rejected(self):
        cases=[(GazeSample(self.context,'calibration',1,0,'valid',(.25,.37)),50),
               (GazeSample(self.context,'calibration',2,100,'valid',(.25,.37)),50),
               (GazeSample(self.context,'calibration',2,50,'valid',(.25,.37)),250),
               (GazeSample(self.context,'calibration',2,50,'valid',(float('nan'),.3)),50)]
        for sample,now in cases:
            with self.subTest(sample=sample):
                self.setUp();self.feed(0)
                self.assertIsNone(self.control.feed(sample,now))
                self.assertEqual(self.control.progress,0)

    def test_gap_resets_even_without_timer_ticks(self):
        self.dwell(duration=600)
        self.feed(800)
        self.assertEqual(self.control.progress,0)

    def test_clock_regression_stops_controller(self):
        self.feed(100);self.control.tick(50)
        self.assertTrue(self.control.closed)
        self.assertEqual(self.dwell(start=150),[])

    def test_more_and_back_require_separate_dwell(self):
        actions=self.dwell(screen=(.75,.7))
        self.assertEqual(actions[0].key,'more')
        self.assertEqual(self.control.page,'more')
        actions=self.dwell(start=1050,screen=(.5,.5))
        self.assertEqual(actions[0].key,'back')
        self.assertEqual(self.control.page,'main')
        self.assertEqual(self.control.progress,0)

    def test_new_more_visit_rearms_only_return_and_requires_full_fresh_dwell(self):
        self.control.locks.update(('water','back'))
        # Only the final fresh frame completes this pending page navigation.
        self.control.target_key='more';self.control.start_time=0
        self.control.last_source=950;self.control.last_seq=0
        self.assertEqual(self.feed(1000,(.75,.7)).key,'more')
        self.assertNotIn('back',self.control.locks)
        self.assertIn('water',self.control.locks)
        self.assertIn('more',self.control.locks)
        self.assertEqual(self.dwell(start=1050,screen=(.5,.55),duration=600),[])
        self.feed(1700,status='lost')
        actions=self.dwell(start=1750,screen=(.5,.55))
        self.assertEqual([e.key for e in actions],['back'])
        self.assertIn('water',self.control.locks)
        self.assertIn('more',self.control.locks)

    def test_uncalibrated_and_stopped_cannot_select(self):
        self.control.invalidate_calibration()
        self.assertEqual(self.dwell(),[])
        self.control.stop(1100)
        self.assertTrue(self.control.closed)


if __name__=='__main__':unittest.main()
