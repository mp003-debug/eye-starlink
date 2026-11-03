"""Small coverage atlas and bounded local-page overlay for native RGB565."""
import json
from pathlib import Path
import numpy as np
from .interaction import MAIN_TARGETS
from .album import PHOTO_BOX
from .visual_theme import local_theme,icon_name,THEMES

def color(rgb):
    r,g,b=rgb
    return ((r>>3)<<11)|((g>>2)<<5)|(b>>3)

BG=color((241,246,242));INK=(23,59,54);WHITE=(255,255,255);MUTED=(89,115,106)

class GlyphAtlas:
    def __init__(self,path,dictionary_sha256):
        self.service=None  # Optional owner-thread communication polling, never a worker.
        with np.load(path,allow_pickle=False) as z:
            meta=json.loads(z['metadata'].tobytes().decode('utf-8'))
            if meta.get('version')!=2 or meta.get('dictionary_sha256')!=dictionary_sha256:
                raise ValueError('text atlas does not match dictionary; rebuild text assets')
            chars=meta['characters']
            if not isinstance(chars,str) or not 1<=len(chars)<=9000 or len(set(chars))!=len(chars):raise ValueError('invalid atlas characters')
            self.index={ch:i for i,ch in enumerate(chars)};self.glyphs={};self.advances={}
            for size in (14,18,28,36):
                a=z['glyphs_'+str(size)];w=z['advances_'+str(size)]
                if a.dtype!=np.uint8 or a.shape!=(len(chars),size+10,size+8) or w.dtype!=np.uint8 or w.shape!=(len(chars),) or np.any(w<1) or np.any(w>size+8):raise ValueError('invalid text atlas')
                self.glyphs[size]=a;self.advances[size]=w

    def require(self,text):
        if any(ch not in self.index for ch in text):raise ValueError('text contains unbuilt glyphs; rebuild text assets')

    def fit(self,text,size,width):
        self.require(text);used=0
        for i,ch in enumerate(text):
            used+=int(self.advances[size][self.index[ch]])
            if used>width:
                while i>0 and self.width(text[:i]+'…',size)>width:i-=1
                return text[:i]+'…'
        return text

    def width(self,text,size):return sum(int(self.advances[size][self.index[ch]]) for ch in text)

    def draw(self,words,text,x,y,size=18,rgb=INK,width=None):
        self.require(text)
        if width is not None:text=self.fit(text,size,width)
        for ch in text:
            index=self.index[ch];mask=self.glyphs[size][index]
            h,w=mask.shape;l=max(0,x-2);t=max(0,y);r=min(words.shape[1],x-2+w);b=min(words.shape[0],y+h)
            if l<r and t<b:
                alpha=mask[t-y:b-y,l-(x-2):r-(x-2)].astype(np.int32)
                dest=words[t:b,l:r];v=dest.astype(np.int32)
                channels=(((v>>11)&31)*255//31,((v>>5)&63)*255//63,(v&31)*255//31)
                rr,gg,bb=[(old*(255-alpha)+new*alpha+127)//255 for old,new in zip(channels,rgb)]
                mixed=((rr>>3)<<11)|((gg>>2)<<5)|(bb>>3)
                np.copyto(dest,mixed.astype(np.uint16),where=alpha!=0)
            x+=int(self.advances[size][index])
        if self.service is not None:self.service()

class DailyRenderer:
    def __init__(self,tools,path=None,tiles=None):
        self.tools=tools
        self.atlas=GlyphAtlas(path or Path(__file__).resolve().parents[2]/'assets/typing/glyphs.npz',tools.composer.lexicon.sha256)
        self.atlas.require(''.join(tools.composer.lexicon.allowed))
        for p in tools.album.photos:self.atlas.require(p['title'])
        if tools.video_library is not None:
            for p in tools.video_library.clips:self.atlas.require(p['title'])
        if tools.audiobook_library is not None:
            for p in tools.audiobook_library.tracks:self.atlas.require(p['title'])
        self.tiles=tiles;self._key=None;self.cache={};self.cache_builds=0
        self.media_tiles={}

    def media_entry(self,words,controller):
        if self.tools.video_library is None:return
        active=controller.target_key=='album_open'
        if active not in self.media_tiles:
            l,t,r,b=[round(v*s) for v,s in zip(MAIN_TARGETS[1].rect,(640,480,640,480))]
            patch=self.tiles['local_video_'+('active' if active else 'idle')][:b+3-t-36].copy()
            patch[14:44,29:59]=self.tiles['local_video_icon_video']
            self.atlas.draw(patch,'相册视频',(r-l-self.atlas.width('相册视频',28))//2,52,28)
            caption='照片与本地短片'
            self.atlas.draw(patch,caption,(r-l-self.atlas.width(caption,14))//2,85,14,MUTED)
            self.media_tiles[active]=patch
        patch=self.media_tiles[active];words[115:115+patch.shape[0],336:608]=patch

    def _build(self,view):
        """Only the current page is cached. No per-frame glyph blending on ARM."""
        if self.tiles is None:raise ValueError('daily renderer needs compiled base tiles')
        a=self.atlas;cache={};theme=local_theme(self.tools.state)
        cache['title']=self.tiles['base_local_tools'][24:58,175:327].copy()
        a.draw(cache['title'],view.title,5,5,18,INK,145)
        cache['summary']=self.tiles['base_local_tools'][58:76,32:608].copy()
        a.draw(cache['summary'],view.summary,0,0,14,INK,576)
        cache['hint']=self.tiles['local_blank_hint'].copy()
        a.draw(cache['hint'],view.hint,10,7,14,INK,556)
        for i,c in enumerate(view.choices):
            if c is None:continue
            l,t,r,b=[round(v*s) for v,s in zip(MAIN_TARGETS[i].rect,(640,480,640,480))]
            height=b+3-t-36
            card_theme='warm' if c.command=='help' else 'blue' if i==3 else theme
            for state in ('idle','active'):
                patch=self.tiles['local_'+card_theme+'_'+state][:height].copy()
                icon='back' if i==3 and '返回' in c.label else icon_name(c.command)
                patch[14:44,29:59]=self.tiles['local_'+card_theme+'_icon_'+icon]
                size=36 if len(c.label)<=2 else 28
                if a.width(c.label,size)>r-l-28:size=18
                label_text=a.fit(c.label,size,r-l-28)
                a.draw(patch,label_text,(r-l-a.width(label_text,size))//2,48 if size==36 else 52 if size==28 else 56,size,INK)
                detail=a.fit(c.detail,14,r-l-28)
                a.draw(patch,detail,(r-l-a.width(detail,14))//2,85,14,MUTED)
                if view.mode=='game' and c.command=='game_answer' and self.tools.game.kind=='match':
                    # Match the graphic itself at the validated target center,
                    # not at a decorative corner that invites off-anchor gaze.
                    patch[47:102,20:-20]=self.tiles['local_'+card_theme+'_'+state][47:102,20:-20]
                    x=(r-l-48)//2;patch[38:86,x:x+48]=self.tiles['game_shape_'+c.label]
                    a.draw(patch,c.label,(r-l-a.width(c.label,14))//2,86,14,INK)
                cache[(i,state)]=patch
            cache[(i,'locked')]=cache[(i,'active')]
            cache[(i,'locked_idle')]=cache[(i,'idle')]
        if view.mode=='game':
            header=np.full((49,576),BG,dtype=np.uint16)
            a.draw(header,view.summary,0,3,14,INK,510 if view.body else 576)
            a.draw(header,'不限时 · 选错可重试',0,26,14,MUTED,500)
            if view.body:header[0:48,528:576]=self.tiles['game_shape_'+view.body]
            cache['game_header']=header
        elif view.mode=='text':
            body=np.full((147,576),color((230,244,236)),dtype=np.uint16)
            lines=[];line=''
            for ch in view.body:
                if a.width(line+ch,28)>520:lines.append(line);line=''
                line+=ch
            if line:lines.append(line)
            if len(lines)>4:raise ValueError('draft exceeds display layout')
            top=(147-len(lines)*32)//2
            for i,line in enumerate(lines):a.draw(body,line,22,top+i*32,28,INK,532)
            cache['body']=body
        elif view.mode=='photo':
            # The picture is copied once on entering this view, not decoded per frame.
            photo=np.full((308,640),BG,dtype=np.uint16)
            l,t,r,b=PHOTO_BOX;photo[t-106:b-106,l:r]=self.tools.album.frame(self.tools.photo_index)
            l,t,r,b=[round(v*s) for v,s in zip(MAIN_TARGETS[3].rect,(640,480,640,480))];t-=106;b-=106
            shell=self.tiles['local_blue_idle'][:b-t].copy()
            shell[14:44,29:59]=self.tiles['local_blue_icon_back']
            photo[t:b,l:r]=shell
            # Align the visible instruction with the frozen lower-right anchor.
            # The earlier left/bottom label invited gaze away from that anchor.
            cx,cy=(l+r)//2,(t+b)//2
            a.draw(photo,'返回控制',cx-a.width('返回控制',28)//2,cy-14,28,INK)
            a.draw(photo,'注视这里返回',cx-a.width('注视这里返回',14)//2,cy+20,14,MUTED)
            cache['photo']=photo
        self.cache=cache;self._key=(view,self.tools.photo_index,self.tools.state);self.cache_builds+=1

    def overlay(self,words,controller,feedback):
        view=self.tools.view()
        if self._key!=(view,self.tools.photo_index,self.tools.state):self._build(view)
        cache=self.cache
        theme_rgb=THEMES[local_theme(self.tools.state)][0]
        words[112:414,0:6]=color(tuple(int(theme_rgb[i:i+2],16) for i in (1,3,5)))
        words[24:58,175:327]=cache['title'];words[58:76,32:608]=cache['summary']
        for i,c in enumerate(view.choices):
            l,t,r,b=[round(v*s) for v,s in zip(MAIN_TARGETS[i].rect,(640,480,640,480))]
            if c is None:words[t:b+3,l:r]=BG
            else:
                key='help' if c.command=='help' else 'tool_slot_'+str(i)
                active=controller.target_key==key;locked=key in controller.locks
                state='locked' if active and locked else 'locked_idle' if locked else 'active' if active else 'idle'
                patch=cache[(i,state)]
                words[t:t+patch.shape[0],l:r]=patch
                theme='warm' if c.command=='help' else 'blue' if i==3 else local_theme(self.tools.state)
                progress=self.tiles['local_'+theme+'_'+state][-36:]
                if active and not locked and controller.progress>0:
                    step=min(20,int(controller.progress*20))
                    if step:progress=self.tiles['local_'+theme+'_progress_'+str(step)]
                words[b+3-36:b+3,l:r]=progress
        if view.mode=='game':
            words[58:107,32:608]=cache['game_header']
        elif view.mode=='book':
            # Numeric prebuilt tiles and a bar only: no per-frame glyph rasterization.
            from .music_ui import TIME_GLYPHS,TIME_GLYPH_SIZE
            p=self.tools.book_player;lib=self.tools.audiobook_library
            index=p.index if p else self.tools.bookmarks.selected
            total=lib.tracks[index]['frames'] if lib.tracks else 0
            pos=min(total,p.position if p else self.tools.bookmarks.position(index) if lib.tracks else 0)
            def stamp(n):return f'{n//16000//60:02d}:{n//16000%60:02d}'
            words[452:480,32:608]=BG
            text=stamp(pos)+' / '+stamp(total)
            for j,ch in enumerate(text):words[458:474,32+j*10:42+j*10]=self.tiles['music_glyph_'+str(TIME_GLYPHS.index(ch))]
            words[464:470,190:608]=color((217,207,192))
            if total:words[464:470,190:190+418*pos//total]=color((137,99,66))
        elif view.mode=='text':
            words[110:257,32:608]=cache['body']
        elif view.mode=='video':
            p=self.tools.video_player
            words[58:263,32:608]=BG
            words[64:262,144:496]=p.frame if p is not None and p.frame is not None else color((20,35,32))
            # Progress uses numeric tiles/copies only; never blend glyphs per frame.
            words[410:415,32:608]=color((204,221,212))
            if p is not None and p.duration:
                width=int(576*min(1,p.position/p.duration));words[410:415,32:32+width]=color((35,124,105))
        elif view.mode=='photo':
            words[106:414,:]=cache['photo']
            l,t,r,b=[round(v*s) for v,s in zip(MAIN_TARGETS[3].rect,(640,480,640,480))]
            if controller.target_key=='tool_slot_3':
                length=int((r-l-40)*controller.progress);words[b-12:b-7,l+20:l+20+length]=color((53,109,173))
        if feedback in (None,'guide_ready','guide_waiting','guide_menu','guide_communication','guide_release'):
            words[418:451,32:608]=cache['hint']
