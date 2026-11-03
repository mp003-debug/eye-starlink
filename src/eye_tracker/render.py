"""Cached 640x480 color UI. Same target rectangles as the dwell controller."""
from PIL import Image, ImageDraw, ImageFont
from .interaction import MAIN_TARGETS, MORE_TARGETS, PAGE_TARGETS, ALL_TARGETS
from .phrases import PHRASE_TEXT
from .emotions import CARDS, PANEL_BOX, selected_card
from .emotion_art import artwork
from .visual_theme import THEMES,key_theme,card_shell
from .music_ui import (MUSIC_PAGES, MUSIC_TRACK_BOX, MUSIC_FOOTER_BOX, MUSIC_BAR_BOX,
                       TIME_ORIGIN, TIME_GLYPH_SIZE, FOOTER_COLOR, BAR_COLOR, FILL_COLOR, display_values)

REASONS = {
    'page_release':'页面已切换 · 请先移开视线，再选择',
    "uncalibrated":"请先完成个人校准", "waiting":"等待有效注视", "tracking":"正在跟踪 · 注视即可选择",
    "speaking":"正在播报 · 完成后再开始新的停留",
    "selected":"已选择", "locked":"已选择 · 移开视线后可再次选择", "paused":"已暂停 · 不会触发选择",
    "stopped":"应用已停止", "closed":"闭眼 · 本次选择已取消", "lost":"暂未找到眼睛 · 选择已取消",
    "unknown":"眼部特征不可用", "stale":"输入中断 · 本次选择已取消", "gap":"输入间隔过长",
    "context_mismatch":"配置改变 · 请重新校准", "out_of_order":"输入顺序异常",
    "future":"输入时间异常", "bad_sample":"输入无效", "bad_coordinate":"坐标无效",
    "clock_fault":"时钟异常 · 应用已停止", "cancelled":"已取消本次选择",
}
STYLES = {
    'quick_open':('#416F9B','#EAF0F9','回应、确认与叫停'),
    'care_open':('#A46432','#FAEEDB','表达生活照护需求'),
    'yes':('#11796C','#E6F4EE','表达肯定'),
    'no':('#416F9B','#EAF0F9','表达否定'),
    'unwell':('#A46432','#FAEEDB','表达身体不适'),
    'please_stop':('#A46432','#FAEEDB','请照护者先停一下'),
    'reposition':('#11796C','#E6F4EE',PHRASE_TEXT['reposition']),
    'toilet':('#416F9B','#EAF0F9',PHRASE_TEXT['toilet']),
    'quick_back':('#11796C','#E6F4EE','回到功能菜单'),
    'care_back':('#11796C','#E6F4EE','回到功能菜单'),
    'music_open':('#77639B','#EEE9F6','播放板上本地音乐'),
    'music_toggle':('#11796C','#E6F4EE','控制当前音乐'),
    'music_next':('#416F9B','#EAF0F9','切换播放列表曲目'),
    'menu_back':('#11796C','#E6F4EE','回到常用表达'),
    'music_back':('#11796C','#E6F4EE','停止音乐并返回'),
    'music_player_open':('#11796C','#E6F4EE','进入播放、暂停与切歌'),
    'music_volume_open':('#416F9B','#EAF0F9','只调整音乐的音量'),
    'music_menu_back':('#11796C','#E6F4EE','回到功能菜单'),
    'music_volume_back':('#11796C','#E6F4EE','保存音量，回到音乐菜单'),
    'music_volume_down':('#416F9B','#EAF0F9','降低一档 · 最低20%'),
    'music_volume_up':('#11796C','#E6F4EE','提高一档 · 最高100%'),
    "water":("#11796C","#E6F4EE",PHRASE_TEXT['water']),
    "rest":("#416F9B","#EAF0F9",PHRASE_TEXT['rest']),
    "help":("#A46432","#FAEEDB",PHRASE_TEXT['help']),
    "more":("#77639B","#EEE9F6","更多交流内容"),
    "back":("#11796C","#E6F4EE","回到常用表达"),
}
SOURCE_LABELS = {"simulated":"测试输入 · 非真实眼控", "replay":"录像回放 · 非实时眼控", "live":"实时摄像头"}
STYLES.update({key:(v[3],v[4],v[1]) for key,v in CARDS.items()})
STYLES.update({
    'communication_open':('#416F9B','#EAF0F9','回应与日常照护'),
    'response_open':STYLES['quick_open'], 'caring_open':STYLES['care_open'],
    'emotion_open':('#B65E74','#FCECF0','用大图表达心情和心意'),
    'emotion_mood_open':('#A47217','#FFF3D7','开心、难过、担心'),
    'emotion_affection_open':('#B65E74','#FCECF0','喜欢、谢谢、想你'),
})
for key,subtitle in (('communication_back','回到功能菜单'),('emotion_menu_back','回到功能菜单'),
                     ('emotion_mood_back','回到表情菜单'),('emotion_affection_back','回到表情菜单'),
                     ('emotion_close','回到刚才的表情页')):
    STYLES[key]=('#11796C','#E6F4EE',subtitle)
