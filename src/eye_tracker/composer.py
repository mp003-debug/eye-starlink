"""Offline single-syllable character input and explicitly saved local phrases."""
import hashlib,json,os,re
from pathlib import Path

MAX_TEXT=64
MAX_FAVORITES=12
SYMBOLS='0123456789，。？！、：；（）-+%'
# Local, editable draft shortcuts. Never spoken or sent automatically.
COMMON_EXPRESSIONS=(
    ('日常需要',('我想喝水','我想休息','请帮我换个姿势','我想上厕所','我不舒服','我有点冷',
                '我有点热','我想听音乐','我想看视频','我想看照片')),
    ('交流心意',('你好','谢谢','请等一下','请再说一遍','我想和你聊天','我想见家人',
                '我想安静一会','我喜欢','我想你','没关系')),
)


class PinyinLexicon:
    def __init__(self,path):
        p=Path(path)
        if p.stat().st_size>1024*1024:raise ValueError('pinyin dictionary too large')
        raw=p.read_bytes();data=json.loads(raw)
        if not isinstance(data,dict):raise ValueError('invalid pinyin dictionary')
        entries=data.get('syllables')
        if type(data.get('version')) is not int or data['version']!=1 or not isinstance(entries,dict) or not 1<=len(entries)<=500:
            raise ValueError('invalid pinyin dictionary')
        chars=set()
        for key,value in entries.items():
            if (not re.fullmatch('[a-z]{1,6}',key) or not isinstance(value,str) or not 1<=len(value)<=512 or
                len(set(value))!=len(value) or any(not '\u4e00'<=c<='\u9fff' for c in value)):
                raise ValueError('invalid pinyin candidates')
            chars.update(value)
        if len(chars)>8105:raise ValueError('too many dictionary characters')
        self.entries=entries;self.characters=frozenset(chars);self.sha256=hashlib.sha256(raw).hexdigest()
        self.allowed=self.characters|frozenset(SYMBOLS)
        self.continuations={}
        for syllable in entries:
            for i,ch in enumerate(syllable):
                self.continuations.setdefault(syllable[:i],set()).add(ch)
        self.continuations={p:''.join(sorted(chars)) for p,chars in self.continuations.items()}

    def candidates(self,pinyin):return self.entries.get(pinyin,'')

    def next_letters(self,pinyin):return self.continuations.get(pinyin,'')

    def valid_text(self,text):
        return isinstance(text,str) and 1<=len(text)<=MAX_TEXT and all(c in self.allowed for c in text)


class Favorites:
    def __init__(self,lexicon,path=None):
        self.lexicon=lexicon;self.path=Path(path) if path is not None else None;self.items=[]
        if self.path is not None and self.path.exists():
            if self.path.stat().st_size>16384:raise ValueError('favorites too large')
            data=json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data,dict):raise ValueError('invalid favorites')
            items=data.get('items')
            if (type(data.get('version')) is not int or data['version']!=1 or not isinstance(items,list) or
                len(items)>MAX_FAVORITES or any(not lexicon.valid_text(s) for s in items) or len(set(items))!=len(items)):
                raise ValueError('invalid favorites')
            self.items=list(items)

    def _commit(self,items):
        if self.path is not None:
            pending=self.path.with_suffix('.json.pending')
            try:
                self.path.parent.mkdir(parents=True,exist_ok=True)
                with pending.open('w',encoding='utf-8') as f:
                    json.dump({'version':1,'items':items},f,ensure_ascii=False);f.write('\n');f.flush();os.fsync(f.fileno())
                pending.replace(self.path)
            finally:
                if pending.exists():pending.unlink()
        self.items=list(items)

    def save(self,text):
        if not self.lexicon.valid_text(text):raise ValueError('empty or invalid phrase')
        if text in self.items:return 'already_saved'
        if len(self.items)>=MAX_FAVORITES:return 'full'
        self._commit(self.items+[text]);return 'saved'

    def delete(self,index):
        if type(index) is not int or not 0<=index<len(self.items):raise ValueError('invalid favorite index')
        self._commit(self.items[:index]+self.items[index+1:])


