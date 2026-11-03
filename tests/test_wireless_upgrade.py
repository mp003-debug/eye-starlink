"""Upgrade coexistence boundaries; deterministic evidence, not a radio/eye trial."""
import threading,unittest
from pathlib import Path
from unittest.mock import patch
from eye_tracker.calibration import Context
from eye_tracker.daily_tools import DailyTools,LOCAL_ACTIONS as DAILY
from eye_tracker.emotions import LOCAL_ACTIONS as EMOTIONS
from eye_tracker.event_link import EventLink
from eye_tracker.event_protocol import Receiver,Packet,ACK,EVENT,PING,TEST
from eye_tracker.interaction import Action,DwellController
from eye_tracker.launch import prepare_launch
from eye_tracker.trial_events import TrialEvents
from eye_tracker.ui import BoardRenderer
from test_events import Transport
ROOT=Path(__file__).resolve().parents[1]

class WirelessUpgradeTests(unittest.TestCase):
    def make(self,test=False):
        self.wire=Transport(Receiver(allow_test=test))
        self.link=EventLink(self.wire,simulation=False,wire_test=test,session_factory=iter(range(100,999)).__next__)
        self.c=DwellController(Context('live-test','geometry','live'),'calibrated')
        self.adapter=TrialEvents(self.link,self.c)
        for t in (0,10,20):self.step(t)
    def step(self,t,a=None):
        self.wire.time=t;return self.adapter.update(t,a,17)

    def test_unknown_and_every_upgrade_local_key_are_not_protocol_submissions(self):
        keys=DAILY|EMOTIONS|{'future_local_feature','video_toggle','book_toggle','game_answer','save','word_commit','yes','please_stop'}
        for test in (False,True):
            self.make(test)
            for i,key in enumerate(sorted(keys)):self.assertFalse(self.step(30+i*10,Action(key,'','live',30+i*10)))
            self.assertEqual(self.adapter.selections,[]);self.assertEqual(self.wire.delivered,[])

    def test_rebinding_retires_pending_session_and_rejects_old_action_or_late_ack(self):
        self.make();self.wire.drop_ack=True
        old_action=Action('water','','live',30);self.step(30,old_action);sent=self.wire.sent[-1]
        self.adapter.suspend(40,'reposition')
        fresh=DwellController(Context('new','geometry','live'))
        self.adapter.resume(fresh,50)
        self.assertFalse(self.step(60,Action('help','','live',60)))
        self.assertEqual(len(self.wire.delivered),1)
        self.wire.rx.extend(Packet(ACK,sent.session,sent.sequence,sent.code,0).encode())
        fresh.calibration_id='new-reference';fresh.reason='waiting';self.wire.drop_ack=False
        self.adapter.resume(fresh,500)
        for t in (500,510,520):self.step(t)
        self.assertFalse(self.step(530,old_action));self.assertTrue(self.step(540,Action('help','','live',540)))
        self.step(550)
        self.assertEqual([p.code for p in self.wire.delivered],[1,3])
        self.assertNotEqual(self.wire.delivered[0].session,self.wire.delivered[1].session)
        self.assertEqual(self.link.counts['delivery_unknown'],1)
        self.assertEqual(self.link.counts['remote_accepted'],1)
        self.assertIs(self.adapter.controller,fresh)
        with self.assertRaises(ValueError):self.adapter.resume(DwellController(Context('replay','geometry','replay')),560)

    def test_suspended_preview_drops_pending_ping_action_and_never_handshakes(self):
        self.make()
        for t in (200,400):self.step(t)
        self.wire.drop_ack=True;self.step(520);self.step(521)
        self.assertTrue(self.step(522,Action('help','','live',522)))
        self.assertIsNotNone(self.link.deferred)
        self.adapter.suspend(530,'preview');count=len(self.wire.sent)
        for t in range(540,2000,100):self.assertFalse(self.step(t,Action('help','','live',t)))
        self.assertEqual(len(self.wire.sent),count);self.assertEqual(self.wire.delivered,[])
        self.assertEqual(self.link.counts['not_sent'],1)

    def test_fresh_help_precedes_unsent_heartbeat_after_feature_processing(self):
        # Board failure: selection age 61 ms, unsent PING then a 92 ms frame
        # leaves an otherwise valid local help too old for its first wire send.
        self.make()
        for t in (200,400,520):self.step(t)
        self.assertEqual(self.link.pending['packet'].kind,PING)
        self.assertEqual(self.link.pending['attempts'],0)
        self.wire.drop_ack=True
        self.assertTrue(self.step(581,Action('help','','live',520)))
        self.assertEqual([p.code for p in self.wire.delivered],[3])
        self.assertEqual(self.wire.sent[-1].kind,EVENT)
        self.assertEqual(self.link.pending['source_time_ms'],520)
        self.step(673)
        self.assertFalse(any(x.get('reason')=='expired_before_first_send' for x in self.adapter.events))

    def test_ping_ack_promotes_and_sends_fresh_help_in_same_service_call(self):
        self.make()
        for t in (200,400,520):self.step(t)
        self.wire.drop_ack=True;self.step(521)
        ping=self.wire.sent[-1];self.assertEqual(ping.kind,PING)
        self.assertTrue(self.step(596,Action('help','','live',535)))
        self.assertEqual(self.wire.delivered,[])
        self.wire.rx.extend(Packet(ACK,ping.session,ping.sequence,0,0).encode())
        self.step(650)  # age 115 ms: must not wait for another camera frame
        self.assertEqual([p.code for p in self.wire.delivered],[3])
        self.assertEqual(self.link.pending['fresh_until'],685)
        self.assertEqual(self.link.pending['source_time_ms'],535)

    def test_delayed_ping_priority_keeps_expiry_and_invalid_input_guards(self):
        for invalid in (False,True):
            self.make()
            for t in (200,400,520):self.step(t)
            self.wire.drop_ack=True;self.step(521);ping=self.wire.sent[-1]
            self.assertTrue(self.step(596,Action('help','','live',535)))
            if invalid:self.c.reason='lost'
            self.wire.rx.extend(Packet(ACK,ping.session,ping.sequence,0,0).encode())
            self.step(650 if invalid else 686)
            self.assertEqual(self.wire.delivered,[])
            self.assertIsNone(self.link.deferred)
            self.assertEqual(self.link.counts['not_sent'],1)

    def test_overdue_service_cancels_instead_of_relaxing_250ms_or_replaying(self):
        self.make();self.wire.drop_ack=True;self.step(30,Action('help','','live',30));self.step(281)
        self.assertEqual(self.link.state,'disabled');self.assertEqual(self.link.counts['delivery_unknown'],1)
        self.assertTrue(any(e.get('reason')=='service_gap' for e in self.adapter.events))
        self.wire.drop_ack=False
        for t in range(300,1100,50):self.step(t)
        self.assertEqual(len(self.wire.delivered),1);self.assertEqual(self.link.counts['remote_accepted'],0)

    def test_cold_text_build_services_same_owner_without_pixel_or_draft_changes(self):
        self.make();d=DailyTools.from_root(ROOT);d.composer.append_text('今天下午');d.state='word_candidates';d.initials='jt'
        self.c.daily_tools=d;self.c.page='local_tools';r=BoardRenderer();r.bind_daily_tools(d)
        plain=r.rgb565(self.c,'guide_ready');atlas=r.daily_renderer.atlas;r.daily_renderer._key=None
        owner=threading.get_ident();now=[30];calls=[]
        self.step(30,Action('help','','live',30))
        def service():
            self.assertEqual(threading.get_ident(),owner);calls.append(now[0]);self.step(now[0])
        draw=atlas.draw
        def slow(*a,**kw):now[0]+=40;return draw(*a,**kw)
        atlas.service=service
        with patch.object(atlas,'draw',side_effect=slow):actual=r.rgb565(self.c,'guide_ready')
        self.assertEqual(actual,plain);self.assertEqual(d.composer.text,'今天下午')
        self.assertGreater(len(calls),10);self.assertGreater(now[0],600)
        self.assertLessEqual(self.adapter.max_service_gap_ms,40)
        self.assertEqual(self.link.counts['remote_accepted'],1)
        self.assertFalse(any(e.get('reason')=='service_gap' for e in self.adapter.events))
        self.assertEqual([p.code for p in self.wire.delivered],[3])

    @unittest.skipUnless((Path(__file__).resolve().parents[1]/'data/private/profiles/current_eye.json').is_file(), 'requires optional local private profile or AI runtime bundle')
    def test_checked_launch_keeps_all_features_and_opt_in_receiver_mode(self):
        flags=dict(music=True,quick_phrases=True,emotion_cards=True,daily_tools=True,local_video=True,pastimes=True,reposition_assist=True)
        for mode in ('off','log','live'):
            p=prepare_launch('data/private/profiles/current_eye.json',ROOT,eye_events=mode,**flags)
            self.assertEqual(p['uart_enabled'],mode!='off');self.assertFalse(p['hardware_loaded'])
            for arg in ('--music','--quick-phrases','--emotion-cards','--daily-tools','--local-video','--pastimes','--reposition-assist'):
                self.assertIn(arg,p['board_arguments'])
            self.assertEqual(p['verified_sha256']['bit'],'662895c04211deb32e805b7f205251faa8abf0d87e62992abac631b864f75c20')
