"""PC-only generated-clip decoder/player evidence; audio registers are simulated."""
import copy,json,sys,time,wave
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from eye_tracker.video_library import VideoLibrary,sha
from eye_tracker.video import VideoPlayer
from eye_tracker.video_decode import opencv
from eye_tracker.music import StreamAudioDevice
from test_music import StreamMMIO
from test_daily_tools import fixture
from eye_tracker.ui import BoardRenderer
from eye_tracker.interaction import DwellController
from eye_tracker.calibration import Context
from eye_tracker.framebuffer import unpack_rgb565

OUT=ROOT/'build/video_upgrade_20261101'
def main():
    library=VideoLibrary(OUT/'fixtures');cv2=opencv();clip=library.clips[0]
    cap=cv2.VideoCapture(str(clip['path']),cv2.CAP_FFMPEG);expected=[]
    try:
        while True:
            ok,bgr=cap.read()
            if not ok:break
            rgb=cv2.cvtColor(bgr,cv2.COLOR_BGR2BGR565).view('<u2').reshape(180,320)
            expected.append(rgb[(np.arange(198)*180//198)[:,None],(np.arange(352)*320//352)[None,:]])
    finally:cap.release()
    assert len(expected)==clip['frames']
    results=[];snapshots=[]
    for audible in (False,True):
        lib=copy.deepcopy(library)
        if not audible:lib.clips[0]['audio']=None
        t=[0.];m=StreamMMIO();p=VideoPlayer(lib,StreamAudioDevice(m),lambda:t[0]);d=fixture();d.video_library=lib;d.video_player=p
        c=DwellController(Context('offline','four','live'),'test',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=d)
        r=BoardRenderer();r.bind_daily_tools(d)
        def wait_frame(index):
            deadline=time.monotonic()+6
            while p.frame_index<index or p.state=='loading':
                p.poll()
                assert p.state!='fault',p.snapshot()
                assert time.monotonic()<deadline,p.snapshot()
                time.sleep(.002)
            np.testing.assert_array_equal(p.frame,expected[index])
        try:
            if audible:
                c.page='leisure';snapshots.append(('media entry',r.rgb565(c,'guide_ready')))
                c.page='local_tools'
                for state in ('media','video'):
                    d.state=state;snapshots.append((state,r.rgb565(c,'guide_ready')))
            p.play();wait_frame(0);d.state='video_view';c.page='local_tools'
            for index in range(clip['frames']):
                if index:
                    t[0]+=.125
                    if audible:m.consume(2000)
                    p.poll();wait_frame(index)
                if audible and index in (0,8,24,40):
                    c.target_key='tool_slot_3';c.progress=.5;snapshots.append(('frame '+str(index),r.rgb565(c,'guide_ready')))
                if index==16:
                    p.suspend();f=p.frame.copy();pos=p.position;t[0]+=3;p.poll()
                    assert pos==p.position;np.testing.assert_array_equal(f,p.frame);assert not m.busy
                    if audible:snapshots.append(('paused',r.rgb565(c,'guide_ready')))
                    p.play();wait_frame(index)
            t[0]+=.125
            if audible:m.consume(2000)
            p.poll();assert p.state=='ended',p.snapshot();assert not m.busy
            if audible:
                with wave.open(str(clip['audio']['path']),'rb') as w:values=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2')
                np.testing.assert_array_equal(m.played,values)
                snapshots.append(('ended',r.rgb565(c,'guide_ready')))
            results.append(dict(mode='simulated_audio_master' if audible else 'silent_clock',**p.snapshot(),all_rgb565_pixels_exact=True,audio_samples_compared=len(m.played)))
        finally:p.close()
    # A killed CPU worker must release video audio promptly and stay faulted.
    m=StreamMMIO();p=VideoPlayer(library,StreamAudioDevice(m))
    try:
        p.play();deadline=time.monotonic()+6
        while p.state=='loading' and time.monotonic()<deadline:p.poll();time.sleep(.01)
        assert p.state=='playing',p.snapshot();p.decoder.process.terminate();p.decoder.process.join(1.)
        p.poll();assert p.state=='fault' and not m.busy,p.snapshot()
        results.append(dict(mode='killed_decoder',**p.snapshot(),audio_stopped=True))
    finally:p.close()
    gallery=Image.new('RGB',(1280,520*((len(snapshots)+1)//2)),(230,238,232));draw=ImageDraw.Draw(gallery)
    for i,(label,raw) in enumerate(snapshots):
        rgb=unpack_rgb565(np.frombuffer(raw,dtype='<u2').reshape(480,640))
        x=i%2*640;y=i//2*520;gallery.paste(Image.fromarray(rgb),(x,y+30));draw.text((x+16,y+8),label,fill=(0,0,0))
    gallery.save(OUT/'ui_review.png')
    result=dict(scope='PC CPU decoder plus simulated audio registers/clock. No PYNQ, DMA, real audio or eye test.',
                clips=library.provenance(),decoder_cases=results,rendered_views=len(snapshots),ui_review_sha256=sha(OUT/'ui_review.png'),passed=True)
    (OUT/'offline_video.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
if __name__=='__main__':main()
