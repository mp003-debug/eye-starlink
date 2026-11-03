import unittest
from eye_tracker.sensor import MT9V034, OpenDrainI2C, SensorError, Nack

class Registers:
    def __init__(self):
        self.regs={r:0 for r in MT9V034.OBSERVED}
        self.regs.update({0:0x1324,3:480,4:752,5:94,6:45,0xFE:0xBEEF,0xAF:0x0303,0x0B:480,0xD2:480,0x35:16,0x36:16})
        self.addresses={0x48};self.writes=[];self.ignore=None;self.fail_once=None
    def read16(self,a,r):
        if a not in self.addresses:raise Nack('absent')
        return self.regs[r]
    def write16(self,a,r,v):
        self.writes.append((r,v))
        if self.fail_once==r:self.fail_once=None;raise SensorError('wire fault')
        if self.ignore!=r:self.regs[r]=v

class SensorTests(unittest.TestCase):
    def setUp(self):self.bus=Registers();self.sensor=MT9V034.probe(self.bus)
    def test_only_identity_probes_do_not_write_registers(self):
        self.assertEqual(self.sensor.address,0x48);self.assertEqual(self.bus.writes,[])
    def test_probe_rejects_multiple_matching_devices(self):
        self.bus.addresses.add(0x4C)
        with self.assertRaisesRegex(SensorError,'expected one'):MT9V034.probe(self.bus)
    def test_probe_rejects_unexpected_identity(self):
        self.bus.regs[0]=0x1313
        with self.assertRaisesRegex(SensorError,'unexpected identity'):MT9V034.probe(self.bus)
    def test_manual_both_contexts_and_exact_restore(self):
        before=dict(self.bus.regs);self.bus.regs[0xAF]|=0x4000;before=dict(self.bus.regs)
        result=self.sensor.apply_manual(120,24)
        for reg in (0x0B,0xD2):self.assertEqual(self.bus.regs[reg],120)
        for reg in (0x35,0x36):self.assertEqual(self.bus.regs[reg],24)
        self.assertEqual(self.bus.regs[0xAF],0x4000)
        self.assertEqual(result['gain_factor'],1.5)
        self.assertTrue(self.sensor.restore());self.assertEqual(self.bus.regs,before)
        self.assertEqual(self.bus.writes[-1],(0xAF,before[0xAF]))
    def test_partial_write_failure_can_restore(self):
        before=dict(self.bus.regs);self.bus.fail_once=0xD2
        with self.assertRaisesRegex(SensorError,'wire fault'):self.sensor.apply_manual(120,16)
        self.assertTrue(self.sensor.restore());self.assertEqual(self.bus.regs,before)
    def test_readback_failure_not_reported_as_success(self):
        self.bus.ignore=0x0B
        with self.assertRaisesRegex(SensorError,'readback'):self.sensor.apply_manual(120,16)
        self.bus.ignore=None;self.assertTrue(self.sensor.restore())
    def test_restore_failure_preserves_pending_original(self):
        self.sensor.apply_manual(120,16);self.bus.ignore=0x0B
        with self.assertRaisesRegex(SensorError,'restore incomplete'):self.sensor.restore()
        self.assertIsNotNone(self.sensor.original)
        self.bus.ignore=None;self.assertTrue(self.sensor.restore())
    def test_lock_and_binning_are_refused_without_writes(self):
        for reg,value in ((0xFE,0xDEAD),(0x0D,1),(0x0E,4),(3,240)):
            bus=Registers();bus.regs[reg]=value;s=MT9V034.probe(bus)
            with self.assertRaises(SensorError):s.apply_manual(120,16)
            self.assertEqual(bus.writes,[])
    def test_inactive_context_defaults_and_reserved_gain_bits_preserved(self):
        self.bus.regs[0x0F]=0x1100;self.bus.regs[0x36]=0x8010
        before=dict(self.bus.regs)
        self.sensor.apply_manual(120,32)
        self.assertEqual(self.bus.regs[0x0F],0x1000)
        self.assertEqual(self.bus.regs[0x36],0x8020)
        self.assertTrue(self.sensor.restore());self.assertEqual(self.bus.regs,before)
    def test_out_of_range_is_refused_before_access(self):
        for rows,gain in ((0,16),(481,16),(100,15),(100,33),(True,16)):
            with self.assertRaises(ValueError):self.sensor.apply_manual(rows,gain)
        self.assertEqual(self.bus.writes,[])

class Gpio:
    def __init__(self):self.control=0;self.stuck=0;self.t=0;self.writes=[]
    def read(self,off):return self.control if off==0 else (((~(self.control>>2))&3&~self.stuck)<<5)
    def write(self,off,value):self.control=value;self.writes.append(value)
    def sleep(self,t):self.t+=t

class BusTests(unittest.TestCase):
    def setUp(self):
        self.g=Gpio();self.bus=OpenDrainI2C(self.g,now=lambda:self.g.t,sleep=self.g.sleep)
    def test_nack_releases_wires(self):
        with self.assertRaises(Nack):self.bus.read16(0x48,0)
        self.assertEqual(self.g.control,0);self.assertEqual(self.bus.lines(),3)
    def test_clock_stretch_timeout_is_bounded_and_releases(self):
        self.g.stuck=2
        with self.assertRaisesRegex(SensorError,'SCL'):self.bus.read16(0x48,0)
        self.assertLess(self.g.t,.05);self.assertEqual(self.g.control,0)
    def test_busy_data_line_refuses_blind_bus_clear(self):
        self.g.stuck=1
        with self.assertRaisesRegex(SensorError,'SDA'):self.bus.read16(0x48,0)
        self.assertLess(len(self.g.writes),12);self.assertEqual(self.g.control,0)
    def test_video_active_does_not_get_overwritten(self):
        self.g.control=2
        with self.assertRaisesRegex(SensorError,'stopped'):OpenDrainI2C(self.g)
        self.assertEqual(self.g.control,2)
    def test_8bit_wire_address_mistake_rejected(self):
        with self.assertRaises(ValueError):self.bus.read16(0x90,0)
        self.assertEqual(self.g.writes,[])
    def test_read_uses_repeated_start_big_endian_and_final_nack(self):
        trace=[];reads=iter((0x13,0x24))
        self.bus._start=lambda repeated=False:trace.append(('start',repeated))
        self.bus._write_byte=lambda b:trace.append(('write',b))
        def rb(ack):trace.append(('ack',ack));return next(reads)
        self.bus._read_byte=rb;self.bus._stop=lambda:trace.append(('stop',))
        self.assertEqual(self.bus.read16(0x48,0),0x1324)
        self.assertEqual(trace,[('start',False),('write',0x90),('write',0),('start',True),('write',0x91),('ack',True),('ack',False),('stop',)])
    def test_register_write_sends_high_byte_first(self):
        values=[];self.bus._start=lambda:None;self.bus._stop=lambda:None
        self.bus._write_byte=values.append
        self.bus.write16(0x48,0x0B,0x0123)
        self.assertEqual(values,[0x90,0x0B,0x01,0x23]);self.assertEqual(self.g.control,0)
