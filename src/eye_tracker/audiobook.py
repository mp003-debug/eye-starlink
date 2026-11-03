"""Local chapter audio using the existing bounded stream, with private bookmarks."""
import json,os,time
from pathlib import Path
from .music import MusicLibrary,MusicPlayer,RATE

class Bookmarks:
    def __init__(self,library,path=None):
        self.library=library;self.path=Path(path) if path is not None else None
        self.positions={};self.selected=0;self.warning=False
        if self.path is None or not self.path.exists():return
        try:
            if self.path.stat().st_size>16384:raise ValueError('bookmark too large')
            data=json.loads(self.path.read_text(encoding='utf-8'))
            if data.get('version')!=1 or type(data.get('chapters')) is not dict or len(data['chapters'])>32:raise ValueError('invalid bookmark')
            for i,t in enumerate(library.tracks):
                row=data['chapters'].get(t['id'])
                if row is None:continue
                if not isinstance(row,dict) or type(row.get('samples')) is not int or not 0<=row['samples']<=t['frames']:raise ValueError('invalid bookmark position')
                if row.get('sha256')==t['sha256']:self.positions[t['id']]=row['samples']
                if data.get('selected')==t['id']:self.selected=i
        except (ValueError,TypeError,AttributeError,OSError):self.positions={};self.selected=0;self.warning=True

    def position(self,index):return self.positions.get(self.library.tracks[index]['id'],0)

    def save(self,index,position):
        if not self.library.tracks:return
        t=self.library.tracks[index];position=max(0,min(t['frames'],int(position)))
        self.positions[t['id']]=position;self.selected=index
        if self.path is None:return
        data=dict(version=1,selected=t['id'],chapters={t['id']:dict(sha256=t['sha256'],samples=self.positions[t['id']])
                  for t in self.library.tracks if t['id'] in self.positions})
        pending=self.path.with_suffix('.json.pending')
        try:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with pending.open('w',encoding='utf-8') as f:
                json.dump(data,f,ensure_ascii=False);f.write('\n');f.flush();os.fsync(f.fileno())
            pending.replace(self.path);self.warning=False
        finally:
            if pending.exists():pending.unlink()

class AudioBookPlayer:
    def __init__(self,device,library,bookmarks,clock=time.monotonic):
        self.stream=MusicPlayer(device,library,clock);self.library=library;self.bookmarks=bookmarks;self.clock=clock
        self.stream.index=bookmarks.selected
        self.stream.offset=bookmarks.position(self.stream.index) if library.tracks else 0
        self.last_saved=clock();self.save_failed=False;self.ends=0;self._ended=False

    @property
    def index(self):return self.stream.index
    @property
    def position(self):return self.stream.offset
    @property
    def state(self):return self.stream.state

    def persist(self):
        try:self.bookmarks.save(self.index,self.position);self.save_failed=False
        except OSError:self.save_failed=True
        self.last_saved=self.clock()

    def suspend(self):
        # STOP releases the common hardware before any help utterance can start.
        self.stream.suspend();self.persist()

    def action(self,command):
        if command=='book_toggle':
            if self.state in ('playing','pausing'):self.suspend()
            else:self.stream.play();self._ended=False
        elif command in ('book_next','book_previous'):
            self.suspend()
            if self.library.tracks:
                self.stream.index=(self.index+(1 if command=='book_next' else -1))%len(self.library.tracks)
                self.stream.offset=self.bookmarks.position(self.index);self.stream.state='paused';self._ended=False;self.persist()
        elif command=='book_restart':
            self.suspend();self.stream.offset=0;self.stream.state='paused';self.persist();self.stream.play();self._ended=False
        elif command in ('book_exit','book_options','book_chapters'):self.suspend()
        else:raise ValueError('unknown book action')

    def poll(self):
        previous=self.position
        try:self.stream.poll()
        except Exception:
            # The shared player stops on faults; retain the last confirmed cursor.
            self.stream.offset=previous;self.persist();raise
        if self.state=='ended' and not self._ended:self._ended=True;self.ends+=1;self.persist()
        elif self.state=='playing' and self.clock()-self.last_saved>=30:self.persist()

    def close(self):self.suspend()

    def snapshot(self):
        return dict(state=self.state,chapter_index=self.index,position_samples=self.position,
                    total_samples=self.library.tracks[self.index]['frames'] if self.library.tracks else 0,
                    chapters=len(self.library.tracks),ends=self.ends,
                    bookmark_warning=self.save_failed or self.bookmarks.warning)
