"""Optional compact native CPU backend; no download, runtime launch or hardware."""
import ctypes,hashlib,json,math
from pathlib import Path
import numpy as np
from .neural import LABELS,NeuralConsensusClassifier
from .appearance import CoarseAppearanceModel

class NativeNeuralModel:
    def __init__(self,model_path,metadata_path,library_path):
        self.meta=json.loads(Path(metadata_path).read_text(encoding='utf-8'))
        if self.meta.get('schema')!='eye_native_q8_v2':raise ValueError('native_schema')
        if hashlib.sha256(Path(model_path).read_bytes()).hexdigest()!=self.meta['compact_sha256']:raise ValueError('native_model_hash')
        self.sha256=self.meta['source_model_sha256'];self.lib=ctypes.CDLL(str(Path(library_path).resolve()))
        self.lib.nn_load.argtypes=[ctypes.c_char_p];self.lib.nn_load.restype=ctypes.c_void_p
        self.lib.nn_free.argtypes=[ctypes.c_void_p];self.lib.nn_free.restype=None
        self.lib.nn_forward.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_float),ctypes.POINTER(ctypes.c_double)]
        self.lib.nn_forward.restype=ctypes.c_int;self.lib.nn_backend.restype=ctypes.c_char_p
        self.handle=self.lib.nn_load(str(Path(model_path).resolve()).encode())
        if not self.handle:raise ValueError('native_model_load_failed')
        self.backend=self.lib.nn_backend().decode()
    def close(self):
        if self.handle:self.lib.nn_free(self.handle);self.handle=None
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
    def logits(self,feature):
        if not self.handle:raise ValueError('native_model_closed')
        f=np.ascontiguousarray(CoarseAppearanceModel.vector(feature),dtype=np.float32)
        output=(ctypes.c_double*5)()
        code=self.lib.nn_forward(self.handle,f.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),output)
        if code:raise ValueError('native_inference_error:'+str(code))
        return np.asarray(output).copy()
    def predict(self,feature,integer=True,accelerator=None):
        if not integer or accelerator is not None:raise ValueError('native_backend_is_cpu_int8')
        logits=self.logits(feature);p=np.exp(logits-logits.max());p/=p.sum();order=np.argsort(p)
        return dict(target=LABELS[int(order[-1])],confidence=float(p[order[-1]]),margin=float(p[order[-1]]-p[order[-2]]),probabilities=p.tolist())
    def guarded(self,feature,legacy_target,accelerator=None):
        p=self.predict(feature,accelerator=accelerator)
        ok=legacy_target is not None and p['target']==legacy_target and p['confidence']>=.8 and p['margin']>=.5
        return dict(p,candidate=p['target'] if ok else None,actions_enabled=False,reason='agreement' if ok else 'legacy_or_neural_rejected')

def attach_native(engine,model):
    if engine.baseline.samples or isinstance(engine.model,NeuralConsensusClassifier):raise ValueError('attach_before_reference_once')
    if model.meta['appearance_sha256']!=engine.pack_sha256:raise ValueError('native_geometry_binding')
    engine.model=NeuralConsensusClassifier(engine.model,model)
