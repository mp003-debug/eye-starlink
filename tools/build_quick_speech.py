"""Generate the six approved fixed phrases locally, never the baseline WAVs."""
import hashlib,json,subprocess,sys,wave
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from eye_tracker.phrases import PHRASE_TEXT,PRIMARY_KEYS,QUICK_KEYS
from eye_tracker.audio import PhraseBank


def main():
    folder=ROOT/'assets/speech';stage=ROOT/'build/phrases_upgrade_20261029'
    stage.mkdir(parents=True,exist_ok=True)
    preserved={key:hashlib.sha256((folder/(key+'.wav')).read_bytes()).hexdigest() for key in PRIMARY_KEYS}
    source=stage/'synthesis_input.json'
    source.write_text(json.dumps([dict(key=k,text=PHRASE_TEXT[k]) for k in QUICK_KEYS],ensure_ascii=False),encoding='utf-8')
    raw_folder=stage/'synthesis'
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','RemoteSigned','-File',str(ROOT/'tools/synthesize_quick_phrases.ps1'),
                    '-CatalogPath',str(source),'-OutputDirectory',str(raw_folder)],capture_output=True,
                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    log=(result.stdout+result.stderr).decode('gb18030',errors='replace')
    (stage/'synthesis.log').write_text(log,encoding='utf-8')
    if result.returncode:raise RuntimeError('local SAPI synthesis failed: '+log)
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    prepared={}
    for key in QUICK_KEYS:
        with wave.open(str(raw_folder/(key+'.wav')),'rb') as w:
            if (w.getnchannels(),w.getsampwidth(),w.getframerate(),w.getcomptype())!=(1,2,16000,'NONE'):
                raise ValueError('unexpected SAPI PCM format')
            n=w.getnframes();raw=w.readframes(n)
        if not 0<n<=16000*8 or len(raw)!=n*2:raise ValueError('phrase exceeds 8 second limit; never truncate an utterance')
        samples=np.frombuffer(raw,dtype='<i2').astype(np.int32)
        peak=int(np.abs(samples).max())
        if peak==0:raise ValueError('silent synthesis')
        prepared[key]=np.rint(samples*min(1.,8191/peak)).astype('<i2')
    for key,pcm in prepared.items():
        path=folder/(key+'.wav')
        with wave.open(str(path),'wb') as w:
            w.setparams((1,2,16000,len(pcm),'NONE',''));w.writeframes(pcm.tobytes())
        manifest['phrases'][key]=dict(text=PHRASE_TEXT[key],file=path.name,samples=len(pcm),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),peak_abs_pcm=int(np.abs(pcm.astype(np.int32)).max()),
            source='Windows SAPI Microsoft Huihui Desktop; rate 0; locally generated 2026-10-29')
    (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    PhraseBank(include_quick=True)
    assert all(hashlib.sha256((folder/(k+'.wav')).read_bytes()).hexdigest()==v for k,v in preserved.items())
    print(json.dumps({k:manifest['phrases'][k] for k in QUICK_KEYS},indent=2))


if __name__=='__main__':main()
