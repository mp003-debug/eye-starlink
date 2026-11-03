"""MT9V034-family setup: slow open-drain I2C, verified reads, temporary controls.

References: onsemi MT9V034 Rev G pp16-21,29,39,54; chip ID corroborated
by Linux drivers/media/i2c/mt9v032.c (0x1324 shared by MT9V024/034).
No generic register CLI, bus-clear pulses, reset, geometry or clock writes.
"""
import math
import time

class SensorError(RuntimeError):
    pass

class Nack(SensorError):
    pass

class OpenDrainI2C:
    """GPIO bits2/3 pull SDA/SCL low; input bits5/6 read synchronized wires.

    Exclusive owner; video gates must be off throughout a transaction. Python
    scheduling may slow the bus, never a precise 100kHz timing claim.
    """
    def __init__(self, gpio, delay=10e-6, timeout=.02, now=time.monotonic, sleep=time.sleep):
        if not math.isfinite(delay) or delay < 5e-6 or not math.isfinite(timeout) or timeout <= delay:
            raise ValueError("invalid I2C timing")
        self.gpio, self.delay, self.timeout, self.now, self.sleep = gpio,delay,timeout,now,sleep
        self.low = 0
        if gpio.read(0) & 3:
            raise SensorError("I2C setup requires stopped video gates")

    def _drive(self, sda_low, scl_low):
        if self.gpio.read(0) & 3:
            raise SensorError("video owner changed during I2C")
        self.low = int(bool(sda_low)) | (int(bool(scl_low)) << 1)
        self.gpio.write(0, self.low << 2)
        self.sleep(self.delay)

    def lines(self):
        return (self.gpio.read(8) >> 5) & 3

    def release(self):
        self._drive(False,False)

    def _high(self, sda_low):
        self._drive(sda_low,False)
        deadline=self.now()+self.timeout
        while not self.lines() & 2:
            if self.now() >= deadline:
                raise SensorError("SCL stuck low or clock-stretch timeout")
            self.sleep(self.delay)
        self.sleep(self.delay)

    def _start(self, repeated=False):
        self._drive(False, repeated)
        self._high(False)
        if not self.lines() & 1:
            raise SensorError("SDA held low; no automatic bus recovery")
        self._drive(True,False)
        self._drive(True,True)

    def _stop(self):
        self._drive(True,True)
        self._high(True)
        self.release()
        if self.lines()!=3:
            raise SensorError("I2C bus not released after STOP")

    def _write_byte(self, value):
        for shift in range(7,-1,-1):
            low=not bool(value & (1 << shift))
            self._drive(low,True)
            self._high(low)
            # An intended one must stay high, except the ninth ACK clock.
            if not low and not self.lines() & 1:
                raise SensorError("unexpected SDA low while transmitting one")
            self._drive(low,True)
        self._drive(False,True)
        self._high(False)
        ack=not bool(self.lines() & 1)
        self._drive(False,True)
        if not ack:
            raise Nack("I2C NACK for byte 0x%02x" % value)

    def _read_byte(self, ack):
        value=0
        for _ in range(8):
            self._drive(False,True)
            self._high(False)
            value=(value << 1) | (self.lines() & 1)
            self._drive(False,True)
        self._drive(ack,True)
        self._high(ack)
        self._drive(ack,True)
        self._drive(False,True)
        return value

    @staticmethod
    def _validate(address,register,value=None):
        if type(address) is not int or not 0<=address<128 or type(register) is not int or not 0<=register<256:
            raise ValueError("7-bit address and 8-bit register required")
        if value is not None and (type(value) is not int or not 0<=value<65536):
            raise ValueError("16-bit register value required")

    def read16(self,address,register):
        self._validate(address,register)
        try:
            self._start()
            self._write_byte(address << 1)
            self._write_byte(register)
            self._start(repeated=True)
            self._write_byte((address << 1)|1)
            value=(self._read_byte(True)<<8)|self._read_byte(False)
            self._stop()
            return value
        except BaseException:
            # Try STOP for NACK/interrupt, then unconditionally release both pins.
            try: self._stop()
            except Exception: pass
            raise
        finally:
            self.release()

    def write16(self,address,register,value):
        self._validate(address,register,value)
        try:
            self._start()
            for byte in (address << 1,register,value >> 8,value & 255):self._write_byte(byte)
            self._stop()
        except BaseException:
            try:self._stop()
            except Exception:pass
            raise
        finally:
            self.release()

