"""Generate explicitly synthetic audio fixtures for offline regression only.

These are tones, NOT spoken care messages. Do not deploy them as user prompts.
Existing WAV files are never replaced. No network or board access.
"""
from pathlib import Path
import array,hashlib,json,math,wave
ROOT=Path(__file__).resolve().parents[1]
def main():
    folder=ROOT/'assets/speech';manifest=folder/'manifest.json'
    meta=json.loads(manifest.read_text(encoding='utf-8'))
    for key,row in meta['phrases'].items():
        p=folder/row['file']
        if not p.exists():
            pcm=array.array('h',(round(6000*math.sin(2*math.pi*220*i/16000)) for i in range(row['samples'])))
            with wave.open(str(p),'wb') as w:
                w.setparams((1,2,16000,len(pcm),'NONE',''));w.writeframes(pcm.tobytes())
            row['sha256']=hashlib.sha256(p.read_bytes()).hexdigest();row['peak_abs_pcm']=6000
            row['source']='SYNTHETIC TEST TONE; not a spoken care message'
    meta['source']='Public offline regression fixtures; synthetic tones only'
    manifest.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Synthetic test tones prepared. Do not deploy as speech prompts.')
if __name__=='__main__':main()
