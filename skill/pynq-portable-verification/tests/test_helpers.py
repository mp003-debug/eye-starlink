from pathlib import Path
import copy,hashlib,json,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from overlay_contract import check,snapshot
from dma_guard import transfer,DmaFailure
from verify_results import compare

class ContractTests(unittest.TestCase):
    def setUp(self):
        self.c={'schema':1,'platform':'fixture-zynq','ips':{'vector':{'vlnv':'team:ip:add:1.0','base':'0x40000000','range':4096,'registers':{'ctrl':0,'length':16}}},'clocks_hz':{'pl0':100000000}}
        self.o=copy.deepcopy(self.c)
    def test_matching_contract(self):self.assertTrue(check(self.c,self.o)['passed'])
    def test_relocated_second_platform(self):
        c=copy.deepcopy(self.c);c['platform']='fixture-zynqmp';c['ips']['vector']['base']='0xa0000000'
        c['clocks_hz']['pl0']=150000000
        self.assertTrue(check(c,c)['passed']);self.assertFalse(check(c,self.o)['passed'])
    def test_missing_ip(self):self.o['ips']={};self.assertFalse(check(self.c,self.o)['passed'])
    def test_wrong_register(self):self.o['ips']['vector']['registers']['length']=20;self.assertFalse(check(self.c,self.o)['passed'])
    def test_wrong_vlnv(self):self.o['ips']['vector']['vlnv']='wrong';self.assertFalse(check(self.c,self.o)['passed'])
    def test_wrong_clock(self):self.o['clocks_hz']['pl0']=50000000;self.assertFalse(check(self.c,self.o)['passed'])
    def test_overlap_and_out_of_range_register(self):
        self.c['ips']['other']=copy.deepcopy(self.c['ips']['vector'])
        self.c['ips']['other']['registers']['bad']=4096
        self.assertFalse(check(self.c,self.c)['passed'])
    def test_pair_hash_and_missing_directory(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);self.c['artifacts']={}
            for ext in ('bit','hwh'):
                raw=('fixture-not-hardware-'+ext).encode();(p/f'example.{ext}').write_bytes(raw)
                self.c['artifacts'][ext]={'file':f'example.{ext}','sha256':hashlib.sha256(raw).hexdigest()}
            self.assertFalse(check(self.c,self.o)['passed'])
            self.assertTrue(check(self.c,self.o,p)['passed'])
            (p/'example.bit').write_bytes(b'corrupt');self.assertFalse(check(self.c,self.o,p)['passed'])
    def test_path_escape_and_basename_mismatch(self):
        self.c['artifacts']={'bit':{'file':'../a.bit','sha256':'0'*64},'hwh':{'file':'b.hwh','sha256':'0'*64}}
        with tempfile.TemporaryDirectory() as d:
            result=check(self.c,self.o,d);self.assertFalse(result['passed'])
            self.assertTrue(any('escapes' in x for x in result['errors']))
    def test_metadata_snapshot_does_not_read_registers(self):
        class Overlay:ip_dict={'unit':{'type':'x:y:z:1','phys_addr':4096,'addr_range':256,'registers':{'x':{'address_offset':8}}}}
        got=snapshot(Overlay(),'other');self.assertEqual(got['ips']['unit']['registers']['x'],8)

class Buffer:
    def __init__(self,name,address,events):self.name=name;self.device_address=address;self.nbytes=64;self.events=events
    def flush(self):self.events.append(self.name+':flush')
    def invalidate(self):self.events.append(self.name+':invalidate')
class Channel:
    running=True
    def __init__(self,name,events,mode):self.name=name;self.events=events;self.mode=mode;self.active=False;self.reads=0
    @property
    def idle(self):
        if not self.active:return True
        self.reads+=1
        return self.mode=='ok' and self.reads>=3
    @property
    def error(self):return self.active and self.mode=='error'
    def transfer(self,buf,nbytes):
        self.events.append(self.name+':start');self.active=True
        if self.mode=='raise':raise RuntimeError('register write failed')
class Dma:
    def __init__(self,events,rx='ok',tx='ok'):self.recvchannel=Channel('rx',events,rx);self.sendchannel=Channel('tx',events,tx)
class Clock:
    def __init__(self):self.t=0
    def __call__(self):return self.t
    def sleep(self,n):self.t+=n

