"""Fresh standalone XSim run; never opens inherited Vivado project/cache."""
from pathlib import Path
import hashlib,json,subprocess,sys

ROOT=Path(__file__).resolve().parents[1]
BIN=Path('D:/AMDDesignTools/2026.1/Vivado/bin')
OUT=ROOT/'build/music_upgrade_20261029/rtl'


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    results={}
    for top,marker in [('tb_audio_aux','audio_test_result.txt'),('tb_audio_stream','audio_stream_result.txt')]:
        work=OUT/top;work.mkdir(exist_ok=True)
        stamp=work/marker
        if stamp.exists():stamp.unlink()
        sources=[ROOT/'fpga/rtl/audio_aux_axi.v',ROOT/f'fpga/sim/{top}.sv']
        commands=[['xvlog.bat','--sv',*[str(p) for p in sources]],
                  ['xelab.bat',top,'-s',top+'_snapshot'],
                  ['xsim.bat',top+'_snapshot','-runall']]
        for command in commands:
            command[0]=str(BIN/command[0])
            log=work/(Path(command[0]).stem+'.log.txt')
            with log.open('w',encoding='utf-8') as f:
                p=subprocess.run(command,cwd=work,stdout=f,stderr=subprocess.STDOUT)
            if p.returncode:raise RuntimeError(f'{top} failed: {log}')
        if not stamp.is_file() or stamp.read_text().strip()!='PASS':
            raise RuntimeError(f'{top} did not produce a fresh PASS')
        results[top]={'passed':True,'sources':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    (OUT/'result.json').write_text(json.dumps({'simulations':results,'board_tested':False},indent=2)+'\n')
    print(json.dumps(results,indent=2))


if __name__=='__main__':main()
