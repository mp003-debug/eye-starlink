"""Host fault tests for the same C endpoint linked into BearPi firmware."""
import hashlib,json,os,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]
out=r/'comm/build/fanout';out.mkdir(parents=True,exist_ok=True)
cc=Path(__import__('os').environ.get('CC','gcc'))
env=os.environ.copy();env['PATH']=str(cc.parent)+os.pathsep+env.get('PATH','')
files=[r/'comm/protocol/eye_event.c',r/'comm/firmware/eye_endpoint.c',r/'comm/firmware/eye_fanout.c',r/'comm/firmware/fanout_check.c']
args=[str(cc),'-std=c99','-Wall','-Wextra','-Werror','-O2','-I'+str(r/'comm/protocol'),'-I'+str(r/'comm/firmware')]
p=subprocess.run(args+list(map(str,files))+['-o',str(out/'fanout_check.exe')],capture_output=True,text=True,env=env)
(out/'compile.log').write_text(p.stdout+p.stderr,encoding='utf-8')
if p.returncode: raise RuntimeError(p.stderr)
p=subprocess.run([str(out/'fanout_check.exe')],capture_output=True,text=True,env=env)
if p.returncode: raise RuntimeError(p.stderr)
result=json.loads(p.stdout)
result.update(hardware_tested=False,scope='real C endpoint fault injection; no UART timing or RF verification',
              sources={str(f.relative_to(r)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files})
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
