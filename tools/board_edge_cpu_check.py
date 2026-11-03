"""Standalone CPU-only research runner, exclusive lock, bounded child processes."""
from pathlib import Path
import ctypes,fcntl,hashlib,json,os,resource,subprocess,sys,time
import numpy as np
S=Path(__file__).resolve().parent;R=Path('/home/xilinx/Eye_Tracker_Upgrade_Version')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    assert S==R/'build/edge_ai_v2_20261103'
    inventory=json.loads((S/'board_inventory.json').read_text())
    with open('/var/lock/eye_tracker_system.lock','a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        subprocess.run(['python3',str(R/'tools/upgrade_preflight.py'),'--owners'],check=True)
        for name,digest in inventory['protected'].items():assert sha(R/name)==digest,name
        assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==inventory['boot_id']
        manifest=json.loads((S/'transfer_manifest.json').read_text())
        for name,digest in manifest.items():assert sha(S/name)==digest,name
        results=dict(board='PYNQ-Z2',cpu_only=True,pl_loaded=False,ui_started=False,network_inference=False,compiler_flags=['-O3','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard'],before_memory=Path('/proc/meminfo').read_text())
        common=['gcc','-std=c11','-O3','-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard']
        subprocess.run(common+['-Wall','-Wextra','-Werror','-shared','-fPIC','-o',str(S/'neural/neural_cpu.so'),str(S/'neural_cpu.c'),'-lm'],check=True,timeout=60)
        lib=ctypes.CDLL(str(S/'neural/neural_cpu.so'));lib.nn_load.argtypes=[ctypes.c_char_p];lib.nn_load.restype=ctypes.c_void_p
        lib.nn_forward.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_float),ctypes.POINTER(ctypes.c_double)]
        lib.nn_free.argtypes=[ctypes.c_void_p];lib.nn_backend.restype=ctypes.c_char_p
        ptr=lib.nn_load(str(S/'neural/eye_q8.bin').encode());assert ptr
        fs=np.fromfile(S/'neural/features.f32','<f4').reshape(-1,1152);expected=np.fromfile(S/'neural/expected.f64','<f8').reshape(-1,5)
        out=(ctypes.c_double*5)();worst=0;times=[]
        for turn in range(20):
            for i,f in enumerate(fs):
                begin=time.perf_counter();rc=lib.nn_forward(ptr,f.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),out);times.append((time.perf_counter()-begin)*1000)
                assert rc==0;worst=max(worst,float(np.max(np.abs(np.asarray(out)-expected[i]))))
        assert worst<1e-10;lib.nn_free(ptr)
        # Baseline uses existing copied Python inference, in the isolated folder.
        sys.path.insert(0,str(S/'python'))
        from eye_tracker.neural import NeuralModel
        baseline=NeuralModel(S/'neural/original_model.npz');base=[]
        for _ in range(4):
            for f in fs:
                begin=time.perf_counter();baseline.logits(f);base.append((time.perf_counter()-begin)*1000)
        results['neural']=dict(backend=lib.nn_backend().decode(),native_runs=len(times),baseline_runs=len(base),max_logit_difference=worst,native_median_ms=float(np.median(times)),native_p95_ms=float(np.percentile(times,95)),baseline_median_ms=float(np.median(base)),baseline_p95_ms=float(np.percentile(base,95)),compact_bytes=(S/'neural/eye_q8.bin').stat().st_size)
        print('NEURAL '+json.dumps(results['neural']),flush=True)
        (S/'neural_board_result.json').write_text(json.dumps(results['neural'],indent=2))
        subprocess.run(common+['-Wno-unknown-pragmas','-o',str(S/'tiny/tiny_run'),str(S/'tiny/tiny_run.c'),'-lm'],check=True,timeout=90)
        from eye_tracker.tiny_tokenizer import TinyTokenizer
        tok=TinyTokenizer(S/'tiny/tokenizer.json');local=json.loads((S/'tiny/local_result.json').read_text());examples=[]
        def child_limits():
            resource.setrlimit(resource.RLIMIT_AS,(160*1024*1024,160*1024*1024));resource.setrlimit(resource.RLIMIT_CPU,(110,115));os.nice(10)
        for i,row in enumerate(local['desktop_examples']):
            tokens=tok.prompt(row['prompt']);p=S/f'tiny/board_prompt_{i}.txt';p.write_text(' '.join(map(str,tokens)))
            begin=time.monotonic();proc=subprocess.run([str(S/'tiny/tiny_run'),str(S/'tiny/minimind_q8.bin'),str(p),'32',str(S/f'tiny/board_logits_{i}.f32')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,universal_newlines=True,timeout=120,preexec_fn=child_limits,env=dict(os.environ,LC_ALL='C'))
            elapsed=time.monotonic()-begin
            if proc.returncode:raise RuntimeError('tiny child '+str(proc.returncode)+' '+proc.stderr)
            ids=list(map(int,proc.stdout.split()));logits=np.fromfile(S/f'tiny/board_logits_{i}.f32','<f4');host=np.fromfile(S/f'tiny/logits_{i}.f32','<f4')
            assert logits.shape==(6400,) and np.all(np.isfinite(logits))
            diff=float(np.max(np.abs(logits-host)));cosine=float(np.dot(logits,host)/(np.linalg.norm(logits)*np.linalg.norm(host)))
            rss=json.loads(proc.stderr)['peak_rss_kib']
            record=dict(prompt=row['prompt'],text=tok.decode(ids),ids=ids,wall_seconds=elapsed,metrics=json.loads(proc.stderr),max_logits_vs_host=diff,logit_cosine_vs_host=cosine,top_token_matches_host=bool(logits.argmax()==host.argmax()),peak_child_rss_kib=rss)
            examples.append(record);print('TINY '+json.dumps(record,ensure_ascii=False),flush=True)
        results['tiny']=dict(examples=examples,model_bytes=(S/'tiny/minimind_q8.bin').stat().st_size,context=256,max_new=32)
        for name,digest in inventory['protected'].items():assert sha(R/name)==digest,name
        results.update(passed=True,protected_files_unchanged=len(inventory['protected']),after_memory=Path('/proc/meminfo').read_text(),fresh_eye_validation=False,mixed_load_tested=False)
        (S/'board_cpu_result.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print('CPU_RESEARCH_COMPLETE',flush=True)
if __name__=='__main__':main()
