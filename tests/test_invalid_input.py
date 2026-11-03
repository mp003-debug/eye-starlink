import json,tempfile,unittest
from pathlib import Path
import numpy as np
from eye_tracker.invalid_input_diagnostic import PLAN,DURATIONS,InvalidInputRecording,run_invalid_input,InvalidInputRenderer

class FakeEngine:
    pack_sha256='diagnostic';relocation=None
    class Baseline:
        summary={'ready':True}
        def finish(self):return self.summary
    def __init__(self):self.baseline=self.Baseline();self.calls=[]
    def observe(self,pixels,index,copied,clock):
        self.calls.append(index)
        return dict(candidate='water',stable_candidate='water',actions_enabled=False,processing_ms=1)
    def observe_reference(self,pixels,index,copied,eligible,clock):
        return dict(candidate=None,stable_candidate=None,actions_enabled=False,processing_ms=1,reference_sample=eligible)

class InvalidInputTests(unittest.TestCase):
    def test_prompt_does_not_force_rejection_and_every_challenge_capture_has_evidence(self):
        engine=FakeEngine();r=InvalidInputRecording(engine);im=np.full((480,640),50,np.uint8)
        r.observe(im,1,12.1,12.2,10.,2);im[:]=230
        self.assertEqual(r.rows[0]['candidate'],'water')
        self.assertEqual(r.rows[0]['stable_candidate'],'water')
        self.assertFalse(r.rows[0]['scored_positive'])
        self.assertFalse(r.rows[0]['action_label_verified'])
        self.assertEqual(engine.calls,[1]);self.assertEqual(len(r.audit),1)
        self.assertTrue((r.audit[0][1]==50).all())
        self.assertEqual(r.audit[0][1].shape,(240,320))
    def test_return_uses_same_engine_without_new_reference(self):
        engine=FakeEngine();r=InvalidInputRecording(engine);im=np.zeros((480,640),np.uint8)
        for i,step in enumerate((1,2,3),1):r.observe(im,i,10+step*10+2.1,10+step*10+2.2,10+step*10,step)
        self.assertEqual(engine.calls,[1,2,3])
        self.assertTrue(r.rows[-1]['scored_positive'])
        self.assertEqual(r.rows[-1]['phase'],'after_close')
    def test_incomplete_save_cannot_claim_invalid_input_passed(self):
        r=InvalidInputRecording(FakeEngine());r.observe(np.zeros((480,640),np.uint8),1,12.1,12.2,10.,2)
        with tempfile.TemporaryDirectory() as tmp:
            result=r.save(tmp,False)
            d=json.loads((Path(tmp)/'invalid_input.json').read_text())
            self.assertFalse(d['completed']);self.assertFalse(d['invalid_input_verified']);self.assertFalse(d['actions_enabled'])
            self.assertEqual(d['counts']['challenge_close']['stable_accepted'],1)
            self.assertFalse(d['prompt_labels_are_ground_truth'])
            self.assertEqual(len(list((Path(tmp)/'audit').glob('*.png'))),1)
    def test_capacity_exhaustion_fails_instead_of_discarding_evidence(self):
        r=InvalidInputRecording(FakeEngine());r.MAX_AUDIT=1;im=np.zeros((480,640),np.uint8)
        r.observe(im,1,12.1,12.2,10.,2)
        with self.assertRaisesRegex(ValueError,'audit image capacity'):r.observe(im,2,12.3,12.4,10.,2)
        self.assertEqual(len(r.rows),1)
    def test_sequence_has_positive_checks_before_and_after_each_challenge(self):
        self.assertEqual(len(PLAN),13);self.assertEqual(sum(DURATIONS)+6,92.)
        for start in (1,4,7,10):
            self.assertEqual(len({PLAN[i][0] for i in range(start,start+3)}),1)
            self.assertTrue(PLAN[start+1][2].startswith('challenge_'))
            self.assertTrue(PLAN[start+2][2].startswith('after_'))
    def test_portable_prompts_cover_every_phase(self):
        renderer=InvalidInputRenderer();self.assertEqual(len(renderer.frame()),614400)
        self.assertNotEqual(renderer.frame(1),renderer.frame(2))
        self.assertEqual(renderer.plan,PLAN)
    def test_runner_keeps_full_challenge_and_checks_link_errors(self):
        class Session:
            t=0.;capture_index=0
            def display_health(self):pass
            def wait_native_frames(self,n):return {'bad_lines':0,'bad_frames':0}
            def present(self,frame):self.t+=.03
            def capture_once(self):
                old=self.t;self.t+=.5;self.capture_index+=1
                self.last_capture={'requested_at_monotonic':old,'copied_at_monotonic':self.t}
                return np.zeros((480,640),np.uint8)
        class Renderer:
            plan=PLAN
            def frame(self,step):return step
        s=Session();r=InvalidInputRecording(FakeEngine())
        result=run_invalid_input(s,Renderer(),r,clock=lambda:s.t,sleep=lambda v:setattr(s,'t',s.t+v))
        self.assertGreaterEqual(result['elapsed_seconds'],92)
        self.assertFalse(result['gaze_and_speech_enabled'])
        self.assertEqual(len(r.audit),64)
        self.assertEqual(len(r.samples),65)
        self.assertEqual(len({x['phase'] for x in r.rows}),13)

