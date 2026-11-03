"""Bounded playback of approved local phrases through the project's audio IP.

ADAU1761 register settings: Analog Devices Rev F and Xilinx PYNQ reference.
The analog output starts muted. No UIO address assumption or kernel sound card.
"""
import hashlib,json,time,wave
from pathlib import Path
import numpy as np
from .sensor import OpenDrainI2C
from .phrases import PHRASE_TEXT, PRIMARY_KEYS, QUICK_KEYS
ROOT=Path(__file__).resolve().parents[2]

class AudioError(RuntimeError):pass

class AudioGpio:
    def __init__(self,mmio):self.mmio=mmio
    def read(self,offset):
        if offset==0:return self.mmio.read(0x18)<<2
        if offset==8:return (self.mmio.read(0x1c)&3)<<5
        raise ValueError('invalid codec GPIO offset')
    def write(self,offset,value):
        if offset!=0 or value&~12:raise ValueError('invalid codec GPIO drive')
        self.mmio.write(0x18,value>>2)

class CodecBus(OpenDrainI2C):
    def transfer(self,register,data=None,count=1):
        if not 0x4000<=register<=0x40ff or not 1<=count<=6:raise ValueError('invalid codec register')
        try:
            self._start()
            for value in (0x3b<<1,register>>8,register&255):self._write_byte(value)
            if data is not None:
                for value in data:self._write_byte(value)
                result=None
            else:
                self._start(repeated=True);self._write_byte((0x3b<<1)|1)
                result=bytes(self._read_byte(i<count-1) for i in range(count))
            self._stop();return result
        except BaseException:
            try:self._stop()
            except Exception:pass
            raise
        finally:self.release()

class Codec:
    def __init__(self,bus):self.bus=bus;self.output_enabled=False;self.core_ready=False
    def read(self,reg,count=1):return self.bus.transfer(reg,count=count)
    def write(self,reg,value):
        self.bus.transfer(reg,bytes([value]))
        actual=self.read(reg)
        if actual!=bytes([value]):raise AudioError('codec readback mismatch at %04x: expected %02x got %s'%(reg,value,actual.hex()))
    def configure_muted(self):
        # MCLK 10MHz, PLL=10MHz*(4+572/625)=49.152MHz. No indefinite lock loop.
        self.core_ready=False;self.output_enabled=False
        self.write(0x4000,0x0e)
        # ADAU1761 startup/reconfiguration: power down PLL before reprogramming.
        # Overlay reload interrupts MCLK; merely rewriting PLLEN=1 may never relock.
        previous=self.read(0x4002,6)
        self.bus.transfer(0x4002,previous[:5]+bytes([previous[5]&~3]))
        if self.read(0x4002,6)[5]&1:raise AudioError('codec PLL failed to power down')
        parameters=bytes([2,0x71,2,0x3c,0x21,0])
        self.bus.transfer(0x4002,parameters)
        actual=self.read(0x4002,6)
        # Lock (bit 1) is read-only and may remain set while PLLEN is zero.
        # Compare writable configuration, not that status flag.
        if actual[:5]!=parameters[:5] or actual[5]&~2:
            raise AudioError('disabled PLL parameter readback mismatch: '+actual.hex())
        self.bus.transfer(0x4002,parameters[:5]+b'\x01')
        deadline=time.monotonic()+.5
        while True:
            pll=self.read(0x4002,6)
            if pll[5]&2:break
            if time.monotonic()>=deadline:raise AudioError('codec PLL lock timeout')
        if pll[:5]!=parameters[:5] or pll[5]&~2!=1:raise AudioError('PLL parameter readback mismatch: '+pll.hex())
        self.write(0x4000,0x0f)
        self.core_ready=True
        settings={0x400a:0,0x400c:0,0x4010:0,0x4019:0x10,
                  0x4015:1,0x4016:0,0x4017:0,0x401c:0,0x401d:0,0x401e:0,0x401f:0,
                  0x4023:0x85,0x4024:0x85,0x4029:3,0x402a:3,
                  0x40f2:1,0x40f3:0,0x40f5:1,0x40f6:1,0x40f8:0,0x40f9:0x7f,0x40fa:3}
        for reg,value in settings.items():self.write(reg,value)
        return {'pll_locked':True,'pll_bytes':list(pll),'settings_read_back':True,'sample_rate_configured':48000,'codec_clock_master':True,'analog_output_muted':True}
    def mute(self):
        if not self.core_ready:
            # Only R0/R1 are accessible without a locked, enabled core.
            self.write(0x4000,0x0e);self.output_enabled=False
            return
        # Attempt both channels and both mixers even if one write fails.
        errors=[]
        for reg,value in ((0x4023,0x85),(0x4024,0x85),(0x401c,0),(0x401e,0)):
            try:self.write(reg,value)
            except Exception as exc:errors.append(str(exc))
        self.output_enabled=False
        if errors:raise AudioError('; '.join(errors))
    def enable_output(self):
        # Upgrade: user confirmed 0dB after restoring speaker power; WAV peaks <=-12dBFS.
        if not self.core_ready:raise AudioError('codec core not ready')
        try:
            for reg,value in ((0x401c,0x21),(0x401e,0x41),(0x4023,0xe7),(0x4024,0xe7)):self.write(reg,value)
            self.output_enabled=True
        except BaseException:
            try:self.mute()
            except Exception:pass
            raise

