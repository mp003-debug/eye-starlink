"""Isolated CPU file worker. No hardware, radio, network or audio-device access."""
import array,json,os,platform,subprocess,sys,wave
from pathlib import Path

def normalize_wav(source,dest):
    with wave.open(str(source),'rb') as w:
        count=w.getnframes();rate=w.getframerate()
        if w.getnchannels()!=1 or w.getsampwidth()!=2 or w.getcomptype()!='NONE' or not 8000<=rate<=48000 or not 0<count<=rate*60:
            raise ValueError('invalid synthesized audio')
        raw=w.readframes(count)
        if len(raw)!=count*2:raise ValueError('truncated synthesized audio')
    values=array.array('h',raw)
    if sys.byteorder!='little':values.byteswap()
    # Linear PCM resampling, bounded to one short utterance, in this worker only.
    size=count*16000//rate
    out=array.array('h')
    for i in range(size):
        q,r=divmod(i*rate,16000);a=values[min(q,count-1)];b=values[min(q+1,count-1)]
        out.append(round(a+(b-a)*r/16000))
    peak=max(abs(v) for v in out)
    if peak==0:raise ValueError('silent synthesized audio')
    if peak>8191:out=array.array('h',(round(v*8191/peak) for v in out))
    if sys.byteorder!='little':out.byteswap()
    with wave.open(str(dest),'wb') as w:
        w.setparams((1,2,16000,len(out),'NONE',''));w.writeframes(out.tobytes())
    return len(out)

def run(request,folder):
    if platform.system()!='Linux' or platform.machine()!='armv7l':raise ValueError('PYNQ ARMv7 worker required')
    import resource
    resource.setrlimit(resource.RLIMIT_AS,(192*1024*1024,192*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU,(50,55));resource.setrlimit(resource.RLIMIT_FSIZE,(4*1024*1024,4*1024*1024))
    os.nice(10)
    if 1 in os.sched_getaffinity(0):os.sched_setaffinity(0,{1})
    from .ai_bundle import AIBundle
    bundle=AIBundle(request['bundle'])
    if bundle.sha256!=request['bundle_sha256']:raise ValueError('bundle changed')
    text=request['text'];kind=request['kind']
    if not isinstance(text,str) or not 1<=len(text)<=64 or any(ord(c)<32 for c in text):raise ValueError('text bounds')
    if kind=='generate':
        from .tiny_tokenizer import TinyTokenizer
        tok=TinyTokenizer(bundle.path/'tokenizer.json')
        ids=tok.prompt('请把下面内容写成一句简短的第一人称表达，只输出句子：'+text)
        if len(ids)>192:raise ValueError('prompt too long')
        tokens=folder/'tokens.txt';tokens.write_text(' '.join(map(str,ids)))
        p=subprocess.run([str(bundle.path/'tiny_run'),str(bundle.path/'minimind_q8.bin'),str(tokens),'48'],capture_output=True,text=True,timeout=40,check=True)
        output=list(map(int,p.stdout.split()));metrics=json.loads(p.stderr)
        if not output or len(output)>=48 or any(not 0<=i<6400 for i in output):raise ValueError('incomplete generation')
        candidate=tok.decode(output).strip()
        if not 1<=len(candidate)<=64 or '\ufffd' in candidate:raise ValueError('candidate bounds')
        return dict(kind=kind,text=candidate)
    if kind=='synthesize':
        tts=bundle.path/'tts';source=folder/'source.txt';source.write_text(text,encoding='utf-8')
        env=dict(os.environ,LD_LIBRARY_PATH=str(tts/'lib'),ESPEAK_DATA_PATH=str(tts),LC_ALL='C.UTF-8')
        subprocess.run([str(tts/'bin/espeak-ng'),'--path='+str(tts),'-v','cmn','-s','155','-a','100','-b','1','-f','source.txt','-w','raw.wav'],
            cwd=str(folder),env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30,check=True)
        frames=normalize_wav(folder/'raw.wav',folder/'speech.wav')
        return dict(kind=kind,frames=frames)
    raise ValueError('unknown job')

def main():
    folder=Path(sys.argv[1]).resolve()
    try:
        p=folder/'request.json'
        if p.stat().st_size>4096:raise ValueError('request bounds')
        result=dict(ok=True,**run(json.loads(p.read_text(encoding='utf-8')),folder))
    except Exception:
        # No private prompt, generated text or library stderr in diagnostic logs.
        result=dict(ok=False,error='worker_failed')
    path=folder/'result.pending';path.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');path.replace(folder/'result.json')
if __name__=='__main__':main()
