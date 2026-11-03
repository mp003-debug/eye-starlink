"""Offline local transcoding. No download, board dependency installation or hardware use."""
import argparse,json,re,subprocess,sys,tempfile,wave
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from eye_tracker.video_library import VideoLibrary,sha,WIDTH,HEIGHT,FPS,MAX_FILE,MAX_TOTAL
from eye_tracker.video_decode import opencv

def inside(path):
    path=Path(path).resolve()
    try:path.relative_to(ROOT)
    except ValueError:raise ValueError('video inputs and outputs must stay inside upgrade workspace')
    return path

def import_video(source,folder,key,title,seconds=60,audio=False):
    source=inside(source);folder=inside(folder)
    if not source.is_file():raise ValueError('local source file missing')
    if re.fullmatch('[a-zA-Z0-9_-]{1,40}',key) is None:raise ValueError('invalid clip id')
    if not 1<=len(title)<=24 or not title.isprintable():raise ValueError('title must be 1..24 printable characters')
    if type(seconds) is not int or not 1<=seconds<=60:raise ValueError('duration must be 1..60 seconds')
    folder.mkdir(parents=True,exist_ok=True);playlist=folder/'playlist.json'
    if playlist.exists():
        library=VideoLibrary(folder);data=json.loads(playlist.read_text(encoding='utf-8'));used=library.total_bytes
    else:data=dict(version=1,clips=[]);used=0
    if len(data['clips'])>=8 or any(c['id']==key for c in data['clips']):raise ValueError('video library full or id already used')
    if any((folder/(key+ext)).exists() for ext in ('.mp4','.wav')):raise ValueError('refusing to overwrite video assets')
    ffmpeg=ROOT/'tools/deps/audio_tools/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
    base=[str(ffmpeg),'-hide_banner','-loglevel','error','-nostdin','-protocol_whitelist','file,pipe','-i',str(source)]
    with tempfile.TemporaryDirectory(prefix='video_import_',dir=folder) as td:
        td=Path(td);mp4=td/(key+'.mp4')
        subprocess.run(base+['-map','0:v:0','-t',str(seconds),'-an','-vf',
            'setpts=PTS-STARTPTS,fps=8,scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2,setsar=1',
            '-c:v','libx264','-preset','veryfast','-crf','24','-maxrate','512k','-bufsize','1024k','-profile:v','baseline','-level','3.0',
            '-pix_fmt','yuv420p','-g','8','-bf','0','-threads','1','-movflags','+faststart',str(mp4)],check=True,timeout=180)
        cv2=opencv();cap=cv2.VideoCapture(str(mp4),cv2.CAP_FFMPEG);frames=0
        try:
            if not cap.isOpened() or abs(cap.get(cv2.CAP_PROP_FPS)-FPS)>.001:raise ValueError('imported video timing invalid')
            while True:
                ok,frame=cap.read()
                if not ok:break
                frames+=1
                if frames>seconds*FPS or frame.shape!=(HEIGHT,WIDTH,3):raise ValueError('imported video shape/length invalid')
        finally:cap.release()
        if not frames or not 0<mp4.stat().st_size<=MAX_FILE:raise ValueError('empty or oversized imported video')
        row=dict(id=key,title=title,file=mp4.name,sha256=sha(mp4),width=WIDTH,height=HEIGHT,fps=FPS,frames=frames,audio=None)
        files=[mp4]
        if audio:
            wav=td/(key+'.wav');raw=td/'audio_raw.wav'
            subprocess.run(base+['-map','0:a:0','-vn','-af','asetpts=PTS-STARTPTS,apad','-t',str(frames/FPS),'-ac','1','-ar','16000','-c:a','pcm_s16le',str(raw)],check=True,timeout=180)
            with wave.open(str(raw),'rb') as w:values=np.frombuffer(w.readframes(frames*2000),dtype='<i2').astype(np.int32)
            if len(values)!=frames*2000:raise ValueError('imported audio sample length mismatch')
            peak=int(np.max(np.abs(values)))
            if peak>8191:values=np.sign(values)*((np.abs(values)*8191+peak//2)//peak)
            with wave.open(str(wav),'wb') as w:
                w.setparams((1,2,16000,0,'NONE','not compressed'));w.writeframes(values.astype('<i2').tobytes())
            row['audio']=dict(file=wav.name,sha256=sha(wav));files.append(wav)
        if used+sum(p.stat().st_size for p in files)>MAX_TOTAL:raise ValueError('video library total storage bound exceeded')
        # Validate staged assets before publishing a catalogue entry.
        (td/'playlist.json').write_text(json.dumps(dict(version=1,clips=[row])),encoding='utf-8');VideoLibrary(td)
        for p in files:p.replace(folder/p.name)
        data['clips'].append(row);pending=folder/'playlist.json.pending'
        pending.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');pending.replace(playlist)
    return dict(clip=row,source_sha256=sha(source),bytes=sum((folder/p.name).stat().st_size for p in files),board_tested=False)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('--folder',type=Path,default=ROOT/'assets/video')
    p.add_argument('--id',required=True);p.add_argument('--title',required=True);p.add_argument('--seconds',type=int,default=60)
    p.add_argument('--audio',action='store_true',help='include matching bounded audio; fails if source has no audio')
    a=p.parse_args();print(json.dumps(import_video(a.source,a.folder,a.id,a.title,a.seconds,a.audio),ensure_ascii=False))
if __name__=='__main__':main()
