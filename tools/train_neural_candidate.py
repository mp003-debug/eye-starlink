"""Fit a real MLP on the 50 predeclared fitting frames, never test frames."""
import os
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
from pathlib import Path
import hashlib, json, sys, time
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools/deps/opencv'), str(ROOT/'src')]
import numpy as np
from eye_tracker.appearance_diagnostic import AppearanceDiagnostic
from eye_tracker.neural import DIMS, LABELS, NeuralModel, quantize

BASE = ROOT/'build/fixed_camera_calibration_20261103'
OUT = ROOT/'build/neural_upgrade_20261103/model'

def main():
    if OUT.exists(): raise ValueError('fresh_training_output_required')
    OUT.mkdir(parents=True)
    policy = dict(seed=20261103, epochs=400, learning_rate=.001, weight_decay=.0001,
                  augmentations_per_frame=8, feature_noise_std=.015,
                  hidden_layers=list(DIMS[1:-1]), training_visits=['fit_a','fit_b'],
                  heldout_for_selection=False, checkpoint_selection='final_epoch_only')
    (OUT/'training_policy.json').write_text(json.dumps(policy,indent=2))
    start=time.monotonic(); rng=np.random.default_rng(policy['seed'])
    appearance_path=BASE/'candidate_01/model.npz'
    engine=AppearanceDiagnostic(appearance_path)
    capture=BASE/'capture_fit_01/targets'
    entries=json.loads((capture/'manifest.json').read_text())['samples_detail'][:50]
    assert len(entries)==50 and all(e['visit'] in ('fit_a','fit_b') for e in entries)
    features=[]; ys=[]
    for e in entries:
        raw=(capture/e['raw']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==e['sha256']
        f,_=engine.feature(np.frombuffer(raw,np.uint8).reshape(480,640))
        features.append(f); ys.append(LABELS.index(e['target']))
    original=np.asarray(features,np.float64)
    x=np.concatenate([original]+[np.clip(original+rng.normal(0,.015,original.shape),0,1) for _ in range(8)])*2-1
    y=np.tile(np.asarray(ys),9); n=len(y)
    weights=[rng.normal(0,np.sqrt(2/DIMS[i]),(DIMS[i],DIMS[i+1])) for i in range(3)]
    biases=[np.zeros(DIMS[i+1]) for i in range(3)]
    params=weights+biases; m=[np.zeros_like(p) for p in params]; v=[np.zeros_like(p) for p in params]
    history=[]
    for epoch in range(1,401):
        h1=np.maximum(x@weights[0]+biases[0],0)
        h2=np.maximum(h1@weights[1]+biases[1],0)
        logits=h2@weights[2]+biases[2]
        p=np.exp(logits-logits.max(1,keepdims=True)); p/=p.sum(1,keepdims=True)
        loss=float(-np.log(p[np.arange(n),y]+1e-30).mean())
        d=p.copy();d[np.arange(n),y]-=1;d/=n
        gb2=d.sum(0);gw2=h2.T@d+.0001*weights[2]
        d=(d@weights[2].T)*(h2>0);gb1=d.sum(0);gw1=h1.T@d+.0001*weights[1]
        d=(d@weights[1].T)*(h1>0);gb0=d.sum(0);gw0=x.T@d+.0001*weights[0]
        for i,g in enumerate([gw0,gw1,gw2,gb0,gb1,gb2]):
            m[i]=.9*m[i]+.1*g;v[i]=.999*v[i]+.001*g*g
            params[i]-=.001*(m[i]/(1-.9**epoch))/(np.sqrt(v[i]/(1-.999**epoch))+1e-8)
        if epoch==1 or epoch%25==0: history.append(dict(epoch=epoch,cross_entropy=loss))
    # Calibration ranges use fitting/augmented fitting data only.
    a=[x]; a.append(np.maximum(a[-1]@weights[0]+biases[0],0))
    a.append(np.maximum(a[-1]@weights[1]+biases[1],0))
    ascales=np.asarray([max(float(np.abs(t).max()),1e-8)/127 for t in a])
    wscales=np.asarray([max(float(np.abs(w).max()),1e-8)/127 for w in weights])
    meta=dict(schema='eye_mlp_int8_v1',labels=list(LABELS),dimensions=list(DIMS),
              appearance_sha256=engine.pack_sha256,training_ids=[e['sha256'] for e in entries],
              training_policy=policy,actions_enabled=False,board_tested=False,
              quantization='symmetric_int8_ties_to_even_int32_dot_float_bias_relu',
              parameters=sum(p.size for p in params),macs=sum(w.size for w in weights))
    arrays={}
    for i in range(3):
        arrays.update({f'w{i}':weights[i].astype(np.float32),f'b{i}':biases[i].astype(np.float32),
                       f'qw{i}':quantize(weights[i],wscales[i])})
    np.savez_compressed(OUT/'model.npz',metadata=np.array(json.dumps(meta)),
                        weight_scales=wscales,activation_scales=ascales,**arrays)
    model=NeuralModel(OUT/'model.npz')
    fit=[model.predict(f) for f in original]
    result=dict(model_sha256=model.sha256,training_frames=50,augmented_rows=n,
                fit_matches=sum(p['target']==LABELS[y] for p,y in zip(fit,ys)),
                parameters=meta['parameters'],macs=meta['macs'],history=history,
                seconds=time.monotonic()-start,heldout_used=False,board_tested=False)
    (OUT/'training_result.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))

if __name__=='__main__': main()
