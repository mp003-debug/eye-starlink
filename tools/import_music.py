"""Import local PCM16 mono 16kHz WAV, bound its peak and update playlist."""
import argparse,hashlib,json,re,sys,wave
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from eye_tracker.music import MusicLibrary,BANK_SAMPLES,RATE


def import_track(source,key,title,root=ROOT):
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,39}',key) or not 1<=len(title)<=40 or any(ord(c)<32 for c in title):
        raise ValueError('id must be 1..40 lowercase letters/digits/underscore/hyphen; title 1..40 characters')
    folder=Path(root)/'assets/music'
    library=MusicLibrary(folder)
    if len(library.tracks)>=32 or any(t['id']==key for t in library.tracks):raise ValueError('playlist full or duplicate id')
    target=folder/(key+'.wav')
    if target.exists():raise ValueError('destination already exists; no overwrite')
    with wave.open(str(source),'rb') as reader:
        if (reader.getnchannels(),reader.getsampwidth(),reader.getframerate(),reader.getcomptype())!=(1,2,RATE,'NONE'):
            raise ValueError('convert source to PCM16 mono 16000Hz WAV before importing')
        total=reader.getnframes();seen=0;peak=0
        if not 0<total<=RATE*3600:raise ValueError('track must be between 0 and 1 hour')
        while seen<total:
            raw=reader.readframes(BANK_SAMPLES)
            if not raw or len(raw)%2:raise ValueError('truncated WAV')
            samples=np.frombuffer(raw,dtype='<i2');seen+=len(samples)
            peak=max(peak,int(np.abs(samples.astype(np.int32)).max()))
        reader.rewind();gain=min(1.,8191/max(1,peak))
        temporary=folder/(key+'.wav.pending')
        try:
            with wave.open(str(temporary),'wb') as out:
                out.setparams((1,2,RATE,total,'NONE',''))
                while True:
                    raw=reader.readframes(BANK_SAMPLES)
                    if not raw:break
                    samples=np.frombuffer(raw,dtype='<i2')
                    out.writeframesraw(np.rint(samples.astype(np.float64)*gain).astype('<i2').tobytes())
            temporary.replace(target)
        finally:
            if temporary.exists():temporary.unlink()
    h=hashlib.sha256()
    with target.open('rb') as f:
        for block in iter(lambda:f.read(65536),b''):h.update(block)
    playlist=folder/'playlist.json';data=json.loads(playlist.read_text(encoding='utf-8'))
    data['tracks'].append(dict(id=key,title=title,file=target.name,sha256=h.hexdigest()))
    staging=folder/'playlist.json.pending'
    staging.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');staging.replace(playlist)
    return dict(id=key,frames=total,gain=gain,sha256=h.hexdigest())


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('--id',required=True);p.add_argument('--title',required=True)
    a=p.parse_args();print(json.dumps(import_track(a.source,a.id,a.title),ensure_ascii=False))
    print('Rebuild title artwork with tools/build_ui_assets.py, then rebuild the upgrade package before deployment.')
