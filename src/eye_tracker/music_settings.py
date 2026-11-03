"""Bounded music-only attenuation; speech and codec gain stay unchanged."""
import json
from pathlib import Path
from .audio import AudioError

VOLUME_LEVELS = (20, 40, 60, 80, 100)


class MusicVolume:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None
        self.level = 5  # Same amplitude as the previously listened-to music.
        if self.path is not None and self.path.exists():
            if self.path.stat().st_size > 1024:
                raise ValueError('invalid music volume settings')
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if (not isinstance(data, dict) or type(data.get('version')) is not int or data['version'] != 1 or
                    type(data.get('level')) is not int or not 1 <= data['level'] <= 5):
                raise ValueError('invalid music volume settings')
            self.level = data['level']

    @property
    def percent(self):
        return VOLUME_LEVELS[self.level - 1]

    def adjust(self, delta):
        if type(delta) is not int or delta not in (-1, 1):
            raise ValueError('music volume requires one step')
        level = max(1, min(5, self.level + delta))
        if level == self.level:
            return False
        if self.path is not None:
            staging = self.path.with_suffix('.json.pending')
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                staging.write_text(json.dumps({'version': 1, 'level': level})+'\n', encoding='utf-8')
                staging.replace(self.path)
            except OSError as exc:
                raise AudioError('music volume could not be saved') from exc
            finally:
                if staging.exists():
                    staging.unlink()
        self.level = level
        return True
