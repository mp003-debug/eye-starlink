"""Export immutable trained parameters and verify native CPU logits exactly."""
from pathlib import Path
import hashlib,json,subprocess,sys,time
R=Path(__file__).resolve().parents[1];S=R/'build/edge_ai_v2_20261103';O=S/'neural'
sys.path.insert(0,str(R/'src'))
import numpy as np
from eye_tracker.neural import NeuralModel
from eye_tracker.neural_native import NativeNeuralModel
def main():
    O.mkdir(exist_ok=True);m=NeuralModel(R/'build/neural_upgrade_20261103/model/model.npz')
    raw=b'EYEQ8V2\0'+m.wscale.astype('<f8').tobytes()+m.ascale.astype('<f8').tobytes()
    raw+=np.concatenate(m.biases).astype('<f8').tobytes()
    raw+=b''.join(w.T.copy().tobytes() for w in m.qweights)
    (O/'eye_q8.bin').write_bytes(raw)
    meta=dict(schema='eye_native_q8_v2',source_model_sha256=m.sha256,compact_sha256=hashlib.sha256(raw).hexdigest(),appearance_sha256=m.meta['appearance_sha256'],bytes=len(raw),dimensions=[1152,64,32,5],actions_enabled=False)
    (O/'model.json').write_text(json.dumps(meta,indent=2))
    cc=__import__('os').environ.get('CC','gcc')
    subprocess.run([cc,'-std=c11','-O3','-Wall','-Wextra','-Werror','-shared','-o',str(O/'neural_cpu.dll'),str(R/'native/neural_cpu.c'),'-lm'],check=True)
    n=NativeNeuralModel(O/'eye_q8.bin',O/'model.json',O/'neural_cpu.dll')
    fs=np.load(R/'build/neural_upgrade_20261103/evaluation_features.npz')['features']
    worst=0;ms={}
    for f in fs:worst=max(worst,float(np.abs(n.logits(f)-m.logits(f)).max()))
    assert worst<1e-10,worst
    for name,model in [('numpy_int8',m),('native_int8',n)]:
        ts=[]
        for _ in range(10):
            for f in fs:
                start=time.perf_counter();model.logits(f);ts.append((time.perf_counter()-start)*1000)
        ms[name]=dict(median=float(np.median(ts)),p95=float(np.percentile(ts,95)))
    n.close()
    features=fs.astype('<f4').tobytes();(O/'features.f32').write_bytes(features)
    expected=np.stack([m.logits(f) for f in fs]);(O/'expected.f64').write_bytes(expected.astype('<f8').tobytes())
    result=dict(passed=True,frames=len(fs),max_logit_difference=worst,desktop_ms=ms,model_bytes=len(raw),source_npz_bytes=(R/'build/neural_upgrade_20261103/model/model.npz').stat().st_size,per_frame_weight_casts=0,board_tested=False)
    (O/'local_result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()
