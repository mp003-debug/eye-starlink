"""Experimental real camera regions -> dwell, with explicit optional local speech.

The pack remains disabled outside this evidence-gated trial. UART is opt-in and records receiver mode separately from real input.
This is not a production calibration or PCCR implementation.
"""
from dataclasses import asdict
from pathlib import Path
import hashlib,json,time,uuid
import numpy as np
from PIL import Image
from .appearance_diagnostic import AppearanceDiagnostic,StableCandidate,DiagnosticRecording,CHECK_TARGETS
from .calibration import Context
from .interaction import DwellController,GazeSample
from .controls import HelperButtons,apply_command
from .fixation import POINTS
from .trial_limits import EventHistory,validate_trial_duration
from .usage_guidance import UsageGuidance


def positive_entry(report):
    if report.get('completed') is not True or report.get('actions_enabled') is not False:
        raise ValueError('completed_candidate_evidence_required')
    spans={}
    for key in POINTS:
        rows=[r for r in report['frames'] if r.get('scored') and r['instructed_target']==key]
        if len(rows)<5:raise ValueError('insufficient_positive_evidence:'+key)
        if any(r['candidate'] not in (None,key) or r['stable_candidate'] not in (None,key) for r in rows):
            raise ValueError('wrong_positive_evidence:'+key)
        start=previous=None;longest=0.;matches=0
        for row in rows:
            t=row['copied_monotonic']
            if row['stable_candidate']==key:
                matches+=1
                if start is None or previous is None or t-previous>.25:start=t
                longest=max(longest,t-start);previous=t
            else:start=previous=None
        if matches/len(rows)<.6 or longest<1:raise ValueError('discontinuous_positive_evidence:'+key)
        spans[key]=longest
    return spans


def load_verified_setup_seed(engine,evidence,seed_pack=None):
    """A prior positive run supplies position only, never new-code acceptance."""
    p=Path(evidence)/'diagnostic.json';raw=p.read_bytes();report=json.loads(raw)
    old_hash=report.get('model_pack_sha256')
    if old_hash!=engine.pack_sha256:
        if seed_pack is None:raise ValueError('setup_seed_model_mismatch')
        old=AppearanceDiagnostic(seed_pack)
        if old.pack_sha256!=old_hash:raise ValueError('setup_seed_model_mismatch')
        # Position can survive a feature-only model revision only when the
        # original image and both same-eye landmark definitions are identical.
        if (not np.array_equal(old.reference,engine.reference) or old.box!=engine.box
                or not np.array_equal(old.anchor.corners,engine.anchor.corners)):
            raise ValueError('setup_seed_geometry_mismatch')
    positive_entry(report)
    seed_previous_eye(engine,report)
    engine.relocation['seed_evidence_sha256']=hashlib.sha256(raw).hexdigest()
    engine.relocation['seed_model_pack_sha256']=old_hash
    engine.relocation['seed_scope']='Position initializer only; all results from current code require a fresh check.'


def seed_previous_eye(engine,report):
    """Use the verified same-eye neighborhood as a bounded setup search seed.

    Current images still pass the unchanged skin/corner/geometry gates, followed
    by five new center samples. No old appearance offset or class output is reused.
    A moved eye outside this window fails closed rather than choosing a new eye.
    """
    old=report.get('reference_relocation') or {}
    shift=np.asarray(old.get('origin_shift'),dtype=np.float32)
    score,margin=old.get('score',0),old.get('margin',0)
    if 'score' not in old and 'seed_evidence_sha256' in old:
        # A seeded fresh check retains the original identity-search scores.
        # They are provenance of the position seed, not current classification confidence.
        digest=old['seed_evidence_sha256']
        if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('verified_seed_provenance_required')
        positive_entry(report)
        score,margin=old.get('previous_score',0),old.get('previous_margin',0)
    if (shift.shape!=(2,) or not np.isfinite(shift).all() or score<.90
            or margin<.04 or (report.get('center_reference') or {}).get('ready') is not True):
        raise ValueError('verified_same_eye_seed_required')
    engine.anchor.origin_shift=shift.copy()
    engine.relocation=dict(origin_shift=shift.tolist(),scope='previous verified same-eye neighborhood; bounded local matching and NEW center reference required',
                           previous_score=score,previous_margin=margin)


