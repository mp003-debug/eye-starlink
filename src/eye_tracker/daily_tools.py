"""Explicit local UI transactions shared by the photo album and text composer."""
from dataclasses import dataclass
from pathlib import Path
from .album import PhotoLibrary
from .composer import PinyinLexicon,Favorites,Composer,SYMBOLS,MAX_TEXT,MAX_FAVORITES,COMMON_EXPRESSIONS

SLOT_KEYS=tuple('tool_slot_'+str(i) for i in range(4))
LOCAL_ACTIONS=frozenset(SLOT_KEYS+('leisure_open','leisure_back','cards_open','album_open','typing_open','memories_open','pastimes_open','pastimes_back'))


def validate_options(enabled,music,quick,emotions,wireless=False):
    if enabled and (not music or not quick or not emotions):
        raise ValueError('daily tools require local music + quick phrases + emotion cards')


@dataclass(frozen=True)
class Choice:
    label:str
    detail:str
    command:str
    value:object=None


@dataclass(frozen=True)
class View:
    title:str
    summary:str
    hint:str
    choices:tuple
    mode:str='cards'
    body:str=''


def choice(label,command,value=None,detail=''):return Choice(label,detail,command,value)
BACK=choice('返回','back',detail='返回上一页')
HELP=choice('需要帮助','help',detail='播放原有帮助语音')