STYLES.update(leisure_open=('#77639B','#EEE9F6','照片观赏与表情心意'),
              leisure_back=('#11796C','#E6F4EE','回到功能菜单'),
              cards_open=STYLES['emotion_open'],album_open=('#416F9B','#EAF0F9','查看本地风景与照片'),
              typing_open=('#11796C','#E6F4EE','拼音选字与常用句收藏'))
from .daily_tools import SLOT_KEYS
STYLES.update(memories_open=('#42764E','#EBF4E5','相册、视频与表情心意'),
              pastimes_open=('#506FAD','#EEF2FC','不限时小游戏与本地听书'),
              pastimes_back=('#356DAD','#EAF2FD','回到功能菜单'))
STYLES.update({key:('#11796C','#E6F4EE','') for key in SLOT_KEYS})


EXTRA_MESSAGES = {'music_empty':'尚未导入音乐 · 请辅助人员添加本地曲目',
                  'music_hub_hint':'请选择播放控制或音乐音量 · 帮助语音优先',
                  'music_volume_hint':'仅调整音乐 · 帮助与交流语音音量保持不变',
                  'music_ready':'音乐已就绪 · 注视播放开始，帮助语音优先',
                  'music_playing':'音乐播放中 · 可暂停、切歌、求助或返回',
                  'music_pausing':'正在暂停 · 请先移开视线',
                  'music_paused':'音乐已暂停 · 重新选择播放可继续',
                  'music_ended':'本曲已结束 · 可重新播放或选择下一首',
                  'music_fault':'音乐播放异常 · 已停止，请辅助人员检查',
                  'guide_page_release':'先看另一区域，再注视按钮 · 避免翻页后连续选择',
                  'guide_menu':'请选择一项功能，或返回常用表达',
                  'guide_communication':'请选择回应交流或日常照护，或返回功能菜单',
                  'guide_quick':'回应交流 · 注视满1秒播报，返回不播音',
                  'guide_care':'日常照护 · 注视满1秒表达需要，返回不播音',
                  "guide_ready":"注视一个大按钮满1秒 · 移开视线可取消未完成的停留",
                  "guide_waiting":"请自然坐好，注视一个大按钮 · 等待有效输入",
                  "guide_back":"请注视中央返回满1秒 · 返回不播音",
                  "guide_release":"已完成本次选择 · 先看别处，再看回来可重新选择",
                  "guide_unavailable":"输入暂不可用 · 未完成的停留已清零",
                  "guide_reposition":"请回到刚才坐姿 · 持续无响应请辅助人员重新启动定位",
                  'guide_reposition_assist':'持续选不中：请辅助人员按 BTN2 查看画面并重新定位',
                  "guide_appearance":"请保持自然睁眼和原来坐姿 · 注视一个大按钮",
                  "guide_unavailable_long":"请回到原来坐姿 · 持续无响应请辅助人员检查定位",
                  "guide_input":"输入暂不可用 · 请稍候，持续异常请辅助人员检查",
                  "guide_uncalibrated":"当前无法选择 · 请辅助人员重新启动并完成定位检查",
                  "guide_paused":"当前已暂停 · 请辅助人员按BTN0恢复，再重新注视",
                  "guide_stopped":"本次使用已结束 · 请辅助人员按需重新启动",
                  "guide_cancelled":"本次操作已取消 · 下一次选择需要重新完成停留",
                  "guide_speaking":"正在播报 · 播完后可继续选择，BTN1可停音",
                  "eye_auto_first":"自动中断测试 · 请看喝水，开始播音后将自动停音",
                  "eye_auto_second":"已自动取消 · 请看帮助，随后会自动暂停",
                  "eye_auto_pause":"已自动暂停 · 2秒后自动恢复",
                  "eye_auto_resume":"已自动恢复 · 继续看帮助3秒，再看休息",
                  "eye_speech":"四区域眼控语音 · BTN0暂停  BTN1停音  BTN3退出",
                  "eye_speech_back":"请看中央返回 · 返回不播音",
                  "eye_trial":"四区域眼图试验 · 仅屏幕反馈，不播音、不发送",
                  "eye_trial_back":"请看中央返回 · 仅屏幕反馈，不播音、不发送",
                  "controls":"BTN0 暂停/恢复   BTN1 取消   BTN2 清校准   BTN3 退出",
                  "audio_test":"音频数字通路测试 · 输出静音，尚未听音验收",
                  "speech_ready":"AUX 听音测试 · 下一句即将播放",
                  "speech_controls":"语音联调 · BTN0暂停  BTN1中止  BTN2清校准  BTN3退出",
                  }
