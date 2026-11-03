"""Explicit sharing UI, separate from local speech, drafts and entertainment."""
from .share_protocol import PHRASE, EMOTION, TEXT, ACTIVITY, PHRASES, EMOTIONS, message_bytes


class SharingUI:
    def __init__(self):
        self.page = 'home'
        self.offset = 0
        self.category = PHRASE
        self.frozen = None
        self.request = None
        self.cancel_requested = False
        self.activity_enabled = False
        self.activity_revision = 0
        self.status = '等待接收端版本检查'
        self.busy = False
        self.error = ''

    def reset(self):
        self.frozen = self.request = None
        self.cancel_requested = True
        self.page = 'home'

    def view(self, composer):
        from .daily_tools import View, choice, HELP
        back = choice('返回', 'share_back')
        hint = '只发送明确选定内容 · 本屏已读不代表护理确认'
        title = '接收屏分享';summary = self.status;mode = 'cards';body = ''
        if self.page == 'home':
            options = (choice('固定表达', 'share_phrases'), choice('心意表情', 'share_emotions'),
                       choice('文字与状态', 'share_text'), back)
        elif self.page == 'list':
            items = PHRASES if self.category == PHRASE else EMOTIONS
            options = tuple(choice(s, 'share_pick', s, detail='预览后确认发送') for s in items[self.offset:self.offset+2])
            options += (choice('下一组', 'share_next'), back)
        elif self.page == 'text':
            options = (choice('预览正文', 'share_draft', detail='发送前完整查看') if composer.text else None,
                       choice('活动摘要', 'share_activity', detail='已开启' if self.activity_enabled else '默认关闭'), HELP, back)
        elif self.page == 'preview':
            title = '发送前预览';summary = '内容已固定 · 尚未发送';mode = 'text';body = self.frozen[1]
            options = (None, None, choice('继续确认', 'share_reviewed'), choice('取消', 'share_cancel'))
            hint = '请检查全文 · 下一页才确认发送'
        elif self.page == 'confirm':
            title = '确认发送';summary = self.frozen[1]
            options = (choice('确认发送', 'share_confirm'), choice('取消', 'share_cancel'), HELP, back)
            hint = '发送到三块接收屏 · 草稿和收藏不会改变'
        elif self.page == 'activity':
            title = '活动摘要';summary = '已开启' if self.activity_enabled else '当前关闭'
            options = (choice('关闭分享' if self.activity_enabled else '开启分享', 'share_toggle'),
                       choice('查看说明', 'share_activity_info'), HELP, back)
            hint = '只分享菜单或休闲类别 · 不含曲名、正文或媒体'
        elif self.page == 'activity_confirm':
            title = '确认开启';summary = '活动变化后分享类别，接收端显示上次活动'
            options = (choice('确认开启', 'share_enable'), choice('取消', 'share_activity'), HELP, back)
            hint = '本次运行有效 · 不发送正文、照片、视频或声音'
        elif self.page == 'activity_info':
            title = '活动摘要说明';summary = '只记录变化 · 两分钟后标为过时'
            options = (None, None, HELP, choice('返回设置', 'share_activity'))
            hint = '上次活动不是实时状态 · 不代表在线或离线'
        elif self.page == 'status':
            title = '发送状态';summary = self.status
            options = (choice('取消发送', 'share_cancel') if self.busy else None,
                       choice('重新预览', 'share_again') if not self.busy and self.frozen else None, HELP, back)
            hint = '接纳回执不等于屏幕已刷新或护理人员已确认'
        else:
            raise ValueError('unknown sharing page')
        return View(title, self.error or summary, hint, options, mode, body)

    def select(self, command, value, composer):
        self.error = ''
        if command == 'share_phrases':self.category=PHRASE;self.offset=0;self.page='list'
        elif command == 'share_emotions':self.category=EMOTION;self.offset=0;self.page='list'
        elif command == 'share_next':self.offset=(self.offset+2)%6
        elif command == 'share_pick':self.frozen=(self.category,value);self.page='confirm'
        elif command == 'share_text':self.page='text'
        elif command == 'share_draft':
            message_bytes(TEXT,composer.text)
            self.frozen=(TEXT,composer.text);self.page='preview'
        elif command == 'share_reviewed':self.page='confirm'
        elif command == 'share_confirm':
            if self.frozen is None:raise ValueError('missing explicitly reviewed message')
            message_bytes(*self.frozen);self.request=self.frozen;self.page='status'
        elif command == 'share_again':self.page='preview' if self.frozen[0]==TEXT else 'confirm'
        elif command == 'share_activity':self.page='activity'
        elif command == 'share_activity_info':self.page='activity_info'
        elif command == 'share_toggle':
            if self.activity_enabled:
                self.activity_enabled=False;self.activity_revision+=1
                self.request=(ACTIVITY,'活动分享已关闭');self.page='status'
            else:self.page='activity_confirm'
        elif command == 'share_enable':
            self.activity_enabled=True;self.activity_revision+=1;self.page='activity'
        elif command in ('share_cancel','share_back'):
            self.request=None;self.cancel_requested=True
            if command=='share_back' and self.page=='home':return 'leave'
            self.frozen=None;self.page='home'
        else:raise ValueError('unknown sharing action')
        return None