class DailyTools:
    def __init__(self,album,composer,video_library=None,audiobook_library=None,bookmarks=None,pastimes=False):
        self.album=album;self.composer=composer
        self.video_library=video_library;self.video_player=None;self.video_command=None
        self.pastimes=bool(pastimes);self.audiobook_library=audiobook_library;self.bookmarks=bookmarks
        self.book_player=None;self.book_command=None
        from .pastimes import LeisureGame
        self.game=LeisureGame()
        self.state='compose';self.history=[];self.photo_index=0;self.candidate_offset=0
        self.favorite_offset=0;self.favorite_index=None;self.display_text='';self.display_back='present'
        self.groups=[];self.symbol_groups=[];self.notice='';self.revision=0;self.last_event=None
        self.phrase_group=0;self.phrase_offset=0;self.present_back='more';self.favorites_back='more'
        from .word_input import WordLexicon
        self.words=WordLexicon(Path(__file__).resolve().parents[2]/'assets/typing/words.json',composer.lexicon)
        self.initials='';self.word_groups=[];self.word_offset=0
        self.symbols_back='edit'
        self._word_cache_key=None;self._word_cache=()
        self.sharing=None  # Explicit launch opt-in, never enabled by saved text.
        self.ai=None

    @classmethod
    def from_root(cls,root,local_video=False,pastimes=False):
        root=Path(root);lex=PinyinLexicon(root/'assets/typing/pinyin.json')
        from .video_library import VideoLibrary
        from .audiobook import MusicLibrary,Bookmarks
        books=MusicLibrary(root/'assets/audiobooks') if pastimes else None
        marks=Bookmarks(books,root/'data/private/audiobook_progress.json') if books is not None else None
        return cls(PhotoLibrary(root/'assets/photos'),Composer(lex,Favorites(lex,root/'data/private/favorites.json')),
                   VideoLibrary(root/'assets/video') if local_video else None,books,marks,pastimes)

    def open(self,name):
        if name not in ('album','compose','pastimes'):raise ValueError('unknown local feature')
        if name=='pastimes' and not self.pastimes:raise ValueError('pastimes are not enabled')
        if name=='album' and self.video_library is not None:name='media'
        self.state=name;self.groups=[];self.symbol_groups=[];self.notice='';self.history=[]
        self.revision+=1;self.last_event=None;self.video_command=None;self.book_command=None

    def reset_navigation(self):
        # Helper reposition keeps the draft/saved phrases, never resumes viewing.
        if self.sharing is not None:self.sharing.reset()
        if self.ai is not None:self.ai.cancel()
        self.open('compose');self.display_text=''

    @staticmethod
    def _groups(text):
        step=max(1,(len(text)+2)//3)
        return [text[i:i+step] for i in range(0,len(text),step)]

    def _group_choices(self,sequence,command):
        chunks=list(sequence) if len(sequence)<=3 else self._groups(sequence)
        result=[]
        for chunk in chunks:
            label=chunk.upper() if command in ('letters','initial_letters') else chunk
            if len(chunk)>3:label=label[0]+'–'+label[-1]
            result.append(choice(label,command,chunk,detail='选择字母' if len(chunk)==1 and command in ('letters','initial_letters') else '进入这一组' if len(chunk)>1 else '加入正文'))
        return tuple(result+[None]*(3-len(result))+[BACK])

    def candidate_choices(self):
        chars=self.composer.candidates()
        items=[choice(ch,'candidate',i,detail='加入正文') for i,ch in enumerate(chars)]
        words=[choice(s,'phrase_candidate',s,detail='词句候选 · 整句加入') for s in self.composer.phrase_candidates()]
        # First character stays at its original rank; all other characters remain reachable.
        return tuple(items[:1]+words+items[1:])

    def word_choices(self):
        c=self.composer;key=(self.initials,c.text,tuple(c.favorites.items))
        if key!=self._word_cache_key:
            items=self.words.lookup(self.initials);phrases=c._phrases()
            # Only dictionary-offered, exact initials gain local context priority.
            exact={self.words.words[i][0] for i in self.words.primary.get(self.initials,())}
            def rank(word):
                if word not in exact:return 2
                if any(phrase.startswith(c.text[-n:]+word) for n in range(1,min(len(c.text),6)+1) for phrase in phrases):return 0
                return 1 if any(word in phrase for phrase in phrases) else 2
            self._word_cache=tuple(sorted(items,key=rank));self._word_cache_key=key
        return self._word_cache

    def view(self):
        c=self.composer;state=self.state
        if state=='ai':return self.ai.view(c)
        if state=='share':return self.sharing.view(c)
        text=c.text or '尚未输入文字'
        summary='正文：'+(('…'+text[-24:]) if len(text)>24 else text)
        hint=self.notice or '可选常用整句 · 拼音选字后继续输入'
        title='文字输入';mode='cards';body=''
        if state=='pastimes':
            title='游戏与听书';summary='慢慢玩 · 随时停';hint='小游戏不限时 · 听书可以暂停续听'
            choices=(choice('眼控小游戏','games'),choice('本地有声书','book_open'),HELP,choice('返回','exit','pastimes'))
        elif state=='games':
            title='眼控小游戏';summary='每轮五题 · 不限时';hint='选错可重试 · 准备好再进入下一题'
            choices=(choice('图形配对','game_start','match',detail='找到相同的图形'),choice('轻松问答','game_start','quiz',detail='两种答案，慢慢想'),HELP,choice('返回','pastimes'))
        elif state=='game':
            g=self.game;title='图形配对' if g.kind=='match' else '轻松问答'
            summary=f'第{g.index+1}/5题 · '+g.current.prompt;hint=g.notice or '注视答案 · 不计时，随时可退出'
            mode='game';body=g.current.shape
            if g.solved:
                choices=(choice('完成本轮' if g.finished else '下一题','game_finish' if g.finished else 'game_next'),choice('再玩一轮','game_start',g.kind),HELP,choice('返回','games'))
            else:choices=tuple(choice(s,'game_answer',i,detail='选择这一项') for i,s in enumerate(g.current.answers))+(HELP,choice('返回','games'))
        elif state=='game_done':
            title='本轮完成';summary='五道题已完成';hint='谢谢参与 · 可以再玩一轮，也可以休息一下'
            choices=(choice('再玩一轮','game_start',self.game.kind),choice('选择游戏','games'),HELP,choice('返回','pastimes'))
        elif state in ('book','book_options','book_chapters'):
            title='本地有声书';p=self.book_player;tracks=self.audiobook_library.tracks
            index=p.index if p is not None else self.bookmarks.selected
            status={'playing':'播放中','paused':'已暂停','ended':'已播完','fault':'播放异常'}.get(p.state if p else 'stopped','准备收听')
            summary=(f'{index+1}/{len(tracks)} '+tracks[index]['title']+' · '+status) if tracks else '暂无章节'
            hint='帮助会停下朗读 · 播完不自动切章';mode='book'
            if (p and p.snapshot()['bookmark_warning']) or self.bookmarks.warning:hint='进度暂未保存 · 可以继续收听，本轮位置仍保留'
            if state=='book':choices=(choice('播放 / 暂停','book_toggle',detail='从记录的位置继续') if tracks else None,choice('章节选项','book_options'),HELP,choice('返回','book_exit'))
            elif state=='book_options':choices=(choice('切换章节','book_chapters'),choice('从头播放','book_restart',detail='重播当前这一篇') if tracks else None,HELP,choice('返回播放','book_controls'))
            else:choices=(choice('上一章','book_previous') if tracks else None,choice('下一章','book_next') if tracks else None,HELP,choice('返回播放','book_controls'))
        elif state=='media':
            title='相册与视频';summary='本地内容 · 不联网';hint='选择照片或短片'
            choices=(choice('本地相册','media_album'),choice('本地视频','media_video'),HELP,choice('返回','exit','leisure'))
        elif state in ('video','video_view'):
            p=self.video_player;clips=self.video_library.clips;index=p.index if p else 0
            status={'stopped':'准备播放','loading':'载入中','playing':'播放中','paused':'已暂停','ended':'已结束','fault':'播放异常'}.get(p.state if p else 'stopped')
            title='本地视频';summary=f'{index+1}/{len(clips)} '+clips[index]['title'] if clips else '暂无短片 · 请先导入视频'
            hint=status+' · 观看中可求助或暂停返回控制'
            if state=='video_view':
                mode='video';hint=(clips[index]['title']+' · '+status) if clips else hint
                choices=(None,None,HELP,choice('暂停 / 控制','video_controls',detail='暂停视频并返回控制页'))
            else:
                choices=(choice('播放观看','video_toggle'),choice('下一段','video_next'),HELP,choice('返回','video_exit')) if clips else (None,None,HELP,choice('返回','video_exit'))
        elif state=='album':
            n=len(self.album.photos);title='本地相册'
            summary=f'{self.photo_index+1}/{n} '+self.album.photos[self.photo_index]['title'] if n else '相册为空 · 请先导入照片'
            hint='先选择照片，再进入观赏 · 观赏时不直接切图'
            choices=(choice('上一张','photo_prev'),choice('下一张','photo_next'),choice('查看大图','photo_view'),choice('返回','exit','leisure')) if n else (None,None,HELP,choice('返回','exit','leisure'))
        elif state=='photo_view':
            title='观赏照片';summary=self.album.photos[self.photo_index]['title'];mode='photo'
            hint='右下打开控制页 · 切图需要再作一次选择'
            choices=(None,None,None,choice('返回控制','photo_controls',detail='打开上一张、下一张'))
        elif state=='compose':
            if c.pinyin:summary='拼音：'+c.pinyin+'  |  '+summary
            choices=(choice('自由输入','input_methods',detail='词语简拼 · 完整拼音'),choice('常用表达','expressions',detail='整句输入 · 我的收藏'),
                     choice('编辑展示','more',detail='删除、展示与收藏'),choice('返回','exit','communication'))
        elif state=='input_methods':
            title='选择输入方式';hint='简拼每字只取首字母 · 今天JT，下午XW'
            choices=(choice('词语简拼','word_keyboard',detail='今天JT · 下午XW'),choice('完整拼音','keyboard',detail='一个字的完整拼音 · 午WU'),
                     choice('标点数字','symbols',detail='逗号、句号与数字'),choice('返回','compose'))
        elif state=='word_keyboard':
            title='词语简拼';summary='首字母：'+(self.initials.upper() or '空')+'  |  '+summary
            hint=self.notice or '每字只取首字母 · 今天JT，下午XW，午W'
            choices=self._group_choices(self.word_groups[-1] if self.word_groups else self.words.next_letters(self.initials),'initial_letters')
            if not self.word_groups:choices=choices[:3]+(choice('修改 / 完成','word_actions',detail='查看候选 · 删除 · 全拼' if self.initials else '撤销、全拼、展示'),)
        elif state=='word_candidates':
            title='简拼候选';summary='简拼：'+self.initials.upper()+'  |  '+summary
            hint='选单字或继续下一字首字母 · 下午XW，午W' if len(self.initials)==1 else '选词后继续输入 · 今天JT，下午XW'
            items=self.word_choices();i=self.word_offset
            choices=tuple(choice(s,'word_commit',s,detail='加入正文 · '+str(len(s))+'字') for s in items[i:i+2])
            choices=choices+(None,)*(2-len(choices))+(choice('下一组','next_words',detail=f'{i+1}–{min(i+2,len(items))} / {len(items)}') if len(items)>2 else None,choice('继续简拼','word_keyboard',detail='输入下一个字的首字母'))
        elif state=='word_actions':
            title='简拼修改';summary='简拼：'+(self.initials.upper() or '空')+'  |  '+summary
            hint=self.notice or ('可返回候选 · 要输入完整拼音请选输入方式' if self.initials else '撤销上次加入的字词 · 不删除收藏')
            choices=(choice('删除一个字母','initial_erase') if self.initials else choice('撤销上次输入','undo') if c.can_undo() else None,
                     choice('输入方式','input_methods',detail='完整拼音 · 标点数字'),
                     choice('查看候选','word_candidates',detail='保留首字母 · 回到原候选') if self.initials else choice('展示收藏','present'),choice('返回简拼','word_keyboard'))
        elif state=='keyboard':
            title='完整拼音';summary='全拼：'+(c.pinyin or '空')+'  |  '+summary
            hint=self.notice or '只显示可接字母 · 拼成音节直接选字 · ü用v'
            choices=self._group_choices(self.groups[-1] if self.groups else c.lexicon.next_letters(c.pinyin),'letters')
            if not self.groups:choices=choices[:3]+(choice('修改 / 完成','keyboard_actions',detail='选字、删除或展示'),)
        elif state=='keyboard_actions':
            title='输入与修改';summary='拼音：'+(c.pinyin or '空')+'  |  '+summary
            choices=(choice('选字','candidates') if c.lexicon.candidates(c.pinyin) else choice('继续输入','keyboard'),
                     choice('删除一字','keyboard_erase',detail='先删拼音，再删正文') if c.text or c.pinyin else None,
                     choice('展示收藏','present'),choice('返回输入','compose'))
        elif state=='candidates':
            items=self.candidate_choices();title='字词候选';summary='拼音：'+(c.pinyin or '空')+'  |  '+summary
            hint='也可直接选词句 · 每次都需明确选择，不自动补字'
            if not items:
                hint='暂无候选 · 返回后补全或修改拼音'
                choices=(None,None,None,choice('继续拼音','keyboard'))
            else:
                i=self.candidate_offset
                choices=items[i:i+2]
                choices=choices+(None,)*(2-len(choices))+(choice('下一组','next_candidates',detail=f'{i+1}–{min(i+2,len(items))} / {len(items)}') if len(items)>2 else None,choice('继续拼音','keyboard',detail='补全拼音或修改'))
        elif state=='suggestions':
            title='继续表达';hint='可选择后面的词句，也可继续拼音 · 不自动加入'
            tails=c.continuations()
            choices=tuple(choice(s,'continuation',s,detail='接在正文后面') for s in tails)
            choices=choices+(None,)*(2-len(choices))+(choice('拼音输入','keyboard'),choice('修改 / 完成','keyboard_actions'))
        elif state=='expressions':
            title='常用表达';hint='整句加入正文 · 不自动展示、不播音'
            choices=(choice('日常需要','phrase_group',0),choice('交流心意','phrase_group',1),choice('我的收藏','favorites'),BACK)
        elif state=='phrases':
            title=COMMON_EXPRESSIONS[self.phrase_group][0];items=COMMON_EXPRESSIONS[self.phrase_group][1];i=self.phrase_offset
            hint='选择后整句追加 · 已有正文保留'
            choices=tuple(choice(s,'phrase',s,detail='加入正文后可展示') for s in items[i:i+2])
            choices=choices+(None,)*(2-len(choices))+(choice('下一组','next_phrases',detail=f'{i+1}–{min(i+2,len(items))} / {len(items)}'),BACK)
        elif state=='more':
            title='编辑与收藏';choices=(choice('修改文字','edit'),choice('展示收藏','present'),choice('常用句','favorites'),BACK)
            if self.sharing is not None:choices=choices[:2]+(choice('接收屏分享','share_open',detail='表达、心意、文字和状态'),BACK)
            if self.ai is not None:choices=(choices[0],choice('文字助手','ai_open',detail='AI候选 · 朗读 · 展示收藏'),choices[2],choices[3])
        elif state=='edit':
            title='修改文字';choices=(choice('删除一字','erase',detail='先删拼音，再删正文'),choice('标点数字','symbols'),choice('清空内容','clear_confirm'),BACK)
        elif state=='symbols':
            title='标点与数字';choices=self._group_choices(self.symbol_groups[-1] if self.symbol_groups else SYMBOLS,'symbols_choose')
        elif state=='clear_confirm':
            title='确认清空';hint='清空当前草稿和拼音 · 已收藏的句子不受影响'
            choices=(choice('确认清空','clear'),choice('取消','back'),HELP,BACK)
        elif state=='present':
            title='展示与收藏';choices=(choice('展示文字','show_draft') if c.text else None,
                choice('收藏本句','save') if c.text else None,HELP,BACK)
            if not c.text:hint='正文为空 · 返回后先输入文字'
        elif state=='display':
            title='我的表达';mode='text';body=self.display_text;summary='文字仅在本屏展示'
            choices=(None,None,HELP,choice('返回','display_back'))
            hint='文字会保持在屏幕上 · 返回后可继续编辑'
        elif state=='favorites':
            title='常用句';items=c.favorites.items;i=self.favorite_offset
            choices=tuple(choice(s[:6]+('…' if len(s)>6 else ''),'favorite',i+j,detail=f'第{i+j+1}句 · {len(s)}字') for j,s in enumerate(items[i:i+2]))
            choices=choices+(None,)*(2-len(choices))+(choice('下一组','next_favorites',detail=f'共{len(items)}句') if len(items)>2 else None,BACK)
            hint=self.notice or ('暂无收藏 · 可输入文字后收藏' if not items else '选择一句，再展示、载入编辑或删除')
        elif state=='favorite':
            title='已收藏句子';summary=c.favorites.items[self.favorite_index]
            choices=(choice('展示此句','show_favorite'),choice('载入编辑','load_confirm'),choice('删除收藏','delete_confirm'),BACK)
        elif state in ('delete_confirm','load_confirm'):
            title='确认删除' if state=='delete_confirm' else '确认载入'
            summary=c.favorites.items[self.favorite_index]
            hint='仅删除这条收藏，草稿保留' if state=='delete_confirm' else '将替换当前草稿，已有收藏保持不变'
            choices=(choice('确认删除' if state=='delete_confirm' else '替换草稿','delete' if state=='delete_confirm' else 'load'),choice('取消','back'),HELP,BACK)
        else:raise ValueError('unknown local page')
        return View(title,summary,self.notice or hint,choices,mode,body)

    def select(self,slot):
        if type(slot) is not int or not 0<=slot<4:raise ValueError('invalid local target')
        option=self.view().choices[slot]
        if option is None:raise ValueError('disabled local target')
        command=option.command;value=option.value;c=self.composer;self.notice='';result=None
        parents={'more':'compose','edit':'more','present':self.present_back,'clear_confirm':'edit',
                 'favorites':self.favorites_back,'favorite':'favorites','delete_confirm':'favorite','load_confirm':'favorite',
                 'candidates':'keyboard','expressions':'compose','phrases':'expressions'}
        if command.startswith('ai_'):
            if self.ai is None:raise ValueError('AI writing is not enabled')
            if command=='ai_open':self.ai.open();self.state='ai'
            elif command=='ai_present':self.ai.cancel('');self.present_back='ai';self.state='present'
            elif command=='ai_back':self.ai.cancel();self.state='more'
            else:
                try:self.ai.select(command,c)
                except (ValueError,OSError):self.ai.cancel('请先完成输入，或稍候重试')
        elif command.startswith('share_'):
            if self.sharing is None:raise ValueError('receiver sharing is not enabled')
            if command=='share_open':self.sharing.page='home';self.state='share'
            else:
                try:
                    if self.sharing.select(command,value,c)=='leave':self.state='more'
                except ValueError as exc:
                    self.notice=str(exc);self.sharing.error=self.notice
        elif command=='back':
            if self.state=='word_keyboard':
                if self.word_groups:self.word_groups.pop()
                else:self.state='input_methods'
            elif self.state=='keyboard':
                if self.groups:self.groups.pop()
                else:self.state='compose'
            elif self.state=='symbols':
                if self.symbol_groups:self.symbol_groups.pop()
                else:self.state=self.symbols_back
            else:self.state=parents[self.state]
        elif command in ('more','edit','present','clear_confirm','delete_confirm','load_confirm','keyboard_actions','compose','expressions','input_methods','word_actions'):
            if command=='present':self.present_back=self.state
            self.state=command
        elif command=='exit':
            if self.state=='album' and self.video_library is not None:self.state='media'
            else:result=value
        elif command=='help':
            if self.ai is not None:self.ai.cancel()
            result='help'
        elif command in ('pastimes','games'):self.state=command
        elif command=='game_start':self.game.start(value);self.state='game'
        elif command=='game_answer':self.game.answer(value)
        elif command=='game_next':self.game.advance()
        elif command=='game_finish':
            if not self.game.finished:raise ValueError('game is not complete')
            self.state='game_done'
        elif command=='book_open':self.state='book'
        elif command.startswith('book_'):
            if command=='book_controls':self.state='book'
            else:
                self.book_command=command
                if command in ('book_options','book_chapters'):self.state=command
                elif command=='book_exit':self.state='pastimes'
                elif command=='book_restart':self.state='book'
        elif command=='media_album':self.state='album'
        elif command=='media_video':self.state='video'
        elif command.startswith('video_'):
            # Dispatch after helper-button and speech priority in the hardware loop.
            self.video_command=command
            if command=='video_toggle':self.state='video_view'
            elif command=='video_controls':self.state='video'
            elif command=='video_exit':self.state='media'
        elif command=='keyboard':self.groups=[];self.state='keyboard'
        elif command=='word_keyboard':self.word_groups=[];self.state='word_keyboard'
        elif command=='word_candidates':self.word_groups=[];self.state='word_candidates'
        elif command=='initial_letters':
            if len(value)>1:self.word_groups.append(value)
            else:
                if value not in self.words.next_letters(self.initials):raise ValueError('invalid next initial')
                self.initials+=value;self.word_groups=[];self.word_offset=0
                if self.word_choices():self.state='word_candidates'
        elif command=='next_words':self.word_offset=self.word_offset+2 if self.word_offset+2<len(self.word_choices()) else 0
        elif command=='word_commit':
            if value not in self.word_choices():raise ValueError('not an offered word')
            if c.append_text(value):self.initials='';self.word_groups=[];self.word_offset=0;self.state='word_keyboard'
            else:self.notice='正文空间不足 · 词语未加入，请先撤销或编辑'
        elif command=='initial_erase':self.initials=self.initials[:-1];self.word_groups=[];self.word_offset=0;self.state='word_keyboard'
        elif command=='undo':
            self.notice='已撤销上次输入 · 收藏保留' if c.undo() else '暂无可撤销的输入'
        elif command=='letters':
            if len(value)>1:self.groups.append(value)
            else:
                if value not in c.lexicon.next_letters(c.pinyin):raise ValueError('letter cannot continue current syllable')
                if not c.letter(value):self.notice='拼音最多6个字母 · 请先选字或删除'
                self.groups=[]
                if c.lexicon.candidates(c.pinyin) and (len(c.pinyin)>1 or c.pinyin in 'aeo'):
                    self.candidate_offset=0;self.state='candidates'
        elif command=='candidates':self.candidate_offset=0;self.state='candidates'
        elif command=='next_candidates':self.candidate_offset=self.candidate_offset+2 if self.candidate_offset+2<len(self.candidate_choices()) else 0
        elif command=='candidate':
            if c.candidate(value):self.state='suggestions' if c.continuations() else 'keyboard';self.groups=[]
            else:self.notice='正文已满64字 · 请先删除或清空'
        elif command=='phrase_candidate':
            if c.phrase_candidate(value):self.present_back='keyboard_actions';self.state='present';self.groups=[]
            else:self.notice='正文空间不足 · 整句未加入，请先删除或清空'
        elif command=='continuation':
            if value not in c.continuations():raise ValueError('not an offered continuation')
            if c.append_text(value):self.present_back='keyboard_actions';self.state='present'
            else:self.notice='正文空间不足 · 整句未加入，请先删除或清空'
        elif command=='keyboard_erase':c.erase();self.groups=[];self.state='keyboard'
        elif command=='phrase_group':self.phrase_group=value;self.phrase_offset=0;self.state='phrases'
        elif command=='next_phrases':
            self.phrase_offset=(self.phrase_offset+2)%len(COMMON_EXPRESSIONS[self.phrase_group][1])
        elif command=='phrase':
            if c.append_text(value):self.present_back='phrases';self.state='present'
            else:self.notice='正文空间不足 · 整句未加入，请先删除或清空'
        elif command=='erase':c.erase()
        elif command=='clear':c.clear();self.initials='';self.word_groups=[];self.word_offset=0;self.state='edit'
        elif command=='symbols':self.symbol_groups=[];self.symbols_back=self.state;self.state='symbols'
        elif command=='symbols_choose':
            if len(value)>1:self.symbol_groups.append(value)
            else:
                if not c.append(value):self.notice='正文已满64字 · 请先删除或清空'
                self.symbol_groups=[]
        elif command=='save':
            try:self.notice={'saved':'已收藏 · 重启后仍可选用','already_saved':'这句话已在收藏中','full':'收藏已满12句 · 请先删除不需要的句子'}[c.favorites.save(c.text)]
            except OSError:self.notice='保存未成功 · 草稿保留，请检查存储'
        elif command=='favorites':self.favorites_back=self.state;self.favorite_offset=0;self.state='favorites'
        elif command=='next_favorites':self.favorite_offset=self.favorite_offset+2 if self.favorite_offset+2<len(c.favorites.items) else 0
        elif command=='favorite':self.favorite_index=value;self.state='favorite'
        elif command=='load':
            c.load(c.favorites.items[self.favorite_index]);self.initials='';self.word_groups=[];self.word_offset=0;self.state='compose'
        elif command=='delete':
            try:
                c.favorites.delete(self.favorite_index);self.favorite_index=None;self.favorite_offset=0;self.state='favorites';self.notice='已删除这条收藏'
            except OSError:self.notice='删除未成功 · 原收藏保留，请检查存储'
        elif command in ('show_draft','show_favorite'):
            self.display_text=c.text if command=='show_draft' else c.favorites.items[self.favorite_index]
            self.display_back='present' if command=='show_draft' else 'favorite';self.state='display'
        elif command=='display_back':self.state=self.display_back
        elif command in ('photo_prev','photo_next'):self.photo_index=(self.photo_index+(-1 if command=='photo_prev' else 1))%len(self.album.photos)
        elif command=='photo_view':self.state='photo_view'
        elif command=='photo_controls':self.state='album'
        else:raise ValueError('unknown local action')
        self.revision+=1
        # No user text or letter payload is copied into runtime telemetry.
        self.last_event=dict(action=command,state=self.state,text_length=len(c.text),pinyin_length=len(c.pinyin),
            initials_length=len(self.initials),favorites_count=len(c.favorites.items),photo_index=self.photo_index,notice=bool(self.notice))
        return result
