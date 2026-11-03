"""Portable build entry points. Never connects to hardware or flashes firmware."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def load(name):
    spec=importlib.util.spec_from_file_location('reproduce_'+name, ROOT/'tools'/f'{name}.py')
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def run(command, cwd):
    print(' '.join(map(str, command)), flush=True)
    subprocess.run(list(map(str,command)), cwd=cwd, check=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('target', choices=['fpga_base','fpga_neural','native_eye','tiny_runtime','receiver'])
    ap.add_argument('--label', required=True, help='A new output folder name: letters, digits and underscores.')
    ap.add_argument('--vivado', default=os.environ.get('VIVADO_BIN','vivado'))
    ap.add_argument('--cc', default=os.environ.get('CC','gcc'))
    ap.add_argument('--arm', action='store_true', help='Compile Cortex-A9/NEON ARMv7 binaries.')
    ap.add_argument('--node', choices=['01','02','03','04'])
    ap.add_argument('--sdk', type=Path, help='Existing pinned SDK source folder containing build.py; copied before edits.')
    args=ap.parse_args()
    if not args.label or any(not (c.isascii() and (c.isalnum() or c=='_')) for c in args.label):
        ap.error('Use an ASCII letters/digits/underscore label.')
    out=ROOT/'build/reproduced'/args.label
    out.mkdir(parents=True,exist_ok=False)
    if args.target.startswith('fpga_'):
        for folder in ['rtl','scripts','constraints','sim']:
            shutil.copytree(ROOT/'fpga'/folder,out/'fpga'/folder)
        if args.target=='fpga_neural':
            module=load('build_neural_overlay');module.ROOT=out
            module.OUT=out/'build/neural_upgrade_20261103/fpga';module.VIVADO=args.vivado
            module.main()
        else:
            for script in ['create_project.tcl','build_project.tcl']:
                run([args.vivado,'-mode','batch','-source',out/'fpga/scripts'/script,
                     '-log',out/(script+'.log'),'-journal',out/(script+'.jou')],out)
    elif args.target in ['native_eye','tiny_runtime']:
        flags=['-std=c11','-O3']
        if args.arm: flags+=['-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard']
        if args.target=='native_eye':
            shared='neural_cpu.so' if args.arm or os.name!='nt' else 'neural_cpu.dll'
            if args.arm or os.name!='nt': flags+=['-fPIC']
            run([args.cc,*flags,'-shared','-o',out/shared,ROOT/'native/neural_cpu.c','-lm'],out)
            # Train/export your own user model before inference; no personal model is published.
        else:
            source=ROOT/'build/edge_ai_v2_20261103/tiny'
            for name in ['tiny_run.c','win.h']: shutil.copy2(source/name,out/name)
            exe='tiny_run' if args.arm or os.name!='nt' else 'tiny_run.exe'
            run([args.cc,*flags,'-Wno-unknown-pragmas','-o',out/exe,out/'tiny_run.c','-lm'],out)
            for name in ['minimind_q8.bin','tokenizer.json']:
                shutil.copy2(ROOT/'assets/ai'/name,out/name)
    else:
        if not args.node or not args.sdk or not (args.sdk/'build.py').is_file():
            ap.error('receiver requires --node and --sdk pointing to SDK src containing build.py')
        lock=json.loads((ROOT/'comm/receiver_upgrade/sdk_lock.json').read_text())
        for row in lock['selected_files']:
            actual=hashlib.sha256((args.sdk/row['path']).read_bytes()).hexdigest()
            if actual!=row['sha256']: raise ValueError('SDK fingerprint mismatch: '+row['path'])
        sdk=out/'comm/fbb_sdk_upgrade/src'
        def ignore(path,names):
            return [n for n in names if n in ['.git','__pycache__'] or
                    (n=='output' and Path(path).resolve()==args.sdk.resolve())]
        shutil.copytree(args.sdk,sdk,ignore=ignore)
        shutil.copytree(ROOT/'comm/receiver_upgrade',out/'comm/receiver_upgrade')
        module=load('build_receiver_firmware');module.ROOT=out;module.SDK=sdk
        module.SOURCE=out/'comm/receiver_upgrade';module.STAGE=out/'build/receiver_sharing_20261102'
        # Ensure CMake/Ninja/RISC-V tools are on PATH; the historical fallback paths are harmless if absent.
        old=sys.argv;sys.argv=['build_receiver_firmware.py',args.node,'--label','reproduced']
        try: module.main()
        finally: sys.argv=old
    (out/'reproduction.json').write_text(json.dumps({'target':args.target,'source_root':str(ROOT),
        'completed':True,'board_connected':False},indent=2),encoding='utf-8')
    print('BUILD_COMPLETED '+str(out))

if __name__=='__main__': main()
