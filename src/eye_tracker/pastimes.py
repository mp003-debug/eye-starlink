"""Small, untimed local games. Completion is play progress, never a clinical score."""
import random
from dataclasses import dataclass

SHAPES=('圆形','三角形','正方形','菱形','星形','爱心')
QUESTIONS=(
    ('彩虹通常出现在什么时候？','雨后见到阳光','漆黑的室内'),
    ('一年中，哪一季通常最温暖？','夏季','冬季'),
    ('哪一种乐器通常有黑白琴键？','钢琴','小提琴'),
    ('哪一种动物会结网？','蜘蛛','企鹅'),
    ('太阳从哪个方向升起？','东方','西方'),
    ('哪一种水果外皮通常是黄色？','香蕉','蓝莓'),
    ('泡一杯茶通常要用到什么？','水','沙子'),
    ('哪一种交通工具在轨道上行驶？','火车','帆船'),
    ('哪种动物有长长的鼻子？','大象','兔子'),
    ('人们通常用什么看远处的星星？','望远镜','放大镜'),
)

@dataclass(frozen=True)
class Round:
    prompt:str
    answers:tuple
    correct:int
    shape:str=''

class LeisureGame:
    def __init__(self,rng=None):
        self.rng=rng or random.Random();self.rounds=[];self.index=0;self.solved=False;self.notice=''
        self.kind=None

    def start(self,kind):
        if kind not in ('match','quiz'):raise ValueError('unknown game')
        rounds=[]
        if kind=='match':
            for shape in self.rng.sample(list(SHAPES),5):
                other=self.rng.choice([s for s in SHAPES if s!=shape]);answers=[shape,other]
                self.rng.shuffle(answers);rounds.append(Round('找到相同的图形',tuple(answers),answers.index(shape),shape))
        else:
            for prompt,right,wrong in self.rng.sample(list(QUESTIONS),5):
                answers=[right,wrong];self.rng.shuffle(answers)
                rounds.append(Round(prompt,tuple(answers),answers.index(right)))
        self.kind=kind;self.rounds=rounds;self.index=0;self.solved=False;self.notice=''

    @property
    def current(self):
        if not self.rounds:raise ValueError('game not started')
        return self.rounds[self.index]

    @property
    def finished(self):return self.solved and self.index==len(self.rounds)-1

    def answer(self,index):
        if type(index) is not int or index not in (0,1):raise ValueError('invalid game answer')
        if self.solved:return False
        if index==self.current.correct:self.solved=True;self.notice='答对了 · 准备好后再继续';return True
        self.notice='再看看 · 可以慢慢选';return False

    def advance(self):
        if not self.solved or self.finished:raise ValueError('round not ready to advance')
        self.index+=1;self.solved=False;self.notice=''
