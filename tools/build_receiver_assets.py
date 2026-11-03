"""Generate actual 480x800 monochrome and 480x272 colour receiver UI assets.

The e-paper RAM is 800x480: portrait pixels rotate clockwise, as in the
existing SSD1677 asset layout. This generator does not connect to hardware.
"""
from pathlib import Path
import hashlib, json
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/receiver_upgrade_20261102/assets'
APP=ROOT/'comm/receiver_upgrade/receivers/application/samples/products/sle_uart'
FONT='assets/fonts/noto_sans_cjk_sc.otf'
PAGES=[('idle','等待消息','暂无待处理需求',False),
       ('water','日常照护','我想喝水',False),('water_ack','日常照护','我想喝水',True),
       ('rest','日常照护','我想休息',False),('rest_ack','日常照护','我想休息',True),
       ('help','优先求助','需要帮助',False),('help_ack','优先求助','需要帮助',True)]


def text(d,xy,s,size,fill,anchor=None):
    d.text(xy,s,font=ImageFont.truetype(FONT,size),fill=fill,anchor=anchor)


def symbol(d,kind,cx,cy,scale=1,colour='black'):
    # Small geometric marks, shared with the device UI; never encode meaning alone.
    def points(p):return [(cx+x*scale,cy+y*scale) for x,y in p]
    w=max(2,round(4*scale))
    if kind=='water':
        d.line(points([(-24,-32),(-18,32),(18,32),(24,-32),(-24,-32)]),fill=colour,width=w)
        d.line(points([(-20,4),(20,4)]),fill=colour,width=w)
    elif kind=='rest':
        d.line(points([(-32,-4),(-32,28),(32,28),(32,-4),(-32,-4)]),fill=colour,width=w)
        d.line(points([(-32,28),(-32,38)]),fill=colour,width=w)
        d.line(points([(32,28),(32,38)]),fill=colour,width=w)
        d.rectangle((cx-24*scale,cy-22*scale,cx-7*scale,cy-7*scale),outline=colour,width=w)
    elif kind=='help':
        d.ellipse((cx-34*scale,cy-34*scale,cx+34*scale,cy+34*scale),outline=colour,width=w)
        d.line(points([(0,-19),(0,9)]),fill=colour,width=w+1)
        d.ellipse((cx-3*scale,cy+18*scale,cx+3*scale,cy+24*scale),fill=colour)


def epaper(name,category,title,ack,node='03'):
    im=Image.new('RGB',(480,800),'white');d=ImageDraw.Draw(im)
    text(d,(30,26),'眼语 · 需求与表达',24,'black')
    text(d,(450,32),node+' · 接收端',18,'black','ra')
    d.line((30,84,450,84),fill='black',width=3)
    urgent=name.startswith('help');idle=name=='idle'
    if urgent:
        d.rounded_rectangle((30,112,450,174),radius=8,fill='black')
        text(d,(240,121),category,30,'white','ma')
    else:text(d,(30,122),category,28,'black')
    if not idle:symbol(d,name.split('_')[0],240,260,1.25)
    if idle:
        text(d,(240,282),'暂无待处理',48,'black','ma')
        text(d,(240,350),'需求',48,'black','ma')
        text(d,(240,446),'收到新需求后显示',26,'black','ma')
    else:
        text(d,(240,354),title,54,'black','ma')
        text(d,(240,450),'请尽快前来查看' if urgent else '请在方便时协助',27,'black','ma')
    d.line((30,598,450,598),fill='black',width=2)
    text(d,(30,625),'无待处理需求' if idle else ('本屏已确认 · 待处理' if ack else '待响应 · 本屏已收到'),28,'black')
    text(d,(30,678),'本屏操作不代表其他接收端状态',20,'black')
    text(d,(30,744),'SW1 确认收到',23,'black')
    text(d,(450,744),'SW2 本屏清除',23,'black','ra')
    # Deterministic threshold, avoiding stochastic dither and gray text on EPD.
    return im.convert('L').point(lambda p:255 if p>=160 else 0).convert('1')


