"""Joint same-eye corner matching; no skin/brow translation surrogate.

Experimental opt-in model mode. Both complete corner patches must score >=.90,
their pair must have unique location and valid geometry, and the required eye
crop must be observed. Acquisition is setup-only; interaction is bounded by the
frozen setup position and does not update templates or position on its own.
"""
from concurrent.futures import ThreadPoolExecutor,wait
import numpy as np
from .appearance import EyeAnchor,AlignmentFailure
from .appearance_diagnostic import CornerMatcher

_WORKERS=ThreadPoolExecutor(max_workers=2,thread_name_prefix="eye-corner")

class PairCornerMatcher(CornerMatcher):
    def __init__(self,*args,parallel=True,**kwargs):
        super().__init__(*args,**kwargs)
        self.parallel=parallel
    SCORE=.90
    MARGIN=.04
    MAX_PEAKS=6
    def _peaks(self,pixels,template,center=None):
        cv=self.cv;h,w=template.shape
        if center is None:x0,y0,x1,y1=0,0,640,480
        else:
            radius=.35*(self.box[2]-self.box[0])
            x0=max(0,int(np.floor(center[0]-w/2-radius)))
            y0=max(0,int(np.floor(center[1]-h/2-radius)))
            x1=min(640,int(np.ceil(center[0]+w/2+radius)))
            y1=min(480,int(np.ceil(center[1]+h/2+radius)))
        if x1-x0<w+2 or y1-y0<h+2:return []
        scores=cv.matchTemplate(pixels[y0:y1,x0:x1],template,cv.TM_CCOEFF_NORMED)
        scores[~np.isfinite(scores)]=-1
        work=scores.copy();peaks=[];radius=max(8,round(.12*np.linalg.norm(self.corners[1]-self.corners[0])))
        for _ in range(self.MAX_PEAKS):
            _,score,_,(x,y)=cv.minMaxLoc(work)
            if score<self.SCORE-self.MARGIN:break
            work[max(0,y-radius):y+radius+1,max(0,x-radius):x+radius+1]=-1
            if not (0<x<scores.shape[1]-1 and 0<y<scores.shape[0]-1):continue
            def offset(left,mid,right):
                den=left-2*mid+right
                return float(np.clip(.5*(left-right)/den,-1,1)) if den<-1e-6 else 0.
            dx=offset(scores[y,x-1],scores[y,x],scores[y,x+1]);dy=offset(scores[y-1,x],scores[y,x],scores[y+1,x])
            peaks.append((np.array([x0+x+dx+w/2,y0+y+dy+h/2]),float(score)))
        if float(work.max())>=self.SCORE-self.MARGIN:
            raise AlignmentFailure("corner_pair_candidates_ambiguous")
        return peaks
    def _pair(self,pixels,global_search):
        EyeAnchor._image(pixels)
        jobs=[(pixels,t,None if global_search else c+self.origin_shift)
              for c,t in zip(self.corners,self.templates)]
        if self.parallel:
            # Independent, read-only searches use the two Cortex-A9 cores.
            # Wait for BOTH even on failure, before a capture buffer can be reused.
            futures=[_WORKERS.submit(self._peaks,*args)for args in jobs]
            wait(futures)
            peaks=[future.result()for future in futures]
        else:peaks=[self._peaks(*args)for args in jobs]
        v=self.corners[1]-self.corners[0];span=float(np.linalg.norm(v));pairs=[]
        for left,ls in peaks[0]:
            for right,rs in peaks[1]:
                q=right-left;a=float(np.dot(v,q)/np.dot(v,v));b=float((v[0]*q[1]-v[1]*q[0])/np.dot(v,v))
                if not .85<=np.hypot(a,b)<=1.18 or abs(np.degrees(np.arctan2(b,a)))>8:continue
                points=np.array([left,right]);shift=np.mean(points-self.corners,axis=0)
                if not global_search and np.linalg.norm(shift-self.origin_shift)>.35*(self.box[2]-self.box[0]):continue
                pairs.append((min(ls,rs),points,[ls,rs],shift))
        if not pairs:raise AlignmentFailure('corner_pair_not_matched')
        pairs.sort(key=lambda p:p[0],reverse=True);best=pairs[0]
        competitors=[p[0]for p in pairs[1:]if np.linalg.norm(p[3]-best[3])>.20*span]
        # Unreported peaks have scores below SCORE-MARGIN; use that conservative
        # upper bound when no competing pair is explicitly present.
        runner=max(competitors,default=self.SCORE-self.MARGIN)
        margin=best[0]-runner
        if best[0]<self.SCORE or margin<self.MARGIN:raise AlignmentFailure('corner_pair_ambiguous')
        metrics=dict(translation=best[3].tolist(),corner_pair_score=best[0],corner_pair_margin=margin,
                     alignment='paired_corners_v1',corner_boundary_retry=[False,False])
        return best,metrics
    def acquire(self,pixels):
        best,metrics=self._pair(pixels,True)
        self._warp_pair(pixels,best[1],best[2],metrics)
        self.origin_shift=best[3].astype(np.float32)
        return dict(origin_shift=self.origin_shift.tolist(),score=best[0],margin=metrics['corner_pair_margin'],
                    scope='explicit center setup, unique complete corner pair; not gaze',alignment='paired_corners_v1')
    def align(self,pixels):
        best,metrics=self._pair(pixels,False)
        return self._warp_pair(pixels,best[1],best[2],metrics)
