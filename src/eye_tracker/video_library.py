"""Strict offline catalogue for small, pre-transcoded local clips."""
import hashlib,json,re,wave
from pathlib import Path
import numpy as np

WIDTH,HEIGHT,FPS=320,180,8
MAX_FRAMES=60*FPS
MAX_FILE=8*1024*1024
MAX_TOTAL=64*1024*1024

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(65536),b''):h.update(block)
    return h.hexdigest()

def stamp(path):
    s=Path(path).stat();return (s.st_size,s.st_mtime_ns)

class VideoLibrary:
    def __init__(self,folder):
        self.folder=Path(folder).resolve();p=self.folder/'playlist.json'
        if p.stat().st_size>16384:raise ValueError('video playlist too large')
        raw=p.read_bytes();self.playlist_sha256=hashlib.sha256(raw).hexdigest();data=json.loads(raw)
        if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('clips'),list) or len(data['clips'])>8:
            raise ValueError('invalid bounded video playlist')
        self.clips=[];ids=set();total=0
        def asset(name,digest,suffix):
            nonlocal total
            if not isinstance(name,str) or re.fullmatch(r'[a-zA-Z0-9_-]+\.'+suffix,name) is None:
                raise ValueError('video asset must be a simple local filename')
            path=(self.folder/name).resolve()
            if path.parent!=self.folder:raise ValueError('video asset escapes library')
            size=path.stat().st_size;total+=size
            if not 0<size<=MAX_FILE or total>MAX_TOTAL:raise ValueError('video storage bound exceeded')
            if not isinstance(digest,str) or sha(path)!=digest:raise ValueError('video SHA256 mismatch')
            return path
        for row in data['clips']:
            if not isinstance(row,dict):raise ValueError('invalid video entry')
            key,title,frames=(row.get(k) for k in ('id','title','frames'))
            if not isinstance(key,str) or re.fullmatch('[a-zA-Z0-9_-]{1,40}',key) is None or key in ids:
                raise ValueError('invalid video id')
            if not isinstance(title,str) or not 1<=len(title)<=24 or not title.isprintable():raise ValueError('invalid video title')
            if type(frames) is not int or not 1<=frames<=MAX_FRAMES:raise ValueError('video duration outside 0..60 seconds')
            if (row.get('width'),row.get('height'),row.get('fps'))!=(WIDTH,HEIGHT,FPS):raise ValueError('video requires 320x180 at 8 fps')
            path=asset(row.get('file'),row.get('sha256'),'mp4')
            clip=dict(id=key,title=title,path=path,frames=frames,sha256=row['sha256'],file_stamp=stamp(path),audio=None)
            if row.get('audio') is not None:
                a=row['audio']
                if not isinstance(a,dict):raise ValueError('invalid video audio')
                wav=asset(a.get('file'),a.get('sha256'),'wav')
                with wave.open(str(wav),'rb') as w:
                    samples=frames*2000
                    if (w.getnchannels(),w.getsampwidth(),w.getframerate(),w.getcomptype(),w.getnframes())!=(1,2,16000,'NONE',samples):
                        raise ValueError('video audio must be matching PCM16 mono 16kHz')
                    seen=0
                    while seen<samples:
                        raw=w.readframes(16384)
                        if not raw or len(raw)%2:raise ValueError('truncated video audio')
                        values=np.frombuffer(raw,dtype='<i2');seen+=len(values)
                        if np.max(np.abs(values.astype(np.int32)))>8191:raise ValueError('video audio peak too high')
                clip['audio']=dict(id=key,title=title,path=wav,frames=samples,sha256=a['sha256'],file_stamp=stamp(wav))
            self.clips.append(clip);ids.add(key)
        self.total_bytes=total

    def provenance(self):
        return dict(playlist_sha256=self.playlist_sha256,bytes=self.total_bytes,
            clips=[dict(id=c['id'],frames=c['frames'],sha256=c['sha256'],audio_sha256=c['audio']['sha256'] if c['audio'] else None) for c in self.clips])
