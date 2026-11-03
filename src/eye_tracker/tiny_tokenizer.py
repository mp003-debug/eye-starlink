"""Pure-Python ByteLevel BPE for the pinned MiniMind tokenizer; no dependencies."""
import json,re,unicodedata
from pathlib import Path

def pieces(text):
    # GPT-2 regex precedence, expressed with Unicode category checks.
    i=0
    def kind(c):
        category=unicodedata.category(c)
        return 'L' if category[0]=='L' else 'N' if category[0]=='N' else 'W' if c.isspace() else 'P'
    while i<len(text):
        contraction=next((s for s in ("'s","'t","'re","'ve","'m","'ll","'d") if text.startswith(s,i)),None)
        if contraction:yield contraction;i+=len(contraction);continue
        start=i
        if text[i]==' ' and i+1<len(text) and kind(text[i+1])!='W':i+=1
        k=kind(text[i]);i+=1
        while i<len(text) and kind(text[i])==k:i+=1
        if k=='W' and i<len(text) and i-start>1:i-=1
        yield text[start:i]

class TinyTokenizer:
    def __init__(self,path):
        t=json.loads(Path(path).read_text(encoding='utf-8'))
        assert t['model']['type']=='BPE' and t['pre_tokenizer']['type']=='ByteLevel'
        self.vocab=t['model']['vocab'];self.inverse={v:k for k,v in self.vocab.items()}
        self.ranks={tuple(m if isinstance(m,list) else m.split()):i for i,m in enumerate(t['model']['merges'])}
        bs=list(range(33,127))+list(range(161,173))+list(range(174,256));cs=bs.copy();n=0
        for b in range(256):
            if b not in bs:bs.append(b);cs.append(256+n);n+=1
        self.encode_byte=dict(zip(bs,map(chr,cs)));self.decode_byte={c:b for b,c in self.encode_byte.items()}
        self.special={r['content']:r['id'] for r in t['added_tokens']}
        self.splitter=re.compile('('+'|'.join(re.escape(s) for s in self.special)+')')
    def encode(self,text):
        if not isinstance(text,str) or len(text)>4096:raise ValueError('prompt_bounds')
        ids=[]
        for span in self.splitter.split(text):
            if span in self.special:ids.append(self.special[span]);continue
            for p in pieces(span):
                symbols=[self.encode_byte[b] for b in p.encode('utf-8')]
                while len(symbols)>1:
                    pairs=[(self.ranks.get((symbols[i],symbols[i+1]),10**9),i) for i in range(len(symbols)-1)]
                    rank,i=min(pairs)
                    if rank==10**9:break
                    symbols[i:i+2]=[symbols[i]+symbols[i+1]]
                ids.extend(self.vocab[s] for s in symbols)
        return ids
    def decode(self,ids):
        special_ids=set(self.special.values())
        raw=bytes(self.decode_byte[c] for i in ids if i not in special_ids for c in self.inverse[i])
        return raw.decode('utf-8','replace')
    def prompt(self,text):
        if any(s in text for s in self.special):raise ValueError('special_tokens_not_allowed_in_user_text')
        return self.encode('<|im_start|>user\n'+text+'<|im_end|>\n<|im_start|>assistant\n')
