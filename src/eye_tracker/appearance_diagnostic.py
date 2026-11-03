"""Read-only live appearance diagnostics. No actions or calibration enable path."""
import hashlib,json,time
from pathlib import Path
import numpy as np
from .appearance import EyeAnchor,appearance_feature,CoarseAppearanceModel,AlignmentFailure
from .fixation import FixationRecording,POINTS

CHECK_TARGETS=[('center',POINTS['center'],'session_reference')]+[(n,POINTS[n],'new_check') for n in ('rest','help','center','more','water')]

class TranslationMatcher:
    """Restricted local translation on quarter-size non-eye pixels."""
    def __init__(self,reference,box):
        import cv2
        self.cv=cv2;cv2.setNumThreads(1);EyeAnchor._image(reference)
        x0,y0,x1,y1=map(int,box);w=x1-x0;h=y1-y0
        if w<64 or h<64 or w%4 or h%4 or not (0<=x0<x1<=640 and 0<=y0<y1<=480):raise ValueError('quarter_grid_seed_required')
        self.reference=reference.copy();self.box=(x0,y0,x1,y1);self.origin_shift=np.zeros(2,np.float32)
        self.crop=(max(0,x0-round(.10*w)),max(0,y0+round(.25*h)),min(640,x1+round(.25*w)),min(480,y0+round(.85*h)))
        mask=np.full((h,w),255,np.uint8);mask[round(.23*h):round(.87*h)]=0
        self.template=cv2.resize(reference[y0:y1,x0:x1],(w//4,h//4),interpolation=cv2.INTER_AREA)
        self.mask=cv2.resize(mask,(w//4,h//4),interpolation=cv2.INTER_NEAREST)
        if np.std(self.template[self.mask>0])<5:raise ValueError('untextured_reference')
    def acquire(self,pixels):
        """One explicit setup relocation; classification never calls this."""
        self._image(pixels) if hasattr(self,'_image') else EyeAnchor._image(pixels)
        cv=self.cv;x0,y0,x1,y1=self.box;xa=x0%4;ya=y0%4
        xb=640-(640-xa)%4;yb=480-(480-ya)%4
        search=cv.resize(pixels[ya:yb,xa:xb],((xb-xa)//4,(yb-ya)//4),interpolation=cv.INTER_AREA)
        scores=cv.matchTemplate(search,self.template,cv.TM_CCOEFF_NORMED,mask=self.mask);scores[~np.isfinite(scores)]=-1
        _,score,_,(px,py)=cv.minMaxLoc(scores)
        second=scores.copy();radius=max(2,round(.2*(x1-x0)/4))
        second[max(0,py-radius):py+radius+1,max(0,px-radius):px+radius+1]=-1
        runner=float(second.max());margin=score-runner
        if score<.90 or margin<.04:raise AlignmentFailure('setup_identity_ambiguous')
        shift=np.array([px*4+xa-x0,py*4+ya-y0],np.float32)
        a,b,c,d=self.crop
        if a+shift[0]<1 or b+shift[1]<1 or c+shift[0]>=639 or d+shift[1]>=479:raise AlignmentFailure('setup_crop_outside')
        self.origin_shift=shift
        return {'origin_shift':shift.tolist(),'score':score,'runner_score':runner,'margin':margin,'scope':'explicit center setup only; not gaze'}
    def _locate(self,pixels):
        """Locate surrounding skin; do not require an unused coarse eye crop."""
        EyeAnchor._image(pixels);cv=self.cv;x0,y0,x1,y1=self.box;w=x1-x0
        pad=round(.35*w)//4*4;ox,oy=self.origin_shift.astype(int);xa=max(0,x0+ox-pad);ya=max(0,y0+oy-pad)
        xa+=(x0-xa)%4;ya+=(y0-ya)%4;xb=min(640,x1+ox+pad);yb=min(480,y1+oy+pad)
        xb-=(xb-xa)%4;yb-=(yb-ya)%4
        search=cv.resize(pixels[ya:yb,xa:xb],((xb-xa)//4,(yb-ya)//4),interpolation=cv.INTER_AREA)
        scores=cv.matchTemplate(search,self.template,cv.TM_CCOEFF_NORMED,mask=self.mask);scores[~np.isfinite(scores)]=-1
        _,score,_,point=cv.minMaxLoc(scores);px,py=point
        if score<.90 or not (0<px<scores.shape[1]-1 and 0<py<scores.shape[0]-1):raise AlignmentFailure('neighborhood_not_matched')
        def offset(left,center,right):
            den=left-2*center+right
            return float(np.clip(.5*(left-right)/den,-1,1)) if den< -1e-6 else 0.
        dx=offset(scores[py,px-1],scores[py,px],scores[py,px+1]);dy=offset(scores[py-1,px],scores[py,px],scores[py+1,px])
        shift=np.array([(px+dx)*4+xa-x0,(py+dy)*4+ya-y0])
        if np.linalg.norm(shift-self.origin_shift)>.35*w:raise AlignmentFailure('motion_envelope')
        return shift,{'translation':shift.tolist(),'neighborhood_score':score}

    def align(self,pixels):
        shift,metrics=self._locate(pixels);cv=self.cv
        a,b,c,d=self.crop
        if a+shift[0]<1 or b+shift[1]<1 or c+shift[0]>=639 or d+shift[1]>=479:raise AlignmentFailure('eye_crop_outside_frame')
        # Render just the eye crop; no full-frame warp allocation each capture.
        M=np.float32([[1,0,a+shift[0]],[0,1,b+shift[1]]])
        patch=cv.warpAffine(pixels,M,(c-a,d-b),flags=cv.INTER_LINEAR|cv.WARP_INVERSE_MAP)
        return patch,metrics

class CornerMatcher(TranslationMatcher):
    """Refine coarse skin translation with two local eye-corner patches.

    Corners are helper-marked on the first fitting image, not gaze estimates.
    This diagnostic remains subject-specific and does not establish open eyes.
    """
    def __init__(self,reference,box,corners,crop_mode="legacy"):
        super().__init__(reference,box)
        self.corners=np.asarray(corners,np.float32)
        if self.corners.shape!=(2,2) or not np.isfinite(self.corners).all():raise ValueError('two_reference_corners_required')
        if np.linalg.norm(self.corners[1]-self.corners[0])<80:raise ValueError('separated_corners_required')
        if crop_mode not in ('legacy','eye_support_v1'):raise ValueError('unknown_feature_crop_mode')
        self.crop_mode=crop_mode
        if crop_mode=='eye_support_v1':
            # Fixed reference anatomy: keep both corners and a 10% span margin.
            # Vertical support and all alignment gates stay unchanged. Models
            # must be refitted on this crop; no missing pixels are padded.
            span=float(np.linalg.norm(self.corners[1]-self.corners[0]))
            margin=round(.10*span)
            left=int(np.floor(self.corners[:,0].min()))-margin
            right=int(np.ceil(self.corners[:,0].max()))+margin
            if not 1<=left<right<639:raise ValueError('reference_eye_support_outside')
            self.crop=(left,self.crop[1],right,self.crop[3])
        self.templates=[]
        for cx,cy in self.corners:
            if cx!=int(cx) or cy!=int(cy) or not (20<=cx<=620 and 32<=cy<=448):raise ValueError('corner_patch_outside')
            cx,cy=int(cx),int(cy);t=reference[cy-32:cy+32,cx-20:cx+20].copy()
            if t.std()<5:raise ValueError('untextured_corner')
            self.templates.append(t)
    def _corner(self,pixels,cx,cy,template,shift):
        cv=self.cv;boundary_peak=None
        for pad in (28,36):
            xx=int(round(cx-20+shift[0]-pad));yy=int(round(cy-32+shift[1]-pad))
            xb,yb=min(640,xx+40+2*pad),min(480,yy+64+2*pad);xx,yy=max(0,xx),max(0,yy)
            if xb-xx<template.shape[1]+2 or yb-yy<template.shape[0]+2:raise AlignmentFailure('corner_search_outside')
            scores=cv.matchTemplate(pixels[yy:yb,xx:xb],template,cv.TM_CCOEFF_NORMED)
            scores[~np.isfinite(scores)]=-1
            _,score,_,(px,py)=cv.minMaxLoc(scores)
            if score<.85:raise AlignmentFailure('corner_not_matched')
            absolute=np.array([xx+px,yy+py],float)
            if boundary_peak is not None and np.max(np.abs(absolute-boundary_peak))>8:
                raise AlignmentFailure('corner_boundary_peak_changed')
            if not (0<px<scores.shape[1]-1 and 0<py<scores.shape[0]-1):
                if pad==28:
                    # One bounded 8-pixel halo to bracket a strong cut-off peak.
                    # No boundary acceptance, image padding or threshold reduction.
                    boundary_peak=absolute;continue
                raise AlignmentFailure('corner_not_matched')
            def offset(left,center,right):
                den=left-2*center+right
                return float(np.clip(.5*(left-right)/den,-1,1)) if den< -1e-6 else 0.
            dx=offset(scores[py,px-1],scores[py,px],scores[py,px+1]);dy=offset(scores[py-1,px],scores[py,px],scores[py+1,px])
            return [xx+px+dx+20,yy+py+dy+32],score,pad==36
        raise AlignmentFailure('corner_not_matched')
    def align(self,pixels):
        shift,metrics=self._locate(pixels);cv=self.cv;dst=[];values=[];expanded=[]
        for (cx,cy),template in zip(self.corners,self.templates):
            point,score,retry=self._corner(pixels,cx,cy,template,shift)
            dst.append(point);values.append(score);expanded.append(retry)
        metrics['corner_boundary_retry']=expanded
        return self._warp_pair(pixels,dst,values,metrics)
    def _warp_pair(self,pixels,dst,values,metrics):
        cv=self.cv
        dst=np.asarray(dst,np.float32);v=self.corners[1]-self.corners[0];q=dst[1]-dst[0]
        a=float(np.dot(v,q)/np.dot(v,v));b=float((v[0]*q[1]-v[1]*q[0])/np.dot(v,v))
        scale=float(np.hypot(a,b));angle=float(np.degrees(np.arctan2(b,a)))
        if not .85<=scale<=1.18 or abs(angle)>8:raise AlignmentFailure('corner_geometry_changed')
        matrix=np.array([[a,-b,0],[b,a,0]],np.float32);matrix[:,2]=dst[0]-matrix[:,:2]@self.corners[0]
        x0,y0,x1,y1=self.crop;boundary=np.array([[x0,y0],[x1,y0],[x1,y1],[x0,y1]])@matrix[:,:2].T+matrix[:,2]
        if np.any(boundary<1) or np.any(boundary[:,0]>=639) or np.any(boundary[:,1]>=479):raise AlignmentFailure('eye_crop_outside_frame')
        transform=matrix.copy();transform[:,2]+=matrix[:,:2]@np.array([x0,y0])
        patch=cv.warpAffine(pixels,transform,(x1-x0,y1-y0),flags=cv.INTER_LINEAR|cv.WARP_INVERSE_MAP)
        metrics.update(corner_scores=values,corner_centers=dst.tolist(),corner_scale=scale,corner_angle_deg=angle,corner_matrix=matrix.tolist())
        return patch,metrics

class SessionBaseline:
    """Explicit center-reference phase; frozen afterward, never self-adapting."""
    def __init__(self,training_center):
        self.training=CoarseAppearanceModel.vector(training_center).copy();self.samples=[];self.ids=set();self.offset=None;self.closed=False;self.summary=None
    def add(self,feature,index):
        if self.closed or type(index) is not int or index<=0 or index in self.ids or len(self.samples)>=5:raise ValueError('invalid_reference_collection')
        self.ids.add(index);self.samples.append(CoarseAppearanceModel.vector(feature).copy())
    def finish(self):
        if self.closed:return self.summary
        self.closed=True;self.summary={'ready':False,'provided':len(self.samples)}
        if len(self.samples)!=5:self.summary['reason']='five_reference_samples_required';return self.summary
        a=np.asarray(self.samples);median=np.median(a,axis=0);keep=np.sqrt(np.mean((a-median)**2,axis=1))<=.05
        if keep.sum()<3:self.summary['reason']='unstable_center_reference';return self.summary
        center=np.median(a[keep],axis=0);delta=center-self.training;size=float(np.sqrt(np.mean(delta**2)))
        self.summary.update(retained=int(keep.sum()),offset_rms=size)
        if size>.18:self.summary['reason']='center_outside_development_envelope';return self.summary
        self.offset=delta;self.summary.update(ready=True,reason='diagnostic_reference_only');return self.summary
    def correct(self,feature):
        if self.offset is None:raise ValueError('center_reference_required')
        return np.clip(CoarseAppearanceModel.vector(feature)-self.offset,0,1)

class StableCandidate:
    """A diagnostic temporal filter; its output is NOT a validated gaze sample."""
    def __init__(self):
        self.last_index=0;self.last_time=None;self.key=None;self.started=None;self.count=0
    def update(self,key,index,copied,now):
        if type(index) is not int or index<=self.last_index or not np.isfinite([copied,now]).all() or copied<0 or now<copied or (self.last_time is not None and copied<=self.last_time):
            self.key=None;self.started=None;self.count=0
            raise ValueError('nonfresh_diagnostic_input')
        gap=self.last_time is not None and copied-self.last_time>.250
        self.last_index,self.last_time=index,copied
        if key not in CoarseAppearanceModel.LABELS or now-copied>.150:
            self.key=None;self.started=None;self.count=0;return None
        if gap or key!=self.key:
            self.key=key;self.started=copied;self.count=1;return None
        self.count+=1
        return key if self.count>=5 and copied-self.started>=.350 else None

class AppearanceDiagnostic:
    def __init__(self,path):
        import cv2
        self.cv=cv2;cv2.setNumThreads(1)
        self.pack_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest()
        with np.load(path,allow_pickle=False) as a:
            self.reference=a['reference'].copy();self.box=tuple(int(x) for x in a['box'])
            templates={k:a['template_'+k].copy() for k in CoarseAppearanceModel.LABELS}
            self.metadata=json.loads(str(a['metadata'].item()));corners=a['corners'].copy()
            metric=self.metadata.get('feature_metric','uniform')
            if metric not in ('uniform','training_fisher_v1'):raise ValueError('unknown_feature_metric')
            weights=a['metric_weights'].copy() if metric=='training_fisher_v1' else None
            if metric=='training_fisher_v1' and self.metadata.get('strict_training_passed') is not True:raise ValueError('weighted_pack_requires_strict_fit')
        if self.metadata.get('diagnostic_only') is not True:raise ValueError('diagnostic pack required')
        if self.metadata.get('alignment')!='corners_and_session_reference':raise ValueError('current diagnostic alignment pack required')
        alignment_mode=self.metadata.get('corner_search_mode','skin_seed_v1')
        if alignment_mode=='paired_corners_v1':
            from .corner_pair import PairCornerMatcher
            matcher=PairCornerMatcher
        elif alignment_mode=='skin_seed_v1':matcher=CornerMatcher
        else:raise ValueError('unknown_corner_search_mode')
        self.anchor=matcher(self.reference,self.box,corners,self.metadata.get('feature_crop_mode','legacy'))
        visits=self.metadata.get('template_visit_count',2)
        if visits not in (1,2):raise ValueError('unsupported_template_visit_count')
        if visits==1:
            ids=self.metadata.get('training_ids',[])
            counts=self.metadata.get('training_counts',{})
            if (self.metadata.get('training_protocol')!='current_session_25'
                    or self.metadata.get('strict_training_passed') is not True
                    or len(ids)!=25 or len(set(ids))!=25
                    or counts!={k:5 for k in CoarseAppearanceModel.LABELS}):
                raise ValueError('explicit_current_session_training_required')
        for k,v in templates.items():
            if v.shape!=(visits,1152):raise ValueError('declared_fitting_visits_required')
            for f in v:CoarseAppearanceModel.vector(f)
        self.geometry_id=hashlib.sha256(self.reference.tobytes()).hexdigest()
        self.model=CoarseAppearanceModel(templates,[],self.geometry_id,weights)
        self.gate=StableCandidate();self.baseline=SessionBaseline(np.median(templates['center'],axis=0));self.relocation=None
    def feature(self,pixels):
        patch,metrics=self.anchor.align(pixels)
        return appearance_feature(patch),metrics
    def observe(self,pixels,index,copied,clock=time.monotonic):
        started=clock();candidate=None;result={'candidate':None,'stable_candidate':None,'actions_enabled':False}
        try:
            feature,metrics=self.feature(pixels);result.update(metrics);feature=self.baseline.correct(feature)
            guess=self.model.propose(feature,self.geometry_id);candidate=guess['target'];result.update(candidate=candidate,classification=guess)
        except (ValueError,self.cv.error) as exc:result['rejection']=str(exc)
        now=clock();result['processing_ms']=(now-started)*1000
        result['copy_to_result_ms']=(now-copied)*1000
        result['stable_candidate']=self.gate.update(candidate,index,copied,now)
        return result

    def observe_reference(self,pixels,index,copied,eligible,clock=time.monotonic):
        started=clock();result={'candidate':None,'stable_candidate':None,'actions_enabled':False,'reference_sample':False}
        if eligible:
            try:
                if self.relocation is None:self.relocation=self.anchor.acquire(pixels)
                feature,metrics=self.feature(pixels);result.update(metrics);self.baseline.add(feature,index);result['reference_sample']=True
            except (ValueError,self.cv.error) as exc:result['rejection']=str(exc)
        now=clock();result['processing_ms']=(now-started)*1000;result['copy_to_result_ms']=(now-copied)*1000
        self.gate.update(None,index,copied,now)
        return result

class DiagnosticRecording(FixationRecording):
    def __init__(self,engine,plan=CHECK_TARGETS,clock=time.monotonic):
        super().__init__(plan);self.engine=engine;self.clock=clock;self.rows=[]
    def observe(self,pixels,index,requested,copied,presented,step):
        before=len(self.samples);super().observe(pixels,index,requested,copied,presented,step)
        if len(self.rows)>=2000:raise ValueError('bounded diagnostic capacity exceeded')
        reference=self.plan[step][2]=='session_reference'
        if reference:
            result=self.engine.observe_reference(pixels,index,copied,len(self.samples)>before,self.clock)
        else:
            self.engine.baseline.finish()
            result=self.engine.observe(pixels,index,copied,self.clock)
        # Prompt labels are attached only after prediction, never passed to engine.
        result.update(frame_index=index,copied_monotonic=copied,step=step,
                      instructed_target=self.plan[step][0],after_present_s=copied-presented,
                      scored=not reference and requested-presented>=2.,phase=self.plan[step][2])
        self.rows.append(result)
    def save(self,output,completed):
        result=super().save(output,completed);counts={k:{'frames':0,'candidate_correct':0,'candidate_wrong':0,'stable_correct':0,'stable_wrong':0,'stable_rejected':0} for k in CoarseAppearanceModel.LABELS}
        for row in self.rows:
            if not row['scored']:continue
            k=row['instructed_target'];c=counts[k];c['frames']+=1
            if row['candidate'] is not None:c['candidate_correct' if row['candidate']==k else 'candidate_wrong']+=1
            v=row['stable_candidate'];c['stable_rejected' if v is None else 'stable_correct' if v==k else 'stable_wrong']+=1
        times=[x['processing_ms'] for x in self.rows if x['phase']!='session_reference']
        summary={'completed':bool(completed),'scope':'candidate-only live diagnostics, no button/audio/UART or calibration enabling','model_pack_sha256':self.engine.pack_sha256,'rows':len(self.rows),'counts':counts,'processing_p95_ms':float(np.percentile(times,95)) if times else None,'actions_enabled':False,'invalid_input_verified':False,'center_reference':self.engine.baseline.summary,'reference_relocation':self.engine.relocation}
        (Path(output)/'diagnostic.json').write_text(json.dumps(dict(summary,frames=self.rows),indent=2)+'\n')
        result['appearance_diagnostic']=summary
        return result
