"""Anchored eye appearance for coarse target research; no pupil/glint/PCCR claim."""
import math
import numpy as np

class AlignmentFailure(ValueError):pass

class EyeAnchor:
    """Match non-eye landmarks to one fixed reference; never accumulate drift."""
    def __init__(self,pixels,box):
        import cv2
        self.cv=cv2;cv2.setNumThreads(1)
        self._image(pixels)
        x0,y0,x1,y1=map(int,box);w=x1-x0;h=y1-y0
        if w<64 or h<64 or not (0<=x0<x1<=640 and 0<=y0<y1<=480):raise AlignmentFailure('invalid_seed')
        self.reference=pixels.copy();self.box=(x0,y0,x1,y1)
        # Use skin immediately around this eye. Distant cheek, hair and background
        # do not share the same local motion when the face turns slightly.
        mask=np.zeros_like(pixels)
        xa,xb=x0,x1
        ya,yb=y0,y1
        mask[ya:yb,xa:xb]=255
        mask[max(0,y0+round(.23*h)):min(480,y0+round(.87*h)),:]=0
        points=cv2.goodFeaturesToTrack(pixels,maxCorners=400,qualityLevel=.02,minDistance=8,mask=mask,blockSize=5)
        # Balance spatial support before RANSAC; strongest texture must not fill
        # every slot from just the brow, leaving an unconstrained vertical warp.
        selected=[]
        if points is not None:
            flat=points.reshape(-1,2);cx=(x0+x1)/2;cy=(y0+y1)/2
            for right,bottom in ((False,False),(True,False),(False,True),(True,True)):
                group=flat[((flat[:,0]>=cx)==right)&((flat[:,1]>=cy)==bottom)]
                selected.extend(group[:25])
        self.points=np.asarray(selected,np.float32).reshape(-1,1,2)
        if len(self.points)<12:raise AlignmentFailure('insufficient_anchors')
        # Constant reference geometry, independent of subsequent detector box sizes.
        self.crop=(max(0,x0-round(.10*w)),max(0,y0+round(.25*h)),min(640,x1+round(.25*w)),min(480,y0+round(.85*h)))
        self.lk=dict(winSize=(21,21),maxLevel=2,criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,20,.03))
        self.coarse_template=cv2.resize(self.reference[y0:y1,x0:x1],(w//2,h//2),interpolation=cv2.INTER_AREA)
        self.coarse_mask=cv2.resize(mask[y0:y1,x0:x1],(w//2,h//2),interpolation=cv2.INTER_NEAREST)

    @staticmethod
    def _image(pixels):
        if not isinstance(pixels,np.ndarray) or pixels.shape!=(480,640) or pixels.dtype!=np.uint8:raise AlignmentFailure('native_gray8_required')

    def _coarse_shift(self,pixels):
        cv=self.cv;x0,y0,x1,y1=self.box;pad=round(.35*(x1-x0))
        xa,ya=max(0,x0-pad),max(0,y0-pad);xb,yb=min(640,x1+pad),min(480,y1+pad)
        # Exact factor two keeps coordinates correct for odd search extents.
        xb-=((xb-xa)%2);yb-=((yb-ya)%2)
        search=cv.resize(pixels[ya:yb,xa:xb],((xb-xa)//2,(yb-ya)//2),interpolation=cv.INTER_AREA)
        scores=cv.matchTemplate(search,self.coarse_template,cv.TM_CCOEFF_NORMED,mask=self.coarse_mask)
        scores[~np.isfinite(scores)]=-1
        _,score,_,point=cv.minMaxLoc(scores)
        # Translation correlation is only an initializer: a small affine warp
        # of fine texture may have weak translation correlation yet valid LK.
        if score<.5:return np.zeros(2,np.float32),float(score)
        return np.array([point[0]*2+xa-x0,point[1]*2+ya-y0],np.float32),float(score)

    def align(self,pixels):
        self._image(pixels);cv=self.cv
        shift,coarse_score=self._coarse_shift(pixels)
        forward,status,_=cv.calcOpticalFlowPyrLK(self.reference,pixels,self.points,self.points+shift.reshape(1,1,2),flags=cv.OPTFLOW_USE_INITIAL_FLOW,**self.lk)
        if forward is None:raise AlignmentFailure('no_forward_matches')
        back,reverse,_=cv.calcOpticalFlowPyrLK(pixels,self.reference,forward,forward-shift.reshape(1,1,2),flags=cv.OPTFLOW_USE_INITIAL_FLOW,**self.lk)
        if back is None:raise AlignmentFailure('no_reverse_matches')
        p=self.points.reshape(-1,2);q=forward.reshape(-1,2)
        good=(status.ravel()==1)&(reverse.ravel()==1)&(np.linalg.norm(back.reshape(-1,2)-p,axis=1)<1.)&np.isfinite(q).all(axis=1)
        if good.sum()<12:raise AlignmentFailure('insufficient_reversible_matches')
        cv.setRNGSeed(0)
        matrix,inliers=cv.estimateAffine2D(p[good],q[good],method=cv.RANSAC,ransacReprojThreshold=1.5,maxIters=500,confidence=.99,refineIters=10)
        if matrix is None or not np.isfinite(matrix).all():raise AlignmentFailure('no_consistent_transform')
        keep=inliers.ravel().astype(bool);anchors=p[good][keep]
        if keep.sum()<12 or keep.mean()<.70:raise AlignmentFailure('inconsistent_anchors')
        w=self.box[2]-self.box[0];h=self.box[3]-self.box[1]
        if np.ptp(anchors[:,0])<.6*w or np.ptp(anchors[:,1])<.6*h:raise AlignmentFailure('clustered_anchors')
        singular=np.linalg.svd(matrix[:,:2],compute_uv=False)
        if np.linalg.det(matrix[:,:2])<=0 or singular.min()<.85 or singular.max()>1.18 or singular.max()/singular.min()>1.15:
            raise AlignmentFailure('excessive_affine_distortion')
        scale=math.hypot(matrix[0,0],matrix[1,0]);angle=math.degrees(math.atan2(matrix[1,0],matrix[0,0]))
        center=np.array([(self.box[0]+self.box[2])/2,(self.box[1]+self.box[3])/2])
        delta=matrix[:,:2]@center+matrix[:,2]-center
        if not .85<=scale<=1.18 or abs(angle)>8 or np.linalg.norm(delta)>.35*w:raise AlignmentFailure('outside_setup_motion_envelope')
        x0,y0,x1,y1=self.crop
        corners=np.array([[x0,y0],[x1,y0],[x1,y1],[x0,y1]],float)@matrix[:,:2].T+matrix[:,2]
        if np.any(corners<1) or np.any(corners[:,0]>=639) or np.any(corners[:,1]>=479):raise AlignmentFailure('crop_out_of_frame')
        # WARP_INVERSE_MAP samples the current image at reference->current coordinates.
        aligned=cv.warpAffine(pixels,matrix,(640,480),flags=cv.INTER_LINEAR|cv.WARP_INVERSE_MAP)
        patch=aligned[y0:y1,x0:x1].copy()
        predicted=anchors@matrix[:,:2].T+matrix[:,2]
        residual=float(np.percentile(np.linalg.norm(predicted-q[good][keep],axis=1),95))
        return patch,{'coarse_match_score':coarse_score,'inliers':int(keep.sum()),'inlier_ratio':float(keep.mean()),'scale':scale,'singular_scales':singular.tolist(),'angle_deg':angle,'delta_pixels':delta.tolist(),'residual_p95_pixels':residual,'matrix':matrix.tolist(),'reference_crop':self.crop,'eye_open_validated':False}


def appearance_feature(patch):
    import cv2
    if not isinstance(patch,np.ndarray) or patch.ndim!=2 or patch.dtype!=np.uint8:raise ValueError('gray patch required')
    low,high=np.percentile(patch,[5,95])
    if high-low<25:raise ValueError('insufficient_eye_contrast')
    small=cv2.resize(cv2.GaussianBlur(patch,(5,5),0),(48,24),interpolation=cv2.INTER_AREA).astype(np.float32)
    small=np.clip((small-low)/(high-low),0,1)
    return small.reshape(-1)


class CoarseAppearanceModel:
    """Five discrete appearance classes, with explicit rejection; not screen coordinates.

    Development constants are fixed before new live checks. Validation samples
    cannot be training frames. A check result is not general gaze accuracy.
    """
    LABELS=('center','water','rest','help','more')
    MAX_DISTANCE=.09
    MAX_RATIO=.75
    MIN_MARGIN=.015

    def __init__(self,templates,training_ids,geometry_id,metric_weights=None):
        self.metric_weights=self.checked_weights(metric_weights)
        self.templates=templates;self.training_ids=frozenset(training_ids)
        self.geometry_id=geometry_id;self.enabled=False;self.validation=None

    @staticmethod
    def vector(value):
        a=np.asarray(value,dtype=np.float32)
        if a.shape!=(1152,) or not np.isfinite(a).all() or np.any(a<0) or np.any(a>1):raise ValueError('normalized48x24_feature_required')
        return a

    @staticmethod
    def checked_weights(value):
        if value is None:return np.ones(1152,np.float32)
        weights=np.asarray(value,dtype=np.float32)
        if (weights.shape!=(1152,) or not np.isfinite(weights).all()
                or weights.min()<.02 or weights.max()>10
                or not np.isclose(weights.mean(),1.,rtol=0,atol=1e-5)):
            raise ValueError('bounded_mean_one_metric_required')
        result=weights.copy();result.setflags(write=False);return result

    @classmethod
    def training_weights(cls,rows):
        """Learn spatial discrimination from fitting examples only.

        Class variation / within-class variation with a fixed variance floor,
        local smoothing and bounded weights. Neither validation examples nor
        current target prompts participate. Positive weights keep novelty
        visible in every pixel; this is not a blink detector.
        """
        import cv2
        means={}
        for label in cls.LABELS:
            values=[cls.vector(x['feature']) for x in rows if x['target']==label]
            if len(values)<3:raise ValueError('insufficient_weight_training:'+label)
            means[label]=np.median(np.asarray(values),axis=0)
        between=np.var(np.asarray(list(means.values())),axis=0)
        within=np.mean(np.asarray([(cls.vector(x['feature'])-means[x['target']])**2 for x in rows]),axis=0)
        importance=cv2.GaussianBlur((between/(within+.0025)).reshape(24,48),(5,5),0).ravel()
        weights=np.clip(importance,.1,3.);weights/=weights.mean()
        return cls.checked_weights(weights)

    @classmethod
    def fit(cls,observations,geometry_id,discriminative=False):
        if not isinstance(geometry_id,str) or not geometry_id:raise ValueError('geometry_required')
        rows=list(observations);ids=[x['frame_id'] for x in rows]
        if not all(isinstance(v,str) and v for v in ids) or len(set(ids))!=len(ids):raise ValueError('unique_training_frames_required')
        if any(x['target'] not in cls.LABELS for x in rows):raise ValueError('unknown_training_target')
        templates={};support={}
        for label in cls.LABELS:
            groups={}
            for row in rows:
                if row['target']==label:groups.setdefault(row['visit'],[]).append(cls.vector(row['feature']))
            if not groups:raise ValueError('missing_training_target:'+label)
            prototypes=[];support[label]=[]
            for visit,values in groups.items():
                if len(values)<3:raise ValueError('insufficient_training_samples:'+label)
                values=np.asarray(values);median=np.median(values,axis=0)
                distance=np.sqrt(np.mean((values-median)**2,axis=1))
                # Use a tight majority, not the most extreme blink/transition frame.
                kept=values[distance<=cls.MAX_DISTANCE]
                if len(kept)<3:raise ValueError('unstable_training_target:'+label)
                prototype=np.median(kept,axis=0);prototype.setflags(write=False);prototypes.append(prototype)
                support[label].append({'visit':visit,'retained':len(kept),'provided':len(values)})
            templates[label]=np.asarray(prototypes)
        model=cls(templates,ids,geometry_id,cls.training_weights(rows) if discriminative else None);model.training_support=support
        for label,prototypes in templates.items():
            for prototype in prototypes:
                result=model.propose(prototype,geometry_id)
                if result['target']!=label:raise ValueError('overlapping_training_targets')
        for label in cls.LABELS:
            visits={x['visit'] for x in rows if x['target']==label}
            for visit in visits:
                group=[x for x in rows if x['target']==label and x['visit']==visit]
                guesses=[model.propose(x['feature'],geometry_id)['target'] for x in group]
                if any(guess not in (None,label) for guess in guesses):raise ValueError('cross_class_training_error:'+label)
                correct=sum(guess==label for guess in guesses)
                if correct<3 or correct/len(group)<.6:raise ValueError('insufficient_consistent_training:'+label)
        return model

    def propose(self,feature,geometry_id):
        if geometry_id!=self.geometry_id:return {'target':None,'reason':'geometry_changed'}
        a=self.vector(feature)
        distances=sorted((float(np.min(np.sqrt(np.mean(self.metric_weights*(v-a)**2,axis=1)))),k) for k,v in self.templates.items())
        best,label=distances[0];runner=distances[1][0]
        ratio=best/max(runner,1e-9);margin=runner-best
        reason='candidate'
        if best>self.MAX_DISTANCE:reason='unfamiliar_appearance'
        elif ratio>self.MAX_RATIO or margin<self.MIN_MARGIN:reason='ambiguous_appearance'
        return {'target':label if reason=='candidate' else None,'reason':reason,'distance':best,'runner_distance':runner,'ratio':ratio,'margin':margin,'source':'eye_appearance_not_pccr'}

    def validate(self,checks,geometry_id):
        self.enabled=False;self.validation=None
        rows=list(checks);ids=[x['frame_id'] for x in rows]
        if geometry_id!=self.geometry_id or not all(isinstance(v,str) and v for v in ids) or len(set(ids))!=len(ids) or self.training_ids.intersection(ids):raise ValueError('check_leakage_or_geometry_change')
        if any(x['target'] not in self.LABELS+('invalid',) for x in rows):raise ValueError('unknown_check_target')
        counts={k:{'total':0,'correct':0,'rejected':0,'wrong':0} for k in self.LABELS+('invalid',)}
        for row in rows:
            target=row['target'];c=counts[target];c['total']+=1
            guess=None if row.get('feature') is None else self.propose(row['feature'],geometry_id)['target']
            if guess is None:c['correct' if target=='invalid' else 'rejected']+=1
            else:c['correct' if target==guess else 'wrong']+=1
        passed=all(c['total']>=5 and c['wrong']==0 and c['correct']/max(1,c['total'])>=.6 for k,c in counts.items() if k!='invalid')
        passed=passed and counts['invalid']['total']>=5 and counts['invalid']['wrong']==0
        self.validation={'passed':passed,'counts':counts,'scope':'independent instructed examples in this geometry; not general gaze accuracy','thresholds':{'max_distance':self.MAX_DISTANCE,'max_ratio':self.MAX_RATIO,'min_margin':self.MIN_MARGIN}}
        self.enabled=passed
        return self.validation
