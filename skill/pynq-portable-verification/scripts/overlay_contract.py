"""Read-only manifest/snapshot comparison; no PYNQ import or hardware access."""
from pathlib import Path
import argparse,hashlib,json,math

def integer(value):
    if isinstance(value,bool):raise ValueError('boolean is not an address')
    if isinstance(value,int):return value
    if isinstance(value,str):return int(value,0)
    raise ValueError('address/offset must be an integer or integer string')

def snapshot(overlay, platform):
    """Normalize metadata of an overlay supplied by the caller; never download it."""
    return {'platform':platform,'ips':{name:{'vlnv':v['type'],
        'base':v['phys_addr'],'range':v['addr_range'],
        'registers':{n:r['address_offset'] for n,r in v.get('registers',{}).items()}}
        for name,v in overlay.ip_dict.items()}}

def check(contract, observed, artifacts=None):
    errors=[]
    if contract.get('schema')!=1:errors.append('unsupported schema')
    if not contract.get('ips'):errors.append('no required IP contracts')
    if observed.get('platform')!=contract.get('platform'):errors.append('platform mismatch')
    spans=[]
    try:
        for name,expected in contract.get('ips',{}).items():
            base=integer(expected['base']);length=integer(expected['range'])
            if base<0 or length<=0 or base%4:errors.append(name+': invalid address range')
            spans.append((base,base+length,name))
            got=observed.get('ips',{}).get(name)
            if got is None:errors.append(name+': missing IP');continue
            if got.get('vlnv')!=expected['vlnv']:errors.append(name+': VLNV mismatch')
            for key in ('base','range'):
                if integer(got[key])!=integer(expected[key]):errors.append(name+': '+key+' mismatch')
            for reg,offset in expected.get('registers',{}).items():
                off=integer(offset)
                if off<0 or off%4 or off+4>length:errors.append(name+': invalid register '+reg)
                actual=got.get('registers',{}).get(reg)
                if actual is None or integer(actual)!=off:errors.append(name+': register mismatch '+reg)
        spans.sort()
        for a,b in zip(spans,spans[1:]):
            if a[1]>b[0]:errors.append('overlapping IP ranges: '+a[2]+'/'+b[2])
        for name,hz in contract.get('clocks_hz',{}).items():
            actual=observed.get('clocks_hz',{}).get(name)
            if not isinstance(hz,(int,float)) or not math.isfinite(hz) or hz<=0 or actual!=hz:
                errors.append('clock mismatch: '+name)
        pair=contract.get('artifacts')
        if pair:
            bit=Path(pair['bit']['file']);hwh=Path(pair['hwh']['file'])
            if bit.suffix!='.bit' or hwh.suffix!='.hwh' or bit.stem!=hwh.stem:
                errors.append('bit/HWH basename mismatch')
            if artifacts is None:errors.append('artifact directory required')
            else:
                root=Path(artifacts).resolve()
                for label,row in pair.items():
                    path=(root/row['file']).resolve()
                    if not path.is_relative_to(root):errors.append(label+': path escapes root');continue
                    if not path.is_file():errors.append(label+': missing file');continue
                    if hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
                        errors.append(label+': hash mismatch')
    except (KeyError,TypeError,ValueError,OverflowError) as exc:
        errors.append('invalid contract/snapshot: '+str(exc))
    return {'passed':not errors,'errors':errors,'hardware_accessed':False}

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('contract',type=Path)
    ap.add_argument('observed',type=Path);ap.add_argument('--artifacts',type=Path)
    a=ap.parse_args();r=check(json.loads(a.contract.read_text()),json.loads(a.observed.read_text()),a.artifacts)
    print(json.dumps(r,indent=2));raise SystemExit(0 if r['passed'] else 1)
