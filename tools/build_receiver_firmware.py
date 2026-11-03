"""Build isolated upgrade firmware with the handoff's pinned SDK/config.
Never opens a COM port. All writes are confined to the upgrade workspace.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, os, shutil, subprocess, sys
import cmake

ROOT=Path(__file__).resolve().parents[1]
SDK=ROOT/'comm/fbb_sdk_upgrade/src'
SOURCE=ROOT/'comm/receiver_upgrade'
STAGE=ROOT/'build/receiver_sharing_20261102'
TARGET='ws63-liteos-app'
APPREL=Path('application/samples/products/sle_uart')


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('node',choices=['01','02','03','04'])
    ap.add_argument('--label',required=True)
    a=ap.parse_args()
    assert a.label and all(c.isalnum() or c in '_-' for c in a.label)
    out=STAGE/'firmware'/f'{a.node}_{a.label}'
    out.mkdir(parents=True,exist_ok=False)
    assert SDK.resolve().is_relative_to(ROOT.resolve())
    result=dict(node=a.node,build='running',flashed=False,board_tested=False,
                sdk_commit='7cda10e7476d8df35f0ac1a4013eb395874247e0',
                recorded_utc=datetime.now(timezone.utc).isoformat())
    lock=STAGE/'build.lock'
    with lock.open('x') as f:f.write(str(os.getpid()))
    try:
        env=os.environ.copy()
        env['PATH']=os.pathsep.join([str(Path(sys.executable).parent),str(Path(sys.executable).parent/'Scripts'),
            str(cmake.CMAKE_BIN_DIR),'D:/hispark_studio/HiSpark Studio/tools/Windows/ninja',
            'D:/hispark_studio/HiSpark Studio/tools/Windows/cc_riscv32_win_env',env.get('PATH','')])
        env['PYTHONPATH']=str(ROOT/'tools/deps')+os.pathsep+env.get('PYTHONPATH','')
        env['PYTHONDONTWRITEBYTECODE']='1';env['PYTHONIOENCODING']='utf-8'
        pin=json.loads((SOURCE/'sdk_lock.json').read_text(encoding='utf-8'))
        for row in pin['selected_files']:assert sha(SDK/row['path'])==row['sha256'],row['path']
        app=SOURCE/('central01' if a.node=='01' else 'receivers')/APPREL
        assert app.is_dir()
        # Clean application directory so previous node objects cannot leak in.
        target_app=SDK/APPREL
        assert target_app.resolve().is_relative_to(SDK.resolve()) and target_app.name=='sle_uart'
        if target_app.exists():shutil.rmtree(target_app)
        shutil.copytree(app,target_app)
        shutil.copytree(app,out/'source')
        for name in ('Kconfig','CMakeLists.txt'):
            shutil.copy2(SOURCE/'build_hooks'/('products_'+name).lower(),target_app.parent/name)
        config=SDK/'build/config/target_config/ws63/menuconfig/acore/ws63_liteos_app.config'
        shutil.copy2(SOURCE/'config'/a.node/'ws63_liteos_app.config',config)
        archive=SDK/f'output/ws63/acore/{TARGET}/application/samples/libsamples.a'
        assert archive.resolve().is_relative_to((SDK/'output').resolve())
        if archive.exists():archive.unlink()
        result['sources']={p.relative_to(app).as_posix():sha(p) for p in app.rglob('*') if p.is_file()}
        print('Building '+a.node+'; log '+str(out/'build.log'),flush=True)
        with (out/'build.log').open('wb') as log:
            proc=subprocess.run([sys.executable,'-B','build.py',TARGET,'-ninja','-j6','-release','-c'],cwd=SDK,env=env,stdout=log,stderr=subprocess.STDOUT)
        if proc.returncode:
            print((out/'build.log').read_text(encoding='utf-8',errors='replace')[-5000:])
            raise RuntimeError('Build exit '+str(proc.returncode))
        compiled=SDK/f'output/ws63/acore/{TARGET}'
        header=compiled/'mconfig.h';h=header.read_text(encoding='utf-8')
        if a.node=='01':assert '#define CONFIG_SAMPLE_SUPPORT_EYE_LINK_A_CONTROL 1' in h
        else:
            assert '#define CONFIG_SAMPLE_SUPPORT_EYE_LINK 1' in h
            assert '#define CONFIG_EYE_LINK_NODE_'+{'02':'B','03':'C','04':'D'}[a.node]+' 1' in h
            assert ('#define CONFIG_SAMPLE_SUPPORT_WEARABLE_EPD 1' in h)==(a.node!='02')
        compiler=SDK/'tools/bin/compiler/riscv/cc_riscv32_musl_105/cc_riscv32_musl_fp_win/bin'
        members=subprocess.check_output([str(compiler/'riscv32-linux-musl-ar.exe'),'t',str(archive)],env=env,text=True).splitlines()
        wanted=['eye_main.c.obj','eye_radio.c.obj','eye_endpoint.c.obj','eye_fanout.c.obj','eye_event.c.obj']
        if a.node!='01':wanted+=['eye_share.c.obj']
        if a.node in ('03','04'):wanted+=['eye_share_render.c.obj']
        if a.node!='01':wanted+=['eye_home.c.obj','care_hmi.c.obj'] if a.node=='02' else ['eye_wearable.c.obj','wearable_epd.c.obj']
        assert sorted(members)==sorted(wanted),members
        elf=compiled/(TARGET+'.elf')
        nm=subprocess.check_output([str(compiler/'riscv32-linux-musl-nm.exe'),str(elf)],env=env,text=True)
        entries=[x.split()[-1] for x in nm.splitlines() if '__zinitcall_run_' in x]
        assert entries==['__zinitcall_run_eye_entry'],entries
        (out/'symbols.txt').write_text(nm,encoding='utf-8')
        artifacts=[SDK/f'output/ws63/fwpkg/{TARGET}/{TARGET}_all.fwpkg',elf,header,config,archive]+list(compiled.glob('*.map'))
        assert any(p.suffix=='.map' for p in artifacts)
        result['artifacts']=[]
        for p in artifacts:
            dest=out/p.name;shutil.copy2(p,dest)
            result['artifacts'].append(dict(path=dest.name,sha256=sha(dest),bytes=dest.stat().st_size))
        assert result['sources']=={p.relative_to(app).as_posix():sha(p) for p in app.rglob('*') if p.is_file()}
        result.update(build='passed',sample_archive_members=members,application_entries=entries)
        print(json.dumps(dict(build='passed',node=a.node,result=str(out/'result.json'))),flush=True)
    except BaseException as e:
        result.update(build='failed',error=str(e));raise
    finally:
        (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        lock.unlink()


if __name__=='__main__':main()
