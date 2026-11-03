import unittest
from collections import deque
from eye_tracker.event_protocol import *
from eye_tracker.event_uart import AxiUartLite, UartError
from eye_tracker.event_link import EventLink, service_controller
from eye_tracker.interaction import Action, DwellController
from eye_tracker.calibration import Context
from eye_tracker.ui_test import InteractionTest


class Transport:
    def __init__(self, receiver=None):
        self.receiver = receiver or Receiver(allow_test=True)
        self.rx = bytearray()
        self.sent = []
        self.delivered = []
        self.drop_ack = False
        self.busy = False
        self.time = 0
        self.resets = 0

    def reset(self):
        self.rx.clear()
        self.resets += 1

    def read(self):
        data = bytes(self.rx[:16]); del self.rx[:16]
        return data

    def try_write(self, raw):
        if self.busy:return False
        packet = Packet.decode(raw)
        self.sent.append(packet)
        reply, deliver = self.receiver.receive(packet, self.time)
        if deliver:self.delivered.append(packet)
        if reply and not self.drop_ack:self.rx.extend(reply.encode())
        return True


def setup_link(simulation=True, receiver=None):
    wire = Transport(receiver)
    sessions = iter(range(100,10000))
    return EventLink(wire, simulation=simulation, session_factory=lambda:next(sessions)), wire


def step(link, wire, now, **kwargs):
    wire.time=now;link.service(now, **kwargs)


def ready(link, wire, base=0):
    for delta in (0,10,20):step(link,wire,base+delta)
    assert link.ready and not link.pending


def action(now, key='water', source='simulated'):
    return Action(key,'',source,now)