def freeze_current_neighborhood(engine,rows):
    """Center the unchanged motion budget on this session's verified eye.

    The previous session supplies only the startup search seed. Five fresh,
    accepted center captures establish this session's frozen search origin;
    no targets, inferred gaze, interaction frames or new templates participate.
    """
    if (engine.baseline.summary or {}).get('ready') is not True:
        raise ValueError('current_center_reference_required')
    accepted=[row for row in rows if row.get('reference_sample') is True]
    ids=[row.get('frame_index') for row in accepted]
    if len(ids)!=5 or len(set(ids))!=5 or set(ids)!=engine.baseline.ids:
        raise ValueError('five_current_alignment_samples_required')
    points=np.asarray([row.get('translation') for row in accepted],dtype=np.float64)
    old=engine.anchor.origin_shift.copy()
    radius=.35*(engine.anchor.box[2]-engine.anchor.box[0])
    if (points.shape!=(5,2) or not np.isfinite(points).all()
            or np.any(np.linalg.norm(points-old,axis=1)>radius)):
        raise ValueError('current_alignment_outside_verified_neighborhood')
    center=np.median(points,axis=0)
    if np.any(np.linalg.norm(points-center,axis=1)>radius):
        raise ValueError('inconsistent_current_neighborhood')
    engine.anchor.origin_shift=center.copy()
    record=dict(previous_seed=old.tolist(),current_origin=center.tolist(),
                radius_pixels=radius,frame_ids=ids,scope='frozen after current center setup; matching gates and templates unchanged')
    engine.relocation['current_setup_neighborhood']=record
    return record


class TrialReference(DiagnosticRecording):
    """Five valid new samples, with bounded retries for blinks during setup."""
    def __init__(self,engine,clock=time.monotonic):
        super().__init__(engine,CHECK_TARGETS[:1],clock)
        self.next_attempt=2.;self.attempts=0;self.reacquire_attempts=0
    def observe(self,pixels,index,requested,copied,presented,step):
        if step!=0 or index<=self.last_index or requested<presented or copied<requested:
            raise ValueError('fresh_reference_capture_required')
        if self.last_time is not None and copied<=self.last_time:raise ValueError('reference_time_not_increasing')
        self.last_index,self.last_time=index,copied;self.frames+=1
        age=copied-presented
        eligible=(requested-presented>=self.next_attempt and age<10. and self.attempts<12 and len(self.engine.baseline.samples)<5)
        if eligible:
            self.next_attempt=age+.6;self.attempts+=1
        started=self.clock()
        result=self.engine.observe_reference(pixels,index,copied,eligible,self.clock)
        # A historical position can become stale after the camera is re-aimed.
        # Only before the FIRST accepted current reference, try the existing
        # strict whole-frame identity acquisition. Never carry a baseline across
        # relocation, lower match thresholds, or reacquire during interaction.
        retry_reasons={'neighborhood_not_matched','motion_envelope',
                       'corner_not_matched','corner_search_outside',
                       'eye_crop_outside_frame','corner_pair_not_matched','corner_pair_ambiguous'}
        if (eligible and not self.engine.baseline.samples and self.reacquire_attempts<3
                and result.get('rejection') in retry_reasons
                and (self.engine.relocation or {}).get('previous_score') is not None):
            self.reacquire_attempts+=1
            previous_shift=self.engine.anchor.origin_shift.copy()
            previous_relocation=self.engine.relocation
            try:
                # Reacquire only the search position here. Reference extraction
                # waits for the NEXT capture, so StableCandidate sees each index
                # once and the reacquisition frame is never a reference sample.
                self.engine.relocation=self.engine.anchor.acquire(pixels)
                self.engine.relocation['previous_setup_seed']=previous_shift.tolist()
                self.engine.relocation['setup_reacquired_before_first_reference']=True
                result['setup_reacquisition_deferred_to_next_frame']=True
            except (ValueError,self.engine.cv.error) as exc:
                self.engine.anchor.origin_shift=previous_shift
                self.engine.relocation=previous_relocation
                result['setup_reacquisition_rejection']=str(exc)
            result['setup_reacquisition_attempt']=self.reacquire_attempts
            now=self.clock();result['processing_ms']=(now-started)*1000
            result['copy_to_result_ms']=(now-copied)*1000
        result.update(frame_index=index,copied_monotonic=copied,step=0,instructed_target='center',
                      after_present_s=age,scored=False,phase='session_reference')
        self.rows.append(result)
        if eligible:
            self.samples.append((dict(step=0,target='center',target_normalized=list(POINTS['center']),visit='session_reference',
                 frame_index=index,slot=self.attempts-1,requested_after_present_s=requested-presented,
                 copied_after_present_s=age,target_present_confirmed_monotonic=presented,copied_monotonic=copied,
                 label_source='instructed_center_not_measured_gaze',reference_sample=result['reference_sample']),pixels.copy()))
    def save(self,output,completed):
        result=super().save(output,completed)
        p=Path(output)/'targets/manifest.json';m=json.loads(p.read_text())
        policy=dict(target_seconds=None,setup_minimum_seconds=6.,setup_maximum_seconds=10.,
                    valid_reference_samples_required=5,maximum_reference_attempts=12,sample_period=.6)
        m.update(policy);p.write_text(json.dumps(m,indent=2)+'\n');result.update(policy)
        return result


