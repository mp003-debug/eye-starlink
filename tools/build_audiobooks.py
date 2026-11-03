"""Synthesize only original story text, then create bounded local PCM chapters."""
import argparse,asyncio,hashlib,json,subprocess,sys,urllib.request,wave
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/deps/voice_tools'))
VOICE='zh-CN-YunjianNeural'
RATE,PITCH='-12%','-6Hz'

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--synthesize',action='store_true');args=parser.parse_args()
    source=ROOT/'assets/audiobooks';out=ROOT/'build/pastimes_20261101/narration';out.mkdir(parents=True,exist_ok=True)
    stories=json.loads((source/'stories.json').read_text(encoding='utf-8'))['stories']
    if args.synthesize:
        import edge_tts
        proxy=urllib.request.getproxies().get('https')
        voices=await asyncio.wait_for(edge_tts.list_voices(proxy=proxy),45)
        selected=[v for v in voices if v['ShortName']==VOICE]
        assert len(selected)==1 and selected[0]['Gender']=='Male'
        (out/'voice.json').write_text(json.dumps(selected[0],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        for item in stories:
            path=out/(item['id']+'.mp3');signature=hashlib.sha256(item['text'].encode()).hexdigest()
            if path.exists():
                assert (out/(item['id']+'.text.sha256')).read_text()==signature
                continue
            talk=edge_tts.Communicate(item['text'],VOICE,rate=RATE,pitch=PITCH,proxy=proxy,connect_timeout=15,receive_timeout=60)
            pending=path.with_suffix('.pending.mp3');await asyncio.wait_for(talk.save(str(pending)),180)
            pending.replace(path);(out/(item['id']+'.text.sha256')).write_text(signature)
            print('Narration ready: '+item['id'],flush=True)
    ffmpeg=ROOT/'tools/deps/audio_tools/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
    tracks=[];report=[]
    for item in stories:
        path=out/(item['id']+'.mp3');raw=subprocess.check_output([str(ffmpeg),'-v','error','-i',str(path),'-f','s16le','-ac','1','-ar','16000','-'])
        data=np.frombuffer(raw,dtype='<i2').astype(np.float64);assert 16000*20<len(data)<16000*180
        peak=float(np.max(np.abs(data)));gain=min(1.,7600/max(peak,1.));data=np.rint(data*gain).astype('<i2')
        # Short fades suppress edge clicks; no time stretching or background music.
        n=min(320,len(data)//2);data[:n]=np.rint(data[:n]*np.linspace(0,1,n)).astype('<i2');data[-n:]=np.rint(data[-n:]*np.linspace(1,0,n)).astype('<i2')
        target=source/(item['id']+'.wav')
        with wave.open(str(target),'wb') as w:w.setparams((1,2,16000,len(data),'NONE',''));w.writeframes(data.tobytes())
        tracks.append(dict(id=item['id'],title=item['title'],file=target.name,sha256=hashlib.sha256(target.read_bytes()).hexdigest()))
        report.append(dict(id=item['id'],seconds=len(data)/16000,bytes=target.stat().st_size,peak=int(np.max(np.abs(data.astype(np.int32)))),gain=gain))
    (source/'playlist.json').write_text(json.dumps(dict(version=1,tracks=tracks),indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (source/'attribution.json').write_text(json.dumps(dict(original_text=True,synthetic_voice=True,voice=VOICE,rate=RATE,pitch=PITCH,
        service='Microsoft Edge online TTS via installed edge-tts',source='https://github.com/rany2/edge-tts',
        third_party_recording_used=False,scope='Local project samples; original fiction, no clinical benefit claim',chapters=report),indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps(dict(chapters=report,total_bytes=sum(r['bytes'] for r in report),total_seconds=sum(r['seconds'] for r in report))))

if __name__=='__main__':asyncio.run(main())
