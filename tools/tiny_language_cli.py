"""Explicit PYNQ-only standalone generation. Never starts eye/UI/radio services."""
from pathlib import Path
import argparse,fcntl,hashlib,json,os,platform,resource,subprocess,sys,tempfile

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',type=Path,required=True)
    parser.add_argument('--prompt',required=True)
    parser.add_argument('--max-new',type=int,default=32)
    args=parser.parse_args();root=Path('/home/xilinx/Eye_Tracker_Upgrade_Version')
    bundle=args.bundle.resolve()
    if bundle!=root/'build/edge_ai_v2_20261103' or platform.machine()!='armv7l':
        parser.error('requires the isolated PYNQ ARMv7 bundle')
    if not 1<=args.max_new<=64:parser.error('max-new must be 1..64')
    manifest=json.loads((bundle/'runtime_manifest.json').read_text())
    for name,digest in manifest.items():
        path=(bundle/name).resolve()
        if bundle not in path.parents:raise ValueError('manifest_path')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('artifact_hash:'+name)
    sys.path.insert(0,str(bundle/'python'))
    from eye_tracker.tiny_tokenizer import TinyTokenizer
    tokenizer=TinyTokenizer(bundle/'tiny/tokenizer.json');tokens=tokenizer.prompt(args.prompt)
    if len(tokens)>192 or len(tokens)+args.max_new>256:parser.error('prompt exceeds short-context limit')
    with open('/var/lock/eye_tracker_system.lock','a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        subprocess.run(['python3',str(root/'tools/upgrade_preflight.py'),'--owners'],check=True,stdout=subprocess.PIPE)
        def limits():
            resource.setrlimit(resource.RLIMIT_AS,(160*1024*1024,160*1024*1024))
            resource.setrlimit(resource.RLIMIT_CPU,(110,115));os.nice(10)
            cpus=os.sched_getaffinity(0)
            if 1 in cpus:os.sched_setaffinity(0,{1})
        with tempfile.TemporaryDirectory(prefix='request_',dir=bundle/'tiny') as temp:
            path=Path(temp)/'tokens.txt';path.write_text(' '.join(map(str,tokens)))
            run=subprocess.run([str(bundle/'tiny/tiny_run'),str(bundle/'tiny/minimind_q8.bin'),str(path),str(args.max_new)],
                capture_output=True,text=True,timeout=120,preexec_fn=limits,check=True)
        ids=list(map(int,run.stdout.split()))
        if len(ids)>args.max_new or any(not 0<=i<6400 for i in ids):raise ValueError('invalid_child_output')
        print(json.dumps(dict(text=tokenizer.decode(ids),metrics=json.loads(run.stderr),local_only=True,
            review_required=True,automatic_speech=False,automatic_wireless=False),ensure_ascii=False))
if __name__=='__main__':main()