EXTRA_MESSAGES.update({'speaking_'+key:'正在播报：'+text+' · BTN1可中止'
                       for key,text in PHRASE_TEXT.items()})
EXTRA_MESSAGES.update(emotion_hint='注视选择一张表情 · 大图会保留在屏幕上',
                      emotion_display_hint='表情正在展示 · 可选择帮助，或返回换一张')

def feedback_message(source, key=None):
    if key in EXTRA_MESSAGES:return EXTRA_MESSAGES[key]
    phrases = {target.key: target.phrase or target.label for target in ALL_TARGETS}
    if key is None:
        return "联调测试 · 程序坐标输入，不识别眼睛、不播放语音" if source == "simulated" else "注视表达你的需要，移开视线可取消本次选择"
    prefix = {"simulated":"测试选择：", "replay":"回放选择：", "live":"已选择："}[source]
    return prefix + phrases[key] + ("（未播放声音）" if source == "simulated" else "")


TEXT="#183B3D"
MUTED="#526F73"

class Renderer:
    def __init__(self,font_path,music_tracks=None):
        if music_tracks is None:
            from pathlib import Path
            from .music import MusicLibrary
            music_tracks=MusicLibrary(Path(__file__).resolve().parents[2]/'assets/music').provenance()['tracks']
        self.music_tracks=music_tracks
        self.fonts={n:ImageFont.truetype(str(font_path),n) for n in (10,12,13,14,15,16,18,26,28,30,44)}
        self.icons={key:self._icon(key,*THEMES[key_theme(key)][:2]) for key in STYLES}
        self.icon_mask=Image.new("L",(56,56),0)
        ImageDraw.Draw(self.icon_mask).rounded_rectangle((0,0,55,55),radius=14,fill=255)
        self.bases={page:self._base(page) for page in (*PAGE_TARGETS,'calibration')}

    def setup_frame(self, count=0, failed=False):
        if type(count) is not int or not 0 <= count <= 5:
            raise ValueError('reference count must be 0..5')
        im=self.bases['calibration'].copy();d=ImageDraw.Draw(im)
        # Replaces only the instructional area; the fixation point stays at
        # the original center (.5, .55), with no selectable targets.
        d.rectangle((0,112,639,417),fill='#F1F6F2')
        color='#9B612E' if failed else '#13796E'
        self._text(d,(320,133),'定位未完成' if failed else '启动定位 · 请看中央圆点',26,color,'mt')
        self._text(d,(320,178),'请辅助人员调整坐姿或检查相机后重新启动' if failed
                   else '保持自然坐姿和光线 · 可以正常眨眼',16,MUTED,'mt')
        cx,cy=320,264
        d.ellipse((cx-28,cy-28,cx+28,cy+28),fill='#E1F0E9')
        d.ellipse((cx-21,cy-21,cx+21,cy+21),fill='#FFFFFF',outline='#164E4B',width=3)
        d.ellipse((cx-8,cy-8,cx+8,cy+8),fill='#E67638')
        self._text(d,(320,321),f'已采集有效参考 {count} / 5',18,TEXT,'mt')
        for i in range(5):
            x=260+i*26
            d.rounded_rectangle((x,356,x+16,364),radius=4,fill=color if i<count else '#CEDFD9')
        self._text(d,(46,427),'尚未启用选择 · 不会播放语音或发送按钮事件',14,TEXT)
        self._text(d,(33,461),'启动位置检查 · 使用已有个人模型',12,MUTED)
        self._text(d,(608,461),'参考采集后还需一致性检查',12,MUTED,'rt')
        return im

    def _text(self,draw,xy,text,size=14,fill=TEXT,anchor="lt"):
        draw.text(xy,text,font=self.fonts[size],fill=fill,anchor=anchor)

    def position_frame(self, state='preview', count=0):
        if state not in ('preview','collecting','failed','limit'):raise ValueError('unknown position state')
        if state=='collecting':
            im=self.setup_frame(count);d=ImageDraw.Draw(im)
            d.rectangle((0,112,639,170),fill='#F1F6F2')
            self._text(d,(320,133),'中央定位 · 请看圆点',26,'#13796E','mt')
            self._text(d,(40,196),'实时画面',13,MUTED)
            d.rounded_rectangle((37,213,170,314),radius=3,fill='#163C40')
            return im
        im=Image.new('RGB',(640,480),'#F1F6F2');d=ImageDraw.Draw(im)
        self._text(d,(32,26),'眼控助手',26,TEXT)
        self._text(d,(608,35),'位置预览 · 暂不选择',14,MUTED,'rt')
        title={'preview':'先看画面，调整到自然坐姿',
               'failed':'定位未通过 · 调整坐姿后再试',
               'limit':'本次重试已用完 · 请退出后检查'}[state]
        self._text(d,(320,80),title,26,'#9B612E' if state!='preview' else TEXT,'mt')
        self._text(d,(320,118),'眼部应清楚入镜；画面可见不代表定位已经通过',14,MUTED,'mt')
        d.rounded_rectangle((156,140,483,387),radius=5,fill='#163C40')
        self._text(d,(320,401),'准备好后按 BTN0，再看屏幕中央圆点' if state!='limit' else '请辅助人员按 BTN3 退出',18,TEXT,'mt')
        self._text(d,(320,438),'辅助按键：BTN0 开始定位 · BTN1 取消采集 · BTN3 退出',14,MUTED,'mt')
        self._text(d,(320,463),'定位期间停止播放；通过后返回主页，需重新注视选择',12,MUTED,'mt')
        return im

    def _icon(self,key,accent,soft):
        # Icons are vector geometry rendered once with antialiasing; no emoji font.
        emotion_icon={'emotion_open':'emotion_happy','cards_open':'emotion_happy','emotion_mood_open':'emotion_happy',
                      'emotion_affection_open':'emotion_like'}.get(key,key)
        if emotion_icon in CARDS:return artwork(emotion_icon,56)
        key={'communication_open':'quick_open','response_open':'quick_open','caring_open':'care_open'}.get(key,key)
        s=3;im=Image.new("RGB",(56*s,56*s),soft);d=ImageDraw.Draw(im)
        def line(points,width=2):
            d.line([(int(x*s),int(y*s)) for x,y in points],fill=accent,width=width*s,joint="curve")
        def oval(box,fill=None,width=2):
            d.ellipse(tuple(int(v*s) for v in box),fill=fill,outline=accent,width=width*s)
        if key=="water":
            line([(16,16),(20,41),(36,41),(40,16),(16,16)])
            line([(19,27),(24,25),(31,28),(37,26)])
            line([(23,46),(33,46)])
        elif key=="rest":
            oval((13,11,43,43),accent)
            d.ellipse((24*s,6*s,48*s,32*s),fill=soft)
            line([(40,35),(40,43)]);line([(36,39),(44,39)])
        elif key=="help":
            oval((15,12,41,38))
            line([(28,18),(28,31)],3);line([(22,24),(34,24)],3)
            line([(14,43),(21,47),(35,47),(43,41)])
        elif key in ('music_open','music_toggle','music_player_open'):
            line([(25,37),(25,15),(40,12),(40,33)],3)
            oval((16,32,26,42),accent);oval((31,28,41,38),accent)
        elif key=='music_next':
            line([(18,15),(37,28),(18,41),(18,15)],3);line([(40,15),(40,41)],3)
        elif key in ('music_volume_open','music_volume_down','music_volume_up'):
            line([(12,23),(21,23),(30,15),(30,41),(21,33),(12,33),(12,23)],3)
            line([(36,28),(46,28)],3)
            if key!='music_volume_down':line([(41,23),(41,33)],3)
        elif key=='yes':
            line([(14,28),(24,38),(43,17)],4)
        elif key=='no':
            line([(17,17),(39,39)],4);line([(39,17),(17,39)],4)
        elif key=='unwell':
            oval((12,12,44,44));oval((21,22,23,24),accent);oval((33,22,35,24),accent)
            line([(21,36),(28,32),(35,36)],2)
        elif key=='quick_open':
            line([(13,15),(43,15),(43,35),(26,35),(18,42),(18,35),(13,35),(13,15)],2)
            for x in (21,28,35):oval((x-1,24,x+1,26),accent)
        elif key=='please_stop':
            d.rounded_rectangle((16*s,16*s,40*s,40*s),radius=4*s,outline=accent,width=3*s)
        elif key in ('care_open','reposition'):
            line([(13,20),(13,41),(44,41)],3)
            line([(16,33),(40,33),(43,41)],3);oval((17,20,25,28))
            line([(30,17),(39,17),(39,25)],2);line([(34,21),(39,26),(44,21)],2)
        elif key=='toilet':
            line([(16,14),(27,14),(27,29),(41,29),(37,39),(26,42),(26,47),(36,47)],3)
            line([(16,14),(16,29),(27,29)],3)
        elif key in ('album_open','leisure_open','memories_open'):
            d.rounded_rectangle((11*s,13*s,45*s,43*s),radius=3*s,outline=accent,width=2*s)
            oval((32,19,38,25),accent);line([(14,39),(24,26),(32,35),(38,29),(43,39)],2)
        elif key in ('game','pastimes_open'):
            d.rounded_rectangle((10*s,18*s,46*s,40*s),radius=7*s,outline=accent,width=2*s)
            line([(17,28),(27,28)],2);line([(22,23),(22,33)],2)
            oval((33,23,37,27),accent);oval((38,30,42,34),accent)
        elif key=='book':
            line([(28,15),(28,43)],2)
            line([(28,17),(14,12),(12,39),(28,44),(44,39),(42,12),(28,17)],2)
            line([(17,21),(23,23)],2);line([(33,23),(39,21)],2)
        elif key=='typing_open':
            line([(12,16),(44,16)],3);line([(28,16),(28,42)],3);line([(20,42),(36,42)],3)
        elif key=='video':
            d.rounded_rectangle((10*s,14*s,46*s,42*s),radius=5*s,outline=accent,width=2*s)
            d.polygon(((24*s,21*s),(24*s,35*s),(36*s,28*s)),fill=accent)
        elif key=='pause':
            for x in (19,32):d.rounded_rectangle((x*s,15*s,(x+5)*s,41*s),radius=2*s,fill=accent)
        elif key=='save':
            line([(16,12),(40,12),(40,45),(28,37),(16,45),(16,12)],3)
        elif key=='erase':
            line([(24,15),(44,15),(44,41),(24,41),(10,28),(24,15)],2)
            line([(27,22),(37,34)],2);line([(37,22),(27,34)],2)
        elif key=='display':
            d.rounded_rectangle((10*s,13*s,46*s,39*s),radius=4*s,outline=accent,width=2*s)
            line([(28,40),(28,46),(18,46),(38,46)],2)
        elif key=="more":
            for x in (20,36):
                for y in (20,36):
                    d.rounded_rectangle(( (x-5)*s,(y-5)*s,(x+5)*s,(y+5)*s),radius=3*s,outline=accent,width=2*s)
        else:
            line([(26,16),(15,28),(26,40)],3);line([(16,28),(42,28)],3)
        resample=getattr(Image,"Resampling",Image).LANCZOS
        return im.resize((56,56),resample)

    def _card(self,image,target,active=False,progress=0.,locked=False):
        d=ImageDraw.Draw(image)
        l,t,r,b=[round(v*s) for v,s in zip(target.rect,(640,480,640,480))]
        theme=key_theme(target.key);accent,soft,_=THEMES[theme];subtitle=STYLES[target.key][2]
        card_shell(image,(l,t,r,b),theme,active)
        cx,cy=(l+r)//2,(t+b)//2
        if target.key not in SLOT_KEYS:
            icon=self.icons[target.key].resize((30,30),Image.Resampling.LANCZOS)
            image.paste(icon,(l+29,t+14))
            self._text(d,(cx,cy-15),target.label,28,TEXT,'mt')
            while d.textlength(subtitle,font=self.fonts[13])>r-l-32:subtitle=subtitle[:-2]+'…'
            self._text(d,(cx,cy+20),subtitle,13,MUTED,'mt')
        if locked:
            hint="已选择 · 请移开视线"
        elif active and progress>0:
            hint="保持注视";self._text(d,(r-20,b-31),f"{round(progress*100)}%",13,accent,"rt")
        else:
            hint="注视选择" if target.key!="back" else "注视这里返回"
        self._text(d,(l+20,b-31),hint,13,accent if active else MUTED)
        if active and progress>0:
            d.rounded_rectangle((l+20,b-12,r-21,b-8),radius=2,fill="#CEDFD9")
            d.rounded_rectangle((l+20,b-12,l+20+(r-l-41)*progress,b-8),radius=2,fill=accent)

    def _base(self,page):
        im=Image.new("RGB",(640,480),"#F1F6F2");d=ImageDraw.Draw(im)
        # A restrained header gradient is cached, never recomputed per gaze sample.
        for y in range(112):
            u=y/111
            d.line((0,y,639,y),fill=(round(227+14*u),round(241+5*u),round(235+7*u)))
        d.rounded_rectangle((32,19,69,56),radius=12,fill="#13796E")
        d.rounded_rectangle((39,28,62,44),radius=6,outline="#FFFFFF",width=2)
        d.line((43,44,43,48,49,44),fill="#FFFFFF",width=2)
        d.ellipse((47,33,53,39),fill="#FFFFFF")
        self._text(d,(81,17),"眼语",28)
        if page not in MUSIC_PAGES and page!='local_tools':self._text(d,(83,52),"用目光，说出你的需要",13,MUTED)
        page_title={'quick':'回应交流','care':'日常照护','menu':'更多功能',
                    'quick_menu':'更多功能','full_menu':'更多功能','extended_menu':'更多功能',
                    'communication_menu':'快捷交流','emotion_hub':'表情与心意',
                    'emotion_mood':'心情','emotion_affection':'心意','emotion_display':'我的表达',
                    'daily_menu':'更多功能','daily_communication':'快捷交流','leisure':'相册与表情','pastimes_leisure':'休闲空间'}.get(page)
        if page_title:self._text(d,(608,62),page_title,10,MUTED,'rt')
        page_theme=('music' if page in MUSIC_PAGES else 'rose' if page.startswith('emotion') else
                    'album' if page=='leisure' else 'blue' if page in ('quick','communication_menu','daily_communication') else 'mint')
        d.rectangle((0,112,5,413),fill=THEMES[page_theme][0])
        if page!="calibration":
            for target in PAGE_TARGETS[page]:self._card(im,target)
        else:
            self._text(d,(320,142),"跟随圆点，完成个人校准",18,TEXT,"mt")
        d.rounded_rectangle((32,418,608,450),radius=11,fill="#FFFFFF",outline="#DBE6E0")
        return im

    def frame(self,controller,message="",calibration_target=None):
        page="calibration" if calibration_target is not None else controller.page
        im=self.bases[page].copy();d=ImageDraw.Draw(im)
        source=SOURCE_LABELS[controller.context.source]
        box=d.textbbox((0,0),source,font=self.fonts[12]);w=box[2]-box[0]+22
        d.rounded_rectangle((608-w,27,608,53),radius=13,fill="#FFFFFF",outline="#CCDCD5")
        self._text(d,(608-w+11,34),source,12,MUTED)
        reason=REASONS.get(controller.reason,"输入无效")
        good=controller.reason in ("waiting","tracking","selected","locked")
        color="#13796E" if good else "#9B612E"
        d.ellipse((34,84,40,90),fill=color)
        self._text(d,(49,80),reason,14,color)
        if calibration_target is not None:
            x,y=calibration_target[0]*640,calibration_target[1]*480
            d.ellipse((x-27,y-27,x+27,y+27),fill="#E1F0E9")
            d.ellipse((x-17,y-17,x+17,y+17),outline="#13796E",width=3)
            d.ellipse((x-5,y-5,x+5,y+5),fill="#13796E")
        else:
            for target in (PAGE_TARGETS[page] if page=='local_tools' and controller.daily_tools is None else controller.targets):
                if target.key==controller.target_key or target.key in controller.locks:
                    self._card(im,target,target.key==controller.target_key,
                               controller.progress if target.key==controller.target_key else 0.,
                               target.key in controller.locks)
            if controller.cursor is not None:
                x,y=controller.cursor[0]*640,controller.cursor[1]*480
                d.ellipse((x-12,y-12,x+12,y+12),outline="#FFFFFF",width=4)
                d.ellipse((x-10,y-10,x+10,y+10),outline="#13796E",width=2)
                d.ellipse((x-2,y-2,x+2,y+2),fill="#13796E")
        self._text(d,(46,427),message or "注视表达你的需要，移开视线可取消本次选择",14,TEXT)
        self._text(d,(33,461),f"停留 {controller.dwell_ms/1000:g} 秒选择",12,MUTED)
        # Informational footer, not an implemented input control.
        self._text(d,(608,461),"眼控交流  /  个人校准",12,MUTED,"rt")
        if page in MUSIC_PAGES:self.music_details(im,controller)
        if page=='emotion_display' and controller.emotion_key is not None:
            self.emotion_details(im,selected_card(controller))
        return im

    def emotion_details(self,im,key):
        label,message,_,accent,soft=CARDS[key]
        d=ImageDraw.Draw(im)
        l,t,r,b=PANEL_BOX
        d.rounded_rectangle((l,t,r-1,b-1),radius=20,fill=soft,outline=accent,width=2)
        im.paste(artwork(key),(70,128))
        self._text(d,(217,131),label,44,accent)
        self._text(d,(219,197),message,26,TEXT)

    def music_details(self,im,controller):
        d=ImageDraw.Draw(im)
        index,level,time_text,width=display_values(controller)
        if controller.page=='music_volume':
            title=f'音乐音量 {level*20}% · 仅影响音乐'
        elif index<0:
            title='暂无音乐 · 请先导入曲目'
        elif index<len(self.music_tracks):
            title=f'{index+1:02d}/{len(self.music_tracks):02d} '+self.music_tracks[index]['title']
        else:title=f'曲目 {index+1:02d} · 未提供曲名'
        available=MUSIC_TRACK_BOX[2]-MUSIC_TRACK_BOX[0]
        size=next((n for n in (18,16,15,14,13,12)
                   if d.textlength(title,font=self.fonts[n])<=available
                   and d.textbbox((0,0),title,font=self.fonts[n],anchor='lt')[3]
                   <=MUSIC_TRACK_BOX[3]-MUSIC_TRACK_BOX[1]),12)
        while d.textlength(title,font=self.fonts[size])>available:
            title=title[:-2]+'…'
        self._text(d,(32,59),title,size,TEXT)
        l,t,r,b=MUSIC_FOOTER_BOX
        d.rectangle((l,t,r-1,b-1),fill=FOOTER_COLOR)
        for i,char in enumerate(time_text):
            self._text(d,(TIME_ORIGIN[0]+i*TIME_GLYPH_SIZE[0]+1,TIME_ORIGIN[1]),char,12,MUTED)
        l,t,r,b=MUSIC_BAR_BOX
        d.rectangle((l,t,r-1,b-1),fill=BAR_COLOR)
        if width:d.rectangle((l,t,l+width-1,b-1),fill=FILL_COLOR)
        self._text(d,(608,458),f'音乐 {level*20}%',14,MUTED,'rt')
