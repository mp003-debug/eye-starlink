"""Bounded board acceptance: explicit listening and physical helper input.

Synthetic positions are restricted to these test routines; they are not gaze.
"""
from dataclasses import asdict
import json,time
import numpy as np
from .audio import AudioDevice,AudioGpio,CodecBus,Codec,AudioError
from .controls import HelperButtons,apply_command
from .calibration import Context
from .interaction import DwellController,GazeSample


def test_controller():
    return DwellController(Context('helper-test','640x480','simulated'),'synthetic-helper-test-only')


def run_audio_test(mmio,bank,session,renderer,output,audible=False,now=time.monotonic,sleep=time.sleep):
    device=AudioDevice(mmio,now);codec=Codec(CodecBus(AudioGpio(mmio)))
    controller=test_controller();controller.pause(0)
    result={'analog_listening_verified':False,'analog_output_enabled':False,'real_gaze_validated':False,
            'phrases':[],'completed':False,'audible_requested':bool(audible)}
    buttons=HelperButtons();test_start=now()
    buttons.update(int(mmio.read(0x20))&15,0)
    def service(feedback):
        command=buttons.update(int(mmio.read(0x20))&15,(now()-test_start)*1000)
        if command:
            device.stop()
            result['interrupted_by']=command
            raise AudioError('audio test interrupted by '+command)
        session.present(renderer.rgb565(controller,feedback))
    try:
        result['codec']=codec.configure_muted()
        start=now();f0=mmio.read(0x24);b0=mmio.read(0x28)
        sleep(.3)
        f1=mmio.read(0x24);b1=mmio.read(0x28);elapsed=now()-start
        frames=(f1-f0)&0xffffffff;bits=(b1-b0)&0xffffffff
        result['clocks']={'interval_seconds':elapsed,'frames':frames,'bits':bits,
                          'lrclk_hz':frames/elapsed,'bclk_hz':bits/elapsed,'bclk_per_frame':bits/frames if frames else 0}
        if not 47040<=frames/elapsed<=48960 or not 63.8<=bits/max(1,frames)<=64.2:
            raise AudioError('codec frame/bit clock differs from 48kHz/64')
        if audible:
            codec.enable_output()
            result['analog_output_enabled']=True
        for key,values in bank.samples.items():
            feedback='speaking_'+key if audible else 'audio_test'
            service(feedback)
            device.play(values);started=now()
            while device.poll()=='busy':
                loop=now()
                service(feedback)
                sleep(max(0,.05-(now()-loop)))
            duration=now()-started
            if abs(duration-len(values)/16000)>.12:raise AudioError('unexpected phrase duration')
            result['phrases'].append({'key':key,'samples':len(values),'duration_seconds':duration,
                'expected_seconds':len(values)/16000,'pcm_readback_verified':True,'hardware_done':True})
            if audible:
                gap_end=now()+1.
                while now()<gap_end:
                    service('speech_ready')
                    sleep(.05)
        # Cancellation is digitally checked without adding an unexplained audible fragment.
        codec.mute()
        device.play(bank.samples['help']);sleep(.1);device.stop()
        result['explicit_stop_busy_cleared']=not bool(device.status()&1)
        result['completed']=True
        return result
    except BaseException as exc:
        result['error']='%s: %s'%(type(exc).__name__,exc)
        raise
    finally:
        errors=[]
        try:device.stop()
        except Exception as exc:errors.append(str(exc))
        try:codec.mute()
        except Exception as exc:errors.append(str(exc))
        result['cleanup_errors']=errors
        result['output_muted_on_exit']=not errors and codec.core_ready
        result['core_disabled_on_exit']=not codec.core_ready and not errors
        if errors:result['completed']=False
        (output/'audio_trace.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if errors and 'error' not in result:raise AudioError('; '.join(errors))


def run_control_test(mmio,session,renderer,output,seconds,now=time.monotonic,sleep=time.sleep,bank=None,event_link=None):
    # Only an explicit CLI --audible supplies the phrase bank; default stays silent.
    device=AudioDevice(mmio,now);device.stop()
    codec=Codec(CodecBus(AudioGpio(mmio))) if bank is not None else None
    buttons=HelperButtons();controller=test_controller();started=now();seq=0
    result={'input':'synthetic_only','real_gaze_validated':False,'audio_enabled':False,'commands':[],
            'actions':[],'speech_events':[],'completed':False,'uncalibrated_actions':0,'paused_actions':0}
    previous=started;intervals=[];hold_until=0;active=None;spoken_times=set()
    demo_ms=0.;demo_previous_ms=0.;demo_freeze_until=0.
    try:
        if codec:
            result['codec']=codec.configure_muted()
            codec.enable_output();result['audio_enabled']=True
            result['demo_pause_behavior']='freeze target during pause; hold same target for 3000ms after resume'
            demo_previous_ms=(now()-started)*1000
        while now()-started<seconds and not controller.closed:
            loop=now();ms=(loop-started)*1000
            comm_action=None
            raw=int(mmio.read(0x20))&15
            command=buttons.update(raw,ms)
            if command:
                # Commands are served before another sample or playback completion.
                device.stop()
                if event_link is not None:event_link.abort(ms,command)
                if active is not None:
                    result['speech_events'].append({'event':'interrupted','key':active,'time_ms':ms,'command':command})
                    active=None
                apply_command(controller,command,ms);hold_until=ms+500
                if bank is not None and command=='toggle_pause' and not controller.paused:
                    demo_freeze_until=ms+3000
                result['commands'].append({'command':command,'time_ms':ms,'raw':raw,
                    'paused':controller.paused,'calibration_valid':bool(controller.calibration_id),
                    'closed':controller.closed,'progress':controller.progress,'audio_busy_after':bool(device.status()&1),
                    'demo_time_ms':demo_ms,'demo_freeze_until_ms':demo_freeze_until})
            if bank is not None:
                # The test source pauses too, so resume cannot silently switch targets.
                # Keep feeding fresh samples at the same locked target during the hold.
                if not controller.paused:
                    demo_ms+=max(0.,ms-max(demo_previous_ms,demo_freeze_until))
                demo_previous_ms=ms
            if active is not None:
                if device.poll()=='done':
                    result['speech_events'].append({'event':'completed','key':active,'time_ms':ms})
                    active=None
            if active is not None:
                # Do not queue stale utterances or accrue a new dwell while speaking.
                controller.tick(ms)
                controller.reason='speaking'
            elif ms>=hold_until and not controller.closed:
                # Five seconds per target: a full dwell, phrase, then held-input lock.
                points=((.25,.37),(.75,.37),(.25,.70)) if bank is not None else ((.25,.37),(.75,.37))
                period=5000 if bank is not None else 4000
                point=points[int((demo_ms if bank is not None else ms)/period)%len(points)]
                seq+=1
                action=controller.feed(GazeSample(controller.context,'synthetic-helper-test-only',seq,ms,'valid',point),ms)
                if action:
                    comm_action=action
                    result['actions'].append(asdict(action))
                    if not controller.calibration_id:result['uncalibrated_actions']+=1
                    if controller.paused:result['paused_actions']+=1
                    if bank is not None and action.phrase:
                        if (controller.paused or controller.closed or not controller.calibration_id
                                or action.source!='simulated' or action.source_time_ms in spoken_times
                                or action.key not in bank.samples or action.phrase!=bank.text[action.key]):
                            raise AudioError('invalid or duplicate speech action')
                        device.play(bank.samples[action.key]);active=action.key
                        spoken_times.add(action.source_time_ms)
                        result['speech_events'].append({'event':'started','key':active,'time_ms':ms,
                                                       'source':'simulated','source_time_ms':action.source_time_ms})
            if event_link is not None:
                from .event_link import service_controller
                service_controller(event_link,controller,ms,comm_action)
            feedback='speaking_'+active if active else ('speech_controls' if bank is not None else 'controls')
            frame=renderer.rgb565(controller,feedback);session.present(frame)
            end=now();intervals.append((end-previous)*1000);previous=end
            sleep(max(0,.05-(now()-loop)))
        result.update(completed=True,elapsed_seconds=now()-started,displayed_frames=session.present_count,
                      exit_reason='BTN3' if controller.closed else 'duration',
                      max_update_interval_ms=max(intervals) if intervals else None,
                      p95_update_interval_ms=float(np.percentile(intervals,95)) if intervals else None)
        return result
    except BaseException as exc:
        result['error']='%s: %s'%(type(exc).__name__,exc)
        raise
    finally:
        errors=[]
        try:device.stop()
        except Exception as exc:errors.append(str(exc))
        if event_link is not None:
            try:event_link.abort((now()-started)*1000,'test_exit')
            except Exception as exc:errors.append(str(exc))
            result['communication']=event_link.snapshot()
        if active is not None:
            result['speech_events'].append({'event':'interrupted','key':active,'time_ms':(now()-started)*1000,'command':'test_exit'})
        if codec:
            try:codec.mute()
            except Exception as exc:errors.append(str(exc))
        result['cleanup_errors']=errors
        try:result['audio_stopped_on_exit']=not bool(device.status()&1)
        except Exception as exc:
            result['audio_stopped_on_exit']=False;errors.append(str(exc))
        result['output_muted_on_exit']=not errors and codec.core_ready if codec else None
        result['core_disabled_on_exit']=not codec.core_ready and not errors if codec else None
        if errors:result['completed']=False
        (output/'controls_trace.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if errors and 'error' not in result:raise AudioError('; '.join(errors))
