"""Replay frozen private recordings; never starts cameras or changes a model."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'tools/deps/opencv'),str(ROOT/'src')]
import numpy as np
from eye_tracker.neural import NeuralAppearanceDiagnostic
BASE=ROOT/'build/fixed_camera_calibration_20261103'
OUT=ROOT/'build/neural_upgrade_20261103'

def load(folder,e):
    raw=(folder/e['raw']).read_bytes()
    if len(raw)!=640*480 or hashlib.sha256(raw).hexdigest()!=e['sha256']:raise ValueError('frame_hash')
    return np.frombuffer(raw,np.uint8).reshape(480,640)

def main():
    results={}; vector_features=[]
    for name,source,session in [('heldout','capture_fit_01',False),('independent','positive_01',True),('invalid','invalid_01',True)]:
        eng=NeuralAppearanceDiagnostic(BASE/'candidate_01/model.npz',OUT/'model/model.npz')
        folder=BASE/source/'targets';entries=json.loads((folder/'manifest.json').read_text())['samples_detail']
        if session:
            for i,e in enumerate(entries[:5]):
                pixels=load(folder,e)
                if i==0:eng.appearance.anchor.acquire(pixels)
                f,_=eng.appearance.feature(pixels);eng.appearance.baseline.add(f,i+1)
            ref=eng.appearance.baseline.finish()
            if not ref['ready']:raise ValueError('session_reference_failed')
            entries=entries[5:]
        else:entries=entries[50:]
        if name=='invalid':
            review=json.loads((BASE/'invalid_review.json').read_text())['negative_image_checks']
            ranges=[(k,a,b) for k,v in review.items() for a,b in v['ranges']]
            entries=[dict(e,invalid_type=next((k for k,a,b in ranges if a<=e['frame_index']<=b),None)) for e in entries]
            entries=[e for e in entries if e['invalid_type']]
        rows=[]
        for e in entries:
            if e['sha256'] in eng.neural.meta['training_ids']:raise ValueError('evaluation_leakage')
            pixels=load(folder,e); p=eng.inspect(pixels,session_correct=session)
            row=dict(raw=e['raw'],frame=e['frame_index'],sha256=e['sha256'],target=e.get('target'),
                     invalid_type=e.get('invalid_type'),prediction=p)
            if name!='invalid':
                f,_=eng.appearance.feature(pixels)
                if session:f=eng.appearance.baseline.correct(f)
                pf=eng.neural.predict(f,integer=False)
                row['float_prediction']=pf
                row['float_int8_same']=pf['target']==p.get('target')
                vector_features.append(f)
            rows.append(row)
        results[name]=dict(total=len(rows),
            matching=sum(r['prediction'].get('candidate')==r['target'] for r in rows) if name!='invalid' else None,
            rejected=sum(r['prediction'].get('candidate') is None for r in rows),
            wrong=sum(r['prediction'].get('candidate') not in (None,r['target']) for r in rows) if name!='invalid' else None,
            accepted_invalid=sum(r['prediction'].get('candidate') is not None for r in rows) if name=='invalid' else None,
            float_int8_same=sum(r.get('float_int8_same',False) for r in rows),rows=rows)
    np.savez_compressed(OUT/'evaluation_features.npz',features=np.asarray(vector_features))
    result=dict(model_sha256=eng.neural.sha256,sets=results,board_tested=False,
                scope='one participant, saved frames, fixed camera; not a population accuracy or live latency test')
    (OUT/'evaluation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:{a:b for a,b in v.items() if a!='rows'} for k,v in results.items()}))
    if any(results[k]['wrong'] or results[k]['matching']!=results[k]['total'] for k in ('heldout','independent')) or results['invalid']['accepted_invalid']:
        raise SystemExit('candidate requires review; no automatic enabling')

if __name__=='__main__':main()
