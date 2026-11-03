import json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from eye_tracker.audio import AudioDevice,AudioError,AudioGpio,Codec,CodecBus,PhraseBank,ROOT
from eye_tracker.controls import HelperButtons,apply_command
from eye_tracker.auxiliary import run_control_test,run_audio_test,test_controller
from eye_tracker.interaction import GazeSample

class FakeMMIO:
    def __init__(self):
        self.regs={0:0x41554431,4:0x10000,12:8,0x1c:7,0x18:0}
        self.array=np.zeros(0x20000//4,dtype='<u4');self.writes=[]
    def read(self,reg):return self.regs.get(reg,0)
    def write(self,reg,value):
        self.writes.append((reg,value));self.regs[reg]=value
        if reg==8:
            if value==1:self.regs[12]=9
            elif value==2:self.regs[12]&=~1
            elif value==4:self.regs[12]&=~6

class AudioTests(unittest.TestCase):
    def test_phrase_bank_is_bounded_local_and_verified(self):
        b=PhraseBank()
        self.assertEqual(set(b.samples),{'water','rest','help'})
        for samples in b.samples.values():
            self.assertLessEqual(len(samples),32768)
            self.assertLessEqual(np.abs(samples.astype('i4')).max(),8191)
        with tempfile.TemporaryDirectory() as folder:
            dest=Path(folder)/'speech';shutil.copytree(ROOT/'assets/speech',dest)
            (dest/'help.wav').write_bytes(b'corrupt')
            with self.assertRaisesRegex(AudioError,'hash'):PhraseBank(dest)
    def test_pcm_packing_odd_negative_and_readback(self):
        m=FakeMMIO();a=AudioDevice(m,lambda:0)
        a.play(np.array([0x1234,-292,12],dtype='<i2'))
        self.assertEqual(list(m.array[16384:16386]),[0xfedc1234,12])
        self.assertEqual(m.regs[16],3)
        self.assertEqual(a.poll(),'busy')
        m.regs[12]=10
        self.assertEqual(a.poll(),'done');self.assertEqual(a.poll(),'idle')
    def test_busy_cannot_overwrite_pcm_or_restart(self):
        m=FakeMMIO();a=AudioDevice(m);a.play(np.array([12,24],dtype='<i2'))
        previous=m.array.copy();writes=list(m.writes)
        with self.assertRaisesRegex(AudioError,'busy'):a.play(np.array([-20],dtype='<i2'))
        np.testing.assert_array_equal(previous,m.array);self.assertEqual(m.writes,writes)
    def test_invalid_hardware_rejected_before_writes(self):
        for reg,value in ((0,0),(4,2),(12,9)):
            m=FakeMMIO();m.regs[reg]=value
            with self.assertRaises(AudioError):AudioDevice(m)
            self.assertEqual(m.writes,[])
    def test_clock_fault_and_timeout_stop_playback(self):
        m=FakeMMIO();clock=[0.];a=AudioDevice(m,lambda:clock[0])
        a.play(np.array([1]*1600,dtype='<i2'));clock[0]=1
        with self.assertRaisesRegex(AudioError,'timeout'):a.poll()
        self.assertFalse(m.regs[12]&1)
        clock[0]=2;a.play(np.array([1],dtype='<i2'));m.regs[12]=13
        with self.assertRaisesRegex(AudioError,'clock fault'):a.poll()
        self.assertFalse(m.regs[12]&1)
    def test_clock_missing_and_invalid_formats_do_not_write(self):
        m=FakeMMIO();a=AudioDevice(m)
        for sample in (np.array([],dtype='<i2'),np.zeros(32769,dtype='<i2'),np.zeros(3,dtype='f4'),np.zeros((2,2),dtype='<i2')):
            with self.assertRaises(ValueError):a.play(sample)
        m.regs[12]=0
        with self.assertRaisesRegex(AudioError,'clock'):a.play(np.array([1],dtype='<i2'))
        self.assertEqual(m.writes,[])
    def test_unexpected_stop_is_not_reported_as_completion(self):
        m=FakeMMIO();a=AudioDevice(m);a.play(np.array([1],dtype='<i2'));m.regs[12]=8
        with self.assertRaisesRegex(AudioError,'without completion'):a.poll()
    def test_i2c_adapter_does_not_touch_camera_video_control(self):
        m=FakeMMIO();g=AudioGpio(m);g.write(0,12)
        self.assertEqual(m.writes,[(24,3)])
        self.assertEqual(g.read(0),12);self.assertEqual(g.read(8),96)
        with self.assertRaises(ValueError):g.write(0,1)
    def test_codec_bus_16bit_register_repeated_start_and_final_nack(self):
        events=[];bus=CodecBus.__new__(CodecBus)
        bus._start=lambda repeated=False:events.append(('start',repeated))
        bus._write_byte=lambda x:events.append(('write',x))
        bus._read_byte=lambda ack:(events.append(('read',ack)) or 42)
        bus._stop=lambda:events.append(('stop',))
        bus.release=lambda:events.append(('release',))
        self.assertEqual(bus.transfer(0x4002,count=2),bytes([42,42]))
        self.assertEqual(events,[('start',False),('write',0x76),('write',0x40),('write',2),('start',True),('write',0x77),('read',True),('read',False),('stop',),('release',)])
    def test_codec_configuration_stays_muted_and_readback_is_required(self):
        class Bus:
            def __init__(self):self.regs={0x4002:bytes([2,0x71,2,0x3c,0x21,1])};self.writes=[]
            def transfer(self,reg,data=None,count=1):
                if data is not None:self.regs[reg]=data;self.writes.append((reg,data));return
                v=self.regs[reg]
                return v[:5]+bytes([v[5]|2]) if reg==0x4002 and v[5]&1 else v
        bus=Bus();codec=Codec(bus);result=codec.configure_muted()
        self.assertTrue(result['pll_locked']);self.assertFalse(codec.output_enabled)
        self.assertEqual(bus.regs[0x4015],b'\x01');self.assertEqual(bus.regs[0x4023],b'\x85')
        codec.enable_output();self.assertTrue(codec.output_enabled)
        self.assertEqual(bus.regs[0x4023],b"\xe7");self.assertEqual(bus.regs[0x4024],b"\xe7")
        codec.mute();self.assertFalse(codec.output_enabled);self.assertEqual(bus.regs[0x401c],b'\0')
        bus.transfer=lambda *args,**kwargs:b'\xff'
        with self.assertRaisesRegex(AudioError,'readback'):codec.write(0x4000,15)
    def test_codec_pll_timeout_is_bounded(self):
        class Bus:
            def __init__(self):self.regs={0x4002:bytes([2,0x71,2,0x3c,0x21,1])}
            def transfer(self,reg,data=None,count=1):
                if data is not None:self.regs[reg]=data;return
                return self.regs[reg]
        with patch('eye_tracker.audio.time.monotonic',side_effect=[0,1]):
            codec=Codec(Bus())
            with self.assertRaisesRegex(AudioError,'lock timeout'):codec.configure_muted()
            self.assertFalse(codec.core_ready)
            codec.mute()
            self.assertNotIn(0x4023,codec.bus.regs)
    def test_mute_attempts_every_channel_after_failure(self):
        c=Codec(None);c.core_ready=True;calls=[]
        def write(reg,value):
            calls.append(reg)
            if reg==0x4023:raise AudioError('I2C fail')
        c.write=write
        with self.assertRaises(AudioError):c.mute()
        self.assertEqual(calls,[0x4023,0x4024,0x401c,0x401e]);self.assertFalse(c.output_enabled)

    def test_warm_codec_requires_pll_disable_before_relock(self):
        class Bus:
            def __init__(self):
                self.regs={0x4002:bytes([2,0x71,2,0x3c,0x21,1])}
                self.powered_down=False;self.writes=[]
            def transfer(self,reg,data=None,count=1):
                if data is not None:
                    self.regs[reg]=data;self.writes.append((reg,data))
                    if reg==0x4002 and not data[5]&1:self.powered_down=True
                    return
                value=self.regs[reg]
                if reg==0x4002 and (not value[5]&1 or self.powered_down):
                    # Board retains read-only LOCK when the PLL is disabled.
                    value=value[:5]+bytes([value[5]|2])
                return value
        bus=Bus();codec=Codec(bus);codec.configure_muted();codec.configure_muted()
        self.assertTrue(codec.core_ready)
        pll_writes=[data for reg,data in bus.writes if reg==0x4002]
        self.assertEqual([data[5]&1 for data in pll_writes],[0,0,1,0,0,1])
        self.assertTrue(all(len(data)==6 for data in pll_writes))
        self.assertFalse(codec.output_enabled)

class ClockTests(unittest.TestCase):
    def test_boot_pll_divisors_are_recalculated_before_use(self):
        from eye_tracker.hardware_contract import configure_overlay_clocks
        class Clocks:
            fclk0_mhz=31.25;fclk1_mhz=62.5
            calls=[]
            def set_pl_clk(self,index,**kwargs):
                self.calls.append((index,kwargs));setattr(self,'fclk%d_mhz'%index,kwargs['clk_mhz'])
        c=Clocks();r=configure_overlay_clocks(c)
        self.assertEqual(c.calls,[(0,{'clk_mhz':50.}),(1,{'clk_mhz':100.})])
        self.assertEqual(r['after_overlay_download']['fclk0_mhz'],31.25)
        self.assertFalse(r['cpu_ddr_plls_changed'])
    def test_unexpected_clock_readback_fails_before_dma(self):
        from eye_tracker.hardware_contract import configure_overlay_clocks
        class Clocks:
            fclk0_mhz=31.25;fclk1_mhz=62.5
            def set_pl_clk(self,*args,**kwargs):pass
        with self.assertRaisesRegex(RuntimeError,'clock readback'):configure_overlay_clocks(Clocks())

class ControlsTests(unittest.TestCase):
    def test_bounce_hold_release_and_second_press(self):
        b=HelperButtons();events=[]
        for raw,t in ((0,0),(1,10),(0,20),(1,25),(1,54),(1,55),(1,80),(1,200),(0,210),(0,240),(1,250),(1,280)):
            v=b.update(raw,t)
            if v:events.append(v)
        self.assertEqual(events,['toggle_pause','toggle_pause'])
    def test_startup_held_and_scheduler_gap_never_forge_press(self):
        b=HelperButtons()
        for raw,t in ((8,0),(8,50),(8,100),(0,150),(0,180),(8,1000),(8,1031)):
            self.assertIsNone(b.update(raw,t))
        self.assertIsNone(b.update(0,1040));self.assertIsNone(b.update(0,1070))
        self.assertIsNone(b.update(8,1080));self.assertEqual(b.update(8,1110),'stop')
    def test_simultaneous_commands_prioritize_stop_then_invalidate(self):
        for raw,command in ((15,'stop'),(7,'invalidate_calibration'),(3,'toggle_pause'),(2,'cancel')):
            b=HelperButtons();b.update(0,0);b.update(raw,10)
            self.assertEqual(b.update(raw,40),command);self.assertIsNone(b.update(raw,80))
    def test_bad_clock_or_raw_is_rejected(self):
        b=HelperButtons();b.update(0,10)
        for raw,now in ((0,9),(16,20),(True,20),(0,float('nan'))):
            with self.assertRaises(ValueError):b.update(raw,now)
    def test_clear_calibration_cannot_resume_gaze_selection(self):
        c=test_controller();apply_command(c,'invalidate_calibration',0)
        apply_command(c,'toggle_pause',1);apply_command(c,'toggle_pause',2)
        self.assertIsNone(c.calibration_id)
        for t in range(10,3010,50):
            self.assertIsNone(c.feed(GazeSample(c.context,'synthetic-helper-test-only',t,t,'valid',(.25,.37)),t))
        self.assertEqual(c.progress,0);self.assertEqual(c.reason,'uncalibrated')
    def test_cancel_resets_partial_dwell_without_forging_action(self):
        c=test_controller()
        for t in range(0,900,50):c.feed(GazeSample(c.context,c.calibration_id,t,t,'valid',(.25,.37)),t)
        apply_command(c,'cancel',900);self.assertEqual(c.progress,0)
        for t in range(950,1900,50):self.assertIsNone(c.feed(GazeSample(c.context,c.calibration_id,t,t,'valid',(.25,.37)),t))
    def test_board_loop_respects_buttons_and_exits_without_audio(self):
        clock=[0.];m=FakeMMIO();read=m.read
        m.read=lambda reg: (8 if clock[0]>=.2 else 0) if reg==0x20 else read(reg)
        class Session:
            present_count=0
            def present(self,frame):self.present_count+=1
        class Renderer:
            def rgb565(self,c,key):return b'test'
        with tempfile.TemporaryDirectory() as folder:
            result=run_control_test(m,Session(),Renderer(),Path(folder),1,lambda:clock[0],lambda dt:clock.__setitem__(0,clock[0]+dt))
            self.assertTrue(result['completed']);self.assertEqual(result['exit_reason'],'BTN3')
            self.assertEqual([c['command'] for c in result['commands']],['stop'])
            self.assertNotIn((8,1),m.writes);self.assertFalse(result['audio_enabled'])
            self.assertTrue((Path(folder)/'controls_trace.json').is_file())

class ListeningTests(unittest.TestCase):
    class CodecStub:
        instances=[]
        def __init__(self,bus):
            self.enabled=False;self.muted=0;self.core_ready=True;self.instances.append(self)
        def configure_muted(self):return {'pll_locked':True,'analog_output_muted':True}
        def enable_output(self):self.enabled=True
        def mute(self):self.enabled=False;self.muted+=1

    class Renderer:
        def rgb565(self,c,key):return b'test'

    class Session:
        def __init__(self,fail_at=None):self.present_count=0;self.fail_at=fail_at
        def present(self,frame):
            self.present_count+=1
            if self.fail_at and self.present_count>=self.fail_at:raise TimeoutError('display stalled')

    def setup_clock(self,buttons=lambda t:0):
        clock=[0.];m=FakeMMIO();read=m.read;write=m.write
        m.ends=0;m.starts=[]
        def get(reg):
            if reg==0x20:return buttons(clock[0])
            if reg==0x24:return int(clock[0]*48000)
            if reg==0x28:return int(clock[0]*48000)*64
            if reg==12 and m.regs[12]&1 and clock[0]>=m.ends:m.regs[12]=10
            return read(reg)
        def put(reg,val):
            write(reg,val)
            if reg==8 and val==1:
                m.ends=clock[0]+m.regs[16]/16000;m.starts.append(clock[0])
        m.read=get;m.write=put
        return clock,m,lambda:clock[0],lambda dt:clock.__setitem__(0,clock[0]+dt)

    def folder(self):
        path=ROOT/'build/test_tmp';path.mkdir(parents=True,exist_ok=True)
        return tempfile.TemporaryDirectory(dir=path)

    def test_listening_opt_in_plays_three_phrases_and_mutes_on_exit(self):
        clock,m,now,sleep=self.setup_clock()
        with patch('eye_tracker.auxiliary.Codec',self.CodecStub),self.folder() as folder:
            result=run_audio_test(m,PhraseBank(),self.Session(),self.Renderer(),Path(folder),True,now,sleep)
            self.assertEqual([p['key'] for p in result['phrases']],['water','rest','help'])
            self.assertTrue(result['analog_output_enabled']);self.assertTrue(result['completed'])
            self.assertTrue(result['output_muted_on_exit']);self.assertFalse(result['analog_listening_verified'])
            self.assertFalse(m.regs[12]&1);self.assertFalse(self.CodecStub.instances[-1].enabled)

    def test_default_audio_test_never_unmutes(self):
        clock,m,now,sleep=self.setup_clock()
        with patch('eye_tracker.auxiliary.Codec',self.CodecStub),self.folder() as folder:
            result=run_audio_test(m,PhraseBank(),self.Session(),self.Renderer(),Path(folder),now=now,sleep=sleep)
            self.assertFalse(result['analog_output_enabled']);self.assertTrue(result['completed'])

    def test_physical_abort_during_listening_preserves_trace_and_mutes(self):
        clock,m,now,sleep=self.setup_clock(lambda t:2 if .8<=t<1.2 else 0)
        with patch('eye_tracker.auxiliary.Codec',self.CodecStub),self.folder() as folder:
            with self.assertRaisesRegex(AudioError,'interrupted'):
                run_audio_test(m,PhraseBank(),self.Session(),self.Renderer(),Path(folder),True,now,sleep)
            result=json.loads((Path(folder)/'audio_trace.json').read_text())
            self.assertEqual(result['interrupted_by'],'cancel');self.assertFalse(result['completed'])
            self.assertTrue(result['output_muted_on_exit']);self.assertFalse(m.regs[12]&1)

    def test_dwell_to_speech_once_per_target_no_held_repetition(self):
        clock,m,now,sleep=self.setup_clock()
        with patch('eye_tracker.auxiliary.Codec',self.CodecStub),self.folder() as folder:
            result=run_control_test(m,self.Session(),self.Renderer(),Path(folder),15,now,sleep,bank=PhraseBank())
            self.assertEqual([a['key'] for a in result['actions']],['water','rest','help'])
            self.assertEqual([e['key'] for e in result['speech_events'] if e['event']=='started'],['water','rest','help'])
            self.assertEqual(len([e for e in result['speech_events'] if e['event']=='completed']),3)
            self.assertTrue(result['audio_stopped_on_exit']);self.assertTrue(result['output_muted_on_exit'])

    def test_each_helper_interrupts_audio_no_resume_or_replay(self):
        for raw in (1,2,4,8):
            with self.subTest(button=raw):
                clock,m,now,sleep=self.setup_clock(lambda t:raw if 1.5<=t<1.75 else 0)
                with patch('eye_tracker.auxiliary.Codec',self.CodecStub),self.folder() as folder:
                    result=run_control_test(m,self.Session(),self.Renderer(),Path(folder),4.5,now,sleep,bank=PhraseBank())
                    events=result['speech_events']
                    self.assertEqual([e['event'] for e in events],['started','interrupted'])
                    self.assertFalse(result['commands'][0]['audio_busy_after'])
                    self.assertLess(events[1]['time_ms']-1500,101)
                    self.assertEqual(result['uncalibrated_actions'],0);self.assertEqual(result['paused_actions'],0)

    def test_resume_keeps_interrupted_target_silent_until_fresh_next_dwell(self):
        clock,m,now,sleep=self.setup_clock(lambda t:1 if 1.5<=t<1.75 or 2.3<=t<2.55 else 0)
        with patch('eye_tracker.auxiliary.Codec',self.CodecStub),self.folder() as folder:
            result=run_control_test(m,self.Session(),self.Renderer(),Path(folder),11,now,sleep,bank=PhraseBank())
            starts=[e for e in result['speech_events'] if e['event']=='started']
            self.assertEqual([e['key'] for e in starts],['water','rest'])
            resume=result['commands'][1]
            self.assertFalse(resume['paused'])
            self.assertGreater(starts[1]['time_ms'],resume['time_ms']+3000+1000)
            self.assertEqual(result['speech_events'][1]['event'],'interrupted')
            self.assertFalse(resume['audio_busy_after'])

    def test_display_failure_stops_voice_preserves_incomplete_trace(self):
        clock,m,now,sleep=self.setup_clock()
        with patch('eye_tracker.auxiliary.Codec',self.CodecStub),self.folder() as folder:
            with self.assertRaisesRegex(TimeoutError,'stalled'):
                run_control_test(m,self.Session(26),self.Renderer(),Path(folder),10,now,sleep,bank=PhraseBank())
            result=json.loads((Path(folder)/'controls_trace.json').read_text())
            self.assertFalse(result['completed']);self.assertTrue(result['audio_stopped_on_exit'])
            self.assertTrue(result['output_muted_on_exit']);self.assertFalse(self.CodecStub.instances[-1].enabled)

if __name__=='__main__':unittest.main()

