"""Launch one explicitly selected personal eye profile through the board CLI.

This is a command simplifier, not a calibration bypass or an autostart service.
Offline checks never import the board CLI or access programmable hardware.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path, PureWindowsPath
import re
import sys
import uuid
from xml.etree.ElementTree import ParseError

from .hardware_contract import verify_artifacts


ROOT = Path(__file__).resolve().parents[2]
_FIELDS = frozenset(('version', 'model', 'evidence', 'expected_bit_sha256',
                     'expected_hwh_sha256', 'expected_model_sha256',
                     'duration_seconds', 'audible'))


def _inside(root, path):
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValueError('profile paths must stay inside the project root: '+str(path))
    return resolved


def _relative(root, value, name):
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(name+' must be a nonempty relative path')
    normalized = value.replace('\\', '/')
    if (Path(normalized).is_absolute() or PureWindowsPath(value).drive
            or '..' in normalized.split('/') or '\x00' in value):
        raise ValueError(name+' must be a relative path without parent traversal')
    return _inside(root, root/normalized)


def _require_file(path):
    if not path.is_file():
        raise ValueError('required file missing: '+str(path))
    return path


def _sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _json_unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate profile field: '+key)
        result[key] = value
    return result


def load_profile(profile_path, root=ROOT, demo_window=False):
    """Validate strict configuration and path boundaries; do not activate it."""
    root = Path(root).resolve()
    path = Path(profile_path)
    path = _inside(root, path if path.is_absolute() else root/path)
    _require_file(path)
    data = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=_json_unique_pairs)
    if type(data) is not dict or set(data) != _FIELDS:
        raise ValueError('profile must contain exactly these fields: '+', '.join(sorted(_FIELDS)))
    if type(data['version']) is not int or data['version'] != 1:
        raise ValueError('profile version must be integer 1')
    if type(data['audible']) is not bool:
        raise ValueError('audible must be a JSON boolean')
    duration = data['duration_seconds']
    maximum = 3600 if demo_window else 1200
    if (type(duration) not in (int, float) or not math.isfinite(duration)
            or not 10 <= duration <= maximum):
        raise ValueError('duration_seconds must be a finite number from 10 to '+str(maximum))
    for field in ('expected_bit_sha256', 'expected_hwh_sha256', 'expected_model_sha256'):
        value = data[field]
        if not isinstance(value, str) or re.fullmatch(r'[0-9a-fA-F]{64}', value) is None:
            raise ValueError(field+' must be 64 hexadecimal SHA256 characters')
        data[field] = value.lower()
    model = _require_file(_relative(root, data['model'], 'model'))
    evidence = _relative(root, data['evidence'], 'evidence')
    if not evidence.is_dir():
        raise ValueError('evidence must be an existing directory')
    for name in ('runtime_manifest.json', 'diagnostic.json'):
        _require_file(_inside(root, evidence/name))
    data['model'] = model.relative_to(root).as_posix()
    data['evidence'] = evidence.relative_to(root).as_posix()
    return path, data


def prepare_launch(profile_path, root=ROOT, eye_events="off", music=False, quick_phrases=False,reposition_assist=False,emotion_cards=False,daily_tools=False,local_video=False,pastimes=False,receiver_sharing=False,demo_window=False,ai_writing=False):
    """Build an offline checked launch plan without creating any output."""
    if eye_events not in ("off", "log", "live"):
        raise ValueError("unknown receiver mode")
    from .emotions import validate_options
    validate_options(emotion_cards,music,quick_phrases,eye_events!='off')
    from .daily_tools import validate_options as validate_daily
    validate_daily(daily_tools,music,quick_phrases,emotion_cards,eye_events!='off')
    if local_video and not daily_tools:raise ValueError('local video requires daily tools')
    if pastimes and not daily_tools:raise ValueError('pastimes require daily tools')
    if ai_writing and not daily_tools:raise ValueError('AI writing requires daily tools')
    if receiver_sharing and (not daily_tools or eye_events=='off'):raise ValueError('receiver sharing requires daily tools and explicit wireless mode')
    root = Path(root).resolve()
    path, profile = load_profile(profile_path, root, demo_window=demo_window)
    artifacts = {
        'bit': _require_file(_inside(root, root/'build/fpga/eye_tracker.bit')),
        'hwh': _require_file(_inside(root, root/'build/fpga/eye_tracker.hwh')),
        'model': _require_file(_inside(root, root/profile['model'])),
    }
    _require_file(_inside(root, root/'build/fpga/result.json'))
    hashes = {}
    for name, artifact in artifacts.items():
        hashes[name] = _sha(artifact)
        if hashes[name] != profile['expected_'+name+'_sha256']:
            raise ValueError('profile SHA256 mismatch: '+name)
    contract = verify_artifacts(root)
    if quick_phrases:
        if not profile['audible']:raise ValueError('quick phrases require an audible profile')
        if contract.get('audio_ip_version')!='0x00020000':raise ValueError('quick phrases require audio IP v2 for longer utterances')
        from .phrases import QUICK_KEYS
        for name in ['manifest.json']+[key+'.wav' for key in QUICK_KEYS]:
            _require_file(_inside(root,root/'assets/speech'/name))
    if music:
        if not profile['audible']:raise ValueError('music requires an audible profile')
        # Keep check-only dependency-free; complete bounded PCM validation runs
        # in the board preflight before the overlay is loaded.
        _require_file(_inside(root,root/'assets/music/playlist.json'))
        if contract.get('audio_ip_version')!='0x00020000':raise ValueError('music requires a recorded audio IP v2 build')
    if daily_tools:
        for name in ('assets/photos/album.json','assets/typing/pinyin.json','assets/typing/glyphs.npz'):
            _require_file(_inside(root,root/name))
    if local_video:_require_file(_inside(root,root/'assets/video/playlist.json'))
    if pastimes:_require_file(_inside(root,root/'assets/audiobooks/playlist.json'))
    if ai_writing:
        from .ai_bundle import AIBundle
        AIBundle(root/'assets/ai')
        if not profile['audible']:raise ValueError('AI speech requires an audible profile')
    run_parent = _inside(root, root/'data/private/runs')
    # Board RTC may be wrong: the timestamp is only a label; UUID ensures a new run.
    label = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = _inside(root, run_parent/('eye_'+label+'_'+uuid.uuid4().hex))
    if output.exists():
        raise ValueError('generated run directory already exists; launch again')
    arguments = ['eye-trial', '--long-run', '--load',
                 '--seconds', str(profile['duration_seconds']),
                 '--trial-model', str(artifacts['model']),
                 '--trial-evidence', str(root/profile['evidence']),
                 '--output', str(output)]
    if eye_events != 'off':
        arguments.extend(['--eye-events', eye_events])
    if profile['audible']:
        arguments.append('--audible')
    if music:arguments.append('--music')
    if quick_phrases:arguments.append('--quick-phrases')
    if reposition_assist:arguments.append('--reposition-assist')
    if emotion_cards:arguments.append('--emotion-cards')
    if daily_tools:arguments.append('--daily-tools')
    if local_video:arguments.append('--local-video')
    if pastimes:arguments.append('--pastimes')
    if receiver_sharing:arguments.append('--receiver-sharing')
    if demo_window:arguments.append('--demo-window')
    if ai_writing:arguments.append('--ai-writing')
    return dict(source='explicit_profile', profile=path.relative_to(root).as_posix(),
                profile_sha256=_sha(path), profile_values=profile,
                verified_sha256=hashes, hardware_contract=contract,
                hardware_loaded=False, positive_evidence_validated=False,
                music_enabled=bool(music),
                local_video_enabled=bool(local_video),
                pastimes_enabled=bool(pastimes),receiver_sharing_enabled=bool(receiver_sharing),
                quick_phrases_enabled=bool(quick_phrases),
                emotion_cards_enabled=bool(emotion_cards),daily_tools_enabled=bool(daily_tools),
                reposition_assist=bool(reposition_assist),
                demo_window=bool(demo_window),ai_writing_enabled=bool(ai_writing),
                fresh_center_reference_verified=False, uart_enabled=eye_events!="off", receiver_mode=eye_events,
                deferred_checks=['VisualTrial independent evidence and classifier/model gate',
                                 'current-session center reference before dwell actions'],
                output=str(output), board_arguments=arguments)


def _invoke_board(arguments):
    # Lazy import is important: check-only must not import the hardware CLI.
    from . import board
    previous = sys.argv
    try:
        sys.argv = ['eye_tracker.board']+list(arguments)
        return board.main()
    finally:
        sys.argv = previous


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, required=True,
                        help='explicit personal JSON profile inside this project; no default')
    parser.add_argument('--eye-events',choices=('off','log','live'),default='off',help='explicit real-eye wireless opt-in; profile cannot enable it')
    parser.add_argument('--check-only', action='store_true',
                        help='verify profile paths/hashes/hardware contract only, without hardware access')
    parser.add_argument('--music',action='store_true',help='enable local music page explicitly; default off')
    parser.add_argument('--quick-phrases',action='store_true',help='enable local quick phrases explicitly; default off')
    parser.add_argument('--reposition-assist',action='store_true',help='explicit live preview and BTN0-confirmed center setup; BTN2 cancels wireless requests before retry')
    parser.add_argument('--daily-tools',action='store_true',help='local album and grouped pinyin; requires music + quick phrases + emotion cards')
    parser.add_argument('--local-video',action='store_true',help='bounded local video; requires daily tools, default off')
    parser.add_argument('--receiver-sharing',action='store_true',help='explicit version-gated sharing; activity summaries still default off')
    parser.add_argument('--pastimes',action='store_true',help='untimed games and local audiobooks; requires daily tools, default off')
    parser.add_argument('--emotion-cards',action='store_true',help='six local visual cards; requires --music --quick-phrases; card choices stay local')
    parser.add_argument('--demo-window',action='store_true',help='explicit filming window up to3600 seconds; default profile limit remains1200')
    parser.add_argument('--ai-writing',action='store_true',help='explicit local AI candidates and confirmed offline draft speech; default off')
    args = parser.parse_args(argv)
    try:
        plan = prepare_launch(args.profile, root, args.eye_events,args.music,args.quick_phrases,args.reposition_assist,args.emotion_cards,args.daily_tools,args.local_video,args.pastimes,args.receiver_sharing,args.demo_window,args.ai_writing)
    except (OSError, ValueError, KeyError, ParseError) as exc:
        parser.error(str(exc))
    print(json.dumps(dict(plan, check_only=args.check_only), ensure_ascii=False, indent=2), flush=True)
    if args.check_only:
        return 0
    try:
        return _invoke_board(plan['board_arguments'])
    finally:
        # The board owns creating the output only after its preflight checks.
        # Never create it here: an existing output would fail the board's gate.
        output = _inside(Path(root).resolve(), Path(plan['output']))
        if output.is_dir():
            provenance = dict(plan, scope='launch plan only; consult result.json for actual completion')
            (output/'launch_profile.json').write_text(
                json.dumps(provenance, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    sys.exit(main())