class ProtocolTests(unittest.TestCase):
    def test_crc_known_check_and_little_endian(self):
        self.assertEqual(crc16(b'123456789'),0x29b1)
        p=Packet(EVENT,0x12345678,0x01020304,3,1)
        raw=p.encode();self.assertEqual(raw[:14].hex(),'a55a011078563412040302010301')
        self.assertEqual(Packet.decode(raw),p)
    def test_fragmentation_and_concatenation(self):
        packets=[Packet(HELLO,12,0),Packet(EVENT,12,1,1)]
        raw=b''.join(p.encode() for p in packets)
        for split in range(len(raw)+1):
            d=Decoder();self.assertEqual(d.feed(raw[:split])+d.feed(raw[split:]),packets)
        d=Decoder();out=[]
        for b in raw:out.extend(d.feed(bytes([b])))
        self.assertEqual(out,packets)
    def test_crc_corruption_noise_and_partial_bound(self):
        p=Packet(EVENT,12,1,1);bad=bytearray(p.encode());bad[8]^=1
        d=Decoder();self.assertEqual(d.feed(b'garbage'+bad+p.encode()),[p])
        self.assertGreater(d.bad_frames,0)
        d.feed(b'\xa5'*10000);self.assertLessEqual(len(d.buffer),15)
    def test_every_single_bit_error_rejected(self):
        raw=Packet(EVENT,12,1,1).encode()
        for bit in range(128):
            bad=bytearray(raw);bad[bit//8]^=1<<(bit%8)
            with self.assertRaises(ValueError):Packet.decode(bad)
    def test_invalid_version_kind_session_size(self):
        raw=Packet(HELLO,1,0).encode()
        for p in (Packet(3,1,0),Packet(HELLO,0,0)):
            with self.assertRaises(ValueError):p.encode()
        for data in (raw[:-1],raw+b'x',raw[:2]+b'\x02'+raw[3:]):
            with self.assertRaises(ValueError):Packet.decode(data)
    def test_receiver_duplicate_event_is_ack_only(self):
        r=Receiver();r.receive(Packet(HELLO,2,0),0)
        p=Packet(EVENT,2,1,1)
        self.assertTrue(r.receive(p,10)[1])
        reply,deliver=r.receive(p,20)
        self.assertFalse(deliver);self.assertEqual(reply.detail,DUPLICATE)
    def test_duplicate_hello_does_not_clear_highwater(self):
        r=Receiver();hello=Packet(HELLO,2,0);r.receive(hello,0)
        p=Packet(EVENT,2,1,1);r.receive(p,10);r.receive(hello,20)
        self.assertFalse(r.receive(p,30)[1])
    def test_old_or_conflicting_sequence_rejected(self):
        r=Receiver();r.receive(Packet(HELLO,2,0),0)
        r.receive(Packet(EVENT,2,2,1),10)
        for p in (Packet(EVENT,2,1,1),Packet(EVENT,2,2,2)):
            ack,deliver=r.receive(p,20)
            self.assertEqual(ack.detail,OLD_SEQUENCE);self.assertFalse(deliver)
    def test_receiver_reboot_expiry_and_unknown_session(self):
        for expire in (False,True):
            r=Receiver();r.receive(Packet(HELLO,2,0),0)
            if not expire:r.disconnect()
            ack,deliver=r.receive(Packet(EVENT,2,1,1),2001 if expire else 1)
            self.assertEqual(ack.detail,NO_SESSION);self.assertFalse(deliver)
    def test_test_mode_needs_both_sides_opt_in(self):
        r=Receiver();ack,_=r.receive(Packet(HELLO,2,0,0,TEST),0)
        self.assertEqual(ack.detail,BAD_MODE)
        r.receive(Packet(HELLO,3,0),1)
        ack,deliver=r.receive(Packet(EVENT,3,1,1,TEST),2)
        self.assertEqual(ack.detail,BAD_MODE);self.assertFalse(deliver)
    def test_invalid_event_and_ack_storm_prevention(self):
        r=Receiver();r.receive(Packet(HELLO,2,0),0)
        ack,deliver=r.receive(Packet(EVENT,2,1,99),1)
        self.assertEqual(ack.detail,BAD_EVENT);self.assertFalse(deliver)
        self.assertEqual(r.receive(Packet(ACK,2,1,1),2),(None,False))


class SenderTests(unittest.TestCase):
    def test_normal_all_five_events(self):
        link,wire=setup_link();ready(link,wire)
        for index,key in enumerate(EVENTS):
            now=30+index*100
            step(link,wire,now)
            self.assertTrue(link.submit(action(now,key),now))
            step(link,wire,now+10);step(link,wire,now+20)
        self.assertEqual([p.code for p in wire.delivered],list(EVENTS.values()))
        self.assertEqual(link.counts['remote_accepted'],5)
    def test_lost_ack_retries_same_id_executes_once(self):
        link,wire=setup_link();ready(link,wire)
        wire.drop_ack=True;link.submit(action(30),30);step(link,wire,40)
        wire.drop_ack=False;step(link,wire,220);step(link,wire,230)
        events=[p for p in wire.sent if p.kind==EVENT]
        self.assertEqual(len(events),2);self.assertEqual(events[0],events[1])
        self.assertEqual(len(wire.delivered),1)
        self.assertEqual(link.counts['remote_accepted'],1)
    def test_ack_timeout_unknown_no_replay_after_reconnect(self):
        link,wire=setup_link();ready(link,wire)
        wire.drop_ack=True;link.submit(action(30),30)
        for now in range(40,641,50):step(link,wire,now)
        self.assertEqual(link.counts['delivery_unknown'],1)
        self.assertEqual(len([p for p in wire.sent if p.kind==EVENT]),3)
        wire.drop_ack=False
        for now in range(690,1200,50):step(link,wire,now)
        self.assertEqual(len(wire.delivered),1)
        self.assertTrue(link.ready)
    def test_wrong_or_stale_ack_does_not_confirm(self):
        link,wire=setup_link();ready(link,wire)
        wire.drop_ack=True;link.submit(action(30),30);step(link,wire,40)
        for index,p in enumerate((Packet(ACK,99,1,1),Packet(ACK,100,2,1),Packet(ACK,100,1,2))):
            wire.rx.extend(p.encode());step(link,wire,50+index*10)
        self.assertEqual(link.counts['remote_accepted'],0)
    def test_cancel_before_send_and_after_send_stop_retries(self):
        for sent in (False,True):
            link,wire=setup_link();ready(link,wire)
            wire.drop_ack=True;link.submit(action(30),30)
            if sent:step(link,wire,40)
            link.abort(50,'cancel');wire.drop_ack=False
            for now in range(60,601,50):step(link,wire,now)
            self.assertEqual(len(wire.delivered),int(sent))
            self.assertEqual(len([p for p in wire.sent if p.kind==EVENT]),int(sent))
    def test_disconnected_or_busy_actions_not_replayed(self):
        link,wire=setup_link()
        self.assertFalse(link.submit(action(0),0))
        ready(link,wire,10);self.assertEqual(wire.delivered,[])
        self.assertTrue(link.submit(action(40),40))
        self.assertFalse(link.submit(action(41,'rest'),41))
        step(link,wire,50);step(link,wire,60)
        self.assertEqual([p.code for p in wire.delivered],[1])
    def test_stale_duplicate_future_replay_and_simulated_default_blocked(self):
        link,wire=setup_link(simulation=False);ready(link,wire)
        for a,now in ((action(30),30),(action(30,source='replay'),30),
                      (action(31,source='live'),30),(action(0,source='live'),200)):
            self.assertFalse(link.submit(a,now))
        a=action(30,source='live');self.assertTrue(link.submit(a,30))
        self.assertFalse(link.submit(a,30))
    def test_service_stall_aborts_instead_of_retrying(self):
        link,wire=setup_link();ready(link,wire)
        wire.drop_ack=True;link.submit(action(30),30);step(link,wire,40)
        step(link,wire,400)
        self.assertFalse(link.ready);self.assertIsNone(link.pending)
        self.assertEqual(len(wire.delivered),1)
    def test_heartbeat_can_defer_one_fresh_action(self):
        link,wire=setup_link();ready(link,wire)
        for now in (200,400,520):step(link,wire,now)
        self.assertTrue(link.submit(action(520),520))
        for now in (530,540,550,560):step(link,wire,now)
        self.assertEqual([p.code for p in wire.delivered],[1])
    def test_deferred_action_expires_while_ping_ack_missing(self):
        link,wire=setup_link();ready(link,wire)
        for now in (200,400,520):step(link,wire,now)
        wire.drop_ack=True;step(link,wire,530)
        link.submit(action(540),540)
        for now in (550,630,710):step(link,wire,now)
        wire.drop_ack=False
        for now in (720,730,740):step(link,wire,now)
        self.assertEqual(wire.delivered,[])
        self.assertGreater(link.counts['not_sent'],0)
    def test_finite_clock_and_sequence_exhaustion(self):
        link,wire=setup_link();ready(link,wire)
        for now in (float('nan'),-1,19):
            with self.assertRaises(ValueError):link.service(now)
        link,wire=setup_link();ready(link,wire);link.sequence=0xffffffff
        self.assertFalse(link.submit(action(30),30))
    def test_unsent_event_expires_instead_of_delayed_send(self):
        link,wire=setup_link();ready(link,wire)
        wire.busy=True;link.submit(action(30),30)
        for now in (40,100,181):step(link,wire,now)
        wire.busy=False;step(link,wire,200)
        self.assertEqual(wire.delivered,[])
        self.assertEqual(link.counts['not_sent'],1)

    def test_receiver_reboot_rejects_pending_event(self):
        link,wire=setup_link();ready(link,wire);wire.receiver.disconnect()
        link.submit(action(30),30);step(link,wire,40);step(link,wire,50)
        self.assertFalse(link.ready);self.assertEqual(wire.delivered,[])
    def test_transport_busy_does_not_spin(self):
        link,wire=setup_link();wire.busy=True
        for now in range(0,701,50):step(link,wire,now)
        self.assertEqual(wire.sent,[]);self.assertEqual(link.counts['timeout'],1)
    def test_full_dwell_scenario_delivers_only_selected_actions(self):
        link,wire=setup_link();scenario=InteractionTest()
        for now in range(0,23000,25):
            wire.time=now;scenario.step(now)
            service_controller(link,scenario.controller,now,scenario.last_action)
            if scenario.done:break
        self.assertTrue(scenario.done)
        self.assertEqual([p.code for p in wire.delivered],[1,1,2,4,5,3])
        self.assertEqual(link.counts['remote_accepted'],6)
    def test_invalid_input_pause_calibration_clear_prevent_send(self):
        for reason in ('lost','closed','stale','cancelled','uncalibrated','context_mismatch'):
            link,wire=setup_link();ready(link,wire)
            c=DwellController(Context('test','geom','simulated'),'test')
            c.reason=reason
            wire.time=30;service_controller(link,c,30,action(30))
            self.assertIsNone(link.pending);self.assertEqual(wire.delivered,[])


class FifoMMIO:
    def __init__(self):
        self.rx=deque();self.tx=[];self.flags=0;self.force_busy=False;self.reads=0
    def read(self,offset):
        self.reads+=1
        if offset==8:
            value=(1 if self.rx else 0)|(0 if self.force_busy or self.tx else 4)|(8 if len(self.tx)>=16 else 0)|self.flags
            self.flags=0;return value
        if offset==0:
            if not self.rx:raise AssertionError('empty FIFO read')
            return self.rx.popleft()
        raise AssertionError(offset)
    def write(self,offset,value):
        if offset==12:
            self.rx.clear();self.tx.clear();return
        if offset==4:
            if len(self.tx)>=16:raise AssertionError('full FIFO write')
            self.tx.append(value);return
        raise AssertionError(offset)


class DriverTests(unittest.TestCase):
    def test_fifo_bounds_and_busy_are_nonblocking(self):
        m=FifoMMIO();u=AxiUartLite(m);data=Packet(HELLO,1,0).encode()
        self.assertEqual(u.read(),b'');self.assertTrue(u.try_write(data))
        self.assertEqual(bytes(m.tx),data);self.assertFalse(u.try_write(data))
        m.rx.extend(range(20));self.assertEqual(u.read(),bytes(range(16)))
        self.assertEqual(u.read(),bytes(range(16,20)))
    def test_errors_read_to_clear_detected_and_reset(self):
        for flag in (0x20,0x40,0x80):
            m=FifoMMIO();u=AxiUartLite(m);m.rx.extend([1,2]);m.flags=flag
            with self.assertRaises(UartError):u.read()
            self.assertEqual(list(m.rx),[])
            m.flags=flag
            with self.assertRaises(UartError):u.try_write(bytes(16))
    def test_frame_size_validation_before_mmio(self):
        m=FifoMMIO();u=AxiUartLite(m);count=m.reads
        with self.assertRaises(ValueError):u.try_write(b'bad')
        self.assertEqual(count,m.reads)
    def test_uart_fault_aborts_link(self):
        m=FifoMMIO();link=EventLink(AxiUartLite(m));m.flags=0x20
        link.service(0)
        self.assertFalse(link.ready);self.assertEqual(link.counts['uart_error'],1)


class IntegratedControlTests(unittest.TestCase):
    def run_case(self, button_raw=0, fail=False, loss=False):
        import test_auxiliary as aux
        from unittest.mock import patch
        from pathlib import Path
        from eye_tracker.auxiliary import run_control_test
        from eye_tracker.audio import PhraseBank
        helper=aux.ListeningTests()
        clock,m,now,sleep=helper.setup_clock(lambda t:button_raw if 1.2<=t<1.45 else 0)
        link,wire=setup_link();write=wire.try_write
        def timed_write(raw):
            wire.time=clock[0]*1000
            wire.drop_ack=loss and Packet.decode(raw).kind==EVENT
            return write(raw)
        wire.try_write=timed_write
        with patch('eye_tracker.auxiliary.Codec',helper.CodecStub),helper.folder() as folder:
            if fail:
                with self.assertRaisesRegex(TimeoutError,'stalled'):
                    run_control_test(m,helper.Session(26),helper.Renderer(),Path(folder),5,now,sleep,
                                     bank=PhraseBank(),event_link=link)
                self.assertEqual(link.state,'disabled');self.assertIsNone(link.pending)
                return
            result=run_control_test(m,helper.Session(),helper.Renderer(),Path(folder),4 if button_raw else 15,
                                    now,sleep,bank=PhraseBank(),event_link=link)
        self.assertTrue(result['completed']);self.assertEqual(link.state,'disabled')
        return result,link,wire
    def test_speech_and_event_share_same_dwell_action(self):
        result,link,wire=self.run_case()
        self.assertEqual([a['key'] for a in result['actions']],['water','rest','help'])
        self.assertEqual([p.code for p in wire.delivered],[1,2,3])
        self.assertEqual(link.counts['remote_accepted'],3)
    def test_all_helpers_stop_retry_without_sending_another_action(self):
        for raw in (1,2,4,8):
            result,link,wire=self.run_case(raw,loss=True)
            command_time=result['commands'][0]['time_ms']
            self.assertEqual([p.code for p in wire.delivered],[1])
            self.assertFalse(any(e['event']=='sent' and e['kind']==EVENT and e['time_ms']>=command_time
                                 for e in link.trace))
    def test_display_failure_aborts_communication_too(self):
        self.run_case(fail=True,loss=True)


class BusyAckTests(unittest.TestCase):
    def test_unavailable_teammate_interface_is_not_accepted(self):
        from eye_tracker.event_protocol import BUSY
        link,wire=setup_link();ready(link,wire)
        link.submit(action(30),30)
        wire.drop_ack=True
        step(link,wire,40)
        pending=link.pending['packet']
        # Inject the actual firmware's rejection status, not an acceptance ACK.
        wire.read=lambda: Packet(ACK,pending.session,pending.sequence,pending.code,BUSY).encode()
        link.service(50)
        self.assertFalse(link.ready)
        self.assertEqual(link.counts['rejected'],1)
        self.assertEqual(link.counts['remote_accepted'],0)
        self.assertIsNone(link.pending)
