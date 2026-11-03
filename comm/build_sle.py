"""Native Windows SDK builds; never flashes hardware.
bridge/receiver build the project UART1 event firmware. server/client retain the
official UART0 baseline. Only a temporary CMake source hook is used inside SDK.
"""
import argparse, hashlib, json, os, shutil, subprocess, sys
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parent
SDK=ROOT/'sdk'; BUILD=ROOT/'build'; TARGET='ws63-liteos-app'
CONFIG=SDK/'build/config/target_config/ws63/menuconfig/acore/ws63_liteos_app.config'
HEADER=SDK/'output/ws63/acore/ws63-liteos-app/mconfig.h'
REVISION='08d2880956249642cc90d7eae9b80ed721646967'
HOOK=SDK/'application/samples/products/sle_uart/CMakeLists.txt'
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('role',choices=['bridge','receiver','server','client'])
    parser.add_argument('--hispark',type=Path,default=Path('D:/hispark_studio/HiSpark Studio'))
    parser.add_argument('--jobs',type=int,default=6)
    parser.add_argument('--node',choices=['B','C','D'],default='B')
    parser.add_argument('--required',choices=['BCD','CD','C'],default='BCD',help='Explicit bench population; production BCD')
    args=parser.parse_args()
    if not 1<=args.jobs<=16: parser.error('jobs must be 1..16')
    import cmake
    env=os.environ.copy()
    bins=[str(Path(sys.executable).parent),str(Path(sys.executable).parent/'Scripts'),str(cmake.CMAKE_BIN_DIR),
          str(args.hispark/'tools/Windows/ninja'),str(args.hispark/'tools/Windows/cc_riscv32_win_env')]
    env['PATH']=os.pathsep.join(bins+[env.get('PATH','')])
    env['PYTHONDONTWRITEBYTECODE']='1'; env['PYTHONIOENCODING']='utf-8'
    assert shutil.which('ninja',path=env['PATH']), 'Missing ninja'
    git=shutil.which('git') or 'D:/Program Files/Git/cmd/git.exe'
    assert subprocess.check_output([git,'-C',str(SDK),'rev-parse','HEAD'],text=True).strip()==REVISION
    official_hook=subprocess.check_output([git,'-C',str(SDK),'show','HEAD:application/samples/products/sle_uart/CMakeLists.txt'])
    original=HOOK.read_bytes()
    assert original.replace(b'\r\n',b'\n')==official_hook.replace(b'\r\n',b'\n'), 'SDK CMake hook differs; inspect before replacing'
    BUILD.mkdir(exist_ok=True)
    lock=BUILD/'.build.lock'
    with lock.open('x') as f: f.write(str(os.getpid()))
    project=args.role in ('bridge','receiver')
    sdk_role='CLIENT' if args.role in ('bridge','client') else 'SERVER'
    node=0 if args.role=='bridge' else {'B':1,'C':2,'D':3}[args.node]
    mask=sum({'B':1,'C':2,'D':4}[c] for c in args.required)
    bus,tx,rx=(1,15,16) if project else (0,17,18)
    dest=BUILD/'network'/('A' if args.role=='bridge' else args.node) if project else BUILD/args.role
    if project and args.role=='bridge' and args.required!='BCD': dest=dest.with_name('A_'+args.required)
    dest.mkdir(parents=True,exist_ok=True)
    if project: (dest/'eye_build_config.h').write_text('#define EYE_NODE_ID '+str(node)+'\n#define EYE_REQUIRED_MASK '+str(mask)+'\n',encoding='utf-8')
    result=dict(role=args.role,node=node if project else None,required_mask=mask if project else None,build='running',hardware_test='pending',sdk_commit=REVISION,
                recorded_utc=datetime.now(timezone.utc).isoformat())
    result_path=dest/'result.json'
    result_path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    try:
        sources=list(sorted((ROOT/'firmware').glob('*.[ch]')))+list(sorted((ROOT/'protocol').glob('eye_event.[ch]'))) if project else []
        source_hash={str(p.relative_to(ROOT)):digest(p) for p in sources}
        if project:
            for name in ('eye_main.c','eye_radio.c','eye_radio.h','eye_endpoint.c','eye_app.h'):
                assert (ROOT/'firmware'/name).is_file(), 'Missing '+name
            files=[ROOT/'firmware'/n for n in ('eye_main.c','eye_radio.c','eye_endpoint.c','eye_fanout.c')]+[ROOT/'protocol/eye_event.c']
            text='set(SOURCES "${SOURCES}"\n'+''.join('    "'+p.as_posix()+'"\n' for p in files)+'    PARENT_SCOPE)\n'
            text+='set(PUBLIC_HEADER "${PUBLIC_HEADER}" "'+(ROOT/'firmware').as_posix()+'" "'+(ROOT/'protocol').as_posix()+'" "'+dest.as_posix()+'" PARENT_SCOPE)\n'
            HOOK.write_text(text,encoding='utf-8')
        assignments=['SAMPLE_ENABLE=y','ENABLE_PERIPHERAL_SAMPLE=n','ENABLE_PRODUCTS_SAMPLE=y',
                     'SAMPLE_SUPPORT_SLE_UART=y','SAMPLE_SUPPORT_SLE_UART_'+sdk_role+'=y',
                     'SLE_UART_BUS='+str(bus),'UART_TXD_PIN='+str(tx),'UART_RXD_PIN='+str(rx)]
        subprocess.run([sys.executable,'-B','build/script/usr_config.py','--command','setconfig','--chip','ws63',
                        '--core','acore','--target',TARGET]+assignments,cwd=SDK,env=env,check=True)
        # ar rcD replaces matching members but does not remove obsolete ones.
        # This SDK links samples with --whole-archive, so stale demo entry points
        # would execute alongside our app even when absent from build.ninja.
        sample_archive=SDK/'output/ws63/acore/ws63-liteos-app/application/samples/libsamples.a'
        assert sample_archive.resolve().is_relative_to((SDK/'output').resolve())
        if sample_archive.exists(): sample_archive.unlink()
        log=BUILD/(args.role+'.log')
        print('Building '+args.role+'; log: '+str(log),flush=True)
        with log.open('wb') as output:
            completed=subprocess.run([sys.executable,'-B','build.py',TARGET,'-ninja','-j'+str(args.jobs),'-release'],
                                     cwd=SDK,env=env,stdout=output,stderr=subprocess.STDOUT)
        if completed.returncode:
            print(log.read_text(encoding='utf-8',errors='replace')[-7000:])
            raise RuntimeError('SDK build failed '+str(completed.returncode))
        header=HEADER.read_text(encoding='utf-8')
        assert '#define CONFIG_SAMPLE_SUPPORT_SLE_UART_'+sdk_role+' 1' in header
        assert '#define CONFIG_SLE_UART_BUS '+str(bus) in header
        assert '#define CONFIG_UART_TXD_PIN '+str(tx) in header
        assert '#define CONFIG_UART_RXD_PIN '+str(rx) in header
        assert source_hash=={str(p.relative_to(ROOT)):digest(p) for p in sources}, 'Source changed during build'
        compiler=SDK/'tools/bin/compiler/riscv/cc_riscv32_musl_105/cc_riscv32_musl_fp_win/bin'
        members=subprocess.check_output([str(compiler/'riscv32-linux-musl-ar.exe'),'t',str(sample_archive)],env=env,text=True).splitlines()
        elf=SDK/'output/ws63/acore/ws63-liteos-app/ws63-liteos-app.elf'
        symbols=subprocess.check_output([str(compiler/'riscv32-linux-musl-nm.exe'),str(elf)],env=env,text=True)
        entries=[line.split()[-1] for line in symbols.splitlines() if '__zinitcall_run_' in line]
        if project:
            assert sorted(members)==sorted(['eye_main.c.obj','eye_radio.c.obj','eye_endpoint.c.obj','eye_fanout.c.obj','eye_event.c.obj']), members
            assert entries==['__zinitcall_run_eye_entry'], entries
            image=(SDK/'output/ws63/fwpkg/ws63-liteos-app/ws63-liteos-app_all.fwpkg').read_bytes()
            assert b'EYE role=' in image and b'[sle uart client]' not in image and b'[sle uart server]' not in image, 'Stale official demo in package'
        result['linked_sample_members']=members
        result['application_init_entries']=entries
        artifacts=[]
        for source in [SDK/'output/ws63/fwpkg/ws63-liteos-app/ws63-liteos-app_all.fwpkg',
                       SDK/'output/ws63/acore/ws63-liteos-app/ws63-liteos-app.elf',HEADER,CONFIG]+([dest/'eye_build_config.h'] if project else []):
            assert source.is_file() and source.stat().st_size>0
            target=dest/source.name
            if source.resolve()!=target.resolve(): shutil.copy2(source,target)
            artifacts.append(dict(path=str(target),bytes=target.stat().st_size,sha256=digest(target)))
        result.update(build='passed',target=TARGET,sdk_url='https://gitee.com/bearpi/bearpi-pico_h3863.git',
                      scope='Group UART1/SLE button-event firmware; A central, unique B/C/D servers; TEST logs only; LIVE requires teammate acceptance hook.' if project else 'Official UART0 SLE baseline only.',
                      uart=dict(bus=bus,tx_gpio=tx,rx_gpio=rx,baud=115200,format='8N1',initialized=project and args.role=='bridge'),
                      sources=source_hash,artifacts=artifacts)
        print(json.dumps(result,indent=2),flush=True)
    except BaseException as error:
        result.update(build='failed',error=str(error)); raise
    finally:
        HOOK.write_bytes(original)
        result_path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        lock.unlink()
if __name__=='__main__': main()
