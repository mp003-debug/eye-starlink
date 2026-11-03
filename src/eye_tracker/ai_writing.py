"""Explicit AI candidate adoption and two-step local speech, no implicit sends."""
from pathlib import Path
from types import SimpleNamespace
import time,wave
from .ai_jobs import AIJob
from .music import MusicPlayer

class AIWriting:
    def __init__(self,bundle,workdir,job_factory=AIJob,clock=time.monotonic):
        self.bundle=bundle;self.workdir=Path(workdir);self.factory=job_factory;self.clock=clock
        self.page='home';self.notice='';self.frozen='';self.candidate='';self.job=None;self.retired=[]
        self.player=None;self.device=None;self.play_requested=False;self.stats=dict(generated=0,adopted=0,synthesized=0,spoken=0,cancelled=0,failed=0)
    def bind_audio(self,device):self.device=device
    def cancel(self,notice='已停止 · 正文保留'):
        self.play_requested=False
        if self.player:self.player.stop();self.player=None
        if self.job:
            self.job.cancel();self.retired.append(self.job);self.job=None;self.stats['cancelled']+=1
        self.frozen='';self.candidate='';self.page='home';self.notice=notice
    def open(self):self.cancel('生成内容需先查看，再确认采用')
    def _start(self,kind,composer):
        if self.job or self.retired:raise ValueError('previous job is closing')
        if composer.pinyin or not composer.lexicon.valid_text(composer.text):raise ValueError('finish the draft first')
        self.frozen=composer.text;self.candidate='';self.notice=''
        self.job=self.factory(self.bundle,self.workdir,kind,self.frozen,clock=self.clock)
        self.page='generating' if kind=='generate' else 'synthesizing'
    def service(self,composer):
        self.retired=[j for j in self.retired if not j.reap()]
        try:
            if self.player:
                self.player.poll()
                if self.player.state=='ended':self.cancel('朗读已结束')
            if self.job and self.page in ('generating','synthesizing'):
                if composer.text!=self.frozen or composer.pinyin:self.cancel('正文已变化 · 请重新选择');return
                result=self.job.poll()
                if result is None:return
                if self.page=='generating':
                    if result.get('kind')!='generate' or not composer.lexicon.valid_text(result.get('text')):raise ValueError('unsupported candidate')
                    self.candidate=result['text'];self.page='preview';self.stats['generated']+=1
                    self.job.cancel();self.retired.append(self.job);self.job=None
                else:
                    if result.get('kind')!='synthesize':raise ValueError('wrong result')
                    path=self.job.path/'speech.wav'
                    with wave.open(str(path),'rb') as w:
                        if (w.getnchannels(),w.getsampwidth(),w.getframerate(),w.getcomptype())!=(1,2,16000,'NONE') or not 0<w.getnframes()<=960000:raise ValueError('audio bounds')
                        frames=w.getnframes()
                    stamp=path.stat();track=dict(path=path,frames=frames,file_stamp=(stamp.st_size,stamp.st_mtime_ns))
                    if self.device is None:raise ValueError('audio is not bound')
                    library=SimpleNamespace(tracks=[track],volume=SimpleNamespace(percent=100))
                    self.player=MusicPlayer(self.device,library,self.clock);self.page='speech_ready';self.stats['synthesized']+=1
        except Exception:
            self.stats['failed']+=1;self.cancel('本次未完成 · 正文保留，请重试')
    def poll_controller(self,controller,tools):
        if (controller.page!='local_tools' or tools.state!='ai' or controller.paused or controller.closed or not controller.calibration_id) and (self.job or self.player or self.play_requested):
            self.cancel()
        previous=self.page
        hit=next((t for t in controller.targets if controller.cursor is not None and t.contains(controller.cursor)),None)
        self.service(tools.composer)
        if previous!=self.page and controller.page=='local_tools' and tools.state=='ai':
            controller._reset('page_release')
            if hit is not None:controller.navigation_block=hit
    def select(self,command,composer):
        self.notice=''
        if command=='ai_generate':self._start('generate',composer)
        elif command=='ai_speech':self._start('synthesize',composer)
        elif command=='ai_reviewed':
            if self.page!='preview' or not self.candidate:raise ValueError('missing candidate')
            self.page='confirm'
        elif command=='ai_adopt':
            if self.page!='confirm' or composer.text!=self.frozen or composer.pinyin:raise ValueError('draft changed')
            composer.load(self.candidate);self.stats['adopted']+=1;self.cancel('已替换正文 · 可在修改页撤销')
        elif command=='ai_play':
            if self.page!='speech_ready' or composer.text!=self.frozen:raise ValueError('speech confirmation expired')
            self.play_requested=True
        elif command in ('ai_cancel','ai_back'):self.cancel()
        else:raise ValueError('unknown AI command')
    def dispatch(self,action,now):
        if not self.play_requested:return
        self.play_requested=False
        if action is None or action.source!='live' or not 0<=now-action.source_time_ms<=150:
            self.cancel('确认已过期 · 请重新选择');return
        try:self.player.play();self.page='speaking';self.stats['spoken']+=1
        except Exception:
            self.stats['failed']+=1;self.cancel('朗读未完成 · 请重试')
    def view(self,composer):
        from .daily_tools import View,choice,HELP
        back=choice('返回','ai_back');title='文字助手';summary=self.notice or '正文：'+(composer.text or '尚未输入')
        hint='本机生成 · 先查看并确认，不自动表达';body='';mode='cards'
        if self.page=='home':
            enabled=bool(composer.text and not composer.pinyin and not self.retired)
            options=(choice('生成候选','ai_generate',detail='根据正文生成一句话') if enabled else None,
                     choice('朗读正文','ai_speech',detail='准备声音后再次确认') if enabled else None,
                     choice('展示收藏','ai_present'),back)
        elif self.page in ('generating','synthesizing'):
            title='正在生成' if self.page=='generating' else '正在准备声音';summary='请稍候 · 可以随时取消或求助'
            options=(choice('取消','ai_cancel'),None,HELP,back)
        elif self.page=='preview':
            title='候选预览';summary='候选尚未采用 · 请核对全文';mode='text';body=self.candidate
            options=(None,None,choice('继续确认','ai_reviewed'),choice('取消','ai_cancel'))
        elif self.page=='confirm':
            title='确认采用';summary='将替换正文 · 原文可以撤销';hint='不会自动收藏、播报或发送'
            options=(choice('替换正文','ai_adopt'),choice('取消','ai_cancel'),HELP,back)
        elif self.page=='speech_ready':
            title='朗读前预览';summary='声音已准备 · 尚未播放';mode='text';body=self.frozen
            options=(None,None,choice('确认朗读','ai_play'),choice('取消','ai_cancel'))
        elif self.page=='speaking':
            title='正在朗读';summary='朗读本次确认的正文';hint='可以立即停音或求助 · 不会自动重播'
            options=(choice('停止朗读','ai_cancel'),None,HELP,back)
        else:raise ValueError('unknown AI page')
        return View(title,summary,hint,options,mode,body)
    def close(self):
        self.cancel('')
        for j in self.retired:
            if not j.reap(2):raise RuntimeError('AI worker did not stop')
        self.retired=[]
