"""Independent NumPy HF-order Q8 reference for conversion/RoPE/numeric checks."""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
from pathlib import Path
import json,sys,subprocess
import numpy as np
from build_tiny_language import tensors
R=Path(__file__).resolve().parents[1];S=R/'build/edge_ai_v2_20261103';O=S/'tiny'

def main():
    t=tensors();weights={};norm={k:v for k,v in t.items() if 'norm' in k}
    for k,w in t.items():
        if w.ndim!=2:continue
        g=w.reshape(-1,64);s=np.maximum(np.abs(g).max(1)/127,1e-12)
        weights[k]=(np.clip(np.rint(g/s[:,None]),-127,127).astype(np.int32).reshape(w.shape),s.reshape(w.shape[0],-1))
    def quant(x):
        g=x.reshape(-1,64);s=np.maximum(np.abs(g).max(1)/127,1e-12)
        y=g/s[:,None];q=(np.sign(y)*np.floor(np.abs(y).astype(np.float64)+.5)).astype(np.int32)
        return q,s
    def mat(k,x):
        q,s=quant(x);w,ws=weights[k];out=np.zeros(w.shape[0],np.float32)
        for j in range(q.shape[0]):out+=(w[:,j*64:(j+1)*64]@q[j]).astype(np.float32)*ws[:,j]*s[j]
        return out
    def rms(x,w):return x*np.float32(1/np.sqrt(np.mean(x.astype(np.float64)**2)+1e-5))*w
    def rope(x,pos,heads):
        x=x.reshape(heads,64);a=x[:,:32].copy();b=x[:,32:].copy()
        theta=np.float32(pos)*np.float32(1)/np.power(np.float32(1e6),np.arange(0,64,2,dtype=np.float32)/64)
        c=np.cos(theta);s=np.sin(theta)
        return np.concatenate([a*c-b*s,a*s+b*c],axis=1)
    check=json.loads((O/'local_result.json').read_text(encoding='utf-8'));errors=[]
    if '--trace' in sys.argv:
        csrc=(O/'tiny_run.c').read_text()
        csrc=csrc.replace('// final rmsnorm', '// final rmsnorm').replace('x[i] += s->xb[i];\n        }','x[i] += s->xb[i];\n        }\n        if(pos<4){FILE *tr=fopen("trace_c.f32","ab");fwrite(x,4,512,tr);fclose(tr);}')
        (O/'trace_run.c').write_text(csrc)
        subprocess.run([__import__('os').environ.get('CC','gcc'),'-std=c11','-O3','-o',str(O/'trace_run.exe'),str(O/'trace_run.c'),'-lm'],check=True)
        (O/'trace_c.f32').write_bytes(b'');p=O/'trace_ids.txt';p.write_text(' '.join(map(str,check['desktop_examples'][0]['input_ids'][:4])))
        subprocess.run([str(O/'trace_run.exe'),str(O/'minimind_q8.bin'),str(p),'1'],cwd=O,capture_output=True,check=True)
        ct=np.fromfile(O/'trace_c.f32','<f4').reshape(4,8,512)
    for case,row in enumerate(check['desktop_examples']):
        if '--short' in sys.argv:
            count=int(sys.argv[sys.argv.index('--short')+1]) if sys.argv[-1]!='--short' else 1
            row=dict(row,input_ids=row['input_ids'][:count]);path=O/f'short_{case}.txt';path.write_text(' '.join(map(str,row['input_ids'])))
            subprocess.run([str(O/'tiny_run.exe'),str(O/'minimind_q8.bin'),str(path),'1',str(O/f'short_logits_{case}.f32')],capture_output=True,check=True)
        cache=[([],[]) for _ in range(8)];logits=None
        for pos,token in enumerate(row['input_ids']):
            w,ws=weights['model.embed_tokens.weight'];x=(w[token].reshape(-1,64)*ws[token,:,None]).reshape(-1).astype(np.float32)
            for l in range(8):
                prefix=f'model.layers.{l}.';a=rms(x,norm[prefix+'input_layernorm.weight'])
                q=rope(mat(prefix+'self_attn.q_proj.weight',a),pos,8)
                k=rope(mat(prefix+'self_attn.k_proj.weight',a),pos,2)
                v=mat(prefix+'self_attn.v_proj.weight',a).reshape(2,64)
                cache[l][0].append(k);cache[l][1].append(v);ks=np.asarray(cache[l][0]);vs=np.asarray(cache[l][1]);att=[]
                for h in range(8):
                    scores=((ks[:,h//4,:].astype(np.float64)@q[h].astype(np.float64))/8).astype(np.float32);scores=np.exp(scores-scores.max());scores/=scores.sum()
                    att.append(scores@vs[:,h//4,:])
                x=x+mat(prefix+'self_attn.o_proj.weight',np.asarray(att).ravel())
                a=rms(x,norm[prefix+'post_attention_layernorm.weight'])
                h=mat(prefix+'mlp.gate_proj.weight',a);h=(h/(1+np.exp(-h)))*mat(prefix+'mlp.up_proj.weight',a)
                x=x+mat(prefix+'mlp.down_proj.weight',h)
                if '--trace' in sys.argv and case==0 and pos<4:
                    print('trace',pos,l,float(np.max(np.abs(x-ct[pos,l]))))
            logits=mat('model.embed_tokens.weight',rms(x,norm['model.norm.weight']))
        c=np.fromfile(O/(f'short_logits_{case}.f32' if '--short' in sys.argv else f'logits_{case}.f32'),'<f4');error=float(np.max(np.abs(c-logits)))
        # float summation order differs, and near-tie activation quantization can
        # amplify tiny differences; compare RMSE/top token as well as max error.
        rmse=float(np.sqrt(np.mean((c-logits)**2)));same=int(c.argmax())==int(logits.argmax())
        cosine=float(np.dot(c,logits)/(np.linalg.norm(c)*np.linalg.norm(logits)))
        errors.append(dict(case=case,max_error=error,rmse=rmse,cosine=cosine,top_token_match=same))
    result=dict(strict_numerical_check_passed=False,approximate_agreement=all(r['cosine']>.9995 and r['max_error']<.5 and r['top_token_match'] for r in errors),
        bit_exact=False,strict_original_tolerance_passed=False,
        scope='approximate conversion agreement only; not model quality or FP16 accuracy',
        tolerance='cosine > .9995, max absolute < .5, top token equal on these full prompts',
        investigation='First three positions match within 4e-6. At position 3 layer 2, ~5e-8 input differences cross activation quantization bins and grow through later layers. Different float reduction and libm operations are retained.',
        reference='independent HF half-rotation ordering; grouped Q8 weights/activations; float reduction order differs',cases=errors)
    (O/('numeric_short.json' if '--short' in sys.argv else 'numeric_reference.json')).write_text(json.dumps(result,indent=2));print(json.dumps(result))
if __name__=='__main__':main()
