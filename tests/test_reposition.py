"""Recovery safety boundaries with deterministic capture and physical-button timing."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from eye_tracker.controls import HelperButtons
from eye_tracker.calibration import Context
from eye_tracker.interaction import DwellController,GazeSample
from eye_tracker.reposition import assisted_reference
from eye_tracker.ui import BoardRenderer,POSITION_PREVIEW_BOX,POSITION_COLLECT_BOX,GRAY565


class AssistedReferenceTests(unittest.TestCase):
    def run_setup(self,presses,fail=False,limit=0,deadline=25.,capture_error=False):
        now=[0.];clock=lambda:now[0];seen=[];rendered=[];commands=[]
        c=DwellController(Context('fixture','geometry','live'),'old')
        for i in range(8):c.feed(GazeSample(c.context,'old',i,i*100,'valid',(.25,.37)),i*100)
        class Trial:
            controller=c;summary={};setup_attempts=limit;resets=0
            def __init__(self):self.new_reference()
            def new_reference(self):
                self.engine=SimpleNamespace(baseline=SimpleNamespace(samples=[],summary={},ids=set()))
                self.reference=SimpleNamespace(frames=0,clock=clock,observe=self.observe)
            def observe(self,pixels,index,requested,copied,shown,step):
                self.reference.frames+=1
                seen.append((index,requested,shown))
                self.assert_no_action()
                if not fail and requested-shown>=2.+len(self.engine.baseline.samples)*.6 and len(self.engine.baseline.samples)<5:
                    self.engine.baseline.samples.append(index)
            def assert_no_action(self):
                assert self.controller.calibration_id is None and self.controller.progress==0
                assert self.controller.feed(GazeSample(self.controller.context,'old',999,clock()*1000,'valid',(.25,.37)),clock()*1000) is None
            def reset_reference(self):
                self.resets+=1;self.new_reference()
                self.controller=DwellController(Context('new'+str(self.resets),'geometry','live'))
            def begin_visual(self):
                if len(self.engine.baseline.samples)!=5:raise ValueError('current_center_reference_required')
                self.engine.baseline.summary={'ready':True}
                self.summary['current_neighborhood']={'scope':'test fixture only'}
                self.controller.calibration_id='fresh'
            def command(self,name,t):
                commands.append(name)
                if name=='stop':self.controller.stop(t*1000)
                else:self.controller.invalidate_calibration()
        trial=Trial()
        class Session:
            capture_index=0
            def capture_once(self):
                if capture_error:raise RuntimeError('capture failed')
                requested=clock();now[0]+=.05;self.capture_index+=1
                self.last_capture=dict(requested_at_monotonic=requested,copied_at_monotonic=clock())
                return np.zeros((480,640),np.uint8)
            def present(self,frame):now[0]+=.01
        class MMIO:
            def read(self,offset):return next((mask for start,end,mask in presses if start<=clock()<end),0)
        def draw(pixels,phase,count):
            rendered.append((phase,count,clock()));return b''
        buttons=HelperButtons();buttons.update(0,0)
        ok=assisted_reference(Session(),SimpleNamespace(position_frame=draw),trial,MMIO(),buttons,clock,deadline)
        return ok,trial,seen,rendered,commands

    def test_preview_never_collects_or_reuses_old_partial_dwell_without_confirmation(self):
        ok,t,seen,frames,_=self.run_setup([],deadline=3)
        self.assertFalse(ok);self.assertEqual(seen,[])
        self.assertIsNone(t.controller.calibration_id);self.assertEqual(t.controller.progress,0)
        self.assertTrue(all(x[0]=='preview' for x in frames))

    def test_held_start_does_not_repeat_and_pre_prompt_capture_is_excluded(self):
        ok,t,seen,frames,_=self.run_setup([(1,15,1)])
        self.assertTrue(ok);self.assertEqual(t.setup_attempts,1)
        self.assertTrue(all(requested>=shown for _,requested,shown in seen))
        events=t.summary['reposition_events'];start=next(e for e in events if e['event']=='collecting')
        ready=next(e for e in events if e['event']=='ready')
        self.assertGreaterEqual(ready['monotonic']-start['monotonic'],6)
        self.assertEqual(len(t.engine.baseline.samples),5)
        self.assertEqual(t.controller.progress,0)

    def test_failed_collection_stays_unavailable_and_requires_new_press(self):
        ok,t,seen,frames,_=self.run_setup([(1,20,1)],fail=True,deadline=18)
        self.assertFalse(ok);self.assertEqual(t.setup_attempts,1)
        self.assertIsNone(t.controller.calibration_id)
        self.assertTrue(any(f[0]=='failed' for f in frames))

    def test_cancel_discards_partial_reference_and_fresh_retry_can_pass(self):
        ok,t,seen,frames,commands=self.run_setup([(1,1.4,1),(4,4.4,2),(6,6.4,1)])
        self.assertTrue(ok);self.assertEqual(t.setup_attempts,2);self.assertEqual(t.resets,1)
        self.assertIn('invalidate_calibration',commands)
        self.assertEqual(len(t.engine.baseline.samples),5)

    def test_exit_works_in_preview_and_collection(self):
        for presses in ([(1,1.5,8)],[(1,1.4,1),(4,4.4,8)]):
            ok,t,*_=self.run_setup(presses)
            self.assertFalse(ok);self.assertTrue(t.controller.closed)
            self.assertIsNone(t.controller.calibration_id)

    def test_retry_limit_and_global_deadline_do_not_enable_actions(self):
        ok,t,seen,frames,_=self.run_setup([(1,1.5,1)],limit=4,deadline=3)
        self.assertFalse(ok);self.assertEqual(seen,[]);self.assertTrue(any(x[0]=='limit' for x in frames))
        ok,t,*_=self.run_setup([(1,1.5,1)],deadline=4)
        self.assertFalse(ok);self.assertIsNone(t.controller.calibration_id)

    def test_capture_failure_propagates_with_actions_disabled(self):
        with self.assertRaisesRegex(RuntimeError,'capture failed'):self.run_setup([],capture_error=True)


class PositionPixelsTests(unittest.TestCase):
    def test_live_preview_is_exact_subsample_and_never_mutates_capture(self):
        ui=BoardRenderer();pixels=np.arange(480*640,dtype=np.uint32).reshape(480,640).astype(np.uint8)
        before=pixels.copy()
        for state,box,step in [('preview',POSITION_PREVIEW_BOX,2),('failed',POSITION_PREVIEW_BOX,2),('collecting',POSITION_COLLECT_BOX,5)]:
            raw=ui.position_frame(pixels,state,3);words=np.frombuffer(raw,dtype='<u2').reshape(480,640)
            l,t,r,b=box;np.testing.assert_array_equal(words[t:b,l:r],GRAY565[pixels[::step,::step]])
        np.testing.assert_array_equal(pixels,before)
        for bad in (pixels[:20],pixels.astype(float),None):
            with self.assertRaises(ValueError):ui.position_frame(bad)