class DmaTests(unittest.TestCase):
    def setUp(self):
        self.events=[];self.send=Buffer('send',4096,self.events);self.recv=Buffer('recv',8192,self.events);self.clock=Clock()
        self.kw=dict(send_bytes=64,receive_bytes=64,word_bytes=4,max_bytes=1024,timeout_s=.01,clock=self.clock,sleep=self.clock.sleep)
    def run_transfer(self,dma,**kw):return transfer(dma,self.send,self.recv,**dict(self.kw,**kw))
    def test_success_cache_and_order(self):
        self.assertTrue(self.run_transfer(Dma(self.events))['completed'])
        self.assertEqual(self.events,['send:flush','recv:flush','rx:start','tx:start','recv:invalidate'])
    def test_timeout_keeps_buffer_ownership(self):
        with self.assertRaises(DmaFailure) as ctx:self.run_transfer(Dma(self.events,rx='stall'))
        self.assertFalse(ctx.exception.quiescent);self.assertIs(ctx.exception.buffers[0],self.send)
        self.assertNotIn('recv:invalidate',self.events);self.assertLess(self.clock.t,.012)
    def test_error_and_successful_recovery(self):
        with self.assertRaises(DmaFailure) as ctx:self.run_transfer(Dma(self.events,rx='error'),quiesce=lambda:True)
        self.assertTrue(ctx.exception.quiescent)
    def test_recovery_failure_preserved(self):
        def fail():raise RuntimeError('reset failed')
        with self.assertRaises(DmaFailure) as ctx:self.run_transfer(Dma(self.events,rx='stall'),quiesce=fail)
        self.assertFalse(ctx.exception.quiescent);self.assertIn('reset failed',ctx.exception.recovery_error)
    def test_partial_start_failure_keeps_buffers(self):
        with self.assertRaises(DmaFailure):self.run_transfer(Dma(self.events,tx='raise'))
        self.assertNotIn('recv:invalidate',self.events)
    def test_bounds_and_alignment(self):
        for kwargs in ({'send_bytes':65},{'receive_bytes':68},{'max_bytes':32},{'timeout_s':float('nan')},{'send_bytes':0}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):self.run_transfer(Dma(self.events),**kwargs)
        self.assertEqual(self.events,[])
    def test_overlapping_buffers(self):
        self.recv.device_address=4128
        with self.assertRaises(ValueError):self.run_transfer(Dma(self.events))
    def test_inactive_channel_rejected(self):
        d=Dma(self.events);d.sendchannel.running=False
        with self.assertRaises(ValueError):self.run_transfer(d)
    def test_first_transfer_after_start(self):
        d=Dma(self.events);d.recvchannel.active=True;d.recvchannel._first_transfer=True
        self.assertTrue(self.run_transfer(d)['completed'])

class GoldenTests(unittest.TestCase):
    def test_exact_integer(self):self.assertTrue(compare({'actual':[[1,2]],'expected':[[1,2]]})['passed'])
    def test_large_integer_not_rounded(self):self.assertFalse(compare({'actual':[2**60+1],'expected':[2**60]})['passed'])
    def test_tolerance_and_p95(self):
        r=compare({'actual':[1.001],'expected':[1],'atol':.002,'latencies_ms':[1,2,3,4]})
        self.assertTrue(r['passed']);self.assertEqual(r['summary']['latency_p95_ms'],4)
    def test_shape_empty_nan_and_ragged_rejected(self):
        for a,g in (([1],[[1]]),([],[]),([float('nan')],[0]),([[1],[2,3]],[[1],[2,3]])):
            with self.subTest(actual=a):self.assertFalse(compare({'actual':a,'expected':g})['passed'])
    def test_independent_numeric_failure_is_not_hidden(self):self.assertFalse(compare({'actual':[1.1],'expected':[1],'atol':.01})['passed'])
    def test_timing_and_resources(self):
        d={'actual':[1],'expected':[1],'implementation':{'part':'fixture','tool':'fixture','stage':'routed','wns_ns':-1,'resources':{'lut':{'used':200,'available':100}}}}
        self.assertEqual(len(compare(d)['errors']),2)
    def test_negative_tolerance(self):self.assertFalse(compare({'actual':[1],'expected':[1],'atol':-1})['passed'])

if __name__=='__main__':unittest.main()
