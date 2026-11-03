import json,tempfile,unittest
from pathlib import Path
import numpy as np
from eye_tracker.fixation import FixationRecording,run_fixation,TARGETS,APPEARANCE_TARGETS,checked_plan

class FixationTests(unittest.TestCase):
    def test_transition_frames_excluded_and_owned_samples_keep_instructed_labels(self):
        r=FixationRecording(); a=np.full((480,640),40,dtype=np.uint8)
        r.observe(a,1,11.9,12.1,10.,0)
        self.assertEqual(len(r.samples),0)
        r.observe(a,2,12.1,12.2,10.,0);a[:]=99
        r.observe(a,3,12.3,12.4,10.,0)
        r.observe(a,4,16.,16.1,10.,0)
        self.assertEqual(len(r.samples),1)
        self.assertEqual(r.samples[0][1][0,0],40)
        with tempfile.TemporaryDirectory() as tmp:
            result=r.save(tmp,True)
            self.assertFalse(result['calibration_fitted'])
            data=json.loads((Path(tmp)/'targets/manifest.json').read_text())
            self.assertEqual(data['samples_detail'][0]['target'],'center')
            self.assertFalse(data['target_labels_are_measured_gaze'])
            with self.assertRaises(FileExistsError):r.save(tmp,True)

    def test_runner_labels_only_after_confirmed_presentation_and_limits_memory(self):
        class Session:
            def __init__(self):
                self.t=0.;self.capture_index=0;self.last_capture=None
                self.presents=[];self.image=np.zeros((480,640),dtype=np.uint8)
            def display_health(self):pass
            def wait_native_frames(self,n):return {'bad_lines':1,'bad_frames':1}
            def present(self,frame):
                self.t+=.03;self.presents.append(frame)
            def capture_once(self):
                start=self.t;self.t+=.21;self.capture_index+=1
                self.last_capture={'requested_at_monotonic':start,'copied_at_monotonic':self.t}
                self.image[:]=self.capture_index%256;return self.image
        class Renderer:
            def frame(self,step):return step
        s=Session();r=FixationRecording()
        def sleep(dt):s.t+=dt
        result=run_fixation(s,Renderer(),r,clock=lambda:s.t,sleep=sleep)
        self.assertEqual(s.presents,list(range(len(TARGETS))))
        self.assertEqual(len(r.samples),45)
        self.assertEqual({m['step'] for m,_ in r.samples},set(range(9)))
        self.assertTrue(all(m['requested_after_present_s']>=2 for m,_ in r.samples))
        self.assertFalse(result['gaze_and_speech_enabled'])
        self.assertGreaterEqual(result['elapsed_seconds'],60)

    def test_appearance_plan_has_separate_visits_and_bounded_owned_records(self):
        p=checked_plan(APPEARANCE_TARGETS);self.assertEqual(len(p),15)
        self.assertEqual([x[2] for x in p],['fit_a']*5+['fit_b']*5+['check']*5)
        for start in (0,5,10):self.assertEqual({x[0] for x in p[start:start+5]}, {'center','water','rest','help','more'})
        r=FixationRecording(p);a=np.zeros((480,640),np.uint8)
        for step in range(15):
            for slot in range(5):
                presented=10+step*6;requested=presented+2.1+slot*.8
                r.observe(a,step*5+slot+1,requested,requested+.05,presented,step)
        self.assertEqual(len(r.samples),75)
        self.assertEqual(r.samples[-1][0]['visit'],'check')
        with self.assertRaises(ValueError):checked_plan(p*2)