class VisualTrial:
    MAX_ROWS=1800
    MAX_AUDIT=1200
    def __init__(self,pack,evidence,root):
        self.reference_inputs=(pack,evidence,root)
        self.reference_history=[]
        self.setup_attempts=0
        self.engine=AppearanceDiagnostic(pack)
        if self.engine.metadata.get('strict_training_passed') is not True:
            raise ValueError('strict_fit_required')
        evidence=Path(evidence);manifest=json.loads((evidence/'runtime_manifest.json').read_text())
        classifier_files=['src/eye_tracker/appearance.py','src/eye_tracker/appearance_diagnostic.py']
        if self.engine.metadata.get('corner_search_mode')=='paired_corners_v1':
            classifier_files.append('src/eye_tracker/corner_pair.py')
        for name in classifier_files:
            if hashlib.sha256((Path(root)/name).read_bytes()).hexdigest()!=manifest['runtime_files'].get(name):
                raise ValueError('classifier_changed_after_positive_evidence')
        data=(evidence/'diagnostic.json').read_bytes();report=json.loads(data)
        model_file=manifest.get('model_file','data/private/diagnostic/model.npz')
        if report['model_pack_sha256']!=self.engine.pack_sha256 or manifest['runtime_files'].get(model_file)!=self.engine.pack_sha256:
            raise ValueError('model_changed_after_positive_evidence')
        self.entry_spans=positive_entry(report);self.evidence_sha256=hashlib.sha256(data).hexdigest()
        seed_previous_eye(self.engine,report)
        self.controller=DwellController(Context(uuid.uuid4().hex,self.engine.geometry_id,'live'))
        self.token='visual-trial-only:'+self.engine.pack_sha256[:16]
        self.reference=TrialReference(self.engine)
        self.rows=[];self.audit=[];self.selections=[];self.commands=[];self.summary={}
        self.audio_enabled=False;self.last_action=None;self.uart_enabled=False
        self.telemetry=None
    def configure_long_run(self):
        if self.rows or self.audit or self.selections or self.commands:
            raise ValueError('long_run_must_be_configured_before_observation')
        from .trial_telemetry import BoundedTrialTelemetry
        self.telemetry=BoundedTrialTelemetry()
        self.rows,self.audit=self.telemetry.rows,self.telemetry.audit
        self.selections=EventHistory();self.commands=EventHistory()
    def event_total(self, name):
        items=getattr(self,name)
        return items.total if isinstance(items,EventHistory) else len(items)
    def begin_visual(self):
        if self.engine.baseline.finish().get('ready') is not True:raise ValueError('current_center_reference_required')
        if 'current_neighborhood' in self.summary:raise ValueError('current_neighborhood_already_frozen')
        self.summary['current_neighborhood']=freeze_current_neighborhood(self.engine,self.reference.rows)
        self.controller.calibration_id=self.token
    def reset_reference(self):
        """Explicit helper retry only. Reload the frozen model and verified seed."""
        self.controller.invalidate_calibration()
        if len(self.reference_history)>=3:raise ValueError('reference_retry_limit')
        fresh=VisualTrial(*self.reference_inputs)
        fresh.controller.music_enabled=self.controller.music_enabled
        fresh.controller.quick_phrases=self.controller.quick_phrases
        fresh.controller.emotion_cards=self.controller.emotion_cards
        fresh.controller.daily_tools=self.controller.daily_tools
        if fresh.controller.daily_tools is not None:fresh.controller.daily_tools.reset_navigation()
        fresh.controller.music_track_index=getattr(self.controller,'music_track_index',0)
        self.reference_history.append(self.reference)
        self.engine,self.reference,self.controller=fresh.engine,fresh.reference,fresh.controller
        self.token=fresh.token+':'+uuid.uuid4().hex
        self.last_action=None
        self.summary.pop('current_neighborhood',None)
    def command(self,name,now):
        apply_command(self.controller,name,now*1000)
        self.engine.gate=StableCandidate()
        self.commands.append(dict(command=name,time=now,progress=self.controller.progress,paused=self.controller.paused,closed=self.controller.closed))
    def feed(self,observation,index,copied,now):
        key=observation.get('stable_candidate')
        # A stale/invalid current frame can never borrow the last stable result.
        if key!=observation.get('candidate') or key not in POINTS:key=None
        point=None
        if key is not None:
            # The points are discrete UI region anchors, NOT estimated gaze pixels.
            point=POINTS[key] if self.controller.page!='more' else POINTS['center'] if key=='center' else (.05,.10)
        action=self.controller.feed(GazeSample(self.controller.context,self.token,index,copied*1000,
                                   'valid' if point is not None else 'unknown',point),now*1000)
        if action:
            event=dict(asdict(action),kind='local_speech_trial' if getattr(self,'audio_enabled',False) else 'visual_only',frame_index=index)
            tools=self.controller.daily_tools
            if tools is not None and (action.key.startswith('tool_slot_') or action.key=='help' and self.controller.page=='local_tools'):
                event['local_action']=dict(tools.last_event)
            self.selections.append(event)
        return action
    def observe(self,pixels,index,copied,clock=time.monotonic,allow_selection=True):
        telemetry=getattr(self,'telemetry',None)
        if telemetry is None and (len(self.rows)>=self.MAX_ROWS or len(self.audit)>=self.MAX_AUDIT):raise ValueError('visual_trial_recording_full')
        observation=self.engine.observe(pixels,index,copied,clock)
        now=clock();action=None
        if allow_selection:action=self.feed(observation,index,copied,now)
        else:
            # Keep acquisition/audit running while preserving held-target locks.
            self.controller.tick(now*1000);self.controller.reason='speaking'
        self.last_action=action
        row=dict(observation,frame_index=index,copied_monotonic=copied,evaluated_monotonic=now,
                 reference_epoch=len(getattr(self,'reference_history',[])),
                 page=self.controller.page,progress=self.controller.progress,target=self.controller.target_key,
                 reason=self.controller.reason,visual_selection=action.key if action else None,
                 audio_enabled=getattr(self,'audio_enabled',False),uart_enabled=getattr(self,'uart_enabled',False))
        if self.controller.daily_tools is not None:
            tools=self.controller.daily_tools
            row['local_state']=tools.state if self.controller.page=='local_tools' else None
            if action and (action.key.startswith('tool_slot_') or action.key=='help' and self.controller.page=='local_tools'):
                row['local_action']=tools.last_event
        if telemetry is not None:telemetry.observe(pixels,row,action)
        else:self.rows.append(row);self.audit.append((index,pixels[::2,::2].copy()))
        return row
    def save(self,output,completed):
        output=Path(output);result=self.reference.save(output,completed)
        history=getattr(self,'reference_history',[])
        for index,reference in enumerate(history):
            folder=output/'reference_attempts'/str(index)
            folder.mkdir(parents=True,exist_ok=False)
            reference.save(folder,False)
        if history:result['previous_reference_attempts']=len(history)
        dest=output/'interaction';dest.mkdir(exist_ok=False);images=[]
        for index,pixels in self.audit:
            name='frame_%06d.png'%index;p=dest/name;Image.fromarray(pixels).save(p)
            images.append(dict(frame_index=index,png=name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
        telemetry=getattr(self,'telemetry',None)
        if telemetry is not None:
            self.summary['telemetry']=telemetry.summary()
            self.summary['event_retention']={name:getattr(self,name).summary() for name in ('selections','commands')}
        report=dict(self.summary,completed=bool(completed),scope='Real camera input, experimental four-region dwell; optional explicit local speech. Not production calibration or PCCR. UART only when explicitly enabled; see communication record.',
                    model_pack_sha256=self.engine.pack_sha256,entry_evidence_sha256=self.evidence_sha256,
                    entry_spans=self.entry_spans,reference=self.engine.baseline.summary,
                    model_enabled=self.engine.model.enabled,commands=self.commands,visual_selections=self.selections,
                    source='live_camera',audio_enabled=getattr(self,'audio_enabled',False),uart_enabled=getattr(self,'uart_enabled',False),rows=list(self.rows),images=images)
        if telemetry is not None:report['sampled_frame_annotations']=list(telemetry.audit_metadata)
        (output/'visual_trial.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        result.update(interaction_frames=telemetry.summary()['total_frames'] if telemetry is not None else len(self.rows),visual_selections=self.event_total('selections'),audio_enabled=getattr(self,'audio_enabled',False),uart_enabled=getattr(self,'uart_enabled',False))
        return result


def run_visual_trial(session,renderer,trial,mmio,seconds,clock=time.monotonic,sleep=time.sleep,challenges=None,bank=None,auto_controls=False,event_link=None,music_library=None,quick_phrases=False,reposition_assist=False,emotion_cards=False,daily_tools=None,demo_window=False):
    from .emotions import validate_options
    validate_options(emotion_cards,music_library is not None,quick_phrases,event_link is not None)
    from .daily_tools import validate_options as validate_daily
    validate_daily(daily_tools is not None,music_library is not None,quick_phrases,emotion_cards,event_link is not None)
    trial.controller.daily_tools=daily_tools
    trial.summary["daily_tools_enabled"]=daily_tools is not None
    trial.summary['local_video_enabled']=daily_tools is not None and daily_tools.video_library is not None
    if reposition_assist and (challenges is not None or auto_controls):
        raise ValueError('reposition assist requires real control without scripted challenges')
    from .audio import AudioDevice,AudioGpio,CodecBus,Codec,AudioError
    from .trial_speech import TrialSpeech,AutomaticTrialControls
    from .trial_events import TrialEvents
    wireless=TrialEvents(event_link,trial.controller) if event_link is not None else None
    trial.uart_enabled=wireless is not None
    trial.summary['music_enabled']=music_library is not None
    trial.summary['quick_phrases_enabled']=bool(quick_phrases)
    trial.summary['emotion_cards_enabled']=bool(emotion_cards)
    trial.controller.emotion_cards=bool(emotion_cards)
    trial.summary['reposition_assist']=bool(reposition_assist)
    long_run=getattr(trial,'telemetry',None) is not None
    validate_trial_duration(seconds,long_run,demo_window)
    trial.summary['demo_window']=bool(demo_window)
    if long_run and (challenges is not None or auto_controls):raise ValueError('long_run_no_scripted_challenges_or_controls')
    if auto_controls and bank is None:raise ValueError('automatic_trial_controls_require_explicit_audio')
    if music_library is not None and (bank is None or auto_controls or challenges):
        raise ValueError('music requires audible eye control without scripted helpers')
    if quick_phrases:
        from .phrases import QUICK_KEYS, PHRASE_TEXT
        if (bank is None or auto_controls or challenges or
                any(key not in bank.samples or bank.text.get(key)!=PHRASE_TEXT[key] for key in QUICK_KEYS)):
            raise ValueError('quick phrases require checked speech bank and no scripted helpers')
        trial.controller.quick_phrases=True
    if challenges is not None:
        from .trial_challenges import DURATION
        if seconds!=DURATION:raise ValueError('challenge_duration_mismatch')
    device=AudioDevice(mmio,clock);device.stop()
    if quick_phrases:
        from .phrase_audio import PhraseAudioDevice
        from .music import StreamAudioDevice
        device=PhraseAudioDevice(device,StreamAudioDevice(mmio),clock)
    music=None
    if music_library is not None:
        from .music import MusicPlayer,StreamAudioDevice
        music=MusicPlayer(StreamAudioDevice(mmio),music_library,clock)
        trial.controller.music_enabled=True
        trial.controller.music_track_index=0 if music_library.tracks else -1
        trial.summary['music_actions']=EventHistory()
        trial.summary['music_volume_initial']=music.volume.level
        trial.summary['music_volume_policy']='Music-only PCM attenuation, persisted 20..100%; speech and codec gain unchanged.'
    video=None
    if trial.summary['local_video_enabled']:
        from .video import VideoPlayer
        video=VideoPlayer(daily_tools.video_library,StreamAudioDevice(mmio),clock)
        daily_tools.video_player=video
        trial.summary['video_actions']=EventHistory()
    books=None
    trial.summary['pastimes_enabled']=bool(daily_tools is not None and daily_tools.pastimes)
    if trial.summary['pastimes_enabled']:
        from .audiobook import AudioBookPlayer
        books=AudioBookPlayer(StreamAudioDevice(mmio),daily_tools.audiobook_library,daily_tools.bookmarks,clock)
        daily_tools.book_player=books;trial.summary['book_actions']=EventHistory()
    codec=Codec(CodecBus(AudioGpio(mmio))) if bank is not None else None
    speech=TrialSpeech(device,bank,trial.controller,clock,bounded=long_run) if bank is not None else None
    ai=getattr(daily_tools,'ai',None)
    if ai is not None:
        if bank is None or music is None:raise ValueError('AI speech requires checked audible streaming')
        ai.bind_audio(StreamAudioDevice(mmio))
    trial.summary['ai_writing_enabled']=ai is not None
    automation=AutomaticTrialControls() if auto_controls else None
    trial.summary['automatic_helper_test']=bool(auto_controls)
    trial.audio_enabled=bank is not None
    trial.summary['speech_events']=speech.events if speech else []
    trial.summary['speech_policy']='No queued dwell; committed utterance survives blinking, explicit helper commands stop it; interrupted phrases never resume.'
    failed=False;result=None;reposition_requested=False
    buttons=HelperButtons();guidance=UsageGuidance();setup_complete=False
    trial.summary['usage_guidance']='Display only; matching, fresh reference, dwell and action gates unchanged.'
    started=clock();buttons.update(int(mmio.read(0x20))&15,started*1000)
    atlas=getattr(getattr(renderer,'daily_renderer',None),'atlas',None)
    previous_service=getattr(atlas,'service',None)
    def service_wireless():
        if wireless:wireless.update(clock()*1000)
    def controls():
        nonlocal reposition_requested
        command=buttons.update(int(mmio.read(0x20))&15,clock()*1000)
        source='physical_button'
        if command and automation:automation.stage='aborted'
        if not command and automation:
            command=automation.update(speech,clock());source='automatic_test'
        if command:
            if wireless:wireless.suspend(clock()*1000,'helper_'+command)
            trial.last_action=None
            if ai is not None:ai.cancel()
            if books:
                daily_tools.book_command=None;books.suspend()
            if video:
                daily_tools.video_command=None
                if command in ('stop','invalidate_calibration'):video.stop()
                else:video.suspend()
            if music:
                if command in ('stop','invalidate_calibration'):music.stop()
                else:music.suspend()
            if speech:speech.interrupt(command)
            trial.command(command,clock())
            if reposition_assist and command=='invalidate_calibration':reposition_requested=True
            if wireless and not reposition_requested:
                wireless.resume(trial.controller,clock()*1000)
                service_wireless()
            trial.commands[-1]['audio_busy_after']=bool(device.status()&1)
            trial.commands[-1]['source']=source
        return command
    try:
        if wireless:
            wireless.suspend(clock()*1000)
            if atlas is not None:atlas.service=service_wireless
        if codec:trial.summary['codec']=codec.configure_muted()
        before=session.wait_native_frames(2)
        if reposition_assist:
            from .reposition import assisted_reference
            if not assisted_reference(session,renderer,trial,mmio,buttons,clock,clock()+60.):
                raise ValueError('assisted_reference_not_completed')
            if speech:speech.controller=trial.controller
        else:
            count=len(trial.engine.baseline.samples)
            session.present(renderer.setup_frame(count));shown=clock()
            while clock()-shown<10. and (clock()-shown<6. or len(trial.engine.baseline.samples)<5):
                if controls():raise ValueError('setup_interrupted_by_helper')
                pixels=session.capture_once();info=session.last_capture
                trial.reference.observe(pixels,session.capture_index,info['requested_at_monotonic'],info['copied_at_monotonic'],shown,0)
                new_count=len(trial.engine.baseline.samples)
                if new_count!=count:
                    count=new_count
                    session.present(renderer.setup_frame(count))
            trial.begin_visual()
        setup_complete=True
        if wireless:wireless.resume(trial.controller,clock()*1000)
        if codec:codec.enable_output()
        if music:music.sync_display(trial.controller)
        frame=renderer.rgb565(trial.controller,guidance.feedback(trial.controller,None,clock()))
        if challenges is not None:frame=challenges.decorate(frame,0)
        session.present(frame);interactive=clock()
        if challenges is not None:challenges.presented(0,interactive)
        while clock()-interactive<seconds and not trial.controller.closed:
            if reposition_requested:
                # Same DMA owner throughout. No model adaptation or overlay reload.
                if wireless:wireless.suspend(clock()*1000,'reposition')
                trial.last_action=None
                if codec:codec.mute()
                if trial.setup_attempts<4:trial.reset_reference()
                if speech:speech.controller=trial.controller
                if not assisted_reference(session,renderer,trial,mmio,buttons,clock,min(interactive+seconds,clock()+60.)):
                    raise ValueError('assisted_reference_not_completed')
                if speech:speech.controller=trial.controller
                if wireless:wireless.resume(trial.controller,clock()*1000)
                guidance=UsageGuidance();reposition_requested=False
                if codec:codec.enable_output()
                if music:music.sync_display(trial.controller)
                session.present(renderer.rgb565(trial.controller,'guide_ready'))
                service_wireless()
                continue
            controls()
            if trial.controller.closed:break
            if reposition_requested:continue
            service_wireless()
            if music:music.poll()
            service_wireless()
            if video:video.poll()
            service_wireless()
            if books:books.poll()
            if ai is not None:
                ai.poll_controller(trial.controller,daily_tools)
            controls()
            if wireless:wireless.update(clock()*1000)
            if trial.controller.closed:break
            if reposition_requested:continue
            pixels=session.capture_once();info=session.last_capture
            controls() # a helper command during capture takes priority
            if trial.controller.closed:break
            if reposition_requested:continue
            if speech:speech.poll()
            if music:music.poll()
            row=trial.observe(pixels,session.capture_index,info['copied_at_monotonic'],clock,
                              allow_selection=speech is None or speech.active is None)
            command=controls() if wireless else None
            if wireless:
                wireless.update(clock()*1000,trial.last_action if not command else None,session.capture_index)
            if speech:
                # Also prioritize a button pressed during feature processing.
                command=command or controls()
                if books:
                    pending_book=daily_tools.book_command;daily_tools.book_command=None
                    if not command and trial.last_action is not None:
                        action=trial.last_action
                        if action.phrase or action.key.startswith('music_') or daily_tools.video_command:
                            books.suspend()
                        elif pending_book:
                            if music:music.stop()
                            if video:video.stop()
                            books.action(pending_book)
                        trial.summary['book_actions'].append(dict(key=action.key,command=pending_book,
                            camera_frame_index=session.capture_index,**books.snapshot()))
                service_wireless()
                if video:
                    pending=daily_tools.video_command;daily_tools.video_command=None
                    if not command and trial.last_action is not None:
                        action=trial.last_action
                        if action.phrase:video.suspend()
                        elif pending:
                            music.stop()
                            video.action(pending)
                        elif action.key.startswith('music_'):video.stop()
                        trial.summary['video_actions'].append(dict(key=action.key,command=pending,
                            camera_frame_index=session.capture_index,**video.snapshot()))
                service_wireless()
                if music and not command and trial.last_action is not None:
                    action=trial.last_action
                    if action.phrase:music.suspend()
                    else:music.action(action.key)
                    trial.summary['music_actions'].append(dict(key=action.key,source=action.source,
                        source_time_ms=action.source_time_ms,frame_index=session.capture_index,
                        state=music.state,track_index=music.index,volume_level=music.volume.level))
                if ai is not None:
                    if command or (trial.last_action is not None and trial.last_action.phrase):ai.cancel()
                    elif ai.play_requested:
                        if books:books.suspend()
                        if video:video.suspend()
                        if music:music.suspend()
                        ai.dispatch(trial.last_action,clock()*1000)
                if not command:speech.start(trial.last_action,session.capture_index)
                row['speech_active']=speech.active
                row['post_observation_command']=command
            if challenges is not None:challenges.annotate(row,info['requested_at_monotonic'])
            trial.controller.tick(clock()*1000)
            if speech and speech.active:trial.controller.reason='speaking'
            feedback=guidance.feedback(trial.controller,row,clock())
            if emotion_cards and feedback in ('guide_ready','guide_waiting','guide_release','guide_menu'):
                if trial.controller.page=='emotion_display':feedback='emotion_display_hint'
                elif trial.controller.page in ('emotion_hub','emotion_mood','emotion_affection'):feedback='emotion_hint'
            if emotion_cards:
                row['emotion_card']=trial.controller.emotion_key
            if reposition_assist and feedback in ('guide_reposition','guide_unavailable_long','guide_appearance','guide_uncalibrated'):
                feedback='guide_reposition_assist'
            if music and trial.controller.page=='music' and feedback in ('guide_ready','guide_waiting','guide_release'):
                feedback=music.feedback()
            if music:
                music.sync_display(trial.controller)
                row.update(music_state=music.state,music_position_samples=music.offset,music_volume_level=music.volume.level)
                if trial.controller.page in ('music_hub','music_volume') and feedback in ('guide_ready','guide_waiting','guide_release'):
                    feedback='music_hub_hint' if trial.controller.page=='music_hub' else 'music_volume_hint'
            if video:row['video']=video.snapshot()
            if books:row['audiobook']=books.snapshot()
            if wireless and getattr(daily_tools,'sharing',None) is not None:
                label='使用菜单'
                if trial.controller.page=='emotion_display':label='展示心意'
                elif trial.controller.page=='local_tools':
                    if daily_tools.state.startswith('game'):label='玩游戏'
                    elif daily_tools.state in ('album','photo_view'):label='看相册'
                    elif daily_tools.state not in ('media','video','video_view','pastimes','book','book_options','book_chapters','share'):label='文字交流'
                if music and music.state=='playing':label='听音乐'
                if books and books.snapshot()['state']=='playing':label='听故事'
                if video and video.snapshot()['state']=='playing':label='看视频'
                wireless.activity(clock()*1000,label)
            if automation:feedback=automation.feedback(clock())
            if speech and speech.active:feedback='speaking_'+speech.active
            row['usage_feedback']=feedback
            service_wireless()
            frame=renderer.rgb565(trial.controller,feedback)
            service_wireless()
            if challenges is not None:
                step=challenges.due(clock()-interactive);frame=challenges.decorate(frame,step)
            session.present(frame)
            service_wireless()
            if challenges is not None:challenges.presented(step,clock())
        after=session.wait_native_frames(1)
        if any(after[k]!=before[k] for k in ('bad_lines','bad_frames')):raise RuntimeError('camera_error_during_visual_trial')
        trial.summary.update(elapsed_seconds=clock()-started,interaction_seconds=clock()-interactive,
                             diagnostic_before=before,diagnostic_after=after,exit_reason='BTN3' if trial.controller.closed else 'duration')
        result=dict(trial.summary,visual_selections=trial.event_total('selections'),audio_enabled=trial.audio_enabled,uart_enabled=trial.uart_enabled)
        return result
    except BaseException as exc:
        failed=True;trial.summary['error']=str(exc)
        # Only a clean reference rejection gets a final explanatory frame.
        # Do not attempt fresh display/AXI traffic after a hardware failure.
        if not setup_complete and isinstance(exc,ValueError) and str(exc)=='current_center_reference_required':
            try:session.present(renderer.setup_frame(len(trial.engine.baseline.samples),failed=True))
            except Exception as display_exc:
                trial.summary['setup_error_display_error']=str(display_exc)
        raise
    finally:
        if atlas is not None:atlas.service=previous_service
        if reposition_assist:
            trial.summary['reference_attempts_started']=trial.setup_attempts
            trial.summary['previous_reference_attempts']=len(trial.reference_history)
            history=trial.summary.get('reposition_events')
            if history is not None:trial.summary['reposition_event_retention']=history.summary()
        if challenges is not None:trial.summary['challenge_schedule']=challenges.report()
        errors=[]
        # Retire requests before decoder teardown or bookmark I/O can wait.
        if wireless:
            try:wireless.close(clock()*1000)
            except Exception as exc:errors.append('wireless cleanup: '+str(exc))
            trial.summary['communication']=wireless.snapshot()
        if ai is not None:
            try:ai.close()
            except Exception as exc:errors.append('AI cleanup: '+str(exc))
            trial.summary['ai_writing']=dict(ai.stats)
        if books:
            trial.summary['book_final']=books.snapshot()
            try:books.close()
            except Exception as exc:errors.append('audiobook cleanup: '+str(exc))
            trial.summary['bookmark_save_failed']=books.save_failed
        if video:
            trial.summary['video_final']=video.snapshot()
            try:video.close()
            except Exception as exc:errors.append('video cleanup: '+str(exc))
        if music:
            trial.summary['music_final']=dict(state=music.state,track_index=music.index,
                position_samples=music.offset,track_count=len(music.library.tracks),volume_level=music.volume.level,scope='local music only')
            try:music.stop()
            except Exception as exc:errors.append('music cleanup: '+str(exc))
        try:
            if speech:speech.interrupt('trial_exit')
            else:device.stop()
        except Exception as exc:errors.append(str(exc))
        if codec:
            try:codec.mute()
            except Exception as exc:errors.append(str(exc))
        try:trial.summary['audio_busy_on_exit']=bool(device.status()&1)
        except Exception as exc:
            errors.append(str(exc));trial.summary['audio_busy_on_exit']=True
        if trial.summary['audio_busy_on_exit']:errors.append('audio_not_stopped')
        trial.summary['audio_cleanup_errors']=errors
        trial.summary['output_muted_on_exit']=not errors and not codec.output_enabled if codec else None
        if long_run:
            trial.summary['telemetry']=trial.telemetry.summary()
            trial.summary['event_retention']={name:getattr(trial,name).summary() for name in ('selections','commands')}
            if speech:trial.summary['speech_event_retention']=speech.events.summary()
        if result is not None:result.update(trial.summary)
        if errors and not failed:raise AudioError('; '.join(errors))