class MT9V034:
    ADDRESSES=(0x48,0x4C,0x58,0x5C)
    OBSERVED=(0x00,0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x0B,0x0D,0x0E,
              0x0F,0x35,0x36,0xAF,0xBA,0xBB,0xD2,0xD5,0xD8,0xFE)
    WRITABLE=(0x0F,0x0B,0xD2,0x35,0x36,0xD5,0xD8,0xAF)
    def __init__(self,bus,address):
        self.bus,self.address=bus,address
        self.original=None

    @classmethod
    def probe(cls,bus):
        found=[]
        for address in cls.ADDRESSES:
            try: identity=bus.read16(address,0)
            except Nack:continue
            if identity==0x1324:
                if any(bus.read16(address,0)!=identity for _ in range(2)):
                    raise SensorError("unstable chip ID")
                found.append(address)
            else:
                raise SensorError("unexpected identity 0x%04x at 0x%02x" % (identity,address))
        if len(found)!=1:raise SensorError("expected one MT9V024/034-family responder; found %r" % found)
        return cls(bus,found[0])

    def snapshot(self):
        return {"0x%02X" % r:self.bus.read16(self.address,r) for r in self.OBSERVED}

    def _write_checked(self,reg,value):
        if reg not in self.WRITABLE:raise SensorError("register not permitted")
        self.bus.write16(self.address,reg,value)
        if self.bus.read16(self.address,reg)!=value:
            raise SensorError("sensor readback mismatch at 0x%02X" % reg)

    def apply_manual(self,rows,gain):
        # Conservative setup range; no geometry/frame-rate changes or ms claim.
        if type(rows) is not int or not 1<=rows<=480 or type(gain) is not int or not 16<=gain<=32:
            raise ValueError("pilot controls require 1..480 rows and 16..32 gain units")
        if self.original is not None:raise SensorError("manual configuration already active")
        before=self.snapshot()
        if before['0x00']!=0x1324 or before['0xFE']!=0xBEEF:
            raise SensorError("unexpected identity or locked register bank")
        if before['0x03']!=480 or before['0x04']!=752 or (before['0x0D']|before['0x0E']) & 15:
            raise SensorError("unsupported geometry/binning; will not change it")
        self.original={reg:before['0x%02X'%reg] for reg in self.WRITABLE}
        # Configure BOTH contexts identically without switching context.
        self._write_checked(0xAF,self.original[0xAF] & ~0x0303)
        self._write_checked(0x0F,self.original[0x0F] & ~0x0101) # linear mode, both contexts
        for reg,value in ((0x0B,rows),(0xD2,rows),
                          (0x35,(self.original[0x35] & ~0x7F)|gain),
                          (0x36,(self.original[0x36] & ~0x7F)|gain),(0xD5,0),(0xD8,0)):
            self._write_checked(reg,value)
        return {'before':before,'after':self.snapshot(),'exposure_rows':rows,
                'gain_units':gain,'gain_factor':gain/16,'fine_exposure_clocks':0,
                'exposure_ms_measured':None,'both_contexts_configured':True,'linear_mode_temporarily_enabled':True}

    def restore(self):
        if self.original is None:return False
        failures=[]
        # Restore stored manual settings first, automatic enables last.
        for reg in self.WRITABLE:
            try:self._write_checked(reg,self.original[reg])
            except Exception as exc:failures.append('0x%02X: %s'%(reg,exc))
        if failures:raise SensorError("restore incomplete: "+'; '.join(failures))
        self.original=None
        return True
