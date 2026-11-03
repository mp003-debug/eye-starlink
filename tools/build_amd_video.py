"""Build the richer B1 candidate locally, without publishing or board access.

Generated keyframes, camera moves, animated light/type, original score and TTS.
Previous 30s source, output and builder checkpoint remain untouched.
"""
import hashlib
import json
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'build/amd_video_20261101/revision3'
SOURCES = ROOT/'assets/video_sources/amd_b1/revision3'
IMAGES = ROOT/'assets/video_sources/amd_b1/revision2'
FFMPEG = ROOT/'tools/deps/audio_tools/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
W, H, FPS, SECONDS, RATE = 1280, 720, 24, 45, 48000


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ffmpeg(args, log):
    with (OUT/log).open('w', encoding='utf-8') as stream:
        subprocess.run([str(FFMPEG), '-hide_banner', '-loglevel', 'warning',
            '-nostdin', '-n', *map(str, args)], cwd=ROOT, stdout=stream,
            stderr=stream, check=True, timeout=300)


def write_wav(path, samples):
    values = np.rint(np.clip(samples, -1, 1)*32767).astype('<i2')
    with wave.open(str(path), 'wb') as stream:
        stream.setparams((1 if values.ndim == 1 else values.shape[1], 2, RATE, 0, 'NONE', 'none'))
        stream.writeframes(values.tobytes())


