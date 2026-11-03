"""Deterministic protocol/control boundary tests; not hardware or gaze evidence."""
import unittest
from unittest.mock import patch
from test_events import Transport
import test_launch
from eye_tracker.event_link import EventLink
from eye_tracker.event_protocol import Packet, ACK, EVENT, BUSY, TEST, Receiver
from eye_tracker.trial_events import TrialEvents
from eye_tracker.interaction import Action, DwellController, GazeSample
from eye_tracker.calibration import Context
from eye_tracker import launch

class TrialEventsTests(unittest.TestCase):
    def make(self, log=True):
        self.wire=Transport(Receiver(allow_test=True))
        self.link=EventLink(self.wire,simulation=False,wire_test=log,session_factory=iter(range(100,999)).__next__)
        self.c=DwellController(Context('test','geom','live'),'current')
        self.events=TrialEvents(self.link,self.c)
        for t in (0,10,20):self.step(t)
    def step(self,t,action=None,frame=1):
        self.wire.time=t
        return self.events.update(t,action,frame)
    def test_real_dwell_provenance_and_all_codes_reach_log_receiver(self):
        self.make()
        for n,key in enumerate(('water','rest','help','more','back')):
            t=30+n*100
            self.assertTrue(self.step(t,Action(key,'','live',t),20+n))
            self.step(t+10)
        self.assertEqual([p.code for p in self.wire.delivered],[1,2,3,4,5])
        self.assertTrue(all(p.detail==TEST for p in self.wire.delivered))
        report=self.events.snapshot()
        self.assertFalse(report['simulation'])
        self.assertEqual(report['receiver_mode'],'log')
        acks=[r for r in report['events'] if r['event']=='remote_accepted']
        self.assertEqual(len(acks),5)
        self.assertEqual([r['source_time_ms'] for r in acks],[30,130,230,330,430])
        self.assertTrue(all(r['session']==100 for r in acks))
    def test_live_mode_flag_and_busy_rejection_not_false_success(self):
        self.make(log=False);self.wire.drop_ack=True
        self.step(30,Action('water','','live',30))
        event=self.wire.sent[-1];self.assertEqual(event.detail,0)
        self.wire.rx.extend(Packet(ACK,event.session,event.sequence,event.code,BUSY).encode())
        self.step(40)
        self.assertEqual(self.link.counts['remote_accepted'],0)
        self.assertEqual(self.link.counts['rejected'],1)
    def test_local_music_navigation_never_becomes_receiver_command(self):
        self.make()
        for n,key in enumerate(('music_open','music_toggle','music_next','music_back','menu_back',
                               'music_player_open','music_volume_open','music_volume_back','music_menu_back',
                               'music_volume_down','music_volume_up')):
            t=30+n*50
            self.assertFalse(self.step(t,Action(key,'','live',t)))
        self.assertEqual(self.wire.delivered,[])
        self.assertEqual(self.events.snapshot()['selections'],[])
        self.assertTrue(self.step(600,Action('help','','live',600)))
        self.step(610)
        self.assertEqual([p.code for p in self.wire.delivered],[3])
    def test_response_care_phrases_and_navigation_are_local_in_both_modes(self):
        from eye_tracker.phrases import QUICK_KEYS,PHRASE_TEXT
        for log in (True,False):
            self.make(log=log)
            keys=('quick_open','quick_back','care_open','care_back')+QUICK_KEYS
            for n,key in enumerate(keys):
                t=30+n*20
                self.assertFalse(self.step(t,Action(key,PHRASE_TEXT.get(key,''),'live',t)))
            self.assertEqual(self.wire.delivered,[])
            self.assertEqual(self.events.snapshot()['selections'],[])
    def test_all_emotion_actions_are_local_even_if_injected_into_wireless_adapter(self):
        from eye_tracker.emotions import LOCAL_ACTIONS
        for log in (True,False):
            self.make(log=log)
            for n,key in enumerate(sorted(LOCAL_ACTIONS)):
                t=30+n*20
                self.assertFalse(self.step(t,Action(key,'','live',t)))
            self.assertEqual(self.wire.delivered,[])
            self.assertEqual(self.events.snapshot()['selections'],[])
    def test_simulated_replay_stale_actions_do_not_cross_real_boundary(self):
        self.make()
        for a in (Action('water','','simulated',30),Action('water','','replay',30),Action('water','','live',-200)):
            self.assertFalse(self.step(30,a))
        self.assertEqual(self.wire.delivered,[])
        with self.assertRaises(ValueError):EventLink(self.wire,simulation=True,wire_test=False)
        with self.assertRaises(ValueError):TrialEvents(EventLink(self.wire,simulation=True),self.c)
    def test_partial_dwell_loss_does_not_emit_but_new_full_dwell_does(self):
        self.make();seq=0
        def feed(t,status):
            nonlocal seq
            seq+=1
            a=self.c.feed(GazeSample(self.c.context,'current',seq,t,status,(.25,.37)),t)
            self.step(t,a,seq)
        for t in range(100,900,100):feed(t,'valid')
        self.assertGreater(self.c.progress,.5)
        feed(900,'unknown');self.assertEqual(self.c.progress,0)
        self.assertEqual(self.wire.delivered,[])
        for t in range(1000,2400,100):feed(t,'valid')
        self.assertEqual([p.code for p in self.wire.delivered],[1])
    def test_cancel_stops_pending_retry_and_reconnect_cannot_replay(self):
        self.make();self.wire.drop_ack=True
        self.step(30,Action('water','','live',30));self.c.reason='cancelled';self.step(40)
        self.c.reason='waiting';self.wire.drop_ack=False
        for t in range(50,900,50):self.step(t)
        self.assertEqual(len(self.wire.delivered),1)
        self.assertEqual(self.link.counts['delivery_unknown'],1)
    def test_held_target_and_normal_shutdown_do_not_repeat(self):
        self.make();a=Action('water','','live',30)
        self.step(30,a);self.step(40);self.assertFalse(self.step(50,a))
        self.events.close(60);self.assertEqual(len(self.wire.delivered),1)
        self.assertEqual(self.link.state,'disabled')
    def test_deferred_ping_preserves_original_stamp_in_ack(self):
        self.make()
        for t in (200,400,520):self.step(t)
        self.step(520,Action('help','','live',520),12)
        for t in (530,540,550,560):self.step(t)
        acks=[r for r in self.events.snapshot()['events'] if r['event']=='remote_accepted']
        self.assertEqual(acks[0]['source_time_ms'],520)
    def test_missing_link_does_not_delay_local_selection_or_replay(self):
        self.make();self.link.abort(30);self.assertFalse(self.step(40,Action('help','','live',40)))
        for t in range(50,800,50):self.step(t)
        self.assertEqual(self.wire.delivered,[])

