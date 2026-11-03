"""Run relevant local behavior tests and write one compact current result."""
from pathlib import Path
import io,json,os,sys,tempfile,unittest
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'src'))
os.environ['PYTHONPATH']=str(root/'src')
test_tmp=root/'build/test_tmp'
test_tmp.mkdir(parents=True,exist_ok=True)
tempfile.tempdir=str(test_tmp)
os.environ['TMP']=os.environ['TEMP']=str(test_tmp)
stream=io.StringIO()
suite=unittest.defaultTestLoader.discover(str(root/'tests'))
result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
text=stream.getvalue()
print(text)
out=root/'build/software';out.mkdir(parents=True,exist_ok=True)
(out/'tests.txt').write_text(text,encoding='utf-8')
(out/'result.json').write_text(json.dumps({'tests':result.testsRun,'failures':len(result.failures),
    'errors':len(result.errors),'skipped':len(result.skipped),'passed':result.wasSuccessful(),
    'scope':'synthetic calibration/interaction, compiled RGB565 UI, untimed games, chapter audio/bookmarks/help priority, local video state/clock/priority/bounds, album/grouped pinyin/favorites, six emotion cards, usage guidance, music and quick phrases, bounded streaming/priority/navigation/import boundaries, camera-loop wiring, appearance rejection/check leakage, bounded recording, simulated DMA/codec/helper/UART failures, artifact contract and explicit-profile startup checks; no board, actual listening or real-eye accuracy','board_tested':False},indent=2)+'\n',encoding='utf-8')
sys.exit(0 if result.wasSuccessful() else 1)
