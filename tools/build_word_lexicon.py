"""Build initials words from already pinned local MIT dictionary sources."""
import hashlib,itertools,json,sys,unicodedata
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from eye_tracker.composer import PinyinLexicon

FRAGMENTS=('我想','我觉得','帮我','和你','陪我','有点','不想','听音乐','看视频','看照片','慢一点','一会儿','谢谢你')
PRIMARY={'音乐':'yy','银行':'yh','行走':'xz','觉得':'jd','了解':'lj','重庆':'cq','重复':'cf','重新':'cx','长大':'zd','快乐':'kl','行为':'xw'}

def main():
    folder=ROOT/'assets/typing';sources=ROOT/'build/daily_tools_20261031/sources'
    attribution=json.loads((folder/'attribution.json').read_text(encoding='utf-8'))
    source=sources/'frequency.txt';source_record=next(x for x in attribution['sources'] if x['file']==source.name)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==source_record['sha256']
    lex=PinyinLexicon(folder/'pinyin.json');initials={c:set() for c in lex.characters}
    for py,chars in lex.entries.items():
        for c in chars:initials[c].add(py[0])
    pronunciations=sources/'pinyin.txt';pinyin_record=next(x for x in attribution['sources'] if x['file']==pronunciations.name)
    assert hashlib.sha256(pronunciations.read_bytes()).hexdigest()==pinyin_record['sha256']
    primary={}
    for line in pronunciations.read_text(encoding='utf-8').splitlines():
        if not line.startswith('U+'):continue
        code,reading=line.split(':',1);ch=chr(int(code[2:],16))
        if ch in initials:
            first=unicodedata.normalize('NFD',reading.strip().split(',')[0].split()[0])[0]
            if first in initials[ch]:primary[ch]=first
    single={};aggregate=Counter();words={}
    for line in source.read_text(encoding='utf-8').splitlines():
        text,freq,*_=line.split();freq=int(freq)
        if not text or any(c not in lex.characters for c in text):continue
        for c in text:aggregate[c]+=freq
        if len(text)==1:single[text]=freq
        elif 2<=len(text)<=6 and freq>=20:words[text]=freq
    words=dict(sorted(words.items(),key=lambda p:(-p[1],p[0]))[:12000])
    words.update({s:max(words.get(s,0),180000) for s in FRAGMENTS})
    words.update({c:max(1,single.get(c,aggregate[c]//20)) for c in lex.characters})
    entries=[]
    for text,freq in sorted(words.items(),key=lambda p:(-p[1],p[0])):
        preferred=PRIMARY.get(text,''.join(primary.get(c,sorted(initials[c])[0]) for c in text))
        assert all(k in initials[c] for k,c in zip(preferred,text))
        aliases=itertools.product(*([primary.get(c,sorted(initials[c])[0])]+sorted(initials[c]-{primary.get(c,sorted(initials[c])[0])}) for c in text))
        keys=list(dict.fromkeys([preferred]+[''.join(chars) for chars in itertools.islice(aliases,16)]))[:16]
        # Retain bounded alternate initials; full pinyin remains available.
        entries.append([text,freq,keys])
    payload=dict(version=1,character_dictionary_sha256=lex.sha256,entries=entries)
    target=folder/'words.json';target.write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    record=dict(source=source_record,source_license='MIT; full jieba_license.txt and pinyin_license.txt alongside',
        character_dictionary_sha256=lex.sha256,words_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        single_characters=len(lex.characters),multi_character_words=len(entries)-len(lex.characters),bytes=target.stat().st_size,
        transformation='Top 12000 frequency-ranked supported 2–6-character words, 13 authored connective fragments, all supported single characters. First-listed reading plus 11 explicit common-word reading overrides ranked first; up to 16 alternate aliases. No cloud or automatic text insertion.',
        pronunciation_source=pinyin_record,authored_fragments=list(FRAGMENTS),common_reading_overrides=PRIMARY)
    (folder/'words_attribution.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in record.items() if k not in ('source','authored_fragments')},ensure_ascii=True))
if __name__=='__main__':main()
