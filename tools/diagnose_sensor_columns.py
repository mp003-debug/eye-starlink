"""Paper-only MT9V034 column-noise diagnostic, not a production sensor profile.
Fixed settings: onsemi MT9V034 Rev.G table8 p22 (current datasheet table8 p14).
https://www.onsemi.com/pdf/datasheet/mt9v034-d.pdf
Snapshots/readbacks/restores all five bias registers; no geometry/clock/reset writes.
The family ID is shared; module is supplier-marketed MT9V034.
"""
import argparse, hashlib, json, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REGS=(0x20,0x13,0x24,0x2B,0x2F)
PROFILES={'columns':((0x2B,3),(0x2F,3)),
          'recommended':((0x13,0x2D2E),(0x24,0x1B),(0x20,0x3C7),(0x2B,3),(0x2F,3))}
class BiasProbe:
    def __init__(self,bus,address):
        self.bus,self.address=bus,address
        self.original={r:bus.read16(address,r) for r in REGS}
    def snapshot(self):
        return {f'0x{r:02X}':self.bus.read16(self.address,r) for r in REGS+(0x42,0x47,0x48)}
    def write(self,r,v):
        if r not in REGS:raise ValueError('not a diagnostic bias register')
        self.bus.write16(self.address,r,v)
        if self.bus.read16(self.address,r)!=v:raise RuntimeError(f'bias readback mismatch {r:#x}')
    def restore(self):
        errors=[]
        for r in REGS:
            try:self.write(r,self.original[r])
            except Exception as e:errors.append(str(e))
        if errors:raise RuntimeError('bias restore failed: '+'; '.join(errors))
    def apply(self,name):
        if name not in PROFILES:raise ValueError('unknown fixed profile')
        self.restore()
        for r,v in PROFILES[name]:self.write(r,v)

def main():
    import fcntl
    from PIL import Image
    from pynq import Overlay,MMIO,allocate,Clocks
    from eye_tracker.sensor import OpenDrainI2C,MT9V034
    from eye_tracker.board_io import VideoIO,UnsafeShutdown
    from eye_tracker.board import hold_for_recovery
    from eye_tracker.hardware_contract import verify_artifacts,configure_overlay_clocks
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--load',action='store_true');args=p.parse_args()
    if not args.load:p.error('--load required')
    contract=verify_artifacts(ROOT)
    out=ROOT/'data/private/bringup/release_sensor_bias_20261028';out.mkdir(parents=True,exist_ok=False)
    report={'scope':'fixed paper only; temporary datasheet bias profiles; no gaze/display/audio/UART','source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'contract':contract,'stages':[],'completed':False}
    board=None;bus=None;sensor=None;probe=None
    with open('/var/lock/eye_tracker_system.lock','a+') as owner:
        fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
        v=MMIO(0x43000000,0x10000)
        assert all((v.read(c+4)&1) and not(v.read(c)&5) for c in (0,0x30))
        try:
            Overlay(str(ROOT/'build/fpga/eye_tracker.bit'),download=True)
            report['clocks']=configure_overlay_clocks(Clocks)
            board=VideoIO(MMIO(0x43000000,0x10000),MMIO(0x41200000,0x10000),MMIO(0x43C00000,0x1000),allocate)
            board.prepare();bus=OpenDrainI2C(board.gpio);sensor=MT9V034.probe(bus)
            report['manual']=sensor.apply_manual(240,32)
            assert bus.read16(sensor.address,0x0B)==240
            probe=BiasProbe(bus,sensor.address);report['bias_original']=probe.snapshot()
            for label in ('original_before','columns','recommended','original_after'):
                if label in PROFILES:probe.apply(label)
                else:probe.restore()
                for _ in range(6):board.wait_native_frames(10)
                entry={'label':label,'registers':probe.snapshot(),'frames':[],'diag_before':board.snapshot()}
                folder=out/label;folder.mkdir()
                for i in range(8):
                    pixels=board.capture_once();raw=pixels.tobytes();name=f'frame_{i:02d}'
                    (folder/(name+'.gray8')).write_bytes(raw)
                    Image.fromarray(pixels).save(folder/(name+'.png'))
                    entry['frames'].append({'raw':name+'.gray8','png':name+'.png','sha256':hashlib.sha256(raw).hexdigest(),'mean':float(pixels.mean())})
                entry['diag_after']=board.wait_native_frames(2)
                assert all(entry['diag_after'][k]==entry['diag_before'][k] for k in ('bad_lines','bad_frames'))
                report['stages'].append(entry)
            report['completed']=True
        except Exception as e:
            report['error']=type(e).__name__+': '+str(e)
        finally:
            try:
                if board:
                    try:board.close()
                    except UnsafeShutdown as e:hold_for_recovery(board,e)
                    report['both_dma_halted_before_free']=board._both_halted()
                    report['reset_recovery_used']=board.reset_recovery_used
                cleanup_errors=[]
                if probe:
                    try:probe.restore();report['bias_restored']=probe.snapshot()
                    except Exception as e:cleanup_errors.append('bias: '+str(e))
                if sensor:
                    try:report['sensor_controls_restored']=sensor.restore();report['sensor_after']=sensor.snapshot()
                    except Exception as e:cleanup_errors.append('controls: '+str(e))
                if bus:
                    try:bus.release()
                    except Exception as e:cleanup_errors.append('bus: '+str(e))
                if cleanup_errors:raise RuntimeError('; '.join(cleanup_errors))
            except Exception as e:report['restore_error']=type(e).__name__+': '+str(e);report['completed']=False
            finally:(out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    archive=ROOT/'build/deploy/release_sensor_bias_20261028.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob('*')):
            if f.is_file():z.write(f,f.relative_to(ROOT))
        z.write(Path(__file__),Path(__file__).relative_to(ROOT))
    print(json.dumps({'completed':report['completed'],'error':report.get('error'),'restore_error':report.get('restore_error'),'both_dma_halted':report.get('both_dma_halted_before_free'),'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}))
if __name__=='__main__':main()