class WirelessLaunchTests(unittest.TestCase):
    def test_explicit_opt_in_only_default_remains_off(self):
        fixture=test_launch.LaunchTests();fixture.setUp()
        try:
            with patch.object(launch,'verify_artifacts',return_value={}):
                default=launch.prepare_launch(fixture.path,fixture.root)
                self.assertFalse(default['uart_enabled'])
                self.assertNotIn('--eye-events',default['board_arguments'])
                for mode in ('log','live'):
                    plan=launch.prepare_launch(fixture.path,fixture.root,mode)
                    self.assertTrue(plan['uart_enabled'])
                    i=plan['board_arguments'].index('--eye-events')
                    self.assertEqual(plan['board_arguments'][i+1],mode)
        finally:fixture.doCleanups()

class TrialLoopWiringTests(unittest.TestCase):
    def test_real_loop_submits_only_controller_action_and_cleans_transport(self):
        from types import SimpleNamespace
        from eye_tracker.appearance_trial import run_visual_trial
        now=[0.]
        wire=Transport(Receiver(allow_test=True))
        link=EventLink(wire,simulation=False,wire_test=True,session_factory=lambda:123)
        c=DwellController(Context('session','geom','live'))
        rows=[];selected=[]
        trial=SimpleNamespace(controller=c,telemetry=None,summary={},commands=[],audio_enabled=False,last_action=None,
            engine=SimpleNamespace(baseline=SimpleNamespace(samples=[1]*5)),
            reference=SimpleNamespace(observe=lambda *a:None),event_total=lambda name:len(selected))
        def begin():c.calibration_id='fresh';trial.summary['reference_passed']=True
        trial.begin_visual=begin
        session=SimpleNamespace(capture_index=0,last_capture={},wait_native_frames=lambda n:dict(bad_lines=0,bad_frames=0),present=lambda frame:None)
        def capture():
            now[0]+=.05;wire.time=now[0]*1000;session.capture_index+=1
            session.last_capture=dict(requested_at_monotonic=now[0],copied_at_monotonic=now[0])
            return None
        session.capture_once=capture
        def observe(pixels,index,copied,clock,allow_selection=True):
            trial.last_action=c.feed(GazeSample(c.context,'fresh',index,copied*1000,'valid',(.25,.37)),clock()*1000)
            if trial.last_action:selected.append(trial.last_action)
            row={};rows.append(row);return row
        trial.observe=observe
        device=SimpleNamespace(stop=lambda:None,status=lambda:0)
        renderer=SimpleNamespace(rgb565=lambda *a:b'',setup_frame=lambda *a,**k:b'')
        with patch('eye_tracker.audio.AudioDevice',return_value=device):
            result=run_visual_trial(session,renderer,trial,SimpleNamespace(read=lambda o:0),10,clock=lambda:now[0],event_link=link)
        self.assertEqual(len(selected),1)
        self.assertEqual([p.code for p in wire.delivered],[1])
        self.assertEqual(result['communication']['counts']['remote_accepted'],1)
        self.assertEqual(result['communication']['selections'][0]['source_time_ms'],selected[0].source_time_ms)
        self.assertTrue(result['uart_enabled']);self.assertEqual(link.state,'disabled')
