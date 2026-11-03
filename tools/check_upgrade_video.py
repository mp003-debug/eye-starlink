"""Bounded synthetic video check on the isolated upgrade board; no eye or UART actions."""
import argparse,fcntl,json,signal,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tools')]
from upgrade_preflight import owners
from eye_tracker.hardware_contract import verify_artifacts,ADDRESSES,configure_overlay_clocks
from eye_tracker.board_io import VideoIO,UnsafeShutdown
from eye_tracker.audio import AudioDevice,PhraseBank,Codec,CodecBus,AudioGpio
from eye_tracker.phrase_audio import PhraseAudioDevice
from eye_tracker.music import StreamAudioDevice
from eye_tracker.video import VideoPlayer
from eye_tracker.daily_tools import DailyTools
from eye_tracker.ui import BoardRenderer
from eye_tracker.interaction import DwellController
from eye_tracker.calibration import Context

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audible',action='store_true');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve();output.relative_to(ROOT)
    if output.exists():raise ValueError('preserve previous video evidence')
    owners();contract=verify_artifacts(ROOT);daily=DailyTools.from_root(ROOT,local_video=True)
    if len(daily.video_library.clips)!=1 or daily.video_library.clips[0]['frames']!=48:raise ValueError('expected one generated six-second fixture')
    renderer=BoardRenderer();renderer.bind_daily_tools(daily);bank=PhraseBank()
    controller=DwellController(Context('video-diagnostic','four','simulated'),'synthetic-only',music_enabled=True,quick_phrases=True,emotion_cards=True,daily_tools=daily)
    controller.page='local_tools';daily.state='video_view'
    report=dict(completed=False,scope='Scripted video/audio/display check. No camera capture, eye recognition or wireless.',audible=args.audible,
                boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),bit=contract['artifact_hashes_verified']['bit'],events=[],frames=[])
    output.mkdir(parents=True);signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
    with open('/var/lock/eye_tracker_system.lock','a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        from pynq import Overlay,MMIO,allocate,Clocks
        overlay=Overlay(str(ROOT/'build/fpga/eye_tracker.bit'),download=True)
        report['pl_clocks']=configure_overlay_clocks(Clocks)
        session=VideoIO(MMIO(ADDRESSES['vdma_0'],0x10000),MMIO(ADDRESSES['video_control'],0x10000),MMIO(ADDRESSES['camera_diag_0'],0x1000),allocate)
        mmio=MMIO(ADDRESSES['audio_aux_0'],0x20000);stream=StreamAudioDevice(mmio)
        codec=Codec(CodecBus(AudioGpio(mmio)));player=VideoPlayer(daily.video_library,stream);daily.video_player=player
        phrase=PhraseAudioDevice(AudioDevice(mmio),StreamAudioDevice(mmio))
        seen=set();started=time.monotonic();last=time.monotonic();max_gap=0
        def step():
            nonlocal last,max_gap
            if mmio.read(0x20)&15:raise ValueError('video check interrupted by helper button')
            player.poll()
            if player.state=='fault':raise ValueError('video fault: '+str(player.error))
            raw=renderer.rgb565(controller,'guide_ready');session.present(raw)
            now=time.monotonic();max_gap=max(max_gap,now-last);last=now
            report['frames'].append(dict(monotonic=now,**player.snapshot()))
            tag=(player.stats['starts'],player.frame_index,player.state)
            if tag not in seen and (player.frame_index in (0,8,16,24,32,40,47) or player.state in ('paused','ended')):
                seen.add(tag);(output/('ui_%03d.rgb565'%len(seen))).write_bytes(raw)
            if now-started>45:raise TimeoutError('video check time bound')
            return now
        try:
            stream.stop();report['codec']=codec.configure_muted();session.prepare();before=session.wait_native_frames(2)
            session.display_dynamic(renderer.rgb565(controller,'guide_ready'))
            if args.audible:codec.enable_output()
            player.play();paused=False;pause_at=None
            while player.state!='ended':
                now=step()
                if player.state=='playing' and player.position>=1.5 and not paused:
                    player.suspend();paused=True;pause_at=now;position=player.position
                    report['events'].append(dict(event='pause',position=position,audio_busy=bool(mmio.read(0x0c)&1)))
                elif player.state=='paused' and now-pause_at>=.8:
                    assert player.position==position
                    player.play();report['events'].append(dict(event='explicit_resume',position=position))
            report['events'].append(dict(event='natural_end',snapshot=player.snapshot(),consumed_register=mmio.read(0x40)))
            assert mmio.read(0x40)==96000-round(position*16000)
            # A second, explicitly started clip is interrupted by the original help phrase.
            while player.retired is not None:step()
            player.play()
            while player.state!='playing' or player.position<1.2:step()
            player.suspend();held=player.position;phrase.play(bank.samples['help'])
            report['events'].append(dict(event='help_started',video_position=held))
            while phrase.poll()!='done':step()
            assert player.state=='paused' and player.position==held
            report['events'].append(dict(event='help_completed',video_position=held))
            until=time.monotonic()+.8
            while time.monotonic()<until:step()
            assert player.state=='paused' and not mmio.read(0x0c)&1
            player.play()
            while player.state!='playing' or player.position<held+.6:step()
            player.action('video_exit');daily.state='media';step()
            assert player.offset==0 and player.frame is None and not mmio.read(0x0c)&1
            report['events'].append(dict(event='return_stopped',snapshot=player.snapshot()))
            after=session.wait_native_frames(1)
            assert all(before[k]==after[k] for k in ('bad_lines','bad_frames'))
            report.update(completed=True,elapsed_seconds=time.monotonic()-started,diagnostic_before=before,diagnostic_after=after,max_present_gap_seconds=max_gap)
        except BaseException as exc:
            report['error']=type(exc).__name__+': '+str(exc);raise
        finally:
            errors=[]
            for cleanup in (player.close,phrase.stop,stream.stop,codec.mute):
                try:cleanup()
                except Exception as exc:errors.append(str(exc))
            report['audio_busy_on_exit']=bool(mmio.read(0x0c)&1);report['output_muted_on_exit']=not codec.output_enabled
            try:session.close();report['both_dma_halted_before_free']=True
            except UnsafeShutdown as exc:
                report['both_dma_halted_before_free']=False;report['completed']=False
                (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
                from eye_tracker.board import hold_for_recovery
                hold_for_recovery(session,exc)
            except Exception as exc:errors.append(str(exc))
            report['reset_recovery_used']=session.reset_recovery_used;report['cleanup_errors']=errors
            if errors or report['audio_busy_on_exit']:report['completed']=False
            (output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps({k:v for k,v in report.items() if k!='frames'}),flush=True)
            if errors:raise RuntimeError('; '.join(errors))
if __name__=='__main__':main()
