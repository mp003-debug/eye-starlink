"""Portable JSON golden comparison and timing/resource summary (standard library)."""
import argparse,json,math,statistics
from pathlib import Path

def array(value):
    if isinstance(value,list):
        children=[array(x) for x in value]
        if children and any(x[0]!=children[0][0] for x in children):raise ValueError('ragged array')
        return (len(value),)+(children[0][0] if children else ()),[n for _,xs in children for n in xs]
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError('non-finite or non-numeric value')
    return (),[value]

def compare(data):
    errors=[];summary={}
    try:
        atol=data.get('atol',0);rtol=data.get('rtol',0)
        if any(not math.isfinite(x) or x<0 for x in (atol,rtol)):raise ValueError('invalid tolerance')
        sa,a=array(data['actual']);sg,g=array(data['expected'])
        if sa!=sg:raise ValueError('shape mismatch')
        if not g:raise ValueError('empty result')
        delta=[abs(x-y) for x,y in zip(a,g)]
        mismatch=sum(d>atol+rtol*abs(y) for d,y in zip(delta,g))
        summary.update(shape=sa,elements=len(g),mismatches=mismatch,max_abs_error=max(delta))
        if mismatch:errors.append('golden mismatch')
        if 'latencies_ms' in data:
            lat=data['latencies_ms'];_,flat=array(lat)
            if not flat or len(flat)!=len(lat) or any(t<0 for t in flat):raise ValueError('invalid latency samples')
            summary['latency_median_ms']=statistics.median(flat)
            summary['latency_p95_ms']=sorted(flat)[math.ceil(.95*len(flat))-1]
        if 'implementation' in data:
            imp=data['implementation']
            for key in ('part','tool','stage'):
                if not imp.get(key):raise ValueError('missing implementation provenance '+key)
            wns=imp['wns_ns']
            if not math.isfinite(wns):raise ValueError('invalid WNS')
            if wns<0:errors.append('timing constraint not met')
            for name,row in imp['resources'].items():
                used,total=row['used'],row['available']
                if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in (used,total)) or used<0 or total<=0:
                    raise ValueError('invalid resource count '+name)
                if used>total:errors.append('resource exceeds device: '+name)
            summary['implementation']=imp
    except (ValueError,TypeError,KeyError,OverflowError) as exc:errors.append(str(exc))
    return dict(passed=not errors,errors=errors,summary=summary,board_tested=False)

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('results',type=Path);a=ap.parse_args()
    result=compare(json.loads(a.results.read_text()));print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 1)
