"""Fixed old/current FPGA comparison on a stationary paper target.
No classifier, display, audio or UART actions. Restores current FPGA and sensor.
Run only with exclusive board ownership and --load.
"""
import argparse, fcntl, hashlib, json, zipfile
from pathlib import Path
import numpy as np
from PIL import Image
from pynq import Overlay, MMIO, allocate, Clocks
from eye_tracker.board_io import VideoIO, UnsafeShutdown
from eye_tracker.board import hold_for_recovery
from eye_tracker.hardware_contract import verify_artifacts, configure_overlay_clocks
from eye_tracker.sensor import OpenDrainI2C, MT9V034

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data/private/bringup/release_capture_compare_20261028'
OLD_HASH={'bit':'1d546b9c7b63825ce075798df87aacccfa78fe37d3d26e379fd1dec6aca59ebc',
          'hwh':'00010d6b16adaa4acb7e91d26ff27c1a473151e7fbcd60adff098d66dc9c87a5'}
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def session():
    return VideoIO(MMIO(0x43000000,0x10000),MMIO(0x41200000,0x10000),MMIO(0x43C00000,0x1000),allocate)
def capture(label, bit):
    entry={'label':label,'bit_sha256':digest(bit),'frames':[],'completed':False}
    board=None; bus=None; sensor=None
    try:
        Overlay(str(bit),download=True)
        entry['clocks']=configure_overlay_clocks(Clocks)
        board=session(); board.prepare()
        bus=OpenDrainI2C(board.gpio); sensor=MT9V034.probe(bus)
        entry['manual']=sensor.apply_manual(240,32)
        board.wait_native_frames(4)
        entry['diag_before']=board.snapshot()
        folder=OUT/label; folder.mkdir()
        for i in range(8):
            pixels=board.capture_once()
            name='frame_%02d'%i
            raw=pixels.tobytes()
            (folder/(name+'.gray8')).write_bytes(raw)
            Image.fromarray(pixels).save(folder/(name+'.png'))
            entry['frames'].append({'raw':name+'.gray8','png':name+'.png','sha256':hashlib.sha256(raw).hexdigest(),'mean':float(pixels.mean()),'index':board.capture_index})
        entry['diag_after']=board.wait_native_frames(2)
        assert all(entry['diag_before'][k]==entry['diag_after'][k] for k in ('bad_lines','bad_frames'))
        entry['completed']=True
    except Exception as e:
        entry['error']=type(e).__name__+': '+str(e)
        raise
    finally:
        try:
            if board:
                try: board.close()
                except UnsafeShutdown as e: hold_for_recovery(board,e)
                entry['both_dma_halted_before_free']=board._both_halted()
                entry['reset_recovery_used']=board.reset_recovery_used
            if sensor:
                entry['sensor_restored']=sensor.restore()
                entry['sensor_after']=sensor.snapshot()
            if bus: bus.release()
        finally:
            (OUT/(label+'.json')).write_text(json.dumps(entry,indent=2)+'\n')
    return entry

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--load',action='store_true');a=p.parse_args()
    if not a.load:p.error('--load required')
    contract=verify_artifacts(ROOT)
    assert contract['artifact_hashes_verified']['bit']=='5bb403212a34a40afae678619a9b65f62dfac8c0e0748a125dfb601ff60b82ce'
    OUT.mkdir(exist_ok=False,parents=True)
    old=OUT/'reference';old.mkdir()
    with zipfile.ZipFile(ROOT/'build/recovery/before_uart_integration_20261027.zip') as z:
        for ext,h in OLD_HASH.items():
            b=z.read('build/fpga/eye_tracker.'+ext);assert hashlib.sha256(b).hexdigest()==h
            (old/('eye_tracker.'+ext)).write_bytes(b)
    current=ROOT/'build/fpga/eye_tracker.bit'
    report={'scope':'fixed paper, same manual exposure240/gain32, current-old-current capture-only','source_sha256':digest(Path(__file__)),'stages':[]}
    with open('/var/lock/eye_tracker_system.lock','a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        v=MMIO(0x43000000,0x10000)
        assert all((v.read(c+4)&1) and not(v.read(c)&5) for c in (0,0x30))
        try:
            for label,bit in [('current_before',current),('old_audio',old/'eye_tracker.bit'),('current_after',current)]:
                report['stages'].append(capture(label,bit))
        finally:
            Overlay(str(current),download=True)
            report['restored_current_clocks']=configure_overlay_clocks(Clocks)
            check=session();check.prepare();check.close()
            report['restored_current_bit_sha256']=digest(current)
            report['both_dma_halted_at_end']=check._both_halted()
            (OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    archive=ROOT/'build/deploy/release_capture_compare_20261028.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for f in sorted(OUT.rglob('*')):
            if f.is_file() and 'reference' not in f.relative_to(OUT).parts:z.write(f,f.relative_to(ROOT))
        z.write(Path(__file__),Path(__file__).relative_to(ROOT))
    print(json.dumps({'stages':[(x['label'],x['completed'],x['both_dma_halted_before_free']) for x in report['stages']],'restored_current':report['restored_current_bit_sha256'],'archive_sha256':digest(archive)}))
if __name__=='__main__':main()
