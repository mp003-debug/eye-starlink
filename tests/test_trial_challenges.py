import unittest
import numpy as np
from eye_tracker.trial_challenges import TrialChallenges,PLAN,DURATION

class ChallengeTests(unittest.TestCase):
 def test_banner_leaves_all_buttons_and_progress_pixels_unchanged(self):
  c=TrialChallenges();words=np.arange(480*640,dtype=np.uint16).reshape(480,640)
  actual=np.frombuffer(c.decorate(words.tobytes(),1),dtype='<u2').reshape(480,640)
  np.testing.assert_array_equal(actual[72:],words[72:])
  self.assertFalse(np.array_equal(actual[:72],words[:72]))
 def test_plan_boundaries_and_confirmed_presentation(self):
  c=TrialChallenges();self.assertEqual(DURATION,80.)
  for value,step in ((0,0),(5.999,0),(6,1),(13.999,1),(14,2),(20,3),(80,11)):
   self.assertEqual(c.due(value),step)
  c.presented(0,1.);c.presented(0,2.);self.assertEqual(c.shown,1.)
  with self.assertRaises(ValueError):c.presented(2,3.)
  with self.assertRaises(ValueError):c.annotate({'copied_monotonic':2.},.9)
  for value in (-1,float('nan')):
   with self.assertRaises(ValueError):c.due(value)
 def test_phase_annotation_cannot_change_real_result(self):
  c=TrialChallenges();c.presented(0,0.);c.presented(1,6.)
  row=dict(copied_monotonic=6.2,candidate='water',stable_candidate='water',progress=.6,visual_selection='water')
  original=row.copy();c.annotate(row,6.1)
  self.assertEqual({k:row[k] for k in original},original)
  self.assertEqual(row['prompt_phase'],'challenge_close');self.assertFalse(row['action_label_verified'])
