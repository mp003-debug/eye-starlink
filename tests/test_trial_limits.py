import json
import math
import unittest
from eye_tracker.trial_limits import EventHistory,validate_trial_duration

class TrialLimitsTests(unittest.TestCase):
 def test_demo_window_requires_long_run_and_stays_bounded(self):
  validate_trial_duration(2400,True,True)
  validate_trial_duration(3600,True,True)
  for seconds in (1201,2400,3600):
   with self.assertRaises(ValueError):validate_trial_duration(seconds,True)
  for seconds in (10,2400,3600):
   with self.assertRaises(ValueError):validate_trial_duration(seconds,False,True)
  for seconds in (9,3601,math.inf,math.nan):
   with self.assertRaises(ValueError):validate_trial_duration(seconds,True,True)
 def test_long_duration_requires_explicit_mode_and_remains_finite(self):
  for seconds in (10,60,90):validate_trial_duration(seconds)
  for seconds in (91,120,300,1200):
   with self.assertRaises(ValueError):validate_trial_duration(seconds)
   validate_trial_duration(seconds,True)
  for seconds in (-1,0,9,1201,math.inf,math.nan):
   for long_run in (False,True):
    with self.assertRaises(ValueError):validate_trial_duration(seconds,long_run)
 def test_event_window_retains_latest_and_full_totals(self):
  log=EventHistory(3)
  for i in range(20):log.append({'event':'started' if i%2==0 else 'completed','index':i})
  self.assertEqual([e['index'] for e in log],[17,18,19])
  self.assertEqual(log.summary(),dict(limit=3,total=20,retained=3,discarded=17,counts={'started':10,'completed':10}))
  self.assertEqual(len(json.loads(json.dumps(log))),3)
  log[-1]['after']='annotation';self.assertEqual(log[-1]['after'],'annotation')
