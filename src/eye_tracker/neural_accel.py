"""Explicit opt-in NN32 AXI driver. Construction never opens a board or MMIO."""
import time
import numpy as np
from .neural import DIMS

BASE_ADDRESS=0x43C40000
ADDRESS_RANGE=0x40000

def packed_weights(model):
    rows=[]; blocks=[]; base=0
    for layer,w in enumerate(model.qweights):
        layer_blocks=[]
        for first in range(0,w.shape[1],32):
            count=min(32,w.shape[1]-first)
            block=np.zeros((w.shape[0],32),np.int8)
            block[:,:count]=w[:,first:first+count]
            rows.append(block);layer_blocks.append((base,w.shape[0],count));base+=w.shape[0]
        blocks.append(layer_blocks)
    data=np.concatenate(rows)
    if data.shape[0]>4096:raise ValueError('weight_capacity_exceeded')
    return data,blocks

class NeuralAccelerator:
    """Single-owner driver, bounded polls; timeout invalidates residency.

    Caller must provide an exclusively owned MMIO object implementing read/write.
    There is deliberately no automatic Overlay download or default-profile edit.
    """
    def __init__(self,mmio,model,timeout=.25,clock=time.monotonic):
        if not np.isfinite(timeout) or not 0<timeout<=1:raise ValueError('bounded_timeout_required')
        self.mmio=mmio;self.model=model;self.timeout=timeout;self.clock=clock
        self.loaded=False;self.active=False
        self.weights,self.blocks=packed_weights(model)
        if mmio.read(0)!=0x4e4e3332 or mmio.read(4)!=0x10000:raise ValueError('accelerator_identity_mismatch')

    def load(self):
        if self.active or self.mmio.read(0xc)&1:raise RuntimeError('accelerator_busy')
        self.loaded=False;self.mmio.write(8,4)
        for i,w in enumerate(np.frombuffer(self.weights.tobytes(),dtype='<u4')):
            self.mmio.write(0x10000+4*i,int(w))
        if self.mmio.read(0x1c)!=len(self.weights):raise RuntimeError('incomplete_weight_upload')
        self.loaded=True

    def dense(self,layer,activation):
        a=np.asarray(activation)
        if type(layer) is not int or not 0<=layer<3 or a.dtype!=np.int8 or a.shape!=(DIMS[layer],):
            raise ValueError('invalid_layer_or_activation')
        if not self.loaded or self.active:raise RuntimeError('weights_not_loaded_or_busy')
        self.active=True
        try:
            if self.mmio.read(0xc)&5 or self.mmio.read(0x1c)!=len(self.weights):raise RuntimeError('accelerator_not_ready')
            for i,w in enumerate(np.frombuffer(a.tobytes(),dtype='<u4')):
                self.mmio.write(0x1000+4*i,int(w))
            results=[]
            for base,length,count in self.blocks[layer]:
                self.mmio.write(0x10,length);self.mmio.write(0x14,base);self.mmio.write(0x18,count)
                self.mmio.write(8,1);deadline=self.clock()+self.timeout
                while True:
                    status=self.mmio.read(0xc)
                    if status&4:raise RuntimeError('accelerator_fault')
                    if status&2 and not status&1:break
                    if self.clock()>=deadline:raise TimeoutError('accelerator_timeout')
                results.extend(self.mmio.read(0x2000+4*j) for j in range(count))
            return np.asarray(results,dtype=np.uint32).view(np.int32)
        except Exception:
            self.loaded=False
            self.mmio.write(8,2)
            raise
        finally:self.active=False
