"""Board bring-up CLI. Default inspect is offline; live modes require --load.

Each live invocation downloads a fresh overlay. Never run alongside another
DMA/Notebook owner. A software polling deadline cannot interrupt a hung AXI read.
"""
import argparse
import json
import math
import platform
import signal
import sys
import time
from pathlib import Path
import numpy as np
from .framebuffer import DISPLAY, pack_rgb565, encode_frame, unpack_rgb565
from .hardware_contract import verify_artifacts, ADDRESSES, configure_overlay_clocks
from .board_io import VideoIO, UnsafeShutdown
from .sensor import OpenDrainI2C, MT9V034

ROOT = Path(__file__).resolve().parents[2]


def test_pattern():
    colors = np.array([[255,255,255],[255,255,0],[0,255,255],[0,255,0],
                       [255,0,255],[255,0,0],[0,0,255],[0,0,0]], dtype=np.uint8)
    rgb = np.tile(np.repeat(colors, 80, axis=0)[None, :, :], (480, 1, 1))
    # Borders and alternating single-pixel stripes reveal crop/scale errors.
    rgb[0, :] = 255
    rgb[-1, :] = 255
    rgb[:, 0] = 255
    rgb[:, -1] = 255
    rgb[400:440, 16:624] = ((np.arange(608) % 2) * 255)[None, :, None]
    return pack_rgb565(rgb).tobytes()


