"""Local bounded WAV streaming on audio IP v2. No background hardware owner."""
import hashlib,json,time,wave
from pathlib import Path
import numpy as np
from .audio import AudioError
from .music_settings import MusicVolume

RATE=16000
BANK_SAMPLES=16384


class MusicLibrary:
    def __init__(self,folder,volume_path=None):
        self.folder=Path(folder).resolve()
        self.volume_path=volume_path
        self.volume=MusicVolume(volume_path)
        playlist_bytes=(self.folder/'playlist.json').read_bytes()
        self.playlist_sha256=hashlib.sha256(playlist_bytes).hexdigest()
        data=json.loads(playlist_bytes)
        if data.get('version')!=1 or not isinstance(data.get('tracks'),list) or len(data['tracks'])>32:
            raise ValueError('invalid bounded music playlist')
        self.tracks=[];ids=set()
        for row in data['tracks']:
            key,title,name,digest=(row.get(k) for k in ('id','title','file','sha256'))
            if (not isinstance(key,str) or not key or key in ids or not isinstance(title,str)
                    or not 1<=len(title)<=40 or any(ord(c)<32 for c in title)
                    or not isinstance(name,str) or Path(name).is_absolute()):
                raise ValueError('invalid music entry')
            path=(self.folder/name).resolve()
            try:path.relative_to(self.folder)
            except ValueError:raise ValueError('music file escapes library')
            if path.suffix.lower()!='.wav':raise ValueError('music requires local WAV')
            h=hashlib.sha256()
            with path.open('rb') as f:
                for block in iter(lambda:f.read(65536),b''):h.update(block)
            if h.hexdigest()!=digest:raise ValueError('music SHA256 mismatch')
            with wave.open(str(path),'rb') as w:
                if (w.getnchannels(),w.getsampwidth(),w.getframerate(),w.getcomptype())!=(1,2,RATE,'NONE'):
                    raise ValueError('music requires PCM16 mono 16kHz')
                frames=w.getnframes()
                if not 0<frames<=RATE*3600:raise ValueError('music length outside 0..1 hour')
                # Check the complete declared data without retaining the song.
                seen=0
                while seen<frames:
                    raw=w.readframes(BANK_SAMPLES)
                    if not raw or len(raw)%2:raise ValueError('truncated music PCM')
                    values=np.frombuffer(raw,dtype='<i2')
                    if np.max(np.abs(values.astype(np.int32)))>8191:
                        raise ValueError('music peak exceeds audio asset bound')
                    seen+=len(values)
                if seen!=frames:raise ValueError('music frame count mismatch')
            stamp=path.stat()
            self.tracks.append(dict(id=key,title=title,path=path,frames=frames,sha256=digest,
                                    file_stamp=(stamp.st_size,stamp.st_mtime_ns)));ids.add(key)

    def provenance(self):
        return dict(playlist_sha256=self.playlist_sha256,
                    tracks=[{k:t[k] for k in ('id','title','frames','sha256')} for t in self.tracks])


class StreamAudioDevice:
    def __init__(self,mmio):
        self.mmio=mmio
        if mmio.read(0)!=0x41554431 or mmio.read(4)!=0x00020000:
            raise AudioError('music requires audio IP v2; rebuild the upgrade bitstream')
        if mmio.read(0x0c)&1:raise AudioError('audio already owned')

    def stop(self):
        self.mmio.write(8,2)
        if self.mmio.read(0x0c)&1:raise AudioError('stream did not stop')

    def prepare(self):
        self.stop();self.mmio.write(8,4);self.mmio.write(0x30,1)

    def submit(self,bank,samples,last):
        if bank not in (0,1) or not isinstance(samples,np.ndarray) or samples.dtype!=np.dtype('<i2') or samples.ndim!=1 or not 0<len(samples)<=BANK_SAMPLES:
            raise ValueError('invalid audio bank')
        if self.mmio.read(0x34)&(1<<bank):raise AudioError('audio bank still owned')
        words=np.pad(samples,(0,len(samples)%2)).astype('<i2',copy=False).view('<u4')
        start=(0x10000+bank*0x8000)//4
        self.mmio.array[start:start+len(words)]=words
        if not np.array_equal(self.mmio.array[start:start+len(words)],words):raise AudioError('stream PCM readback mismatch')
        self.mmio.write(0x38+bank*4,len(samples)|(0x80000000 if last else 0))
        if not self.mmio.read(0x34)&(1<<bank):raise AudioError('audio bank commit not acknowledged')

    def start(self):
        if not self.mmio.read(0x0c)&8:raise AudioError('audio clock missing')
        self.mmio.write(8,1)
        if not self.mmio.read(0x0c)&1:raise AudioError('stream start not acknowledged')

    def snapshot(self):
        status=self.mmio.read(0x0c)
        if status&4:raise AudioError('audio underrun' if status&32 else 'audio clock fault')
        return dict(busy=bool(status&1),done=bool(status&2),paused=bool(status&16),
                    banks=self.mmio.read(0x34)&3,consumed=self.mmio.read(0x40))

    def pause(self):self.mmio.write(8,8)
    def resume(self):self.mmio.write(8,16)


