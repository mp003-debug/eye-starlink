"""CPU/file-only feasibility probe. NEVER opens camera, /dev/mem, DMA or audio.

Each decoder lives in a bounded subprocess. No live gaze actions are generated.
The representative eye workload replays five existing reference frames only;
timings do not constitute a new calibration or accuracy check.
"""
import argparse,hashlib,json,os,platform,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'build/video_research_20261031'
sys.path.insert(0,str(ROOT/'src'))
if platform.system()=='Windows':sys.path.insert(0,str(ROOT/'tools/deps/opencv'))
import numpy as np

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def stats(values):
 a=np.asarray(values,float);return dict(count=len(a),median_ms=float(np.median(a)*1000),p95_ms=float(np.percentile(a,95)*1000),max_ms=float(a.max()*1000))
def memory():
 if platform.system()!='Linux':return {}
 return {k:int(v.split()[0]) for k,v in (s.split(':',1) for s in Path('/proc/self/status').read_text().splitlines()) if k in ('VmRSS','VmHWM','Threads')}
def validated_manifest():
 p=OUT/'fixtures.json'
 if p.stat().st_size>65536:raise ValueError('oversized fixture manifest')
 m=read(p)
 if m['version']!=1 or m['fps']!=12 or m['frames']!=72 or len(m['clips'])!=6:raise ValueError('unexpected probe')
 for c in m['clips']:
  p=(OUT/c['file']).resolve();p.relative_to(OUT.resolve())
  if p.name!=c['file'] or c['codec'] not in ('raw','mjpeg','h264') or (c['width'],c['height']) not in ((320,180),(480,270)):raise ValueError('unexpected clip')
  if p.stat().st_size!=c['bytes'] or sha(p)!=c['sha256']:raise ValueError('clip mismatch')
 return m

class Reader:
 def __init__(self,clip):
  import cv2
  self.cv=cv2;self.clip=clip;self.cap=None;self.file=None
  self.shape=(clip['height'],clip['width']);self.count=0
  p=OUT/clip['file']
  if clip['codec']=='raw':
   self.file=p.open('rb');self.buffer=bytearray(self.shape[0]*self.shape[1]*2)
  else:
   self.cap=cv2.VideoCapture(str(p),cv2.CAP_FFMPEG)
   if not self.cap.isOpened():raise ValueError('decoder unavailable')
 def next(self):
  started=time.perf_counter()
  if self.file:
   n=self.file.readinto(self.buffer)
   if n==0:return None,0,0
   if n!=len(self.buffer):raise ValueError('short raw frame')
   decoded=time.perf_counter();words=np.frombuffer(self.buffer,dtype='<u2').reshape(self.shape)
  else:
   ok,bgr=self.cap.read()
   if not ok:return None,0,0
   decoded=time.perf_counter()
   if bgr.shape!=self.shape+(3,):raise ValueError('decoded geometry changed')
   packed=self.cv.cvtColor(bgr,self.cv.COLOR_BGR2BGR565)
   words=packed.view('<u2').reshape(self.shape)
  self.count+=1
  return words,decoded-started,time.perf_counter()-decoded
 def close(self):
  if self.cap is not None:self.cap.release()
  if self.file is not None:self.file.close()

def eye_workload():
 """Frozen-model feature extraction on recorded reference frames, no actions."""
 from eye_tracker.appearance_diagnostic import AppearanceDiagnostic
 p=read(ROOT/'data/private/profiles/current_eye.json')
 engine=AppearanceDiagnostic(ROOT/p['model'])
 run=ROOT/'data/private/runs/eye_20250509T130243Z_d86c5c240d7d46899314233db8821c19'
 if not run.exists():
  run=ROOT/'build/daily_tools_20261031/favorites_check_evidence'/run.relative_to(ROOT)
 manifest=read(run/'targets/manifest.json')
 assert len(manifest['samples_detail'])==5
 # Only the frozen matching neighborhood from this recorded run is replayed.
 # No new reference gate is passed and no controller receives these samples.
 visual=read(run/'visual_trial.json')
 neighborhood=[e for e in visual['reposition_events'] if e['event']=='ready'][-1]['neighborhood']
 engine.anchor.origin_shift=np.array(neighborhood['current_origin'])
 frames=[np.fromfile(run/'targets'/f'sample_{i:02d}.gray8',dtype=np.uint8).reshape(480,640) for i in range(5)]
 features=[]
 for pixels in frames:
  feature,_=engine.feature(pixels);features.append(feature)
 def work(i):
  feature,_=engine.feature(frames[i%5])
  engine.model.propose(feature,engine.geometry_id)
 return work,dict(scope='recorded center-frame feature/classifier CPU load only; no live gaze or selection',frames=5,model_sha256=sha(ROOT/p['model']))

