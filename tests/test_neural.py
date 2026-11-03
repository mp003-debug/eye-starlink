"""Functional neural safety/quantization/driver contract regression, no board."""
import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from eye_tracker.neural import NeuralModel,NeuralConsensusClassifier,LABELS,DIMS,quantize,attach_neural
from eye_tracker.neural_accel import NeuralAccelerator,packed_weights

class ArrayMMIO:
    """Independent register emulator for PS driver tests (RTL separately simulated)."""
    def __init__(self):
        self.reg={0:0x4e4e3332,4:0x10000,0xc:0,0x1c:0};self.w=bytearray();self.x=bytearray();self.hang=False
    def write(self,a,v):
        if a>=0x10000:
            pos=a-0x10000
            if pos==0:self.w=bytearray()
            if pos!=len(self.w):raise ValueError('not sequential')
            self.w.extend(v.to_bytes(4,'little'));self.reg[0x1c]=len(self.w)//32
        elif 0x1000<=a<0x1800:
            if a==0x1000:self.x=bytearray()
            self.x.extend(v.to_bytes(4,'little'))
        elif a==8:
            if v==4:self.w=bytearray();self.reg[0x1c]=0;self.reg[0xc]=0
            elif v==2:self.reg[0xc]=4
            elif v==1:
                if self.hang:self.reg[0xc]=1;return
                n=self.reg[0x10];start=self.reg[0x14];out=self.reg[0x18]
                x=np.frombuffer(self.x,np.int8)[:n].astype(np.int32)
                w=np.frombuffer(self.w,np.int8).reshape(-1,32)[start:start+n].astype(np.int32)
                for i,r in enumerate(x@w):self.reg[0x2000+4*i]=int(r)&0xffffffff
                self.reg[0xc]=2
        else:self.reg[a]=v
    def read(self,a):return self.reg.get(a,0)

class NeuralTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.path=Path(cls.temp.name)/'model.npz'
        rng=np.random.default_rng(7);a={}
        for i in range(3):
            q=rng.integers(-12,13,(DIMS[i],DIMS[i+1]),dtype=np.int8)
            a.update({f'w{i}':q.astype(np.float32)*.01,f'qw{i}':q,f'b{i}':np.zeros(DIMS[i+1],np.float32)})
        a.update(metadata=np.array(json.dumps(dict(schema='eye_mlp_int8_v1',labels=list(LABELS),actions_enabled=False,appearance_sha256='appearance'))),
                 weight_scales=np.full(3,.01),activation_scales=np.array([1/127,.1,.2]))
        cls.arrays=a;np.savez(cls.path,**a);cls.model=NeuralModel(cls.path)
        cls.feature=np.linspace(0,1,1152,dtype=np.float32)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_hash_binding(self):
        with self.assertRaisesRegex(ValueError,'hash_mismatch'):NeuralModel(self.path,'0'*64)
    def test_symmetric_rounding_and_saturation(self):
        np.testing.assert_array_equal(quantize([-128.9,-1.5,-.5,.5,1.5,128.9],1),[-127,-2,0,0,2,127])
    def test_nonfinite_scale_and_input_rejected(self):
        for value,scale in [([0],0),([0],float('nan')),([float('inf')],1)]:
            with self.assertRaises(ValueError):quantize(value,scale)
    def test_invalid_feature_rejected(self):
        for f in [np.zeros(2),np.full(1152,np.nan),np.full(1152,2)]:
            with self.assertRaises(ValueError):self.model.predict(f)
    def test_parameters_immutable(self):
        with self.assertRaises(ValueError):self.model.qweights[0][0,0]=1
    def test_declared_schema_required(self):
        a=dict(self.arrays);a['metadata']=np.array(json.dumps(dict(schema='eye_mlp_int8_v1',labels=list(LABELS),actions_enabled=True)))
        p=Path(self.temp.name)/'invalid.npz';np.savez(p,**a)
        with self.assertRaises(ValueError):NeuralModel(p)
    def test_parameter_shape_rejected(self):
        a=dict(self.arrays);a['qw0']=np.zeros((2,2),np.int8)
        p=Path(self.temp.name)/'shape.npz';np.savez(p,**a)
        with self.assertRaises(ValueError):NeuralModel(p)
    def test_probabilities_normalized(self):
        p=self.model.predict(self.feature);self.assertAlmostEqual(sum(p['probabilities']),1)
    def test_guard_never_bypasses_legacy(self):
        self.assertIsNone(self.model.guarded(self.feature,None)['candidate'])
    def test_legacy_rejection_skips_neural(self):
        legacy=SimpleNamespace(geometry_id='g',propose=lambda *_:dict(target=None,reason='invalid'))
        c=NeuralConsensusClassifier(legacy,None);self.assertIsNone(c.propose(self.feature,'g')['target'])
    def test_consensus_disagreement_rejects(self):
        legacy=SimpleNamespace(geometry_id='g',propose=lambda *_:dict(target='help'))
        nn=SimpleNamespace(guarded=lambda *_:dict(candidate=None))
        self.assertIsNone(NeuralConsensusClassifier(legacy,nn).propose(self.feature,'g')['target'])
    def test_hardware_error_rejects_without_fallback(self):
        def fail(*_):raise TimeoutError('test')
        legacy=SimpleNamespace(geometry_id='g',propose=lambda *_:dict(target='help'))
        c=NeuralConsensusClassifier(legacy,SimpleNamespace(guarded=fail))
        self.assertEqual(c.propose(self.feature,'g')['reason'],'neural_failure')
    def test_model_memory_layout(self):
        weights,blocks=packed_weights(self.model)
        self.assertEqual(weights.shape,(2400,32));self.assertEqual(blocks[2],[(2368,32,5)])
        np.testing.assert_array_equal(weights[:1152],self.model.qweights[0][:,:32])
        self.assertTrue((weights[2368:,5:]==0).all())
    def test_ps_driver_matches_integer_network(self):
        mmio=ArrayMMIO();driver=NeuralAccelerator(mmio,self.model);driver.load()
        np.testing.assert_allclose(self.model.logits(self.feature,accelerator=driver),self.model.logits(self.feature),rtol=0,atol=0)
    def test_driver_requires_upload(self):
        driver=NeuralAccelerator(ArrayMMIO(),self.model)
        with self.assertRaises(RuntimeError):driver.dense(0,np.zeros(1152,np.int8))
    def test_driver_rejects_wrong_identity(self):
        mmio=ArrayMMIO();mmio.reg[0]=0
        with self.assertRaises(ValueError):NeuralAccelerator(mmio,self.model)
    def test_driver_rejects_wrong_layer_and_dtype(self):
        driver=NeuralAccelerator(ArrayMMIO(),self.model)
        for layer,a in [(3,np.zeros(32,np.int8)),(0,np.zeros(1152,np.float32))]:
            with self.assertRaises(ValueError):driver.dense(layer,a)
    def test_timeout_aborts_and_requires_reload(self):
        ticks=iter([0,.1,.2,.3,.4,.5]);mmio=ArrayMMIO()
        driver=NeuralAccelerator(mmio,self.model,clock=lambda:next(ticks));driver.load();mmio.hang=True
        with self.assertRaises(TimeoutError):driver.dense(0,np.zeros(1152,np.int8))
        self.assertFalse(driver.loaded);self.assertEqual(mmio.reg[0xc],4)
    def test_busy_upload_refused(self):
        mmio=ArrayMMIO();mmio.reg[0xc]=1;driver=NeuralAccelerator(mmio,self.model)
        with self.assertRaises(RuntimeError):driver.load()
    def test_hardware_reset_detected(self):
        mmio=ArrayMMIO();driver=NeuralAccelerator(mmio,self.model);driver.load();mmio.reg[0x1c]=0
        with self.assertRaises(RuntimeError):driver.dense(0,np.zeros(1152,np.int8))
        self.assertFalse(driver.loaded)
    def test_attach_bound_to_appearance_before_reference(self):
        e=SimpleNamespace(pack_sha256='appearance',baseline=SimpleNamespace(samples=[]),model=SimpleNamespace(geometry_id='g'))
        attach_neural(e,self.path,self.model.sha256);self.assertIsInstance(e.model,NeuralConsensusClassifier)
        with self.assertRaises(ValueError):attach_neural(e,self.path,self.model.sha256)
    def test_attach_wrong_geometry_refused(self):
        e=SimpleNamespace(pack_sha256='wrong',baseline=SimpleNamespace(samples=[]),model=None)
        with self.assertRaises(ValueError):attach_neural(e,self.path,self.model.sha256)
    def test_attach_after_reference_refused(self):
        e=SimpleNamespace(baseline=SimpleNamespace(samples=[1]),model=None)
        with self.assertRaises(ValueError):attach_neural(e,self.path,self.model.sha256)

if __name__=='__main__':unittest.main()