def hmi(name,category,title,ack):
    urgent=name.startswith('help');idle=name=='idle'
    bg='#fff0ee' if urgent else '#f0f5fb';fg='#20344c';accent='#b22a2a' if urgent else '#175eac'
    im=Image.new('RGB',(480,272),bg);d=ImageDraw.Draw(im)
    d.rectangle((0,0,479,40),fill='white')
    text(d,(16,9),'眼语 · 接收端',19,fg);text(d,(464,12),'02 · 本屏状态',14,fg,'ra')
    text(d,(18,53),category,18,accent)
    if idle:
        text(d,(18,90),'暂无待处理需求',32,fg)
        for x,y,s in [(18,152,'照护需求'),(246,152,'交流表达'),(18,202,'情绪心意'),(246,202,'休闲娱乐')]:
            d.rounded_rectangle((x,y,x+216,y+42),radius=7,fill='white')
            text(d,(x+108,y+7),s,20,fg,'ma')
    else:
        text(d,(18,86),title,38,fg)
        text(d,(18,140),'请尽快前来查看' if urgent else '请在方便时协助',18,fg)
        text(d,(18,176),'本屏已确认 · 待处理' if ack else '待响应 · 本屏已收到',17,fg)
        d.rounded_rectangle((16,218,232,260),radius=8,fill='#203c5d')
        d.rounded_rectangle((248,218,464,260),radius=8,fill='white',outline='#bccbdc')
        text(d,(124,226),'已确认' if ack else '确认收到',21,'white','ma')
        text(d,(356,226),'本屏已处理',21,fg,'ma')
    return im


def rle(data):
    result=bytearray();i=0
    while i<len(data):
        count=1
        while i+count<len(data) and count<255 and data[i+count]==data[i]:count+=1
        result.extend((count,data[i]));i+=count
    return result


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    hmi_assets=ROOT/'comm/receiver_upgrade/hmi/assets'
    hmi_assets.mkdir(parents=True,exist_ok=True)
    headers={node:['/* Generated portrait 480x800; node '+node+'. */','#include <stdint.h>'] for node in ('03','04')}
    entries=[]
    for index,page in enumerate(PAGES,3):
        name=page[0]
        hi=hmi(*page);hi.save(OUT/f'hmi_{name}.png')
        hi.save(hmi_assets/f'{index:02d}_{name}.png')
        for node in ('03','04'):
            ep=epaper(*page,node=node);ep.save(OUT/f'epd_{node}_{name}.png')
            raw=ep.transpose(Image.Transpose.ROTATE_270).tobytes()
            assert len(raw)==48000
            packed=rle(raw)
            assert b''.join(bytes([packed[i+1]])*packed[i] for i in range(0,len(packed),2))==raw
            headers[node].append('static const uint8_t ui_'+name+'[] = {')
            headers[node] += [','.join(str(x) for x in packed[i:i+32])+',' for i in range(0,len(packed),32)]
            headers[node].append('};')
            entries.append(dict(node=node,name=name,bytes=len(packed),raw_sha256=hashlib.sha256(raw).hexdigest()))
    for node,header in headers.items():
        (APP/f'wearable_ui_assets_{node}.h').write_text('\n'.join(header)+'\n',encoding='utf-8')
    (APP/'wearable_ui_assets.h').write_text('''/* Generated node selection; mconfig.h is supplied by the pinned SDK. */
#ifndef WEARABLE_UI_ASSETS_H
#define WEARABLE_UI_ASSETS_H
#if defined(CONFIG_EYE_LINK_NODE_D)
#include "wearable_ui_assets_04.h"
#else
#include "wearable_ui_assets_03.h"
#endif
#endif
''',encoding='utf-8')
    (OUT/'manifest.json').write_text(json.dumps(dict(pages=entries,epd_size=[480,800],ram_size=[800,480],hmi_size=[480,272],board_tested=False),indent=2),encoding='utf-8')
    sheet=Image.new('RGB',(960,1240),'#e2e8ef')
    for col,name in enumerate(('water','help')):
        sheet.paste(Image.open(OUT/f'hmi_{name}.png'),(col*480,0))
        sheet.paste(Image.open(OUT/f'epd_03_{name}.png').convert('RGB'),(col*480,300))
    sheet.save(OUT/'care_preview.png')
    print(json.dumps(dict(pages=len(entries),rle_bytes=sum(x['bytes'] for x in entries),output=str(OUT))))


if __name__=='__main__':main()
