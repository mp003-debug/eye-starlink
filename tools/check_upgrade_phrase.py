"""One isolated fixed-phrase check on the already loaded upgrade audio IP.

Does not load a bitstream, start video DMA or enable eye/wireless input.
"""
import argparse,fcntl,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from upgrade_preflight import owners
from eye_tracker.audio import AudioDevice,PhraseBank,Codec,CodecBus,AudioGpio
from eye_tracker.music import StreamAudioDevice
from eye_tracker.phrase_audio import PhraseAudioDevice
from eye_tracker.hardware_contract import verify_artifacts,ADDRESSES

def main():
    p=argparse.ArgumentParser();p.add_argument('--audible',action='store_true')
    p.add_argument('--key',choices=('reposition','toilet'),default='reposition')
    p.add_argument('--gain-db',type=int,choices=(-6,-3,0),default=-6)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    output=a.output.resolve();output.relative_to(ROOT)
    if output.exists():raise ValueError('refuse to overwrite a prior check')
    owners();contract=verify_artifacts(ROOT);bank=PhraseBank(include_quick=True)
    report=dict(key=a.key,phrase=bank.text[a.key],audible=a.audible,completed=False,bit=contract['artifact_hashes_verified']['bit'],
                bitstream_loaded_this_check=False,camera_or_wireless_used=False,actual_listening_verified=False,
                headphone_gain_db=a.gain_db)
    with open('/var/lock/eye_tracker_system.lock','a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        from pynq import MMIO,Clocks
        if abs(Clocks.fclk0_mhz-50)>.1 or abs(Clocks.fclk1_mhz-100)>.1:raise ValueError('unexpected current PL clocks')
        mmio=MMIO(ADDRESSES['audio_aux_0'],0x20000)
        short=AudioDevice(mmio);device=PhraseAudioDevice(short,StreamAudioDevice(mmio))
        codec=Codec(CodecBus(AudioGpio(mmio)))
        try:
            device.stop();report['codec']=codec.configure_muted()
            if mmio.read(0x20)&15:raise ValueError('release helper buttons before the check')
            if a.audible:
                codec.enable_output()
                # ADAU1761 Rev F, R29/R30: volume bits 7:2 are -57 + code dB.
                volume=((57+a.gain_db)<<2)|3
                for reg in (0x4023,0x4024):codec.write(reg,volume)
                report['headphone_registers']=[codec.read(reg)[0] for reg in (0x4023,0x4024)]
            started=time.monotonic();device.play(bank.samples[a.key])
            while device.poll()!='done':
                if mmio.read(0x20)&15:raise ValueError('check interrupted by helper button')
                time.sleep(.005)
            report.update(completed=True,elapsed_seconds=time.monotonic()-started,
                          expected_samples=len(bank.samples[a.key]),consumed_samples=mmio.read(0x40))
        except BaseException as exc:
            report['error']=str(exc);raise
        finally:
            errors=[]
            for cleanup in (device.stop,codec.mute):
                try:cleanup()
                except Exception as exc:errors.append(str(exc))
            report.update(cleanup_errors=errors,output_muted_on_exit=not codec.output_enabled,audio_busy_on_exit=bool(mmio.read(0x0c)&1))
            if errors:report['completed']=False
            output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps(report,ensure_ascii=True))
            if errors:raise RuntimeError('; '.join(errors))

if __name__=='__main__':main()