class PhraseBank:
    def __init__(self,path=ROOT/'assets/speech',include_quick=False):
        path=Path(path);manifest=json.loads((path/'manifest.json').read_text(encoding='utf-8'))
        self.samples={};self.text={}
        for key in PRIMARY_KEYS+(QUICK_KEYS if include_quick else ()):
            phrase=PHRASE_TEXT[key]
            meta=manifest['phrases'][key];p=path/(key+'.wav')
            limit=16000*8 if key in QUICK_KEYS else 32768
            if p.stat().st_size>limit*2+65536:raise AudioError('phrase file exceeds bounded size')
            if meta['file']!=p.name or meta['text']!=phrase or hashlib.sha256(p.read_bytes()).hexdigest()!=meta['sha256']:
                raise AudioError('phrase identity/hash mismatch: '+key)
            with wave.open(str(p),'rb') as w:
                if (w.getnchannels(),w.getsampwidth(),w.getframerate(),w.getcomptype())!=(1,2,16000,'NONE'):
                    raise AudioError('PCM16 mono 16kHz required')
                n=w.getnframes()
                if not 0<n<=limit:raise AudioError('invalid phrase length')
                raw=w.readframes(n)
            if n!=meta['samples'] or not 0<n<=limit or len(raw)!=n*2:raise AudioError('invalid phrase length')
            values=np.frombuffer(raw,dtype='<i2')
            if np.max(np.abs(values.astype(np.int32)))>8191:raise AudioError('phrase peak exceeds asset bound')
            self.samples[key]=values;self.text[key]=phrase

class AudioDevice:
    def __init__(self,mmio,now=time.monotonic):
        self.mmio=mmio;self.now=now;self.deadline=None
        self.version=mmio.read(4)
        if mmio.read(0)!=0x41554431 or self.version not in (0x00010000,0x00020000):raise AudioError('wrong audio IP identity')
        if mmio.read(0x0c)&1:raise AudioError('audio hardware already busy')
    def status(self):return self.mmio.read(0x0c)
    def stop(self):
        self.mmio.write(8,2);self.deadline=None
        if self.status()&1:raise AudioError('audio did not stop')
    def play(self,samples):
        if not isinstance(samples,np.ndarray) or samples.dtype!=np.dtype('<i2') or samples.ndim!=1 or not 0<len(samples)<=32768:
            raise ValueError('bounded PCM16 vector required')
        status=self.status()
        if status&1:raise AudioError('audio busy; no queue or overwrite')
        if status&4 or not status&8:raise AudioError('audio fault or clock missing')
        if self.version==0x00020000:self.mmio.write(0x30,0)
        padded=np.pad(samples,(0,len(samples)%2)).astype('<i2',copy=False)
        words=padded.view('<u4')
        self.mmio.array[0x10000//4:0x10000//4+len(words)]=words
        if not np.array_equal(self.mmio.array[0x10000//4:0x10000//4+len(words)],words):raise AudioError('PCM BRAM readback mismatch')
        self.mmio.write(8,4);self.mmio.write(0x10,len(samples));self.mmio.write(8,1)
        if not self.status()&1:raise AudioError('audio start not acknowledged')
        self.deadline=self.now()+len(samples)/16000+.25
    def poll(self):
        status=self.status()
        if status&4:
            self.stop();raise AudioError('audio clock fault')
        if status&1:
            if self.deadline is not None and self.now()>self.deadline:
                self.stop();raise AudioError('bounded playback timeout')
            return 'busy'
        if self.deadline is not None:
            self.deadline=None
            if not status&2:raise AudioError('audio stopped without completion')
            return 'done'
        return 'idle'
