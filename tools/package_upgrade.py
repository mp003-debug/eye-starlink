"""Private, complete upgrade bundle; never contains baseline service templates."""
import argparse,hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from eye_tracker.hardware_contract import verify_artifacts
from eye_tracker.launch import load_profile

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',default='eye_tracker_upgrade_private.zip')
    parser.add_argument('--output-dir',default='build/upgrade_deploy_20261029')
    args=parser.parse_args()
    if Path(args.archive).name!=args.archive or not args.archive.endswith('.zip'):
        parser.error('--archive must be a zip filename without a directory')
    out=(ROOT/args.output_dir).resolve()
    try:out.relative_to((ROOT/'build').resolve())
    except ValueError:parser.error('--output-dir must be inside the upgrade build directory')
    archive=out/args.archive
    if archive.exists():raise ValueError('archive already exists; choose a new name to preserve prior evidence')
    verify_artifacts(ROOT)
    _,profile=load_profile('data/private/profiles/current_eye.json',ROOT)
    profile=dict(profile,duration_seconds=120)
    target=ROOT/'data/private/profiles/upgrade_check.json'
    target.write_text(json.dumps(profile,indent=2)+'\n',encoding='utf-8')
    names={'pyproject.toml','build/fpga/eye_tracker.bit','build/fpga/eye_tracker.hwh','build/fpga/result.json',
           'tools/run_eye.sh','tools/run_board.sh','tools/board_probe.py','tools/upgrade_preflight.py','tools/check_upgrade_phrase.py','tools/check_upgrade_music.py','tools/check_upgrade_video.py','tools/benchmark_typing_ui.py','tools/check_wireless_coexistence.py',
           'deploy/systemd/eye-control-upgrade.service','data/private/profiles/upgrade_check.json',
           'data/private/profiles/current_eye.json','docs/reposition.md','docs/emotion_cards.md','docs/daily_tools.md','docs/local_video.md','docs/ui_typing.md','docs/typing_words.md','docs/free_text.md',profile['model'],profile['evidence']+'/diagnostic.json',
           profile['evidence']+'/runtime_manifest.json','docs/quick_phrases.md','docs/music.md','docs/upgrade_deployment.md','docs/pastimes.md','docs/wireless_upgrade.md',
           'docs/receiver_displays.md','docs/receiver_sharing.md'}
    for folder,pattern in [('src/eye_tracker','*.py'),('config','*.json'),('assets','*'),('assets/speech','*'),('assets/music','*'),('assets/photos','*'),('assets/typing','*'),('assets/video','*'),('assets/audiobooks','*')]:
        names.update(p.relative_to(ROOT).as_posix() for p in (ROOT/folder).glob(pattern)
                     if p.is_file() and p.suffix in ('.py','.json','.npz','.png','.xml','.wav','.mp4','.rgb565','.txt'))
    payload={name:(ROOT/name).read_bytes() for name in sorted(names)}
    manifest=dict(target_root='/home/xilinx/Eye_Tracker_Upgrade_Version',private=True,auto_start=False,
                  files={n:dict(bytes=len(b),sha256=hashlib.sha256(b).hexdigest()) for n,b in payload.items()})
    payload['upgrade_manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    out.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for n,b in sorted(payload.items()):
            info=zipfile.ZipInfo(n,date_time=(2026,10,29,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16;z.writestr(info,b)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for n,m in manifest['files'].items():assert hashlib.sha256(z.read(n)).hexdigest()==m['sha256']
    result=dict(archive=archive.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                bytes=archive.stat().st_size,files=len(manifest['files']),private=True,contains_personal_model=True,
                board_deployed=False,hardware_tested=False)
    # Packaging metadata must not erase accumulated deployment/listening evidence.
    (out/'package.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    if not (out/'result.json').exists():
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__':main()
