"""Generate only the public B1 concept narration; no project data is uploaded."""
import asyncio
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/deps/voice_tools'))
import edge_tts

OUT = ROOT / 'assets/video_sources/amd_b1/revision3'
VOICE, SPEED, PITCH = 'zh-CN-YunjianNeural', '-12%', '-6Hz'
LINES = [
    (1.0, '想象，从一枚芯片开始。'),
    (6.2, '每一次思考，都在寻找，更进一步的可能。'),
    (12.8, 'AMD 锐龙。让计算的力量，走进游戏与创作。'),
    (20.2, '在虚拟世界里，探索新的边界。'),
    (26.3, '在灵感涌现时，把想法变成作品。'),
    (33.0, '从专注当下，到创造下一刻。'),
    (38.8, 'AMD 锐龙。让灵感，持续向前。'),
]

async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    voices = await asyncio.wait_for(edge_tts.list_voices(proxy=urllib.request.getproxies().get('https')), timeout=45)
    selected = [v for v in voices if v['ShortName'] == VOICE]
    assert len(selected) == 1 and selected[0]['Gender'] == 'Male', 'requested male voice unavailable'
    (OUT/'voice_selection.json').write_text(json.dumps(selected[0], ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    rows = []
    for i, (start, text) in enumerate(LINES, 1):
        path = OUT / ('voice_%02d.mp3' % i)
        if not path.exists():
            pending = path.with_suffix('.pending.mp3')
            talk = edge_tts.Communicate(text, VOICE, rate=SPEED,
                pitch=PITCH, proxy=urllib.request.getproxies().get('https'),
                connect_timeout=15, receive_timeout=45)
            await asyncio.wait_for(talk.save(str(pending)), timeout=60)
            pending.replace(path)
        rows.append(dict(start=start, text=text, file=path.name,
                         sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        print('Narration %d/7 ready' % i, flush=True)
    data = dict(voice=VOICE, rate=SPEED, pitch=PITCH,
                synthetic_voice=True, service='Microsoft Edge online TTS via edge-tts',
                source='https://github.com/rany2/edge-tts', lines=rows)
    (OUT/'narration.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

if __name__ == '__main__':
    asyncio.run(main())