def soundtrack():
    if (SOURCES/'mix.wav').exists():
        return json.loads((OUT/'audio.json').read_text(encoding='utf-8'))
    n = RATE*SECONDS
    license_data = json.loads((SOURCES/'music_license.json').read_text(encoding='utf-8'))
    song = SOURCES/'scott_buckley_titan.mp3'
    raw = subprocess.check_output([str(FFMPEG),'-v','error','-i',str(song),
        '-ss',str(license_data['excerpt_start_seconds']),'-t',str(SECONDS),
        '-af','highpass=f=35,equalizer=f=1800:t=q:w=0.7:g=-2',
        '-f','f32le','-ac','2','-ar',str(RATE),'-'])
    music = np.frombuffer(raw,dtype='<f4').reshape(-1,2).astype(np.float64)
    assert len(music)==n
    music *= .64/np.max(np.abs(music))
    timeline = np.arange(n)/RATE
    envelope = np.interp(timeline,[0,1.7,6,12,25,38,43,45],[0,.58,.70,.94,1,1,.8,0])
    music *= envelope[:,None]
    voice = np.zeros(n)
    duck = np.ones(n)
    metadata = json.loads((SOURCES/'narration.json').read_text(encoding='utf-8'))
    for i,row in enumerate(metadata['lines']):
        raw = subprocess.check_output([str(FFMPEG),'-v','error','-i',str(SOURCES/row['file']),
            '-af','highpass=f=70,equalizer=f=180:t=q:w=0.8:g=1.8,acompressor=threshold=0.125:ratio=2.5:attack=15:release=140:makeup=1.3',
            '-f','f32le','-ac','1','-ar',str(RATE),'-'])
        samples = np.frombuffer(raw,dtype='<f4').astype(np.float64)
        active = np.flatnonzero(np.abs(samples)>.004)
        assert len(active),'empty narration'
        samples = samples[max(0,active[0]-round(.06*RATE)):min(len(samples),active[-1]+round(.12*RATE))]
        samples *= .73/max(np.abs(samples))
        start,duration = row['start'],len(samples)/RATE
        next_start = metadata['lines'][i+1]['start'] if i+1<len(metadata['lines']) else 44.3
        assert start+duration<next_start,(row['text'],duration,next_start-start)
        a=round(start*RATE)
        voice[a:a+len(samples)] += samples
        row.update(duration=duration,end=start+duration)
        local=np.minimum(np.clip((timeline-start+.18)/.18,0,1),np.clip((start+duration+.65-timeline)/.65,0,1))
        duck=np.minimum(duck,1-.70*local)
    mixed=music*duck[:,None]+voice[:,None]
    peak=float(np.max(np.abs(mixed)))
    gain=min(1.,.95/peak)
    mixed*=gain
    assert np.max(np.abs(mixed))<=.950001
    write_wav(SOURCES/'score.wav',music)
    write_wav(SOURCES/'narration.wav',voice)
    write_wav(SOURCES/'mix.wav',mixed)
    music_info=dict(license_data,source_sha256=digest(song),source_bytes=song.stat().st_size)
    metadata.update(seconds=SECONDS,sample_rate=RATE,channels=2,samples=n,
        peak=float(np.abs(mixed).max()),music_peak=float(np.abs(music).max()),
        music=music_info,ducking='music falls to 30% during speech; 180ms attack / 650ms release',
        voice_processing='70Hz high-pass, +1.8dB at 180Hz, gentle 2.5:1 compression',
        final_mix_gain=gain,
        mix_rms=float(np.sqrt(np.mean(mixed**2))),
        score_rms=float(np.sqrt(np.mean(music**2))),
        mix_sha256=digest(SOURCES/'mix.wav'))
    (OUT/'audio.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return metadata


def base_video():
    # Reuse the exact approved scene edit. Only the new voice's subtitle timing
    # and a compact music attribution are composited over this base.
    base=ROOT/'build/amd_video_20261101/revision2/picture_base.mp4'
    assert base.is_file()
    return base


def typography_and_light(base, audio):
    master = SOURCES/'master.mkv'
    if master.exists():
        return master
    fonts={s:ImageFont.truetype('assets/fonts/noto_sans_cjk_sc.otf',s) for s in (20,24,32,36,42,44,52)}
    fonts.update({s:ImageFont.truetype('assets/fonts/noto_sans_cjk_sc.otf',s) for s in (48,56,64,78)})
    def appear(t,start,end):
        return min(1.,max(0.,(t-start)/.65),max(0.,(end-t)/.5))
    def text(draw,xy,value,size,alpha=1.,color=(245,242,236),anchor=None):
        draw.text(xy,value,font=fonts[size],fill=(*color,round(255*alpha)),anchor=anchor,
                  stroke_width=1,stroke_fill=(0,0,0,round(150*alpha)))
    log = (OUT/'composite.log').open('w',encoding='utf-8')
    command=[str(FFMPEG),'-hide_banner','-loglevel','warning','-nostdin','-n','-i',str(base),
        '-f','rawvideo','-pixel_format','rgba','-video_size',f'{W}x{H}','-framerate',str(FPS),'-i','pipe:0',
        '-i',str(SOURCES/'mix.wav'),'-filter_complex_threads','1','-filter_complex',
        '[0:v][1:v]overlay=shortest=1,fade=t=out:st=44.2:d=0.8,format=yuv420p[out]',
        '-map','[out]','-map','2:a','-t','45','-c:v','libx264','-preset','fast','-crf','18',
        '-threads','2','-c:a','pcm_s16le',str(master)]
    process=subprocess.Popen(command,cwd=ROOT,stdin=subprocess.PIPE,stdout=log,stderr=log)
    try:
        for index in range(SECONDS*FPS):
            t=index/FPS
            layer=Image.new('RGBA',(W,H))
            d=ImageDraw.Draw(layer)
            if 5.6<t<19.4:
                alpha=appear(t,5.6,19.4)
                for j in range(6):
                    phase=((t-5.6)*.12+j/6)%1
                    x=80+phase*1070
                    y=570-j*31-90*phase
                    d.line([(x-85,y+15),(x-25,y+15),(x,y),(x+20,y)],fill=(255,148,48,round(90*alpha)),width=2)
                    d.ellipse((x-3,y-3,x+3,y+3),fill=(255,208,126,round(150*alpha)))
            if 19.2<t<32.3:
                for j in range(24):
                    x=(j*179.3+t*(5+j%3))%W
                    y=(j*127.7-t*(3+j%4))%H
                    a=round(70*appear(t,19.2,32.3))
                    d.ellipse((x,y,x+2,y+2),fill=(255,181,84,a))
            titles=[(1.,5.6,(760,245),'想象，由此点亮','A SPARK OF POSSIBILITY'),
                    (6.3,11.4,(78,94),'微小之间 · 无限可能','THE POSSIBILITY WITHIN'),
                    (13.,18.5,(78,105),'AMD 锐龙','COMPUTE · PLAY · CREATE'),
                    (20.,24.6,(765,120),'探索新的边界','PLAY'),
                    (26.,31.6,(82,110),'让想法，成为作品','CREATE'),
                    (33.,37.5,(740,210),'专注当下','CREATE WHAT COMES NEXT')]
            for start,end,(x,y),title,eyebrow in titles:
                a=appear(t,start,end)
                if a>0:
                    dy=round(18*(1-a))
                    text(d,(x,y+dy),eyebrow,20,a,(244,169,87))
                    text(d,(x,y+42+dy),title,56,a)
                    d.line((x,y+112,x+round(130*a),y+112),fill=(244,143,51,round(200*a)),width=2)
            a=appear(t,38.1,44.7)
            if a:
                text(d,(760,205),'AMD',64,a)
                text(d,(756,282),'RYZEN',78,a)
                text(d,(760,395),'让灵感，持续向前',48,a)
                text(d,(760,465),'非官方概念展示',44,a,(190,183,177))
            for row in audio['lines']:
                a=appear(t,row['start']-.12,row['end']+.25)
                if a:
                    for y in range(H-155,H):
                        opacity=round(165*a*(y-(H-155))/155)
                        d.line((0,y,W,y),fill=(0,0,0,opacity))
                    lines=['']
                    for char in row['text']:
                        if d.textlength(lines[-1]+char,font=fonts[52])>W-140:
                            lines.append('')
                        lines[-1]+=char
                    for j,line in enumerate(lines):
                        text(d,(W//2,H-48-(len(lines)-1-j)*61),line,52,a,anchor='mm')
            # Draw credit after subtitle backing, so the backing cannot erase it.
            credit_alpha=appear(t,38.1,44.7)
            if credit_alpha:
                d.rounded_rectangle((44,544,654,621),radius=8,fill=(0,0,0,round(150*credit_alpha)))
                text(d,(58,550),"'Titan' by Scott Buckley · CC BY 4.0",24,credit_alpha,(208,203,197))
                text(d,(58,583),'www.scottbuckley.com.au · edited excerpt',24,credit_alpha,(208,203,197))
            process.stdin.write(layer.tobytes())
            if index%240==0:
                print(f'Composited {index}/{SECONDS*FPS} frames',flush=True)
        process.stdin.close()
        assert process.wait(timeout=180)==0,'FFmpeg composite failed'
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        log.close()
    return master


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    audio=soundtrack()
    base=base_video()
    master=typography_and_light(base,audio)
    preview=OUT/'amd_b1_cinematic_preview.mp4'
    if not preview.exists():
        ffmpeg(['-i',master,'-c:v','copy','-c:a','aac','-b:a','192k','-metadata','comment=Music: Titan by Scott Buckley (CC BY 4.0), https://www.scottbuckley.com.au/library/titan/ ; https://creativecommons.org/licenses/by/4.0/ ; edited excerpt 124.5-169.5s; mixed with synthetic narration.','-movflags','+faststart',preview],'preview.log')
    record=dict(seconds=SECONDS,frames=SECONDS*FPS,width=W,height=H,fps=FPS,
        method='generated keyframes, virtual camera moves, animated light paths, particles and typography; not physically modeled 3D animation',
        preview=str(preview.relative_to(ROOT)),preview_bytes=preview.stat().st_size,
        preview_sha256=digest(preview),master_sha256=digest(master),audio=audio,
        image_sha256={p.name:digest(p) for p in IMAGES.glob('*.png')},
        user_review='pending',board_tested=False,board_operations=False)
    (OUT/'render.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(preview_bytes=record['preview_bytes'],seconds=SECONDS,board_tested=False)),flush=True)


if __name__=='__main__':
    main()
