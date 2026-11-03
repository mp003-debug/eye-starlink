"""Original vector artwork baked locally; no emoji fonts or external images."""
import math
from PIL import Image, ImageDraw
from .emotions import CARDS


def artwork(key, size=112):
    _, _, _, ink, soft = CARDS[key]
    scale=4
    im=Image.new('RGB',(112*scale,112*scale),soft)
    d=ImageDraw.Draw(im)
    def box(values):return tuple(round(v*scale) for v in values)
    def line(points,width=3,color=ink):
        d.line([(round(x*scale),round(y*scale)) for x,y in points],fill=color,width=width*scale,joint='curve')
    def ellipse(values,fill=None,outline=ink,width=3):
        d.ellipse(box(values),fill=fill,outline=outline,width=width*scale)
    def arc(values,start,end,width=3):d.arc(box(values),start,end,fill=ink,width=width*scale)
    def heart(cx,cy,r,color):
        points=[]
        for i in range(97):
            t=2*math.pi*i/96
            x=16*math.sin(t)**3
            y=13*math.cos(t)-5*math.cos(2*t)-2*math.cos(3*t)-math.cos(4*t)
            points.append((round((cx+r*x/17)*scale),round((cy-r*y/17)*scale)))
        d.polygon(points,fill=color)
    if key in ('emotion_happy','emotion_sad','emotion_worried'):
        ellipse((17,17,95,95),fill='#FFFFFF',width=3)
        if key=='emotion_happy':
            arc((31,37,45,51),185,355);arc((66,37,80,51),185,355)
            arc((36,44,76,77),10,170,4)
            ellipse((25,57,35,62),fill='#F1B5A3',outline=None)
            ellipse((77,57,87,62),fill='#F1B5A3',outline=None)
        else:
            ellipse((36,44,41,50),fill=ink,width=1)
            ellipse((71,44,76,50),fill=ink,width=1)
            if key=='emotion_sad':
                line([(31,38),(44,33)]);line([(68,33),(81,38)])
                arc((39,68,73,90),195,345)
                d.polygon([box((80,54)),box((74,66)),box((86,66))],fill='#83B6DB')
                ellipse((74,61,86,73),fill='#83B6DB',outline=None)
            else:
                line([(30,40),(45,33)]);line([(67,33),(82,40)])
                line([(40,75),(48,70),(56,74),(64,70),(72,75)],3)
                line([(92,21),(96,15)],2);line([(98,30),(105,27)],2)
    elif key=='emotion_like':
        heart(56,54,35,ink)
        line([(25,18),(25,27)],2);line([(21,22),(29,22)],2)
        line([(89,77),(89,86)],2);line([(85,81),(93,81)],2)
    elif key=='emotion_thanks':
        line([(56,59),(56,97)],4)
        ellipse((34,76,55,88),fill='#A9D5B6',outline=None)
        ellipse((57,81,78,93),fill='#A9D5B6',outline=None)
        for i in range(6):
            angle=math.pi*i/3
            x,y=56+19*math.cos(angle),45+19*math.sin(angle)
            ellipse((x-13,y-13,x+13,y+13),fill='#F4C677',outline=None)
        ellipse((43,32,69,58),fill='#FFFFFF',outline=ink,width=2)
        arc((48,39,64,51),5,175,2)
    else:
        d.rounded_rectangle(box((14,22,74,68)),radius=12*scale,fill='#FFFFFF',outline=ink,width=3*scale)
        line([(25,68),(22,80),(40,68)],3)
        d.rounded_rectangle(box((50,57,98,89)),radius=10*scale,fill=soft,outline=ink,width=3*scale)
        line([(82,89),(91,98),(90,87)],3)
        heart(44,44,13,ink)
        for x in (63,74,85):ellipse((x-2,71,x+2,75),fill=ink,width=1)
    return im.resize((size,size),getattr(Image,'Resampling',Image).LANCZOS)
