"""Instructed fixation image collection. Target labels are not measured gaze."""
import hashlib
import json
import time
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from .framebuffer import encode_frame

# First visit and later repeats are kept separate. No calibration fitted here.
TARGETS = [
    ("center",(.5,.55),"first"), ("water",(.2625,.38),"first"),
    ("rest",(.7375,.38),"first"), ("help",(.2625,.70),"first"),
    ("more",(.7375,.70),"first"), ("rest",(.7375,.38),"repeat"),
    ("help",(.2625,.70),"repeat"), ("water",(.2625,.38),"repeat"),
    ("more",(.7375,.70),"repeat")]
# Frozen before the new live capture: two fitting visits, then unseen checks.
POINTS = {name:point for name,point,_ in TARGETS}
APPEARANCE_TARGETS = [(name,POINTS[name],visit) for visit,names in (
    ('fit_a',('center','water','rest','help','more')),
    ('fit_b',('more','rest','center','water','help')),
    ('check',('help','center','more','rest','water'))) for name in names]


def checked_plan(plan):
    plan=tuple((name,tuple(point),visit) for name,point,visit in plan)
    if not 1<=len(plan)<=19:raise ValueError('bounded target plan required')
    for name,point,visit in plan:
        if name not in POINTS or len(point)!=2 or not np.isfinite(point).all() or not all(0<=v<=1 for v in point) or not isinstance(visit,str) or not visit:
            raise ValueError('invalid instructed target')
    return plan

INTRO_SECONDS = 6.
TARGET_SECONDS = 6.
SETTLE_SECONDS = 2.
SAMPLE_PERIOD = .8
SAMPLES_PER_TARGET = 5


class FixationRenderer:
    def __init__(self,plan=TARGETS):
        self.plan=checked_plan(plan)
        with Image.open(Path(__file__).resolve().parents[2]/"assets/fixation_template.png") as im:
            if im.size != (640,480):
                raise ValueError("fixation template geometry")
            self.base = im.convert("RGB")
        self.font = ImageFont.load_default()

    def frame(self, step=None):
        image = self.base.copy()
        draw = ImageDraw.Draw(image)
        target = (.5,.55) if step is None else self.plan[step][1]
        cx,cy = round(target[0]*640), round(target[1]*480)
        draw.ellipse((cx-21,cy-21,cx+21,cy+21),fill="#ffffff",outline="#164e4b",width=3)
        draw.ellipse((cx-8,cy-8,cx+8,cy+8),fill="#e67638")
        draw.text((550,25),"READY" if step is None else "%d / %d"%(step+1,len(self.plan)),fill="#164e4b",font=self.font)
        return encode_frame(np.asarray(image,dtype=np.uint8))


class FixationRecording:
    def __init__(self,plan=TARGETS):
        self.plan=checked_plan(plan)
        self.samples = []
        self.slots = set()
        self.last_index = 0
        self.last_time = None
        self.frames = 0

    def observe(self,pixels,index,requested,copied,presented,step):
        if not isinstance(pixels,np.ndarray) or pixels.shape!=(480,640) or pixels.dtype!=np.uint8:
            raise ValueError("native640x480 GRAY8 required")
        if type(index) is not int or index<=self.last_index or not 0<=step<len(self.plan):
            raise ValueError("fresh capture and valid target required")
        if not np.isfinite([requested,copied,presented]).all() or copied<requested or requested<presented:
            raise ValueError("capture must follow confirmed target presentation")
        if self.last_time is not None and copied<=self.last_time:
            raise ValueError("capture time must increase")
        self.last_index,self.last_time=index,copied
        self.frames+=1
        age=copied-presented
        # Also gate request time: no transition capture can earn a target label.
        if requested-presented<SETTLE_SECONDS or age>=TARGET_SECONDS:
            return
        slot=int((age-SETTLE_SECONDS)/SAMPLE_PERIOD)
        if not 0<=slot<SAMPLES_PER_TARGET or (step,slot) in self.slots:
            return
        self.slots.add((step,slot))
        key,point,visit=self.plan[step]
        self.samples.append(({"step":step,"target":key,"target_normalized":list(point),"visit":visit,
            "frame_index":index,"slot":slot,"requested_after_present_s":requested-presented,
            "copied_after_present_s":age,"target_present_confirmed_monotonic":presented,
            "copied_monotonic":copied,"label_source":"instructed_target_not_measured_gaze"},pixels.copy()))

    def save(self,output,completed):
        dest=Path(output)/"targets";dest.mkdir(parents=True,exist_ok=False)
        entries=[]
        for i,(meta,pixels) in enumerate(self.samples):
            name="sample_%02d"%i;raw=pixels.tobytes()
            (dest/(name+".gray8")).write_bytes(raw)
            Image.fromarray(pixels,mode="L").save(dest/(name+".png"))
            entries.append(dict(meta,raw=name+".gray8",png=name+".png",sha256=hashlib.sha256(raw).hexdigest()))
        summary={"completed_run":bool(completed),"source":"live_camera","frames":self.frames,
            "samples":len(entries),"raw_bytes":len(entries)*307200,"settle_seconds":SETTLE_SECONDS,
            "target_seconds":TARGET_SECONDS,"target_plan":self.plan,
            "target_labels_are_measured_gaze":False,"sensor_exposure_timestamps_available":False,
            "calibration_fitted":False,"gaze_validated":False}
        (dest/"manifest.json").write_text(json.dumps(dict(summary,samples_detail=entries),indent=2)+"\n",encoding="utf-8")
        return summary


def run_fixation(session,renderer,recording,clock=time.monotonic,sleep=time.sleep):
    if getattr(renderer,"plan",recording.plan)!=recording.plan:raise ValueError("renderer/recording plan mismatch")
    started=clock()
    while clock()-started<INTRO_SECONDS:
        session.display_health();sleep(.02)
    before=session.wait_native_frames(2)
    presentations=[]
    for step in range(len(recording.plan)):
        session.present(renderer.frame(step))
        shown=clock()  # timestamp after hardware-confirmed buffer switch
        presentations.append({"step":step,"confirmed_elapsed_s":shown-started})
        while clock()-shown<TARGET_SECONDS:
            pixels=session.capture_once(); info=session.last_capture
            recording.observe(pixels,session.capture_index,info["requested_at_monotonic"],
                              info["copied_at_monotonic"],shown,step)
    after=session.wait_native_frames(1)
    if after["bad_lines"]!=before["bad_lines"] or after["bad_frames"]!=before["bad_frames"]:
        raise RuntimeError("camera errors increased during fixation collection")
    return {"elapsed_seconds":clock()-started,"camera_frames":recording.frames,
            "presentations":presentations,"diagnostic_before":before,"diagnostic_after":after,
            "calibration_fitted":False,"gaze_and_speech_enabled":False}
