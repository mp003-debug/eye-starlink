"""Bake a bounded Chinese coverage atlas; no font or IME dependency on board."""
import ast,hashlib,json,sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from eye_tracker.composer import PinyinLexicon,SYMBOLS

def main():
    lex=PinyinLexicon(ROOT/'assets/typing/pinyin.json')
    chars=set(lex.allowed)|set(chr(i) for i in range(32,127))|set('ü–…')
    for name in ('daily_tools.py','text_ui.py','composer.py','pastimes.py','audiobook.py','sharing_ui.py','share_link.py','share_protocol.py','ai_writing.py'):
        tree=ast.parse((ROOT/'src/eye_tracker'/name).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Constant) and isinstance(node.value,str):chars.update(node.value)
    album=json.loads((ROOT/'assets/photos/album.json').read_text(encoding='utf-8'))
    for item in album['photos']:chars.update(item['title'])
    video=ROOT/'assets/video/playlist.json'
    if video.exists():
        for item in json.loads(video.read_text(encoding='utf-8'))['clips']:chars.update(item['title'])
    books=ROOT/'assets/audiobooks/playlist.json'
    if books.exists():
        for item in json.loads(books.read_text(encoding='utf-8'))['tracks']:chars.update(item['title'])
    chars=''.join(sorted(c for c in chars if c.isprintable()))
    arrays={}
    for size in (14,18,28,36):
        font=ImageFont.truetype('assets/fonts/noto_sans_cjk_sc.otf',size)
        cells=[];advances=[]
        for ch in chars:
            im=Image.new('L',(size+8,size+10))
            ImageDraw.Draw(im).text((2,-font.getbbox('国')[1]),ch,font=font,fill=255)
            cells.append(np.asarray(im));advances.append(max(1,round(font.getlength(ch))))
        arrays['glyphs_'+str(size)]=np.stack(cells)
        arrays['advances_'+str(size)]=np.asarray(advances,dtype=np.uint8)
    meta=dict(version=2,characters=chars,dictionary_sha256=lex.sha256,sizes=[14,18,28,36],font_file_distributed=False)
    arrays['metadata']=np.frombuffer(json.dumps(meta,ensure_ascii=False).encode('utf-8'),dtype=np.uint8)
    target=ROOT/'assets/typing/glyphs.npz';np.savez_compressed(target,**arrays)
    print(json.dumps(dict(glyphs=len(chars),bytes=target.stat().st_size,uncompressed_bytes=sum(a.nbytes for a in arrays.values()))))

if __name__=='__main__':main()
