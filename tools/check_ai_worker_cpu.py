"""Optional silent PYNQ CPU/file check in an isolated staging directory."""
import hashlib,json,shlex,zipfile
from pathlib import Path
from edge_board_session import connect,command,R,REMOTE
S=R/'build/ai_integration_20261103'

def main():
    bundle=S/'worker_probe.zip'
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED) as z:
        for p in (R/'assets/ai').rglob('*'):
            if p.is_file():z.write(p,'assets/ai/'+p.relative_to(R/'assets/ai').as_posix())
        for name in ['ai_bundle.py','ai_worker.py','ai_jobs.py','tiny_tokenizer.py']:
            z.write(R/'src/eye_tracker'/name,'python/eye_tracker/'+name)
        z.write(R/'native/audio_file_only.c','native/audio_file_only.c')
        z.writestr('python/eye_tracker/__init__.py','')
    c=connect();dest=REMOTE+'/build/ai_integration_20261103'
    try:
        command(c,'python3 '+shlex.quote(REMOTE+'/tools/upgrade_preflight.py')+' --owners',sudo=True)
        command(c,'mkdir -p '+shlex.quote(dest))
        sftp=c.open_sftp();sftp.put(str(bundle),dest+'/worker_probe.zip');sftp.close()
        script='''import pathlib,json,hashlib,zipfile,fcntl,subprocess,sys,time,wave,shutil,os
R=pathlib.Path('''+repr(REMOTE)+''');S=R/'build/ai_integration_20261103'
with open('/var/lock/eye_tracker_system.lock','a+') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 subprocess.run(['python3',str(R/'tools/upgrade_preflight.py'),'--owners'],check=True)
 baseline=json.loads((R/'build/edge_ai_v2_20261103/board_inventory.json').read_text())['protected']
 assert all(hashlib.sha256((R/n).read_bytes()).hexdigest()==h for n,h in baseline.items())
 with zipfile.ZipFile(S/'worker_probe.zip') as z:
  assert all(S in (S/n).resolve().parents for n in z.namelist());z.extractall(S)
 for n in ['tiny_run','tts/bin/espeak-ng']:(S/'assets/ai'/n).chmod(0o755)
 subprocess.run(['gcc','-std=c99','-Wall','-Wextra','-Werror','-Os','-shared','-fPIC','-Wl,-soname,libpcaudio.so.0',str(S/'native/audio_file_only.c'),'-o',str(S/'assets/ai/tts/lib/libpcaudio.so.0')],check=True)
 manifest=S/'assets/ai/manifest.json';m=json.loads(manifest.read_text())
 m['files']['tts/lib/libpcaudio.so.0']=hashlib.sha256((S/'assets/ai/tts/lib/libpcaudio.so.0').read_bytes()).hexdigest()
 m['audio_backend']='file-only local adapter; no ALSA or PulseAudio output'
 manifest.write_text(json.dumps(m,indent=2))
 sys.path.insert(0,str(S/'python'))
 from eye_tracker.ai_bundle import AIBundle
 from eye_tracker.ai_jobs import AIJob
 b=AIBundle(S/'assets/ai');rows=[]
 tts=S/'assets/ai/tts';env=dict(os.environ,LD_LIBRARY_PATH=str(tts/'lib'),ESPEAK_DATA_PATH=str(tts),LC_ALL='C.UTF-8')
 diagnostics=[]
 for args in [['ldd',str(tts/'bin/espeak-ng')],[str(tts/'bin/espeak-ng'),'--path='+str(tts),'--voices=cmn'],[str(tts/'bin/espeak-ng'),'--path='+str(tts),'-v','cmn','-w',str(S/'direct_raw.wav'),'你好']]:
  p=subprocess.run(args,env=env,capture_output=True,text=True,timeout=15);diagnostics.append(dict(args=args[:2],code=p.returncode,stdout=p.stdout,stderr=p.stderr))
 folder=S/'diagnose';folder.mkdir(exist_ok=True)
 req=dict(bundle=str(b.path),bundle_sha256=b.sha256,kind='synthesize',text='今天下午我想去公园散步。')
 probe="import sys,json,pathlib;sys.path.insert(0,"+repr(str(S/'python'))+");from eye_tracker.ai_worker import run;print(run(json.loads("+repr(json.dumps(req))+") ,pathlib.Path("+repr(str(folder))+")))"
 p=subprocess.run(['python3','-c',probe],capture_output=True,text=True,timeout=65);diagnostics.append(dict(args=['static-worker-trace'],code=p.returncode,stdout=p.stdout,stderr=p.stderr))
 for mode in ('trace',):
  output=S/('diag_'+mode+'.wav')
  args=[str(tts/'bin/espeak-ng'),'--path='+str(tts),'-v','cmn','-s','155','-a','100','-b','1','-w',str(output)]
  args+=['今天下午我想去公园散步。'] if mode in ('argument','trace','unlimited') else (['--stdin'] if mode=='stdin' else ['-f',str(folder/'source.txt')])
  def file_limit():
   import resource
   resource.setrlimit(resource.RLIMIT_FSIZE,(4*1024*1024,4*1024*1024))
  if mode=='trace':
   if not shutil.which('strace'):diagnostics.append(dict(strace=False));continue
   args=['strace','-e','trace=%file,%network,write,lseek,ftruncate,prlimit64']+args
  p=subprocess.run(args,env=env,input='今天下午我想去公园散步。',capture_output=True,text=True,timeout=15,preexec_fn=None if mode=='unlimited' else file_limit)
  diagnostics.append(dict(mode=mode,code=p.returncode,bytes=output.stat().st_size if output.exists() else 0,stderr=p.stderr))
  assert p.returncode==0
  if mode=='trace':assert not any(token in p.stderr for token in ('/dev/snd','/dev/mem','/dev/uio','connect(','socket('))
 for kind,text in [('synthesize','今天下午我想去公园散步。'),('synthesize','你好'*32),('generate','今天下午我想去公园散步')]:
  j=AIJob(b,S/'work',kind,text);start=time.monotonic()
  try:
   while True:
    result=j.poll()
    if result is not None:break
    time.sleep(.05)
   if kind=='synthesize':
    with wave.open(str(j.path/'speech.wav')) as w:assert w.getnchannels()==1 and w.getframerate()==16000 and 0<w.getnframes()<=960000
    if len(text)<64:shutil.copyfile(j.path/'speech.wav',S/'probe_speech.wav')
   rows.append(dict(kind=kind,input_characters=len(text),seconds=time.monotonic()-start,result=result))
  except Exception as exc:rows.append(dict(kind=kind,input_characters=len(text),error=type(exc).__name__))
  finally:j.cancel();assert j.reap(2)
 j=AIJob(b,S/'work','generate','今天下午我想去公园散步');time.sleep(.1);j.cancel();assert j.reap(2)
 assert all(hashlib.sha256((R/n).read_bytes()).hexdigest()==h for n,h in baseline.items())
 owners=subprocess.check_output(['python3',str(R/'tools/upgrade_preflight.py'),'--owners'],text=True)
 report=dict(cpu_only=True,no_audio_output=True,no_camera_or_pl=True,no_wireless=True,protected_unchanged=len(baseline),cancel_reaped=True,rows=rows,tts_diagnostics=diagnostics,owners=json.loads(owners))
 (S/'worker_result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
'''
        out=command(c,'python3 -c '+shlex.quote(script),timeout=240,sudo=True);print(out,flush=True)
        if (S/'worker_result.json').exists():
            import time
            (S/('worker_result_previous_'+str(int(time.time()))+'.json')).write_bytes((S/'worker_result.json').read_bytes())
        sftp=c.open_sftp();sftp.get(dest+'/worker_result.json',str(S/'worker_result.json'))
        sftp.get(dest+'/assets/ai/tts/lib/libpcaudio.so.0',str(R/'assets/ai/tts/lib/libpcaudio.so.0'))
        sftp.get(dest+'/assets/ai/manifest.json',str(R/'assets/ai/manifest.json'))
        sftp.get(dest+'/assets/ai/tts/lib/libpcaudio.so.0',str(S/'audio_file_only.so'))
        try:sftp.get(dest+'/probe_speech.wav',str(S/'probe_speech.wav'))
        except IOError:pass
        sftp.close()
    except Exception as exc:
        (S/'worker_check_failure.txt').write_text(str(exc),encoding='utf-8');raise
    finally:c.close()
if __name__=='__main__':main()
