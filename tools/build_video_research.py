"""Build bounded synthetic video fixtures; no production UI changes or media download."""
import hashlib,json,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/video_research_20261031'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 ffmpeg=ROOT/'tools/deps/audio_tools/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
 assert ffmpeg.is_file()
 manifest={'version':1,'scope':'generated moving test pattern, not clinical or representative-content validation','fps':12,'frames':72,'seconds':6,'clips':[],'generator':subprocess.check_output([str(ffmpeg),'-version'],text=True).splitlines()[0]}
 for w,h in ((320,180),(480,270)):
  for codec,ext,args in [('raw','rgb565',['-c:v','rawvideo','-pix_fmt','rgb565le','-f','rawvideo']),('mjpeg','avi',['-c:v','mjpeg','-q:v','4','-pix_fmt','yuvj420p']),('h264','mp4',['-c:v','libx264','-preset','veryfast','-crf','24','-profile:v','baseline','-level','3.0','-pix_fmt','yuv420p','-g','12','-bf','0','-movflags','+faststart'])]:
   p=OUT/f'probe_{w}x{h}_{codec}.{ext}'
   if p.exists():raise ValueError('preserve existing evidence: '+str(p))
   subprocess.run([str(ffmpeg),'-hide_banner','-loglevel','error','-nostdin','-f','lavfi','-i',f'testsrc2=size={w}x{h}:rate=12','-frames:v','72','-an','-threads','1',*args,str(p)],check=True,timeout=60)
   if codec=='raw':assert p.stat().st_size==w*h*2*72
   manifest['clips'].append(dict(file=p.name,codec=codec,width=w,height=h,bytes=p.stat().st_size,sha256=sha(p)))
 (OUT/'fixtures.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
 protected=json.loads((ROOT/'build/daily_tools_20261031/protected_before.json').read_text())
 assert all(sha(ROOT/n)==digest for n,digest in protected.items())
 (OUT/'protected_before.json').write_text(json.dumps(protected,indent=2)+'\n',encoding='utf-8')
 with zipfile.ZipFile(ROOT/'build/daily_tools_20261031/eye_tracker_upgrade_daily_tools_verified.zip') as z:
  (OUT/'runtime_before.json').write_bytes(z.read('upgrade_manifest.json'))
 names=['tools/benchmark_video_research.py','build/video_research_20261031/fixtures.json']+[f'build/video_research_20261031/{c["file"]}' for c in manifest['clips']]
 hashes={n:sha(ROOT/n) for n in names}
 with zipfile.ZipFile(OUT/'probe_bundle.zip','x',zipfile.ZIP_DEFLATED) as z:
  for n in names:z.write(ROOT/n,n)
  z.writestr('transfer_manifest.json',json.dumps(hashes,indent=2))
 print(json.dumps(dict(clips=manifest['clips'],bundle_bytes=(OUT/'probe_bundle.zip').stat().st_size,bundle_sha256=sha(OUT/'probe_bundle.zip'))))
if __name__=='__main__':main()
