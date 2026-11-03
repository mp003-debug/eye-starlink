"""Fault-oriented tests for real DMA ownership boundaries (no board access)."""
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from eye_tracker.board_io import VideoIO, HardwareFault, UnsafeShutdown, MM2S, S2MM, FRAME_DONE
from eye_tracker.framebuffer import CAPTURE, DISPLAY
from eye_tracker.hardware_contract import verify_artifacts

ROOT=Path(__file__).resolve().parents[1]

class Clock:
    def __init__(self): self.t=0.0
    def now(self): return self.t
    def sleep(self, seconds): self.t+=seconds

class Buffer(np.ndarray):
    def __new__(cls, size, address, events):
        obj=np.zeros(size,dtype=np.uint8).view(cls)
        obj.device_address=address;obj.events=events;obj.freed=False
        return obj
    def flush(self): self.events.append(('flush',self.device_address))
    def invalidate(self): self.events.append(('invalidate',self.device_address))
    def freebuffer(self):
        if self.freed: raise AssertionError('double free')
        self.events.append(('free',self.device_address));self.freed=True

class Allocator:
    def __init__(self, events):
        self.events=events;self.items=[];self.address=0x18000000;self.overlap=False
    def __call__(self, shape, dtype):
        buffer=Buffer(shape[0],self.address,self.events);self.items.append(buffer)
        if not self.overlap:self.address+=0x100000
        return buffer

class Vdma:
    def __init__(self, clock, events, allocator):
        self.clock=clock;self.events=events;self.allocator=allocator
        self.reg={0:0,4:1,0x30:0,0x34:1,0x28:0}
        self.complete_at=None;self.stop_at={};self.capture_error=0
        self.capture_stalled=False;self.stop_stuck=False;self.reset_stuck=set()
        self.start_delay=0.0;self.start_at={}
        self.switch_at=None;self.switch_stalled=False
    def read(self, address):
        if self.switch_at is not None and self.clock.t>=self.switch_at:
            self.reg[0x28]=(self.reg[0x28]&~0x1F0000)|((self.reg[0x28]&0x1F)<<16)
            self.switch_at=None
        for ch,deadline in list(self.start_at.items()):
            if self.clock.t>=deadline:
                self.reg[ch+4]&=~1;del self.start_at[ch]
        for ch,deadline in list(self.stop_at.items()):
            if self.clock.t>=deadline:
                self.reg[ch+4]|=1;del self.stop_at[ch]
        if self.complete_at is not None and self.clock.t>=self.complete_at:
            self.complete_at=None
            self.reg[0x34]=1|FRAME_DONE|self.capture_error;self.reg[0x30]&=~1
            address0=self.reg[0xAC]
            for buffer in self.allocator.items:
                if buffer.device_address==address0:
                    buffer[:]=np.arange(buffer.size,dtype=np.uint32).astype(np.uint8)
        return self.reg.get(address,0)
    def write(self, address, value):
        self.events.append(('write',address,value))
        if address==0x28:
            self.reg[address]=(self.reg[address]&0x1F1F0000)|(value&0x1F1F)
            if (value&0x1F)!=((self.reg[address]>>16)&0x1F) and not self.switch_stalled:
                self.switch_at=self.clock.t+.004
            return
        if address in (0,0x30):
            was_running=bool(self.reg.get(address,0)&1)
            self.reg[address]=value
            if value&4:
                if address not in self.reset_stuck:
                    self.reg[address]=0;self.reg[address+4]=1
                    if address==0x30:self.complete_at=None
                    self.stop_at.pop(address,None)
                    self.start_at.pop(address,None)
                return
            if value&1:
                if self.start_delay:self.start_at[address]=self.clock.t+self.start_delay
                else:self.reg[address+4]&=~1
            elif was_running:
                if not self.stop_stuck:self.stop_at[address]=self.clock.t+0.002
            return
        self.reg[address]=value
        if address==0xA0 and not self.capture_stalled:
            self.complete_at=self.clock.t+0.005

class Gpio:
    def __init__(self, vdma, events):self.vdma=vdma;self.events=events;self.control=0;self.fault=0;self.rearm_stuck=False
    def read(self, address):
        if address==8:
            locked=8 if self.control&2 and not self.vdma.read(4)&1 else 0
            return locked|self.fault|(16 if not self.control&1 and not self.rearm_stuck else 0)
        return self.control
    def write(self,address,value):self.control=value;self.events.append(('gpio',address,value))

