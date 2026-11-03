"""Explicit synthetic input for an on-board communication UI acceptance test.

This module never opens a camera, fits real calibration, or invokes audio.
The same DwellController and BoardRenderer are reusable by the real input path.
"""
from dataclasses import asdict, dataclass
import json
import math
import time
import numpy as np
from PIL import Image
from .calibration import Context
from .interaction import DwellController, GazeSample
from .framebuffer import unpack_rgb565


@dataclass(frozen=True)
class Phase:
    name: str
    duration_ms: int
    point: tuple = (.25,.37)
    status: object = "valid"
    command: object = None
    expected: tuple = ()


PHASES = (
    Phase("uncalibrated",800),
    Phase("water_once_despite_hold",2400,command="test_calibration",expected=("water",)),
    Phase("loss_does_not_unlock",800,status="lost"),
    Phase("return_without_valid_exit",800),
    Phase("valid_exit_rearms",450,point=(.5,.5)),
    Phase("partial_before_cancel",600),
    Phase("cancel_restarts_dwell",500,command="cancel"),
    Phase("move_away_cancels",450,point=(.5,.5)),
    Phase("water_after_new_dwell",1400,expected=("water",)),
    Phase("pause_blocks_rest",1000,point=(.75,.37),command="pause"),
    Phase("resume_partial_rest",600,point=(.75,.37),command="resume"),
    Phase("missing_input_clears_progress",500,status=None),
    Phase("rest_needs_new_dwell",1400,point=(.75,.37),expected=("rest",)),
    Phase("more_page",1400,point=(.75,.70),expected=("more",)),
    Phase("return_page",1400,point=(.5,.5),expected=("back",)),
    Phase("partial_help",600,point=(.25,.70)),
    Phase("closed_cancels_help",600,status="closed"),
    Phase("help_needs_new_dwell",1400,point=(.25,.70),expected=("help",)),
    Phase("stopped_blocks_input",1000,point=(.25,.70),command="stop"),
)


class InteractionTest:
    def __init__(self):
        self.context=Context("board-ui-test", "640x480-fixed-targets", "simulated")
        self.controller=DwellController(self.context)
        self.index=-1;self.phase_started=0.;self.sequence=0;self.now=0.
        self.actions=[];self.checks=[];self.commands=[];self.phase_actions=[]
        self.feedback_key=None;self.feedback_at=-math.inf;self.done=False
        self.samples=0;self.no_input_ticks=0;self.last_action=None

    @property
    def feedback(self):
        return self.feedback_key if self.now-self.feedback_at < 1500 else None

    def _enter(self, now):
        self.index+=1
        if self.index==len(PHASES):
            self.done=True
            return
        self.phase_started=now;self.phase_actions=[]
        command=PHASES[self.index].command
        if command:
            if command=="test_calibration":
                # Marker only for the explicitly synthetic context. Not a fitted
                # or persisted calibration, and never transferable to live input.
                self.controller.calibration_id="synthetic-ui-test-only"
            else:
                getattr(self.controller,command)(now)
            self.commands.append({"command":command,"time_ms":now,"progress_after":self.controller.progress})

    def _finish(self):
        phase=PHASES[self.index]
        passed=tuple(self.phase_actions)==phase.expected
        if phase.name=="missing_input_clears_progress":
            passed=passed and self.controller.reason=="stale" and self.controller.progress==0
        if phase.command=="pause":
            passed=passed and self.controller.paused and self.controller.progress==0
        if phase.command=="stop":
            passed=passed and self.controller.closed and self.controller.progress==0
        self.checks.append({"name":phase.name,"expected":list(phase.expected),"actual":list(self.phase_actions),"passed":passed})
        if not passed:
            raise RuntimeError("UI interaction acceptance failed: "+phase.name)

    def step(self, now):
        self.last_action=None
        if not math.isfinite(now) or now<self.now:
            raise ValueError("test monotonic clock regressed")
        self.now=now
        if self.done:return
        if self.index<0:self._enter(now)
        elif now-self.phase_started>=PHASES[self.index].duration_ms:
            self._finish();self._enter(now)
            if self.done:return
        phase=PHASES[self.index]
        if phase.status is None:
            self.controller.tick(now);self.no_input_ticks+=1
            return
        self.sequence+=1;self.samples+=1
        sample=GazeSample(self.context,"synthetic-ui-test-only",self.sequence,now,phase.status,phase.point)
        action=self.controller.feed(sample,now)
        if action:
            self.last_action=action
            item=asdict(action);item["phase"]=phase.name
            self.actions.append(item);self.phase_actions.append(action.key)
            self.feedback_key=action.key;self.feedback_at=now

    def result(self):
        return {"input":"synthetic_only", "real_gaze_validated":False,
                "camera_enabled":False,"audio_enabled":False,"test_calibration_is_real":False,
                "scenario_completed":self.done,"phase_checks":self.checks,"actions":self.actions,
                "commands":self.commands,"samples":self.samples,"missing_input_ticks":self.no_input_ticks}


def run_on_board(session,renderer,output,now=time.monotonic,sleep=time.sleep,event_link=None):
    scenario=InteractionTest()
    start=now();intervals=[];draw_ms=[];previous=start;snapshots={}
    try:
        while not scenario.done:
            loop=now()
            if loop-start>sum(p.duration_ms for p in PHASES)/1000+15:
                raise RuntimeError("UI test exceeded bounded runtime")
            scenario.step((loop-start)*1000)
            if event_link is not None:
                from .event_link import service_controller
                service_controller(event_link,scenario.controller,(loop-start)*1000,scenario.last_action)
            if scenario.done:break
            frame=renderer.rgb565(scenario.controller,scenario.feedback)
            draw_ms.append((now()-loop)*1000)
            session.present(frame)
            finished=now();intervals.append((finished-previous)*1000);previous=finished
            control=scenario.controller
            key = ("dwell" if control.progress>=.5 else "paused" if control.paused
                   else "interrupted" if control.reason=="stale" else "more" if control.page=="more"
                   else "selected" if scenario.feedback else None)
            if key and key not in snapshots:snapshots[key]=frame
            sleep(max(0,.05-(now()-loop)))
        elapsed=now()-start
        result=scenario.result()
        result.update(elapsed_seconds=elapsed,displayed_frames=session.present_count,
                      display_update_fps=session.present_count/elapsed,
                      p95_update_interval_ms=float(np.percentile(intervals,95)),
                      max_update_interval_ms=max(intervals),p95_draw_ms=float(np.percentile(draw_ms,95)),
                      assertion_scope="expected action sequence per phase; hardware-confirmed display slots; no real gaze or audio")
        for name,raw in snapshots.items():
            image=unpack_rgb565(np.frombuffer(raw,dtype="<u2").reshape(480,640))
            Image.fromarray(image,mode="RGB").save(output/("ui_"+name+".png"))
        return result
    finally:
        # Preserve incomplete trace as well; never treat it as a passing run.
        if event_link is not None:
            event_link.abort((now()-start)*1000,"test_exit")
            (output/"event_trace.json").write_text(json.dumps(event_link.snapshot(),indent=2)+"\n",encoding="utf-8")
        (output/"interaction_trace.json").write_text(json.dumps(scenario.result(),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
