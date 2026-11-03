"""Build a reproducible minimal diagnostic zip; exclude private data and fonts."""
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
from PIL import Image
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from eye_tracker.framebuffer import encode_frame
from eye_tracker.hardware_contract import verify_artifacts


def main():
    verify_artifacts(ROOT)
    names = ['pyproject.toml', 'config/hardware.json', 'config/appearance_evaluation.json', 'config/appearance_diagnostic_protocol.json', 'config/invalid_input_protocol.json', 'config/appearance_repair_protocol.json', 'config/appearance_edge_protocol.json', 'config/appearance_trial_protocol.json', 'config/appearance_corner_protocol.json', 'config/appearance_eye_support_protocol.json', 'config/appearance_current_fit_protocol.json', 'config/appearance_pair_protocol.json', 'config/appearance_parallel_protocol.json', 'config/appearance_return_protocol.json', 'config/appearance_ui_challenge_protocol.json', 'config/session_calibration_protocol.json', 'docs/board_bringup.md',
             'docs/status.md', 'docs/communication.md', 'comm/protocol/README.md', 'docs/audio_controls.md', 'build/board/result.json',
             'tools/board_probe.py', 'tools/run_board.sh', 'assets/preview_template.png', 'assets/eye_region_template.png', 'assets/fixation_template.png', 'assets/invalid_input_prompts.npz', 'assets/trial_challenge_prompts.npz', 'assets/haarcascade_eye.xml', 'assets/eye_region_model.json', 'assets/communication_ui.npz', 'build/fpga/eye_tracker.bit',
             'build/fpga/eye_tracker.hwh', 'build/fpga/result.json']
    names += [p.relative_to(ROOT).as_posix() for p in (ROOT/'src/eye_tracker').glob('*.py')]
    names += [p.relative_to(ROOT).as_posix() for p in (ROOT/'assets/speech').iterdir() if p.suffix in ('.wav','.json')]
    names += [p.relative_to(ROOT).as_posix() for p in (ROOT/'assets/music').iterdir() if p.suffix in ('.wav','.json')]
    payload = {name:(ROOT/name).read_bytes() for name in names}
    with Image.open(ROOT/'build/previews/uncalibrated.png') as im:
        ui = encode_frame(np.asarray(im.convert('RGB'), dtype=np.uint8))
    payload['build/deploy/ui_static.rgb565'] = ui
    manifest = {name:{'bytes':len(data), 'sha256':hashlib.sha256(data).hexdigest()}
                for name,data in sorted(payload.items())}
    payload['package_manifest.json'] = (json.dumps(manifest,indent=2)+'\n').encode('utf-8')
    memory = io.BytesIO()
    with zipfile.ZipFile(memory,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in sorted(payload.items()):
            item=zipfile.ZipInfo(name, date_time=(2026,10,20,0,0,0))
            item.compress_type=zipfile.ZIP_DEFLATED
            item.external_attr=0o100644 << 16
            archive.writestr(item,data)
    data=memory.getvalue()
    with zipfile.ZipFile(io.BytesIO(data)) as check:
        assert check.testzip() is None
        for name, expected in manifest.items():
            assert hashlib.sha256(check.read(name)).hexdigest()==expected['sha256']
    out=ROOT/'build/deploy';out.mkdir(parents=True,exist_ok=True)
    (out/'ui_static.rgb565').write_bytes(ui)
    (out/'eye_tracker_board.zip').write_bytes(data)
    result={'archive':'build/deploy/eye_tracker_board.zip','bytes':len(data),
            'sha256':hashlib.sha256(data).hexdigest(),'files':len(payload),
            'entry_hashes_verified':True,'hardware_tested_by_packager':False,'files_manifest':manifest}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='files_manifest'},indent=2))


if __name__=='__main__':
    main()