def hold_for_recovery(session, error):
    # Keep allocations and the exclusive lock alive after an unconfirmed halt.
    # Power-cycle recovery ends this process together with the unsafe DMA state.
    def explain(*_):
        print("DMA halt is unconfirmed. Buffers retained. Power-cycle the board; do not force-kill this process.", flush=True)
    for name in ("SIGINT", "SIGTERM", "SIGHUP"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), explain)
    print(str(error), file=sys.stderr, flush=True)
    explain()
    while True:
        time.sleep(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inspect", "display", "capture", "combined", "stream", "sensor", "preview", "ui-test", "audio-test", "control-test", "fixation", "eye-trial"), nargs="?", default="inspect")
    parser.add_argument("--load", action="store_true", help="download the verified overlay before live diagnostics")
    parser.add_argument("--frame", type=Path, help="exact 640x480 RGB565_LE file; default is an unlabelled diagnostic pattern")
    parser.add_argument("--seconds", type=float, default=10.0, help="capture/display duration; ui-test has a fixed acceptance sequence")
    parser.add_argument("--output", type=Path, default=ROOT / "data/private/bringup")
    parser.add_argument("--exposure-rows", type=int, help="temporary manual exposure, 1..480 sensor rows")
    parser.add_argument("--gain-units", type=int, help="temporary gain, 16..32; 16 is unity")
    parser.add_argument("--audible", action="store_true", help="enable low-level AUX output only for audio-test/control-test/eye-trial")
    parser.add_argument("--event-test", action="store_true", help="explicitly transmit SIMULATED events via Arduino UART; test receiver required")
    parser.add_argument("--eye-events", choices=("off","log","live"), default="off", help="eye-trial only: real choices to receiver log or LIVE hook; default off")
    parser.add_argument('--music',action='store_true',help='explicit local music page; audible eye-trial and audio IP v2 required')
    parser.add_argument('--quick-phrases',action='store_true',help='explicit response/care pages; audible eye-trial and audio IP v2 required')
    parser.add_argument('--reposition-assist',action='store_true',help='helper-confirmed live preview/center setup; cancels wireless requests before retry')
    parser.add_argument('--daily-tools',action='store_true',help='local album and grouped pinyin; requires music + quick phrases + emotion cards')
    parser.add_argument('--local-video',action='store_true',help='bounded local video; requires daily tools, default off')
    parser.add_argument('--receiver-sharing',action='store_true',help='version-gated explicit receiver content sharing')
    parser.add_argument('--pastimes',action='store_true',help='untimed games and local audiobooks; requires daily tools, default off')
    parser.add_argument('--ai-writing',action='store_true',help='local AI candidate and explicitly confirmed draft speech')
    parser.add_argument('--emotion-cards',action='store_true',help='local visual cards; requires music + quick phrases; card choices stay local')
    parser.add_argument("--record-preview", action="store_true", help="save bounded raw samples and per-frame brightness after clean preview shutdown")
    parser.add_argument("--locate-eye", action="store_true", help="eye-region setup preview only; no gaze or speech")
    parser.add_argument("--calibration-samples", action="store_true", help="fixation only: two fitting visits and separate checks, about96s; no actions")
    parser.add_argument("--appearance-check", type=Path, help="fixation only: candidate-only diagnostic pack; no actions")
    parser.add_argument("--invalid-input-check", action="store_true", help="candidate-only appearance challenges, no actions")
    parser.add_argument("--trial-model",type=Path,help="disabled strictly fitted pack for experimental eye-trial")
    parser.add_argument("--trial-evidence",type=Path,help="frozen positive diagnostic evidence for experimental eye-trial")
    parser.add_argument("--appearance-seed",type=Path,help="prior verified same-eye diagnostic position only; never classification acceptance")
    parser.add_argument("--appearance-seed-model",type=Path,help="original pack for verifying unchanged same-eye geometry after a feature-only revision")
    parser.add_argument("--trial-auto-controls",action="store_true",help="explicit audible eye-trial only: automatically cancel first live utterance, pause/resume second; no synthetic gaze")
    parser.add_argument("--trial-challenges",action="store_true",help="eye-trial only: prompted80s closed/cover/leave/blink check, muted")
    parser.add_argument("--fit-session",action="store_true",help="fixation --appearance-check only: collect and strictly fit fresh five-position candidate, disabled until independent check")
    parser.add_argument('--long-run',action='store_true',help='eye-trial only: bounded sampled audit and resource telemetry, at most1200s; not full per-frame evidence')
    parser.add_argument('--demo-window',action='store_true',help='explicit real-eye filming window up to3600s; requires --long-run')
    args = parser.parse_args()
    if args.demo_window and (args.mode!='eye-trial' or not args.long_run or args.trial_auto_controls or args.trial_challenges):
        parser.error('--demo-window requires real eye-trial with --long-run and no scripted controls')
    if args.reposition_assist and (args.mode!='eye-trial' or args.trial_auto_controls or args.trial_challenges):
        parser.error('--reposition-assist requires real eye-trial without scripted controls')
    from .emotions import validate_options
    try:validate_options(args.emotion_cards,args.music,args.quick_phrases,args.eye_events!='off')
    except ValueError as exc:parser.error(str(exc))
    if args.music and (args.mode!='eye-trial' or not args.audible or args.trial_auto_controls or args.trial_challenges):
        parser.error('--music requires audible eye-trial without scripted controls')
    if args.quick_phrases and (args.mode!='eye-trial' or not args.audible or args.trial_auto_controls or args.trial_challenges):
        parser.error('--quick-phrases requires audible eye-trial without scripted controls')
    from .daily_tools import DailyTools,validate_options as validate_daily
    try:validate_daily(args.daily_tools,args.music,args.quick_phrases,args.emotion_cards,args.eye_events!='off')
    except ValueError as exc:parser.error(str(exc))
    if args.local_video and not args.daily_tools:parser.error('--local-video requires daily tools')
    if args.pastimes and not args.daily_tools:parser.error('--pastimes requires daily tools')
    daily_tools=DailyTools.from_root(ROOT,local_video=args.local_video,pastimes=args.pastimes) if args.daily_tools else None
    if args.ai_writing:
        if args.mode!='eye-trial' or not args.daily_tools or not args.audible or args.trial_auto_controls or args.trial_challenges:
            parser.error('--ai-writing requires audible daily-tools eye-trial without scripted helpers')
        from .ai_bundle import AIBundle
        from .ai_writing import AIWriting
        daily_tools.ai=AIWriting(AIBundle(ROOT/'assets/ai'),args.output/'ai_work')
    music_library=None
    if args.music:
        from .music import MusicLibrary
        music_library=MusicLibrary(ROOT/'assets/music',volume_path=ROOT/'data/private/music_volume.json')
    if args.receiver_sharing and (not args.daily_tools or args.eye_events=='off' or args.event_test):
        parser.error('--receiver-sharing requires real daily tools and explicit eye-events')
    if args.receiver_sharing:
        from .sharing_ui import SharingUI
        daily_tools.sharing=SharingUI()
    if args.eye_events != "off" and (args.mode != "eye-trial" or args.event_test or args.trial_auto_controls or args.trial_challenges):
        parser.error("--eye-events requires real eye-trial without scripted helpers")
    if args.long_run and (args.mode!='eye-trial' or args.trial_auto_controls or args.trial_challenges):
        parser.error('--long-run requires eye-trial without scripted controls/challenges')
    if args.trial_auto_controls and (args.mode!="eye-trial" or not args.audible or args.trial_challenges):
        parser.error("--trial-auto-controls requires audible eye-trial without challenges")
    if args.fit_session and (args.mode!="fixation" or not args.appearance_check or args.invalid_input_check or args.calibration_samples or args.output.exists()):
        parser.error("--fit-session requires fixation --appearance-check and a fresh output; no challenge/check reuse")
    if args.trial_challenges and (args.mode!="eye-trial" or args.seconds!=80):
        parser.error("--trial-challenges requires eye-trial --seconds80")
    if args.appearance_seed_model and not args.appearance_seed:
        parser.error("--appearance-seed-model requires --appearance-seed")
    if args.appearance_seed and not (args.mode=="fixation" and args.appearance_check):
        parser.error("--appearance-seed requires fixation --appearance-check")
    if args.mode=="eye-trial":
        from .trial_limits import validate_trial_duration
        try:validate_trial_duration(args.seconds,args.long_run,args.demo_window)
        except ValueError as exc:parser.error(str(exc))
        if not args.trial_model or not args.trial_evidence or args.frame or args.output.exists():
            parser.error("eye-trial requires --trial-model/--trial-evidence and fresh --output")
    elif args.trial_model or args.trial_evidence:
        parser.error("trial options require eye-trial mode")
    if args.invalid_input_check and not args.appearance_check:
        parser.error("--invalid-input-check requires --appearance-check")
    if args.appearance_check and (args.mode != "fixation" or args.calibration_samples):
        parser.error("--appearance-check requires fixation without --calibration-samples")
    if args.calibration_samples and args.mode != "fixation":
        parser.error("--calibration-samples requires fixation mode")
    if args.locate_eye and (args.mode != "preview" or not args.record_preview):
        parser.error("--locate-eye requires preview --record-preview")
    if args.mode == "fixation" and (args.frame or args.seconds != 10.0 or (args.output/"targets").exists()):
        parser.error("fixation uses a fixed collection sequence and fresh targets directory; omit --frame/--seconds")
    if args.record_preview and args.mode != "preview":
        parser.error("--record-preview requires preview mode")
    if args.record_preview and (args.output / "recording").exists():
        parser.error("recording already exists; use a fresh output directory")
    if args.event_test and args.mode not in ("ui-test", "control-test"):
        parser.error("--event-test is restricted to ui-test/control-test")
    if args.audible and args.mode not in ("audio-test", "control-test", "eye-trial"):
        parser.error("--audible is restricted to audio-test/control-test/eye-trial")
    if (args.exposure_rows is None) != (args.gain_units is None):
        parser.error("manual exposure and gain must be provided together")
    if args.exposure_rows is not None:
        if args.mode not in ("capture", "combined", "stream", "preview") or not 1<=args.exposure_rows<=480 or not 16<=args.gain_units<=32:
            parser.error("manual settings require capture/combined/stream/preview, 1..480 rows and 16..32 gain units")
    if not math.isfinite(args.seconds) or not 0 < args.seconds <= (3600 if args.demo_window else 1200 if args.long_run else 120):
        parser.error("seconds exceed the explicitly selected bounded run policy")
    report = {"mode": args.mode, "live_attempted": False, "completed": False,
              "gaze_validated": False, "screen_visually_verified": False, "capture_saved_this_run": False,
              "contract": verify_artifacts(ROOT)}
    if args.music and report['contract'].get('audio_ip_version')!='0x00020000':
        parser.error('--music requires the matching recorded audio IP v2 build')
    if args.quick_phrases and report['contract'].get('audio_ip_version')!='0x00020000':
        parser.error('--quick-phrases requires the matching recorded audio IP v2 build')
    if args.mode == "inspect":
        if args.load:
            parser.error("inspect never downloads hardware")
        print(json.dumps(report, indent=2))
        return 0
    if not args.load:
        parser.error("live modes require --load and exclusive board ownership")
    if platform.system() != "Linux" or platform.machine() not in ("armv7l", "armv8l", "aarch64"):
        parser.error("live diagnostics must run on the PYNQ board")
    frame = args.frame.read_bytes() if args.frame else test_pattern()
    if len(frame) != DISPLAY.size_bytes:
        parser.error("frame must contain exactly 614400 RGB565_LE bytes")
    recording = None
    if args.record_preview:
        from .preview_recording import PreviewRecording
        recording = PreviewRecording(args.seconds)
    fixation_recording = None
    trial = None
    eye_locator = None
    renderer = None
    if args.mode == "preview":
        if args.frame:
            parser.error("preview builds its own camera view; --frame is not used")
        from .preview import PreviewRenderer
        if args.locate_eye:
            from .eye_region import EyeRegionLocator
            eye_locator = EyeRegionLocator()  # validate dependency/model before loading hardware
            renderer = PreviewRenderer(ROOT / "assets/eye_region_template.png")
            renderer.set_region({"state":"searching","crop":None})
        else:
            renderer = PreviewRenderer()  # validate asset before loading hardware
        frame = encode_frame(np.asarray(renderer.base, dtype=np.uint8))
    if args.mode == "fixation":
        from .fixation import FixationRenderer, FixationRecording, run_fixation, TARGETS, APPEARANCE_TARGETS
        plan = APPEARANCE_TARGETS if args.calibration_samples else TARGETS
        if args.appearance_check:
            from .appearance_diagnostic import AppearanceDiagnostic,DiagnosticRecording,CHECK_TARGETS
            if args.invalid_input_check:
                from .invalid_input_diagnostic import InvalidInputRenderer,InvalidInputRecording,run_invalid_input
                renderer=InvalidInputRenderer();plan=renderer.plan
                fixation_recording=InvalidInputRecording(AppearanceDiagnostic(args.appearance_check))
                run_fixation=run_invalid_input
            else:
                plan=CHECK_TARGETS
                if args.fit_session:
                    from .session_calibration import FIT_TARGETS
                    plan=FIT_TARGETS
                fixation_recording=DiagnosticRecording(AppearanceDiagnostic(args.appearance_check),plan)
            if args.appearance_seed:
                from .appearance_trial import load_verified_setup_seed
                load_verified_setup_seed(fixation_recording.engine,args.appearance_seed,args.appearance_seed_model)
        else:
            fixation_recording = FixationRecording(plan)
        if renderer is None:renderer = FixationRenderer(plan)
        frame = renderer.frame()
    if args.mode == "eye-trial":
        from .appearance_trial import VisualTrial,run_visual_trial
        from .ui import BoardRenderer
        from .fixation import FixationRenderer
        from .appearance_diagnostic import CHECK_TARGETS
        trial=VisualTrial(args.trial_model,args.trial_evidence,ROOT)
        if args.long_run:trial.configure_long_run()
        from .trial_challenges import TrialChallenges
        challenge_schedule=TrialChallenges() if args.trial_challenges else None
        renderer=BoardRenderer()
        if music_library is not None:renderer.bind_music(music_library)
        if daily_tools is not None:renderer.bind_daily_tools(daily_tools)
        frame=renderer.setup_frame(0)
    if args.mode == "ui-test":
        if args.seconds != 10.0:
            parser.error("ui-test has a fixed acceptance sequence; omit --seconds")
        if args.frame:
            parser.error("ui-test renders its own state; --frame is not used")
        from .ui import BoardRenderer
        from .ui_test import InteractionTest, run_on_board
        renderer = BoardRenderer()  # load and validate portable assets before MMIO
        frame = renderer.rgb565(InteractionTest().controller)
    bank = None
    if args.mode == "eye-trial" and args.audible:
        from .audio import PhraseBank
        bank = PhraseBank(include_quick=args.quick_phrases)
    if args.mode in ("audio-test", "control-test"):
        if args.frame:parser.error("auxiliary tests render their own UI")
        from .ui import BoardRenderer
        from .auxiliary import test_controller, run_audio_test, run_control_test
        from .audio import PhraseBank
        renderer = BoardRenderer()
        if args.mode == "audio-test" or args.audible:bank = PhraseBank()
        frame = renderer.rgb565(test_controller(), "speech_controls" if args.audible else "audio_test" if bank else "controls")
    args.output.mkdir(parents=True, exist_ok=True)
    if trial is not None:
        import hashlib
        runtime_files={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in sorted((ROOT/'src/eye_tracker').glob('*.py'))}
        model_name=args.trial_model.resolve().relative_to(ROOT).as_posix() if args.trial_model.resolve().is_relative_to(ROOT) else str(args.trial_model.resolve())
        runtime_files[model_name]=hashlib.sha256(args.trial_model.read_bytes()).hexdigest()
        manifest=dict(runtime_files=runtime_files,model_file=model_name,
                      expected_bit_sha256=report['contract']['artifact_hashes_verified']['bit'],
                      expected_hwh_sha256=report['contract']['artifact_hashes_verified']['hwh'],
                      duration_requested=args.seconds,long_run=args.long_run,eye_events=args.eye_events,
                      demo_window=args.demo_window,
                      source='current_files_before_overlay_load',classifier_evidence=str(args.trial_evidence))
        manifest['music_enabled']=music_library is not None
        manifest['quick_phrases_enabled']=args.quick_phrases
        manifest['emotion_cards_enabled']=args.emotion_cards
        manifest['daily_tools_enabled']=args.daily_tools
        manifest['local_video_enabled']=args.local_video
        manifest['pastimes_enabled']=args.pastimes
        manifest['receiver_sharing_enabled']=args.receiver_sharing
        manifest['ai_writing_enabled']=args.ai_writing
        if args.pastimes:manifest['audiobooks']=daily_tools.audiobook_library.provenance()
        if args.local_video:manifest['video']=daily_tools.video_library.provenance()
        if daily_tools is not None:
            manifest['photos']=daily_tools.album.provenance()
            manifest['pinyin_sha256']=daily_tools.composer.lexicon.sha256
        manifest['reposition_assist']=args.reposition_assist
        if bank is not None:
            manifest['speech_assets']={name:hashlib.sha256((ROOT/'assets/speech'/name).read_bytes()).hexdigest()
                                       for name in ['manifest.json']+[key+'.wav' for key in bank.samples]}
        if music_library is not None:
            manifest['music']=music_library.provenance()
        (args.output/'runtime_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    import fcntl
    from pynq import Overlay, MMIO, allocate, Clocks
    # This lock coordinates our program only; it cannot lock out unrelated tools.
    with open("/var/lock/eye_tracker_system.lock", "a+") as owner:
        try:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("another eye tracker process owns the board lock")
        if args.mode=="eye-trial":print("Loading experimental eye-region UI trial; local speech " + ("ENABLED." if args.audible else "muted."),flush=True)
        else:print("Loading diagnostic overlay. Real gaze is disabled; AUX output " + ("ENABLED for explicit listening test." if args.audible else "muted."), flush=True)
        overlay = Overlay(str(ROOT / "build/fpga/eye_tracker.bit"), download=False)
        overlay.download()
        report["pl_clocks"] = configure_overlay_clocks(Clocks)
        session = VideoIO(MMIO(ADDRESSES["vdma_0"], 0x10000),
                          MMIO(ADDRESSES["video_control"], 0x10000),
                          MMIO(ADDRESSES["camera_diag_0"], 0x1000), allocate)
        report["live_attempted"] = True
        exit_code = 1
        sensor = None
        sensor_bus = None
        event_link = None
        try:
            session.prepare()
            if args.event_test or args.eye_events != "off":
                from .event_uart import AxiUartLite
                from .event_link import EventLink
                link_type=EventLink
                if args.receiver_sharing:
                    from .share_link import SharingEventLink
                    link_type=SharingEventLink
                event_link = link_type(AxiUartLite(MMIO(ADDRESSES["event_uart_0"],0x10000)), simulation=args.event_test, wire_test=args.event_test or args.eye_events=="log")
            if args.mode == "sensor" or args.exposure_rows is not None:
                sensor_bus = OpenDrainI2C(session.gpio)
                sensor = MT9V034.probe(sensor_bus)
                report["sensor"] = {"address_7bit":sensor.address,"chip_id":0x1324,
                    "identity_scope":"MT9V024/034-family; module marketed as MT9V034",
                    "registers":sensor.snapshot()}
                if args.exposure_rows is not None:
                    report["manual_controls"] = sensor.apply_manual(args.exposure_rows,args.gain_units)
                    session.wait_native_frames(4) # discard configuration transition frames

            if args.mode in ("display", "combined", "stream"):
                session.display_static(frame)
            if args.mode in ("preview", "ui-test", "audio-test", "control-test", "fixation", "eye-trial"):
                session.display_dynamic(frame)
            if args.mode == "fixation":
                report["fixation"] = run_fixation(session,renderer,fixation_recording)
            if args.mode == "eye-trial":
                report["visual_trial"]=run_visual_trial(session,renderer,trial,MMIO(ADDRESSES["audio_aux_0"],0x20000),args.seconds,challenges=challenge_schedule,bank=bank,auto_controls=args.trial_auto_controls,event_link=event_link,music_library=music_library,quick_phrases=args.quick_phrases,reposition_assist=args.reposition_assist,emotion_cards=args.emotion_cards,daily_tools=daily_tools,demo_window=args.demo_window)
            if args.mode in ("audio-test", "control-test"):
                auxiliary_mmio = MMIO(ADDRESSES["audio_aux_0"], 0x20000)
                if args.mode == "audio-test":
                    report["audio_test"] = run_audio_test(auxiliary_mmio, bank, session, renderer, args.output, audible=args.audible)
                else:
                    report["control_test"] = run_control_test(auxiliary_mmio, session, renderer, args.output, args.seconds, bank=bank if args.audible else None,event_link=event_link)
            if args.mode == "ui-test":
                report["interaction_test"] = run_on_board(session, renderer, args.output,event_link=event_link)
            if args.mode in ("capture", "combined", "stream", "preview"):
                before = session.wait_native_frames(2)
                if args.mode in ("stream", "preview"):
                    started = time.monotonic()
                    completed_times, request_ms, switch_ms, render_ms = [], [], [], []
                    deadline = started + args.seconds
                    while time.monotonic() < deadline:
                        pixels = session.capture_once()
                        info = session.last_capture
                        completed_times.append(info["copied_at_monotonic"])
                        request_ms.append(1000 * (info["copied_at_monotonic"] - info["requested_at_monotonic"]))
                        if renderer is not None:
                            region = eye_locator.update(pixels, session.capture_index, info["copied_at_monotonic"]) if eye_locator else None
                            if region is not None:
                                renderer.set_region(region)
                            render_started = time.monotonic()
                            encoded, preview_stats = renderer.rgb565(pixels, session.capture_index,
                                                                      render_started - started)
                            if recording is not None:
                                recording.observe(pixels, session.capture_index, info["copied_at_monotonic"] - started, preview_stats, region=region)
                            switch_started = time.monotonic()
                            render_ms.append(1000 * (switch_started - render_started))
                            session.present(encoded)
                            switch_ms.append(1000 * (time.monotonic() - switch_started))
                    elapsed = time.monotonic() - started
                    intervals = np.diff([started] + completed_times) * 1000
                    report["stream"] = {
                        "frames": len(completed_times), "elapsed_seconds": elapsed,
                        "accepted_copy_fps": len(completed_times) / elapsed,
                        "max_copy_interval_ms": float(intervals.max()),
                        "p95_copy_interval_ms": float(np.percentile(intervals, 95)),
                        "max_request_to_copy_ms": float(max(request_ms)),
                        "fresh_dma_request_per_frame": True,
                        "same_overlay_and_capture_buffer": True,
                        "sensor_exposure_timestamps_available": False,
                        "eye_tracking_fps": None,
                    }
                    if renderer is not None:
                        from PIL import Image
                        shown = unpack_rgb565(np.frombuffer(encoded, dtype="<u2").reshape(480, 640))
                        Image.fromarray(shown, mode="RGB").save(args.output / "preview.png")
                        report["preview"] = {
                            "hardware_confirmed_switches": session.present_count,
                            "presented_fps": session.present_count / elapsed,
                            "display_slots": 3,
                            "final_slot": session.display_slot,
                            "p95_render_ms": float(np.percentile(render_ms, 95)),
                            "max_render_ms": float(max(render_ms)),
                            "p95_switch_ms": float(np.percentile(switch_ms, 95)),
                            "max_switch_ms": float(max(switch_ms)),
                            "last_frame_statistics": preview_stats,
                            "eye_detection_enabled": args.locate_eye,
                            "gaze_and_speech_enabled": False,
                            "sensor_to_photon_latency_measured": False,
                        }
                else:
                    pixels = session.capture_once()
                raw = pixels.tobytes()
                # Writes only after DMA completion/halt and cache invalidation.
                (args.output / "capture.gray8").write_bytes(raw)
                (args.output / "capture.pgm").write_bytes(b"P5\n640 480\n255\n" + raw)
                from PIL import Image
                Image.fromarray(pixels, mode="L").save(args.output / "capture.png")
                report["capture_saved_this_run"] = True
                after = session.wait_native_frames(1)
                report["capture"] = {
                    "width": 640, "height": 480, "format": "GRAY8", "bytes": len(raw),
                    "min": int(pixels.min()), "max": int(pixels.max()),
                    "mean": float(pixels.mean()), "std": float(pixels.std()),
                    "diagnostic_before": before, "diagnostic_after": after,
                    "content_verified": False, "pl_status_after_stop": session.gpio.read(8),
                }
                if (after["bad_frames"] != before["bad_frames"] or after["bad_lines"] != before["bad_lines"]):
                    raise RuntimeError("camera link error counters increased during capture")
            if args.mode in ("display", "combined"):
                deadline = time.monotonic() + args.seconds
                checks = 0
                while time.monotonic() < deadline:
                    session.display_health()
                    checks += 1
                    time.sleep(0.02)
                report["display_health_checks"] = checks
            report["registers_before_stop"] = session.registers()
            report["completed"] = True
            exit_code = 0
        except (Exception, KeyboardInterrupt) as exc:
            report["error"] = "%s: %s" % (type(exc).__name__, exc)
            report["completed"] = False
            report["accepted_frames_before_failure"] = session.capture_index
            if session.prepared:
                report["registers_at_failure"] = session.registers()
        finally:
            if event_link is not None:
                if event_link.state != "disabled":
                    event_link.abort(event_link.last_service or 0,"board_exit")
                report["communication"] = event_link.snapshot()
            try:
                session.close()
                report["both_dma_halted_before_free"] = True
                report["reset_recovery_used"] = session.reset_recovery_used
            except UnsafeShutdown as exc:
                report["completed"] = False
                report["both_dma_halted_before_free"] = False
                report["error"] = str(exc)
                try:
                    (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
                finally:
                    hold_for_recovery(session, exc)
            except Exception as exc:
                report["completed"] = False
                exit_code = 1
                report["cleanup_error"] = "%s: %s" % (type(exc).__name__, exc)
            if sensor is not None:
                try:
                    report["sensor_settings_restored"] = sensor.restore()
                    report["sensor_registers_after_restore"] = sensor.snapshot()
                except Exception as exc:
                    report["completed"] = False
                    exit_code = 1
                    report["sensor_restore_error"] = "%s: %s" % (type(exc).__name__, exc)
            if sensor_bus is not None:
                try:
                    sensor_bus.release()
                    report["i2c_lines_after_release"] = sensor_bus.lines()
                except Exception as exc:
                    report["completed"] = False
                    exit_code = 1
                    report["i2c_release_error"] = str(exc)
            if fixation_recording is not None and report.get("both_dma_halted_before_free"):
                try:
                    report["fixation_recording"] = fixation_recording.save(args.output,report["completed"])
                    if args.fit_session and report["completed"]:
                        from .session_calibration import save_candidate
                        report["session_calibration"] = save_candidate(fixation_recording,args.output,ROOT)
                except Exception as exc:
                    report["completed"] = False
                    exit_code = 1
                    report["fixation_recording_error"] = str(exc)
            if trial is not None and report.get("both_dma_halted_before_free"):
                try:report["visual_trial_recording"]=trial.save(args.output,report["completed"])
                except Exception as exc:
                    report["completed"]=False;exit_code=1;report["visual_trial_recording_error"]=str(exc)
            if eye_locator is not None:
                report["eye_region"] = eye_locator.summary()
            if recording is not None and report.get("both_dma_halted_before_free"):
                try:
                    report["preview_recording"] = recording.save(args.output, report["completed"])
                except Exception as exc:
                    report["completed"] = False
                    exit_code = 1
                    report["recording_error"] = "%s: %s" % (type(exc).__name__, exc)
            (args.output / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return exit_code


if __name__ == "__main__":
    sys.exit(main())