class Composer:
    def __init__(self,lexicon,favorites):
        self.lexicon=lexicon;self.favorites=favorites;self.text='';self.pinyin='';self._edits=[]
    def _set_text(self,text):
        if text==self.text:return
        if self._edits and self._edits[-1][1]!=self.text:self._edits=[]
        self._edits.append((self.text,text));self._edits=self._edits[-16:];self.text=text
    def can_undo(self):return bool(self._edits and self._edits[-1][1]==self.text)
    def undo(self):
        if not self.can_undo():return False
        before,_=self._edits.pop();self.text=before;return True
    def load(self,text):
        if not self.lexicon.valid_text(text):raise ValueError('invalid draft')
        self._set_text(text);self.pinyin=''
    def letter(self,letter):
        if not isinstance(letter,str) or not re.fullmatch('[a-z]',letter):raise ValueError('invalid letter')
        if len(self.pinyin)>=6:return False
        self.pinyin+=letter;return True
    def append(self,char):
        if not isinstance(char,str) or len(char)!=1 or char not in self.lexicon.allowed:raise ValueError('invalid character')
        if len(self.text)>=MAX_TEXT:return False
        self._set_text(self.text+char);return True
    def append_text(self,text):
        if not self.lexicon.valid_text(text):raise ValueError('invalid phrase')
        if len(self.text)+len(text)>MAX_TEXT:return False
        self._set_text(self.text+text);return True
    def candidates(self):
        chars=self.lexicon.candidates(self.pinyin)
        if not self.text:return chars
        # Explicit local favorites and fixed phrases only; no learning writes,
        # cloud input, telemetry of text, or change to recognition thresholds.
        phrases=tuple(self.favorites.items)+tuple(s for _,items in COMMON_EXPRESSIONS for s in items)
        ranked=[]
        for size in range(min(len(self.text),MAX_TEXT),0,-1):
            suffix=self.text[-size:]
            for phrase in phrases:
                if phrase.startswith(suffix) and len(phrase)>size and phrase[size] in chars:
                    if phrase[size] not in ranked:ranked.append(phrase[size])
        return ''.join(ranked)+''.join(ch for ch in chars if ch not in ranked)
    def _phrases(self):
        # Stable local vocabulary, with explicit favorites as extra suggestions.
        return tuple(dict.fromkeys(tuple(s for _,items in COMMON_EXPRESSIONS for s in items)+tuple(self.favorites.items)))
    def phrase_candidates(self):
        chars=self.lexicon.candidates(self.pinyin)
        return tuple(s for s in self._phrases() if len(s)>1 and s[0] in chars and
                     len(self.text)+len(s)<=MAX_TEXT)[:3]
    def continuations(self):
        if self.pinyin or not self.text:return ()
        result=[]
        for size in range(min(len(self.text),MAX_TEXT),0,-1):
            suffix=self.text[-size:]
            for phrase in self._phrases():
                if phrase.startswith(suffix) and len(phrase)>size:
                    tail=phrase[size:]
                    if len(self.text)+len(tail)<=MAX_TEXT and tail not in result:result.append(tail)
        return tuple(result[:2])
    def phrase_candidate(self,text):
        if text not in self.phrase_candidates():raise ValueError('not an offered phrase candidate')
        if not self.append_text(text):return False
        self.pinyin='';return True
    def candidate(self,index):
        chars=self.candidates()
        if type(index) is not int or not 0<=index<len(chars):raise ValueError('invalid candidate')
        if not self.append(chars[index]):return False
        self.pinyin='';return True
    def erase(self):
        if self.pinyin:self.pinyin=self.pinyin[:-1]
        else:self._set_text(self.text[:-1])
    def clear(self):self._set_text('');self.pinyin=''
