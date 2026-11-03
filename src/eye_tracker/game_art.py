"""Code-drawn, static matching shapes for baking into RGB565 assets."""
import math
from PIL import Image,ImageDraw

def shape_image(name,size=48):
    image=Image.new('RGB',(size,size),'#F1F6F2');d=ImageDraw.Draw(image)
    color={'圆形':'#376FAC','三角形':'#477D61','正方形':'#A06D35','菱形':'#795AA0','星形':'#A77A23','爱心':'#AB5772'}[name]
    pad=size//8;l=pad;r=size-pad-1;cx=cy=(size-1)/2
    if name=='圆形':d.ellipse((l,l,r,r),fill=color)
    elif name=='正方形':d.rounded_rectangle((l,l,r,r),radius=3,fill=color)
    elif name=='三角形':d.polygon(((cx,l),(r,r),(l,r)),fill=color)
    elif name=='菱形':d.polygon(((cx,l),(r,cy),(cx,r),(l,cy)),fill=color)
    elif name=='星形':
        points=[]
        for i in range(10):
            angle=-math.pi/2+i*math.pi/5;rad=(size/2-pad)*(1 if i%2==0 else .45)
            points.append((cx+math.cos(angle)*rad,cy+math.sin(angle)*rad))
        d.polygon(points,fill=color)
    else:
        d.ellipse((l,l,cx+2,cy+4),fill=color);d.ellipse((cx-2,l,r,cy+4),fill=color)
        d.polygon(((l,cy),(r,cy),(cx,r)),fill=color)
    return image
