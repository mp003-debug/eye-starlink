from pathlib import Path
import sys,json,math
r=Path(__file__).resolve().parents[1];sys.path[:0]=[str(r/'tools/deps/opencv'),str(r/'src')]
import cv2,numpy as np
from PIL import Image,ImageDraw
from eye_tracker.appearance import EyeAnchor
src=r/'data/private/bringup/fixation/targets';ref=np.frombuffer((src/'sample_00.gray8').read_bytes(),np.uint8).reshape(480,640)
a=EyeAnchor(ref,(128,108,328,308));p=a.points.reshape(-1,2)
out=r/'data/private/analysis/appearance';canvas=Image.new('RGB',(1280,960))
for j,i in enumerate([0,17,26,29]):
 im=np.frombuffer((src/('sample_%02d.gray8'%i)).read_bytes(),np.uint8).reshape(480,640)
 q,st,_=cv2.calcOpticalFlowPyrLK(ref,im,a.points,None,**a.lk);bk,st2,_=cv2.calcOpticalFlowPyrLK(im,ref,q,None,**a.lk);q=q.reshape(-1,2)
 ok=(st.ravel()==1)&(st2.ravel()==1)&(np.linalg.norm(bk.reshape(-1,2)-p,axis=1)<1)
 cv2.setRNGSeed(0);M,k=cv2.estimateAffinePartial2D(p[ok],q[ok],method=cv2.RANSAC,ransacReprojThreshold=1.5,maxIters=500,confidence=.99,refineIters=10)
 k=k.ravel().astype(bool);points=p[ok][k];pred=points@M[:,:2].T+M[:,2]
 tile=Image.fromarray(im).convert('RGB');d=ImageDraw.Draw(tile)
 for x,y in q[ok][k]:d.ellipse((x-3,y-3,x+3,y+3),fill='lime')
 d.text((10,10),'sample '+str(i),fill='red');canvas.paste(tile,((j%2)*640,(j//2)*480))
 print(i,'all',len(p),'reversible',sum(ok),'inliers',sum(k),'ratio',k.mean(),'spread',np.ptp(points,axis=0).tolist(),'M',M.tolist(),'p95',np.percentile(np.linalg.norm(pred-q[ok][k],axis=1),95))
canvas.save(out/'anchor_debug.png')