class Diag:
    def __init__(self, clock):
        self.clock=clock;self.seq=0;self.request=False;self.stale=False;self.writes=0
        self.frozen=False;self.width=752;self.base_count=45
    def read(self,address):
        if address==0:return 0x45594531
        if address==4:return 0x00010003
        if address==0x0C:
            if self.request and not self.stale:
                self.seq=(self.seq+1)&0xFFFFFFFF;self.request=False
            return 2 # old valid flag persists even during a stale request
        if address==0x10:return self.seq
        count=(self.base_count + (0 if self.frozen else int(self.clock.t / .004))) & 0xFFFFFFFF
        return {0x14:count,0x18:444444,0x1C:self.width*480,0x20:(480<<16)|self.width,0x30:24000000}.get(address,0)
    def write(self,address,value):self.request=True;self.writes+=1

class BoardIOTests(unittest.TestCase):
    def setUp(self):
        self.events=[];self.clock=Clock();self.alloc=Allocator(self.events)
        self.vdma=Vdma(self.clock,self.events,self.alloc);self.gpio=Gpio(self.vdma,self.events);self.diag=Diag(self.clock)
        self.io=VideoIO(self.vdma,self.gpio,self.diag,self.alloc,timeout=.03,now=self.clock.now,sleep=self.clock.sleep)
        self.io.prepare()
    def test_display_programming_and_cache_ownership(self):
        self.io.display_static(b'\x00\xf8'*(640*480))
        buffer=self.alloc.items[0]
        self.assertEqual(self.vdma.reg[0x54],1280)
        self.assertEqual(self.vdma.reg[0x58],1280)
        self.assertEqual(self.vdma.reg[0x50],480)
        self.assertEqual([self.vdma.reg[x] for x in (0x5C,0x60,0x64)],[buffer.device_address]*3)
        self.assertLess(self.events.index(('flush',buffer.device_address)),self.events.index(('write',0x50,480)))
        self.assertFalse(buffer.freed)
        self.io.close();self.assertTrue(buffer.freed)
        self.assertEqual(self.gpio.control,0)
    def test_dynamic_slots_unique_flush_before_request_and_current_slot_ack(self):
        self.io.display_dynamic(bytes(DISPLAY.size_bytes))
        addresses=[b.device_address for b in self.alloc.items]
        self.assertEqual(len(set(addresses)),3)
        self.assertEqual([self.vdma.reg[a] for a in (0x5C,0x60,0x64)],addresses)
        start=self.clock.t
        self.vdma.reg[0x28]|=2<<8  # read switch must preserve S2MM park reference
        for expected in (1,2,0,1):
            active=self.io.display_slot
            old=self.alloc.items[active].copy()
            self.events.clear()
            value=bytes([expected+1])*DISPLAY.size_bytes
            self.assertEqual(self.io.present(value),expected)
            self.assertTrue(np.array_equal(old,self.alloc.items[active]))
            self.assertEqual((self.vdma.read(0x28)>>16)&0x1F,expected)
            self.assertEqual((self.vdma.read(0x28)>>8)&0x1F,2)
            self.assertLess(self.events.index(('flush',addresses[expected])),
                            self.events.index(('write',0x28,(2<<8)|expected)))
        self.assertGreaterEqual(self.clock.t-start,.016)
        self.assertEqual(self.io.present_count,4)
        self.io.capture_once()
        self.assertEqual(self.vdma.read(0x28)&0x1F,1)
        self.assertEqual(len(self.alloc.items),4)
        self.io.close();self.assertTrue(all(b.freed for b in self.alloc.items))

    def test_requested_slot_readback_cannot_hide_stuck_hardware_pointer(self):
        self.io.display_dynamic(bytes(DISPLAY.size_bytes));self.vdma.switch_stalled=True
        with self.assertRaisesRegex(HardwareFault,'hardware frame switch'):
            self.io.present(bytes([31])*DISPLAY.size_bytes)
        self.assertEqual(self.vdma.read(0x28)&0x1F,1)
        self.assertEqual((self.vdma.read(0x28)>>16)&0x1F,0)
        self.assertEqual(self.io.present_count,0)
        events=len(self.events)
        with self.assertRaisesRegex(HardwareFault,'previous display switch'):
            self.io.present(bytes(DISPLAY.size_bytes))
        self.assertEqual(len(self.events),events)
        self.assertFalse(any(b.freed for b in self.alloc.items))
        self.io.close()

    def test_foreign_display_pointer_prevents_cpu_buffer_write(self):
        self.io.display_dynamic(bytes(DISPLAY.size_bytes))
        self.vdma.reg[0x28]=1<<16
        events=len(self.events)
        with self.assertRaisesRegex(HardwareFault,'ownership changed'):
            self.io.present(bytes([1])*DISPLAY.size_bytes)
        self.assertEqual(len(self.events),events)
        self.assertFalse(any(b.any() for b in self.alloc.items))
        self.io.close()

    def test_bad_preview_frame_does_not_poison_or_touch_display(self):
        self.io.display_dynamic(bytes(DISPLAY.size_bytes));events=len(self.events)
        with self.assertRaises(ValueError):self.io.present(bytes(CAPTURE.size_bytes))
        self.assertEqual(len(self.events),events)
        self.assertFalse(self.io.display_faulted)
        self.io.present(bytes(DISPLAY.size_bytes));self.io.close()

    def test_static_display_cannot_be_updated_in_place(self):
        self.io.display_static(bytes(DISPLAY.size_bytes))
        with self.assertRaisesRegex(HardwareFault,'dynamic display'):
            self.io.present(bytes(DISPLAY.size_bytes))
        self.io.close()

    def test_display_error_during_switch_poisoned_and_buffers_retained(self):
        self.io.display_dynamic(bytes(DISPLAY.size_bytes))
        original_read=self.vdma.read
        def read(address):
            value=original_read(address)
            if address==4 and self.clock.t>=.002:return value|0x8000
            return value
        self.vdma.read=read
        with self.assertRaisesRegex(HardwareFault,'display fault'):
            self.io.present(bytes(DISPLAY.size_bytes))
        self.assertTrue(self.io.display_faulted)
        self.assertEqual(self.io.present_count,0)
        self.assertFalse(any(b.freed for b in self.alloc.items))
        self.io.close()

    def test_dynamic_failed_shutdown_retains_all_four_buffers(self):
        self.io.display_dynamic(bytes(DISPLAY.size_bytes));self.io.capture_once()
        self.vdma.stop_stuck=True;self.vdma.reset_stuck={0}
        with self.assertRaises(UnsafeShutdown):self.io.close()
        self.assertEqual(len(self.io.buffers),4)
        self.assertFalse(any(b.freed for b in self.alloc.items))

    def test_capture_requires_completion_and_invalidates_cache(self):
        image=self.io.capture_once()
        self.assertEqual(image.shape,(480,640));self.assertEqual(image.dtype,np.uint8)
        self.assertEqual(image[0,:4].tolist(),[0,1,2,3])
        self.assertEqual(self.vdma.reg[0xA4],640);self.assertEqual(self.vdma.reg[0xA8],640)
        self.assertTrue(self.vdma.read(0x34)&1)
        self.assertIn(('invalidate',self.alloc.items[0].device_address),self.events)
        self.assertFalse(self.alloc.items[0].freed)
        self.io.close()
    def test_combined_buffers_have_independent_addresses_and_sizes(self):
        self.io.display_static(bytes(DISPLAY.size_bytes));self.io.capture_once()
        display,capture=self.alloc.items
        self.assertNotEqual(display.device_address,capture.device_address)
        self.assertEqual((display.nbytes,capture.nbytes),(614400,307200))
        self.assertTrue(self.io.display_health()&8)
        self.io.close();self.assertTrue(all(b.freed for b in self.alloc.items))
    def test_active_channel_cannot_be_taken_over(self):
        self.vdma.reg[0]=1;self.vdma.reg[4]=0
        other=VideoIO(self.vdma,self.gpio,self.diag,self.alloc)
        count=len(self.events)
        with self.assertRaises(HardwareFault):other.prepare()
        self.assertEqual(len(self.events),count);self.assertEqual(len(self.alloc.items),0)
    def test_wrong_frame_size_does_not_start_dma(self):
        count=len(self.events)
        with self.assertRaises(ValueError):self.io.display_static(bytes(CAPTURE.size_bytes))
        self.assertEqual(len(self.events),count);self.assertEqual(len(self.alloc.items),0)
    def test_capture_error_rejects_frame_before_cache_read(self):
        self.vdma.capture_error=0x8000
        with self.assertRaises(HardwareFault):self.io.capture_once()
        self.assertFalse(any(e[0]=='invalidate' for e in self.events))
        self.io.close()
    def test_stale_frame_done_cannot_pass_a_new_stalled_capture(self):
        self.vdma.reg[0x34]=1|FRAME_DONE;self.vdma.capture_stalled=True
        with self.assertRaises(HardwareFault):self.io.capture_once()
        self.assertFalse(any(e[0]=='invalidate' for e in self.events))
        self.assertFalse(self.alloc.items[0].freed);self.io.close()
    def test_no_frame_event_cannot_be_mistaken_for_completion(self):
        self.vdma.capture_stalled=True
        with self.assertRaises(HardwareFault):self.io.capture_once()
        self.assertFalse(any(e[0]=='invalidate' for e in self.events));self.io.close()
    def test_repeated_captures_reuse_one_buffer_and_return_owned_copies(self):
        first=self.io.capture_once();saved=first.copy()
        self.alloc.items[0].fill(99)
        self.assertTrue(np.array_equal(first,saved))
        self.io.capture_once()
        self.assertEqual(self.io.capture_index,2)
        self.assertEqual(len(self.alloc.items),1)
        self.assertEqual(sum(e[0]=='invalidate' for e in self.events),2)
        self.io.close()
    def test_queue_not_empty_prevents_reuse(self):
        self.io.capture_once();self.gpio.rearm_stuck=True
        count=sum(e==('write',0xA0,480) for e in self.events)
        with self.assertRaisesRegex(HardwareFault,'queue'):self.io.capture_once()
        self.assertEqual(sum(e==('write',0xA0,480) for e in self.events),count)
        self.io.close()
    def test_failed_request_cannot_be_retried_in_same_session(self):
        self.vdma.capture_stalled=True
        with self.assertRaises(HardwareFault):self.io.capture_once()
        self.vdma.capture_stalled=False
        with self.assertRaisesRegex(HardwareFault,'previous capture failed'):self.io.capture_once()
        self.io.close()
    def test_latched_fault_rejects_even_completed_frame(self):
        original_read=self.gpio.read
        def read(address):
            value=original_read(address)
            return value|1 if address==8 and self.vdma.read(0x34)&FRAME_DONE else value
        self.gpio.read=read
        with self.assertRaisesRegex(HardwareFault,'FIFO/frame fault'):self.io.capture_once()
        self.assertFalse(any(e[0]=='invalidate' for e in self.events));self.io.close()
    def test_native_errors_after_dma_reject_copy(self):
        original_read=self.diag.read
        def read(address):
            if address==0x28 and self.clock.t>=.005:return 1
            return original_read(address)
        self.diag.read=read
        with self.assertRaisesRegex(HardwareFault,'link error'):self.io.capture_once()
        self.assertFalse(any(e[0]=='invalidate' for e in self.events));self.io.close()
    def test_capture_fifo_overflow_is_fatal_before_completion(self):
        self.gpio.fault=1
        with self.assertRaises(HardwareFault):self.io.capture_once()
        self.io.close()
    def test_display_fault_does_not_look_healthy(self):
        self.io.display_static(bytes(DISPLAY.size_bytes));self.gpio.fault=2
        with self.assertRaises(HardwareFault):self.io.display_health()
        self.io.close()
    def test_both_channels_must_halt_before_any_free(self):
        self.io.display_static(bytes(DISPLAY.size_bytes));self.vdma.capture_stalled=True
        with self.assertRaises(HardwareFault):self.io.capture_once()
        self.vdma.stop_stuck=True;self.vdma.reset_stuck={0,0x30}
        with self.assertRaises(UnsafeShutdown):self.io.close()
        self.assertEqual(len(self.io.buffers),2)
        self.assertFalse(any(b.freed for b in self.alloc.items))
    def test_reset_recovery_must_complete_before_free(self):
        self.io.display_static(bytes(DISPLAY.size_bytes));self.vdma.stop_stuck=True
        self.io.close()
        self.assertTrue(self.io.reset_recovery_used)
        self.assertTrue(self.alloc.items[0].freed)
        self.assertEqual(self.vdma.read(0),0);self.assertEqual(self.vdma.read(4)&1,1)
    def test_missing_capture_clock_reset_times_out_without_allocation(self):
        self.vdma.reset_stuck.add(0x30)
        with self.assertRaises(HardwareFault):self.io.capture_once()
        self.assertEqual(len(self.alloc.items),0)
    def test_unaligned_address_is_not_programmed(self):
        self.alloc.address+=1
        with self.assertRaises(HardwareFault):self.io.display_static(bytes(DISPLAY.size_bytes))
        self.assertNotIn(0x5C,self.vdma.reg);self.io.close()
        self.assertTrue(self.alloc.items[0].freed)
    def test_overlapping_physical_addresses_are_rejected(self):
        self.alloc.overlap=True;self.io.display_static(bytes(DISPLAY.size_bytes))
        with self.assertRaises(HardwareFault):self.io.capture_once()
        self.assertNotIn(0xAC,self.vdma.reg);self.io.close()
    def test_diagnostic_valid_bit_alone_is_not_fresh(self):
        self.diag.stale=True
        with self.assertRaises(HardwareFault):self.io.snapshot()
        self.assertEqual(self.diag.writes,1)
    def test_diagnostic_sequence_wrap_is_accepted(self):
        self.diag.seq=0xFFFFFFFF
        snap=self.io.snapshot()
        self.assertEqual(snap['sequence'],0);self.assertEqual(snap['frame_lines'],480)
        self.assertEqual(snap['line_pixels'],752)
    def test_display_waits_for_delayed_dma_start_before_enabling_sink(self):
        self.vdma.start_delay=.005
        self.io.display_static(bytes(DISPLAY.size_bytes))
        self.assertGreaterEqual(self.clock.t,.005)
        self.assertTrue(self.io.display_health()&8);self.io.close()
    def test_display_start_timeout_never_enables_sink(self):
        self.vdma.start_delay=100
        with self.assertRaisesRegex(HardwareFault,'starting'):
            self.io.display_static(bytes(DISPLAY.size_bytes))
        self.assertEqual(self.gpio.control,0);self.io.close()
    def test_native_frame_counter_must_advance_not_just_snapshot_sequence(self):
        self.diag.frozen=True
        with self.assertRaisesRegex(HardwareFault,'native camera frames'):
            self.io.wait_native_frames()
    def test_native_frame_geometry_rejects_wrong_sensor_window(self):
        self.diag.width=640
        with self.assertRaisesRegex(HardwareFault,'geometry'):
            self.io.wait_native_frames()
    def test_native_frames_complete_before_geometry_is_accepted(self):
        current=self.io.wait_native_frames()
        self.assertGreaterEqual(current['frame_count'],47)
        self.assertGreaterEqual(self.clock.t,.008)
    def test_native_frame_counter_wrap_is_valid_progress(self):
        self.diag.base_count=0xFFFFFFFF
        current=self.io.wait_native_frames()
        self.assertEqual(current['frame_count'],1)
    def test_close_is_idempotent(self):
        self.io.display_static(bytes(DISPLAY.size_bytes));self.io.close();self.io.close()
        self.assertEqual(sum(e[0]=='free' for e in self.events),1)

class ContractTests(unittest.TestCase):
    def test_real_built_pair_matches_contract(self):
        self.assertTrue(verify_artifacts(ROOT)['hardware_configuration_verified'])
    def test_corrupt_bitstream_is_rejected_before_hwh_or_mmio(self):
        folder=ROOT/'build/test_tmp';folder.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(folder)) as temp:
            base=Path(temp)/'build/fpga';base.mkdir(parents=True)
            (base/'eye_tracker.bit').write_bytes(b'not the built bitstream')
            original=json.loads((ROOT/'build/fpga/result.json').read_text(encoding='utf-8'))
            (base/'result.json').write_text(json.dumps(original),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'manifest mismatch'):verify_artifacts(temp)
