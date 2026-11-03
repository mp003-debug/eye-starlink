"""Build private monochrome GB2312 receiver font and validation bitset."""
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import json,hashlib
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'comm/receiver_upgrade/receivers/application/samples/products/sle_uart/eye_link'
font=ImageFont.truetype('assets/fonts/noto_sans_cjk_sc.otf',24)
glyphs=[];valid=[]
for index in range(95+87*94):
    raw=bytes([index+32]) if index<95 else bytes([0xa1+(index-95)//94,0xa1+(index-95)%94])
    try:text=raw.decode('gb2312');ok=len(text)==1 and text.isprintable()
    except UnicodeDecodeError:text='';ok=False
    valid.append(int(ok));im=Image.new('1',(24,24),0)
    if ok:ImageDraw.Draw(im).text((0,-font.getbbox('国')[1]),text,font=font,fill=1)
    glyphs.append(im.tobytes())
def array(name,raw):
    lines=['static const unsigned char '+name+'[] = {']
    for i in range(0,len(raw),32):lines.append(','.join(str(b) for b in raw[i:i+32])+',')
    return '\n'.join(lines+['};',''])
(OUT/'eye_share_font.h').write_text('/* Generated 24px Noto Sans CJK glyph subset; SIL OFL 1.1; see assets/fonts/license.txt. */\n'+array('share_font',b''.join(glyphs)),encoding='utf-8')
(OUT/'eye_share_valid.h').write_text(array('share_glyph_valid',bytes(valid)),encoding='utf-8')
print(json.dumps({'glyph_slots':len(glyphs),'supported':sum(valid),'bitmap_bytes':sum(map(len,glyphs))}))