class MusicPlayer:
    """Two 32KiB hardware banks and bounded block reads, never a whole song."""
    def __init__(self,device,library,clock=time.monotonic):
        self.device,self.library,self.clock=device,library,clock
        self.index=0;self.offset=0;self.base=0;self.reader=None;self.state='stopped'
        self.live=False;self.eof=False;self.next_bank=0;self.deadline=None;self.started=None
        self.last_consumed=0;self.progress_at=clock()
        self.volume=library.volume

    def _close(self):
        if self.reader is not None:self.reader.close();self.reader=None

    def _fill(self):
        for _ in range(2):
            if self.eof or self.device.snapshot()['banks']&(1<<self.next_bank):break
            raw=self.reader.readframes(BANK_SAMPLES)
            if not raw or len(raw)%2:raise AudioError('music ended before declared length')
            samples=np.frombuffer(raw,dtype='<i2')
            if np.max(np.abs(samples.astype(np.int32)))>8191:raise AudioError('music asset changed or peak too high')
            if self.volume.percent != 100:
                # Apply gain only to new, unowned buffers. Round symmetrically;
                # no changes to WAVs, the codec, or the speech playback path.
                values=samples.astype(np.int32)
                magnitude=(np.abs(values)*self.volume.percent+50)//100
                samples=(np.sign(values)*magnitude).astype('<i2')
            self.eof=self.reader.tell()==self.library.tracks[self.index]['frames']
            self.device.submit(self.next_bank,samples,self.eof);self.next_bank^=1

    def play(self):
        if not self.library.tracks:return False
        if self.state=='paused' and self.live:
            self.device.resume();self.state='playing';self.progress_at=self.clock();return True
        if self.state in ('playing','pausing'):return False
        track=self.library.tracks[self.index]
        stamp=track['path'].stat()
        if (stamp.st_size,stamp.st_mtime_ns)!=track['file_stamp']:
            raise AudioError('music file changed after validation')
        if self.offset>=track['frames']:self.offset=0
        try:
            self.device.prepare();self.live=True
            self.reader=wave.open(str(track['path']),'rb');self.reader.setpos(self.offset)
            self.base=self.offset;self.next_bank=0;self.eof=False
            self._fill();self.device.start();self.state='playing';self.started=self.clock()
            self.last_consumed=0;self.progress_at=self.clock()
            return True
        except BaseException:
            self.stop();raise

    def pause(self):
        if self.state=='playing':
            self.device.pause();self.state='pausing';self.deadline=self.clock()+.25

    def suspend(self):
        # Help/helper priority uses STOP immediately. Resume restarts at the
        # consumed sample; at most an in-flight sub-sample repeat is interrupted.
        if self.live:
            try:self.offset=self.base+self.device.snapshot()['consumed']
            finally:
                try:self.device.stop()
                finally:self.live=False;self._close()
        if self.library.tracks:self.state='paused'

    def stop(self):
        try:
            if self.live:self.device.stop()
        finally:
            self.live=False;self._close();self.state='stopped';self.offset=0

    def next(self):
        was_playing=self.state=='playing'
        self.stop()
        if self.library.tracks:
            self.index=(self.index+1)%len(self.library.tracks)
            if was_playing:self.play()

    def poll(self):
        if not self.live:return
        try:
            state=self.device.snapshot()
            self.offset=self.base+state['consumed']
            if state['done']:
                self.live=False;self._close();self.state='ended';return
            if not state['busy']:raise AudioError('stream stopped without completion')
            if state['consumed']!=self.last_consumed or state['paused']:
                self.last_consumed=state['consumed'];self.progress_at=self.clock()
            elif self.state=='playing' and self.clock()-self.progress_at>1.5:
                raise AudioError('audio stream progress timeout')
            if self.state=='pausing':
                if state['paused']:self.state='paused'
                elif self.clock()>self.deadline:raise AudioError('audio pause timeout')
            self._fill()
        except BaseException:
            self.stop();self.state='fault';raise

    def action(self,key):
        if key=='music_toggle':
            if self.state=='playing':self.pause()
            elif self.state!='pausing':self.play()
        elif key=='music_next':self.next()
        elif key in ('music_back','music_menu_back','music_volume_open'):self.stop()
        elif key in ('music_volume_down','music_volume_up'):
            if self.live:raise AudioError('stop music before changing volume')
            self.volume.adjust(-1 if key=='music_volume_down' else 1)

    def sync_display(self,controller):
        controller.music_track_index=self.index if self.library.tracks else -1
        controller.music_total_samples=int(self.library.tracks[self.index]['frames']) if self.library.tracks else 0
        controller.music_position_samples=int(self.offset)
        controller.music_volume_level=self.volume.level

    def feedback(self):
        if not self.library.tracks:return 'music_empty'
        return {'playing':'music_playing','pausing':'music_pausing','paused':'music_paused',
                'ended':'music_ended','fault':'music_fault'}.get(self.state,'music_ready')
