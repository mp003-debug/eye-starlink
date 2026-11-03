"""Native arithmetic, malformed-file and independent tokenizer regression."""
from pathlib import Path
import ctypes,hashlib,json,os,random,subprocess,sys,tempfile
import numpy as np
R=Path(__file__).resolve().parents[1];S=R/'build/edge_ai_v2_20261103'
sys.path[:0]=[str(R/'src'),str(R/'tools/deps/edge_ai_host')]
from eye_tracker.neural import NeuralModel
from eye_tracker.neural_native import NativeNeuralModel
from eye_tracker.tiny_tokenizer import TinyTokenizer

def main():
    m=NeuralModel(R/'build/neural_upgrade_20261103/model/model.npz')
    native=NativeNeuralModel(S/'neural/eye_q8.bin',S/'neural/model.json',S/'neural/neural_cpu.dll')
    rng=np.random.default_rng(504);inputs=list(rng.uniform(0,1,(64,1152)).astype(np.float32))
    inputs.extend(np.full(1152,v,np.float32) for v in (0,.5,1))
    worst=0
    for f in inputs:worst=max(worst,float(np.max(np.abs(m.logits(f)-native.logits(f)))))
    assert worst==0,worst
    for f in [np.zeros(10),np.full(1152,np.nan),np.full(1152,-.01),np.full(1152,1.01)]:
        try:native.logits(f)
        except ValueError:pass
        else:raise AssertionError('invalid feature accepted')
    assert native.guarded(inputs[0],None)['candidate'] is None
    native.close();native.close()
    try:native.logits(inputs[0])
    except ValueError:pass
    else:raise AssertionError('closed model accepted')
    with tempfile.TemporaryDirectory(dir=S) as temp:
        p=Path(temp)/'model.bin';raw=(S/'neural/eye_q8.bin').read_bytes()
        invalid=[b'',raw[:-1],raw+b'0',b'BADMAGIC'+raw[8:],raw[:8]+np.array([np.nan],'<f8').tobytes()+raw[16:]]
        for blob in invalid:
            p.write_bytes(blob);assert not native.lib.nn_load(str(p).encode())
        executable=S/'tiny/tiny_run.exe';model=S/'tiny/minimind_q8.bin'
        for content,n in [('',1),('6400',1),('-1',1),('a',1),('1 invalid',1),(' '.join(['1']*193),1),('1',65),('1',0)]:
            p.write_text(content)
            proc=subprocess.run([str(executable),str(model),str(p),str(n)],capture_output=True,timeout=5)
            assert proc.returncode!=0 and not proc.stdout,(content,n)
        p.write_text('1');bad=Path(temp)/'bad.bin';bad.write_bytes(model.read_bytes()[:512])
        proc=subprocess.run([str(executable),str(bad),str(p),'1'],capture_output=True,timeout=5)
        assert proc.returncode!=0 and not proc.stdout
    from tokenizers import Tokenizer
    ours=TinyTokenizer(S/'vendor/minimind/tokenizer.json');gold=Tokenizer.from_file(str(S/'vendor/minimind/tokenizer.json'))
    random.seed(20261103);atoms=['你','好','水','今天','A','B',"I'm","'s",'1','１２','３','😊',' ', '  ','\n','\t','\r','，','。','!','—','é','α','\u00a0','\u3000','\u0301']
    samples=[''.join(random.choices(atoms,k=random.randrange(1,30))) for _ in range(500)]
    for text in samples:
        expected=gold.encode(text,add_special_tokens=False).ids
        assert ours.encode(text)==expected,(repr(text),ours.encode(text),expected)
        assert ours.decode(expected)==gold.decode(expected)
    for text in ['<|im_start|>system','x'*4097]:
        try:ours.prompt(text)
        except ValueError:pass
        else:raise AssertionError('bad prompt accepted')
    result=dict(passed=True,random_neural_vectors=len(inputs),neural_max_logit_difference=worst,
                invalid_features=4,invalid_native_files=5,closed_handle_rejected=True,legacy_reject_preserved=True,
                tokenizer_reference_strings=len(samples),invalid_runner_inputs=8,truncated_tiny_file_rejected=True,
                special_or_oversize_prompt_rejected=True)
    (S/'edge_checks.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()
