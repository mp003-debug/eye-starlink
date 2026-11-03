"""Run the imported read-only reference tests against the upgrade package."""
import io,json,os,sys,tempfile,unittest,shutil,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'build/wireless_upgrade_20261101'
original=ROOT/'imports/Eye_Wireless_Upgrade_Handoff_20261101/pynq/reference_tests'
reference=OUT/'reference_adapter';reference.mkdir(exist_ok=True)
# Keep the imported evidence immutable. The old loop fixture used a removed
# FixationRenderer; only its display stub is adapted to the existing upgrade API.
for p in original.glob('*.py'):shutil.copy2(p,reference/p.name)
p=reference/'test_trial_events.py';s=p.read_text(encoding='utf-8')
s=s.replace("renderer=SimpleNamespace(rgb565=lambda *a:b'')","renderer=SimpleNamespace(rgb565=lambda *a:b'',setup_frame=lambda *a,**k:b'')")
s=s.replace(",patch('eye_tracker.appearance_trial.FixationRenderer',return_value=reference)","")
p.write_text(s,encoding='utf-8')
sys.path[:0]=[str(ROOT/'src'),str(reference)]
os.environ['PYTHONPATH']=str(ROOT/'src');os.environ['PYTHONDONTWRITEBYTECODE']='1'
temp=ROOT/'build/test_tmp';temp.mkdir(exist_ok=True);tempfile.tempdir=str(temp);os.environ['TEMP']=os.environ['TMP']=str(temp)
stream=io.StringIO();suite=unittest.TestSuite()
for name in ('test_events.py','test_launch.py','test_trial_events.py'):
    suite.addTests(unittest.defaultTestLoader.discover(str(reference),pattern=name))
result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
record=dict(tests=result.testsRun,passed=result.wasSuccessful(),failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
    scope='Protocol, launch and wireless adapter reference tests against upgrade Python modules; no hardware acceptance',
    adaptation='Only old camera-loop display fixture changed to upgrade setup_frame API. Imported files untouched; all assertions retained.',
    auxiliary='test_auxiliary imported for fixtures only. Its obsolete -6dB expectation is not run; current 0dB audio is covered by the full upgrade suite.')
(OUT/'reference_tests.txt').write_text(stream.getvalue(),encoding='utf-8')
(OUT/'reference_result.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
print(json.dumps(record));sys.exit(not result.wasSuccessful())
