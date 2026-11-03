"""Offline artifact checks; this module never imports a board or starts a job."""
import hashlib,json
from pathlib import Path

class AIBundle:
    def __init__(self,path):
        self.path=Path(path).resolve();p=self.path/'manifest.json'
        if p.stat().st_size>200000:raise ValueError('AI manifest too large')
        self.manifest=json.loads(p.read_text(encoding='utf-8'))
        if self.manifest.get('version')!=1 or self.manifest.get('platform')!='linux-armv7l':raise ValueError('AI bundle version')
        if self.manifest.get('audio_backend')!='file-only local adapter; no ALSA or PulseAudio output':raise ValueError('file-only audio backend required')
        files=self.manifest['files']
        for name in ('tiny_run','minimind_q8.bin','tokenizer.json','tts/bin/espeak-ng','tts/lib/libespeak-ng.so.1'):
            if name not in files:raise ValueError('AI bundle incomplete')
        for name,digest in files.items():
            raw=self.path/name;q=raw.resolve()
            if self.path not in q.parents or raw.is_symlink():raise ValueError('AI artifact path')
            if hashlib.sha256(q.read_bytes()).hexdigest()!=digest:raise ValueError('AI artifact hash: '+name)
        self.sha256=hashlib.sha256(p.read_bytes()).hexdigest()
