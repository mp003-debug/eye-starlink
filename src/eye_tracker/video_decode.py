"""CPU-only spawned decoder. Never imports PYNQ or receives a hardware handle."""
import multiprocessing as mp
from queue import Empty,Full
import time
import numpy as np
from .video_library import WIDTH,HEIGHT,FPS,stamp

VIEW_WIDTH,VIEW_HEIGHT=352,198

def opencv():
    # Windows development dependency lives inside the upgrade workspace only.
    import sys
    from pathlib import Path
    if sys.platform=='win32':
        folder=Path(__file__).resolve().parents[2]/'tools/deps/opencv'
        if folder.is_dir() and str(folder) not in sys.path:sys.path.insert(0,str(folder))
    import cv2
    cv2.setNumThreads(1)
    return cv2

def _worker(clip,requests,results,halt):
    cap=None
    def send(item):
        while not halt.is_set():
            try:results.put(item,timeout=.05);return
            except Full:continue
    try:
        cv2=opencv()
        if stamp(clip['path'])!=clip['file_stamp']:raise ValueError('video file changed after validation')
        cap=cv2.VideoCapture(str(clip['path']),cv2.CAP_FFMPEG)
        if not cap.isOpened():raise ValueError('video decoder unavailable')
        if (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))!=(WIDTH,HEIGHT):raise ValueError('video dimensions mismatch')
        if abs(cap.get(cv2.CAP_PROP_FPS)-FPS)>.001 or int(cap.get(cv2.CAP_PROP_FRAME_COUNT))!=clip['frames']:raise ValueError('video timing mismatch')
        fourcc=int(cap.get(cv2.CAP_PROP_FOURCC)).to_bytes(4,'little').decode('ascii',errors='replace').lower()
        if fourcc not in ('avc1','h264'):raise ValueError('video must be imported H.264')
        xx=np.arange(VIEW_WIDTH)*WIDTH//VIEW_WIDTH;yy=np.arange(VIEW_HEIGHT)*HEIGHT//VIEW_HEIGHT
        mx,my=np.meshgrid(xx.astype(np.float32),yy.astype(np.float32))
        maps=cv2.convertMaps(mx,my,cv2.CV_16SC2,nninterpolation=True)
        index=-1
        while not halt.is_set():
            try:wanted=requests.get(timeout=.1)
            except Empty:continue
            if not 0<=wanted<clip['frames'] or wanted<=index:continue
            frame=None
            while index<wanted and not halt.is_set():
                ok,frame=cap.read();index+=1
                if not ok or frame.shape!=(HEIGHT,WIDTH,3):raise ValueError('video truncated or frame format changed')
            if halt.is_set():break
            words=cv2.cvtColor(frame,cv2.COLOR_BGR2BGR565).view('<u2').reshape(HEIGHT,WIDTH)
            display=cv2.remap(words,*maps,interpolation=cv2.INTER_NEAREST)
            send(('frame',index,display))
    except Exception as exc:send(('error',str(exc)))
    finally:
        if cap is not None:cap.release()
        # Parent may discard queued frames on cancellation. Never wait on its pipe.
        results.cancel_join_thread()

class Decoder:
    """One process, one pending request and two output frames; poll never waits."""
    def __init__(self,clip):
        ctx=mp.get_context('spawn')
        self.requests=ctx.Queue(1);self.results=ctx.Queue(2);self.halt=ctx.Event()
        self.process=ctx.Process(target=_worker,args=(clip,self.requests,self.results,self.halt),daemon=True)
        self.last_request=-1;self.closed=False
        self.process.start()

    def request(self,index):
        if self.closed or index<=self.last_request:return
        try:self.requests.put_nowait(index);self.last_request=index
        except Full:pass

    def poll(self):
        latest=None
        for _ in range(2):
            try:item=self.results.get_nowait()
            except Empty:break
            if item[0]=='error':raise ValueError(item[1])
            latest=(item[1],item[2])
        if latest is None and not self.process.is_alive():raise ValueError('video decoder exited')
        return latest

    def stop(self):
        if not self.closed:
            self.closed=True;self.halt.set()
            # This process has no hardware handles. Killing it cannot leave DMA owned.
            self.process.terminate()

    def reap(self,timeout=0):
        self.process.join(timeout)
        if self.process.is_alive():return False
        for q in (self.requests,self.results):q.cancel_join_thread();q.close()
        self.process.close();return True