def child(index,mode,resize='numpy'):
 import cv2
 cv2.setNumThreads(1)
 m=validated_manifest();clip=m['clips'][index]
 from eye_tracker.framebuffer import pack_rgb565
 colors=np.array([[[0,0,255],[0,255,0],[255,0,0],[79,127,211]]],dtype=np.uint8)
 assert np.array_equal(cv2.cvtColor(colors,cv2.COLOR_BGR2BGR565).view('<u2').reshape(1,4),pack_rgb565(colors[:,:,::-1]))
 workload=lambda i:None;work_info=None;renderer=None
 if mode=='replay':
  workload,work_info=eye_workload()
  from eye_tracker.ui import BoardRenderer
  from eye_tracker.interaction import DwellController
  from eye_tracker.calibration import Context
  renderer=BoardRenderer();controller=DwellController(Context('video-cpu-probe','recorded','live'))
 # Fit 16:9 source into the current 608x296 viewing area, preserving aspect.
 yy=np.minimum(np.arange(296)*clip['height']//296,clip['height']-1)
 xx=np.minimum(np.arange(526)*clip['width']//526,clip['width']-1)
 probe=np.arange(clip['width']*clip['height'],dtype=np.uint16).reshape(clip['height'],clip['width'])
 mx,my=np.meshgrid(xx.astype(np.float32),yy.astype(np.float32))
 maps=cv2.convertMaps(mx,my,cv2.CV_16SC2,nninterpolation=True)
 assert np.array_equal(cv2.remap(probe,*maps,interpolation=cv2.INTER_NEAREST),probe[yy[:,None],xx[None,:]])
 screen=np.zeros((480,640),dtype='<u2');decode=[];convert=[];compose=[];loops=[];eyes=[];checks=[];previews={}
 begin=time.perf_counter();cpu=time.process_time();opened=begin;reader=Reader(clip);open_ms=(time.perf_counter()-opened)*1000
 first=None
 try:
  for i in range(72):
   t=time.perf_counter();pixels,d,c=reader.next()
   if pixels is None:raise ValueError('early decoder EOF')
   if first is None:first=time.perf_counter()-begin
   dt=time.perf_counter();workload(i);eyes.append(time.perf_counter()-dt)
   dt=time.perf_counter()
   if renderer:screen[:]=np.frombuffer(renderer.rgb565(controller),dtype='<u2').reshape(480,640)
   screen[112:408,57:583]=(cv2.remap(pixels,*maps,interpolation=cv2.INTER_NEAREST) if resize=='opencv' else pixels[yy[:,None],xx[None,:]])
   # Include serialization to the existing display transfer format, without DMA.
   output=screen.tobytes();checks.append(output[160000]);compose.append(time.perf_counter()-dt)
   decode.append(d);convert.append(c);loops.append(time.perf_counter()-t)
   if i in (0,35,71):previews[i]=screen.copy()
  if reader.next()[0] is not None:raise ValueError('unexpected extra frames')
 finally:reader.close()
 wall=time.perf_counter()-begin;cpu=time.process_time()-cpu;mem=memory()
 for i,screen in previews.items():np.save(OUT/f'preview_{index}_{mode}_{resize}_{i}.npy',screen,allow_pickle=False)
 return dict(index=index,file=clip['file'],mode=mode,resize=resize,nearest_pixels_equivalent=True,frames=72,open_ms=open_ms,first_frame_ms=first*1000,wall_seconds=wall,cpu_seconds=cpu,cpu_percent_one_core=100*cpu/wall,effective_unpaced_fps=72/wall,decode=stats(decode),convert=stats(convert),compose=stats(compose),eye_replay=stats(eyes),loop=stats(loops),over_83ms=sum(x>1/12 for x in loops),over_125ms=sum(x>.125 for x in loops),over_150ms=sum(x>.150 for x in loops),memory=mem,workload=work_info,hardware_touched=False)

def main():
 p=argparse.ArgumentParser();p.add_argument('--child',type=int);p.add_argument('--mode',choices=('decode','replay'),default='decode');p.add_argument('--local-check',action='store_true');p.add_argument('--optimized',action='store_true');p.add_argument('--resize',choices=('numpy','opencv'),default='numpy');a=p.parse_args()
 if a.child is not None:
  if not 0<=a.child<6:p.error('invalid clip index')
  print(json.dumps(child(a.child,a.mode,a.resize)));return
 validated_manifest()
 if not a.local_check:
  assert platform.system()=='Linux' and ROOT==Path('/home/xilinx/Eye_Tracker_Upgrade_Version')
  subprocess.run(['/usr/bin/python3','tools/upgrade_preflight.py','--owners'],cwd=ROOT,check=True)
  # Hold the same advisory lock as the runtime even though no MMIO is used.
  import fcntl
  lock=open('/var/lock/eye_tracker_system.lock','r')
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 import cv2
 result=dict(scope='CPU and cached file decoding only; no camera, physical display, audible audio or eye selection',hostname=platform.node(),machine=platform.machine(),cv2=cv2.__version__,video_build=[s.strip() for s in cv2.getBuildInformation().splitlines() if any(k in s for k in ('Video I/O','FFMPEG','avcodec','avformat','swscale','GStreamer'))],ffmpeg_cli=shutil.which('ffmpeg'),cores=os.cpu_count(),runs=[],live_eye_tested=False,audio_video_sync_tested=False,hardware_touched=False,process_timeout_seconds=60)
 for mode in (('replay',) if a.optimized else ('decode','replay')):
  for index in ((2,5) if a.optimized else range(6)):
   proc=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child',str(index),'--mode',mode,'--resize','opencv' if a.optimized else 'numpy'],cwd=ROOT,capture_output=True,text=True,timeout=60)
   if proc.returncode:result['runs'].append(dict(index=index,mode=mode,error=proc.stderr[-2000:],exit_code=proc.returncode))
   else:result['runs'].append(json.loads(proc.stdout))
   print(json.dumps(result['runs'][-1]),flush=True)
 if not a.local_check:
  result['boot_id']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
  subprocess.run(['/usr/bin/python3','tools/upgrade_preflight.py','--owners'],cwd=ROOT,check=True)
 dest=OUT/(('local_' if a.local_check else 'board_')+('optimized.json' if a.optimized else 'benchmark.json'))
 result['probe_source_sha256']=sha(Path(__file__).resolve())
 dest.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
 print('REPORT',dest.name,sha(dest),flush=True)
 if not a.local_check:lock.close()
if __name__=='__main__':main()
