"""One bounded CPU job. Poll/cancel never waits for model inference or synthesis."""
import json,os,signal,subprocess,sys,tempfile,time
from pathlib import Path

class AIJob:
    def __init__(self,bundle,folder,kind,text,clock=time.monotonic):
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='ai_',dir=folder);self.path=Path(self.temp.name)
        self.clock=clock;self.started=clock();self.cancelled=False;self.done=False;self.result=None
        request=dict(bundle=str(bundle.path),bundle_sha256=bundle.sha256,kind=kind,text=text)
        (self.path/'request.json').write_text(json.dumps(request,ensure_ascii=False),encoding='utf-8')
        env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
        try:
            self.process=subprocess.Popen([sys.executable,'-m','eye_tracker.ai_worker',str(self.path)],env=env,
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                start_new_session=os.name=='posix',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except BaseException:self.temp.cleanup();raise
    def poll(self):
        if self.cancelled:return None
        if self.done:return self.result
        if self.clock()-self.started>60:self.cancel();raise ValueError('AI job timeout')
        code=self.process.poll()
        if code is None:return None
        self.done=True;p=self.path/'result.json'
        if code or not p.is_file() or p.stat().st_size>8192:raise ValueError('AI worker stopped')
        self.result=json.loads(p.read_text(encoding='utf-8'))
        if not self.result.get('ok'):raise ValueError('AI job failed')
        return self.result
    def cancel(self):
        if not self.cancelled:
            self.cancelled=True
            if self.process.poll() is None:
                try:
                    if os.name=='posix':os.killpg(self.process.pid,signal.SIGKILL)
                    else:self.process.kill()
                except ProcessLookupError:pass
    def reap(self,wait=0):
        try:self.process.wait(timeout=wait)
        except subprocess.TimeoutExpired:return False
        self.temp.cleanup();return True
