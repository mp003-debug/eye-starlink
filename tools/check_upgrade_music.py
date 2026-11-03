"""Bounded real-track check on the loaded upgrade audio IP; no eye/video/UART."""
import argparse,fcntl,json,resource,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools')]
from upgrade_preflight import owners
from eye_tracker.audio import Codec,CodecBus,AudioGpio
from eye_tracker.music import MusicLibrary,MusicPlayer,StreamAudioDevice
from eye_tracker.hardware_contract import verify_artifacts,ADDRESSES

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--audible',action='store_true')
    p.add_argument('--seconds',type=float,default=25)
    p.add_argument('--first-complete',action='store_true')
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    if not 1<=a.seconds<=60:p.error('--seconds must be 1..60')
    output=a.output.resolve();output.relative_to(ROOT)
    if output.exists():raise ValueError('refuse to overwrite evidence')
    owners();contract=verify_artifacts(ROOT);library=MusicLibrary(ROOT/'assets/music')
    if len(library.tracks)!=3:raise ValueError('expected the three selected tracks')
    if a.first_complete and library.tracks[0]['frames']>16000*180:raise ValueError('full first track limited to three minutes')
    report=dict(audible=a.audible,completed=False,tracks=[],library=library.provenance(),
        bit=contract['artifact_hashes_verified']['bit'],bitstream_loaded_this_check=False,
        camera_or_wireless_used=False,actual_listening_verified=False)
    with open('/var/lock/eye_tracker_system.lock','a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        from pynq import MMIO,Clocks
        if abs(Clocks.fclk0_mhz-50)>.1 or abs(Clocks.fclk1_mhz-100)>.1:raise ValueError('unexpected PL clocks')
        mmio=MMIO(ADDRESSES['audio_aux_0'],0x20000)
        device=StreamAudioDevice(mmio);player=MusicPlayer(device,library)
        codec=Codec(CodecBus(AudioGpio(mmio)))
        try:
            device.stop();report['codec']=codec.configure_muted()
            if mmio.read(0x20)&15:raise ValueError('release helper buttons')
            if a.audible:codec.enable_output()
            report['headphone_registers']=[codec.read(reg)[0] for reg in (0x4023,0x4024)]
            for index,track in enumerate(library.tracks):
                player.index=index;player.play();started=previous=time.monotonic();max_gap=0
                full=bool(index==0 and a.first_complete)
                limit=track['frames']/16000+3 if full else a.seconds
                while player.state!='ended':
                    now=time.monotonic();max_gap=max(max_gap,now-previous);previous=now
                    if mmio.read(0x20)&15:raise ValueError('music check interrupted by helper button')
                    player.poll()
                    if now-started>=limit:
                        if full:raise ValueError('complete-track timeout')
                        break
                    time.sleep(.005)
                consumed=mmio.read(0x40)
                if full and (player.state!='ended' or consumed!=track['frames']):raise ValueError('sample count mismatch')
                row=dict(id=track['id'],elapsed_seconds=time.monotonic()-started,
                    consumed_samples=consumed,expected_total_samples=track['frames'],
                    natural_end=player.state=='ended',max_poll_gap_seconds=max_gap,
                    max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
                report['tracks'].append(row);print(json.dumps(row),flush=True)
                player.stop();device.stop()
                if index<2:time.sleep(2)
            report['completed']=True
        except BaseException as exc:
            report['error']=str(exc);raise
        finally:
            errors=[]
            for cleanup in (player.stop,device.stop,codec.mute):
                try:cleanup()
                except Exception as exc:errors.append(str(exc))
            report.update(cleanup_errors=errors,output_muted_on_exit=not codec.output_enabled,
                          audio_busy_on_exit=bool(mmio.read(0x0c)&1))
            if errors:report['completed']=False
            output.parent.mkdir(parents=True,exist_ok=True)
            output.write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report),flush=True)
            if errors:raise RuntimeError('; '.join(errors))

if __name__=='__main__':main()
