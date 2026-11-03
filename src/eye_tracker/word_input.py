"""Bounded offline initials lookup; suggestions never commit themselves."""
from bisect import bisect_left
from pathlib import Path
import hashlib,json,re

class WordLexicon:
    def __init__(self,path,characters):
        path=Path(path)
        if path.stat().st_size>2*1024*1024:raise ValueError('word dictionary too large')
        raw=path.read_bytes();data=json.loads(raw)
        if not isinstance(data,dict) or type(data.get('version')) is not int or data['version']!=1 or data.get('character_dictionary_sha256')!=characters.sha256:
            raise ValueError('word dictionary mismatch')
        rows=data.get('entries')
        if not isinstance(rows,list) or not 1<=len(rows)<=20000:raise ValueError('invalid word dictionary')
        initials={c:set() for c in characters.characters}
        for py,chars in characters.entries.items():
            for c in chars:initials[c].add(py[0])
        self.index={};self.primary={};self.words=[];seen=set();key_count=0
        for row in rows:
            if not isinstance(row,list) or len(row)!=3:raise ValueError('invalid word row')
            text,weight,keys=row
            if (not isinstance(text,str) or not 1<=len(text)<=6 or text in seen or
                any(c not in characters.characters for c in text) or type(weight) is not int or not 0<weight<=10**12 or
                not isinstance(keys,list) or not 1<=len(keys)<=16 or any(not isinstance(k,str) for k in keys) or len(set(keys))!=len(keys)):
                raise ValueError('invalid word entry')
            for key in keys:
                if (not isinstance(key,str) or not re.fullmatch('[a-z]{1,6}',key) or len(key)!=len(text) or
                    any(k not in initials[c] for k,c in zip(key,text))):raise ValueError('invalid word initials')
                self.index.setdefault(key,[]).append(len(self.words));key_count+=1
            self.primary.setdefault(keys[0],set()).add(len(self.words))
            seen.add(text);self.words.append((text,weight))
        if key_count>100000:raise ValueError('too many word aliases')
        self.keys=tuple(sorted(self.index));self.sha256=hashlib.sha256(raw).hexdigest()
        self.characters=characters;self._lookup_cache={};self._letters_cache={}

    def _keys(self,prefix):
        start=bisect_left(self.keys,prefix);end=bisect_left(self.keys,prefix+'{')
        return self.keys[start:end]

    def next_letters(self,prefix):
        if prefix not in self._letters_cache:
            if len(self._letters_cache)>=128:self._letters_cache.clear()
            self._letters_cache[prefix]=''.join(sorted({k[len(prefix)] for k in self._keys(prefix) if len(k)>len(prefix)}))
        return self._letters_cache[prefix]

    def lookup(self,prefix):
        if not prefix:return ()
        if prefix not in self._lookup_cache:
            # One initial offers single characters only; two or more offer words.
            exact=set(self.index.get(prefix,()))
            more=set() if len(prefix)==1 else {i for k in self._keys(prefix) for i in self.index[k]}-exact
            primary=self.primary.get(prefix,set())
            order=lambda i:(i not in primary,-self.words[i][1],self.words[i][0])
            result=tuple(self.words[i][0] for i in sorted(exact,key=order)+sorted(more,key=order))
            if len(self._lookup_cache)>=64:self._lookup_cache.clear()
            self._lookup_cache[prefix]=result
        return self._lookup_cache[prefix]
