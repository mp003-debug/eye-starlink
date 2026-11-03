import unittest
from eye_tracker.event_protocol import Packet, ACK, HELLO, EVENT, PING
from eye_tracker.share_protocol import (SharePacket,MixedDecoder,CAPS,BEGIN,DATA,COMMIT,
    PHRASE,EMOTION,TEXT,ACTIVITY,PHRASES,EMOTIONS,fragments,message_bytes)
from eye_tracker.share_link import SharingEventLink
from eye_tracker.sharing_ui import SharingUI
from eye_tracker.interaction import Action


class Transport:
    def __init__(self):
        self.incoming=b'';self.sent=[];self.old=False;self.drop=False;self.wrong_version=False
    def reset(self):self.incoming=b''
    def read(self):raw=self.incoming;self.incoming=b'';return raw
    def try_write(self,raw):
        p=MixedDecoder().feed(raw)[0];self.sent.append(p)
        if not self.drop and not (self.old and isinstance(p,SharePacket)):
            kind=Packet if self.wrong_version or not isinstance(p,SharePacket) else SharePacket
            self.incoming+=kind(ACK,p.session,p.sequence,p.code,0).encode()
        return True


class SharingTests(unittest.TestCase):
    def ready(self):
        t=Transport();l=SharingEventLink(t,session_factory=iter(range(100,1000)).__next__)
        for now in range(0,100,5):l.service(now)
        self.assertEqual(l.capable_session,l.session)
        return t,l

    def test_v1_bytes_and_mixed_resynchronization(self):
        p=Packet(EVENT,1,2,3,0);q=SharePacket(DATA,1,3,0xc4,0xe3)
        d=MixedDecoder();out=[]
        bad=bytearray(q.encode());bad[-1]^=1
        for b in b'noise'+p.encode()+bytes(bad)+q.encode():out+=d.feed(bytes([b]))
        self.assertEqual(out,[p,q]);self.assertEqual(d.bad_frames,1)
        self.assertEqual(p.encode()[2],1);self.assertEqual(q.encode()[2],2)

    def test_text_bounds_and_command_characters(self):
        self.assertEqual(len(message_bytes(TEXT,'你'*64)),128)
        for text in ('','你'*65,'😀','a\n','a\x00'):
            with self.assertRaises(ValueError):message_bytes(TEXT,text)
        self.assertEqual(message_bytes(TEXT,'"\\;'),b'"\\;')
        for category,items in ((PHRASE,PHRASES),(EMOTION,EMOTIONS)):
            for value in items:self.assertTrue(fragments(category,value))
        with self.assertRaises(ValueError):fragments(PHRASE,'随便一句')

    def test_full_message_and_blink_after_commit_intent(self):
        t,l=self.ready();a=Action('tool_slot_0','','live',100)
        self.assertTrue(l.submit_share(a,TEXT,'你'*64,100))
        for now in range(100,1200,5):l.service(now,enabled=not (200<=now<250))
        self.assertIsNone(l.transfer)
        self.assertEqual(l.counts['share_accepted'],1)
        data=[p for p in t.sent if p.kind==DATA]
        self.assertEqual(len(data),64)
        self.assertEqual(sum(p.kind==COMMIT for p in t.sent),1)

    def test_confirmed_short_message_finishes_while_gaze_remains_unknown(self):
        t,l=self.ready()
        self.assertTrue(l.submit_share(Action('tool_slot_0','','live',100),PHRASE,'是',100))
        l.service(100)
        l.service(105)
        self.assertEqual(t.sent[-1].kind,DATA)
        # Hardware failure: the user looked away after confirming. With service
        # still running, no next fragment may wait for a new valid gaze sample.
        for now in range(110,3110,5):l.service(now,enabled=False)
        self.assertIsNone(l.transfer)
        self.assertEqual(l.counts['share_accepted'],1)
        self.assertEqual(sum(p.kind==COMMIT for p in t.sent),1)
        self.assertFalse(any(p.kind==HELLO for p in t.sent[4:]))

    def test_helper_pause_still_cancels_confirmed_transfer(self):
        from types import SimpleNamespace
        from eye_tracker.trial_events import TrialEvents
        t,l=self.ready();ui=SharingUI()
        c=SimpleNamespace(context=SimpleNamespace(source='live'),daily_tools=SimpleNamespace(sharing=ui),
            calibration_id='checked',paused=False,closed=False,reason='selected')
        trial=TrialEvents(l,c)
        self.assertTrue(l.submit_share(Action('tool_slot_0','','live',100),PHRASE,'是',100))
        l.service(100)
        c.paused=True
        for now in range(105,500,5):trial.update(now)
        self.assertIsNone(l.transfer)
        self.assertFalse(any(p.kind==COMMIT for p in t.sent))

    def test_help_preempts_fragments_and_stays_v1(self):
        t,l=self.ready();self.assertTrue(l.submit_share(Action('tool_slot_0','','live',100),TEXT,'你好'*10,100))
        l.service(100);l.service(105)
        l.service(110,allow_heartbeat=False)
        self.assertTrue(l.submit(Action('help','','live',110),110))
        l.service(110);l.service(115)
        self.assertIsNone(l.transfer)
        self.assertFalse(any(p.kind==COMMIT for p in t.sent))
        care=[p for p in t.sent if p.kind==EVENT]
        self.assertEqual(len(care),1);self.assertIsInstance(care[0],Packet)
        self.assertEqual(l.counts['remote_accepted'],1)

    def test_cancel_never_replays_on_reconnect(self):
        t,l=self.ready();l.submit_share(Action('tool_slot_0','','live',100),TEXT,'你好',100)
        l.service(100);l.abort(105,'helper_reposition')
        for now in range(105,900,5):l.service(now)
        self.assertIsNone(l.transfer);self.assertFalse(any(p.kind==COMMIT for p in t.sent))

    def test_inflight_ping_ack_sends_begin_without_another_frame(self):
        t,l=self.ready()
        l._request(PING,100);l.service(100)
        self.assertTrue(l.submit_share(Action('tool_slot_0','','live',101),TEXT,'你好',101))
        l.service(245)
        self.assertEqual(t.sent[-1].kind,BEGIN)
        self.assertEqual(l.pending['attempts'],1)
        self.assertLessEqual(l.pending['sent']-101,150)

    def test_commit_uncertainty_and_no_private_fragment_bytes_in_trace(self):
        t,l=self.ready();l.submit_share(Action('tool_slot_0','','live',100),TEXT,'你好',100)
        for now in range(100,200,5):
            if l.pending and l.pending['packet'].kind==COMMIT:t.drop=True
            l.service(now)
            if l.pending and l.pending['packet'].kind==COMMIT and l.pending['attempts']:break
        l.abort(now,'user_share_cancel')
        self.assertIn('不确定',l.share_status)
        for item in l.trace:
            if item.get('kind') in (CAPS,BEGIN,DATA,COMMIT):self.assertNotIn('code',item)

    def test_old_firmware_is_not_sent_new_content(self):
        t=Transport();t.old=True;l=SharingEventLink(t,session_factory=iter(range(1,99)).__next__)
        for now in range(0,1500,5):l.service(now)
        self.assertTrue(l.unsupported)
        self.assertFalse(l.submit_share(Action('tool_slot_0','','live',1500),TEXT,'你好',1500))
        self.assertFalse(any(p.kind in (BEGIN,DATA,COMMIT) for p in t.sent))
        self.assertTrue(l.submit(Action('help','','live',1501),1501))
        l.service(1501);l.service(1506);self.assertEqual(l.counts['remote_accepted'],1)

    def test_wrong_version_ack_rejected_and_freshness_kept(self):
        t,l=self.ready();t.wrong_version=True
        l.submit_share(Action('tool_slot_0','','live',100),TEXT,'你好',100)
        for now in range(100,850,5):l.service(now)
        self.assertEqual(l.counts['share_accepted'],0)
        self.assertGreater(l.counts['ignored_reply'],0)
        t,l=self.ready();l.submit_share(Action('tool_slot_0','','live',100),TEXT,'你好',100)
        l.service(251);self.assertFalse(any(p.kind==BEGIN for p in t.sent))

    def test_ui_freezes_text_and_requires_final_confirmation(self):
        class Composer:text='今天下午'
        c=Composer();ui=SharingUI()
        self.assertFalse(ui.activity_enabled)
        ui.select('share_draft',None,c);c.text='更改后的正文'
        self.assertEqual(ui.view(c).body,'今天下午');self.assertIsNone(ui.request)
        ui.select('share_reviewed',None,c);self.assertIsNone(ui.request)
        ui.select('share_confirm',None,c);self.assertEqual(ui.request,(TEXT,'今天下午'))
        ui.select('share_cancel',None,c);self.assertIsNone(ui.request)
        ui.select('share_toggle',None,c);self.assertFalse(ui.activity_enabled)
        ui.select('share_enable',None,c);self.assertTrue(ui.activity_enabled)
        ui.select('share_toggle',None,c);self.assertFalse(ui.activity_enabled)
        self.assertEqual(ui.request,(ACTIVITY,'活动分享已关闭'))

    def test_trial_boundary_keeps_local_actions_local_and_honors_opt_out(self):
        from types import SimpleNamespace
        from eye_tracker.trial_events import TrialEvents
        t,l=self.ready();ui=SharingUI()
        c=SimpleNamespace(context=SimpleNamespace(source='live'),daily_tools=SimpleNamespace(sharing=ui),
            calibration_id='checked',paused=False,closed=False,reason='selected')
        trial=TrialEvents(l,c)
        trial.activity(100,'听音乐');self.assertIsNone(l.transfer)
        trial.update(100,Action('tool_slot_0','','live',100));self.assertIsNone(l.transfer)
        ui.activity_enabled=True;ui.activity_revision+=1
        trial.activity(110,'听音乐');self.assertIsNotNone(l.transfer)
        trial.update(110)
        ui.select('share_toggle',None,SimpleNamespace(text='你好'))
        self.assertTrue(trial.update(120,Action('tool_slot_0','','live',120)))
        self.assertEqual(l.transfer['parts'],fragments(ACTIVITY,'活动分享已关闭'))
        trial.suspend(130);self.assertIsNone(l.transfer)
        self.assertFalse(ui.activity_enabled)


if __name__=='__main__':unittest.main()
