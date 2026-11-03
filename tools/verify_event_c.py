"""Compile portable C reference and compare real C output against Python.

Build artifacts stay under comm/build/protocol. No SDK/radio/board interaction.
"""
import argparse,json,os,random,subprocess,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from eye_tracker.event_protocol import *


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cc',default=__import__('os').environ.get('CC','gcc'))
    args=parser.parse_args()
    out=ROOT/'comm/build/protocol';out.mkdir(parents=True,exist_ok=True)
    env=os.environ.copy();env['PATH']=str(Path(args.cc).parent)+os.pathsep+env.get('PATH','')
    command=[args.cc,'-std=c99','-Wall','-Wextra','-Werror','-O2',str(ROOT/'comm/protocol/eye_event.c'),
             str(ROOT/'comm/protocol/host_check.c'),'-o',str(out/'host_check.exe')]
    build=subprocess.run(command,capture_output=True,text=True,env=env)
    (out/'compile.log').write_text(build.stdout+build.stderr,encoding='utf-8')
    if build.returncode:raise RuntimeError('C compilation failed: '+build.stderr)
    rng=random.Random(3863);records=[];vectors=[]
    now=0
    for session in range(1,25):
        hello=Packet(HELLO,session,0,0,TEST);records.append((now,hello.encode()))
        for seq in range(1,18):
            now+=10
            p=Packet(EVENT,session,seq,1+seq%5,TEST)
            records.append((now,p.encode()))
            records.append((now+1,p.encode()))  # duplicate ACK, no second delivery
            records.append((now+2,Packet(EVENT,session,seq,99,TEST).encode()))
            if seq%4==0:records.append((now+3,hello.encode()))
            bad=bytearray(p.encode());bad[rng.randrange(16)]^=1
            records.append((now+4,bytes(bad)))
        now+=2200  # expired session must reject direct event
        records.append((now,Packet(EVENT,session,200,2,TEST).encode()))
        now+=10
    decoder=Decoder();receiver=Receiver(allow_test=True);expected=[]
    for t,raw in records:
        for p in decoder.feed(raw):
            ack,deliver=receiver.receive(p,t)
            expected.append(ack.encode().hex()+' '+str(int(deliver)) if ack else 'none')
    stdin=''.join(str(t)+' '+raw.hex()+'\n' for t,raw in records)
    run=subprocess.run([str(out/'host_check.exe')],input=stdin,capture_output=True,text=True,env=env)
    actual=run.stdout.splitlines()
    if run.returncode or actual!=expected:
        raise RuntimeError('C/Python mismatch: '+str((run.returncode,len(actual),len(expected)))+' '+run.stderr)
    for p in (Packet(HELLO,0x12345678,0,0,TEST),Packet(EVENT,0x12345678,1,1,TEST),
              Packet(ACK,0x12345678,1,1,OK),Packet(ACK,0x12345678,1,1,DUPLICATE)):
        vectors.append(dict(kind=p.kind,session=p.session,sequence=p.sequence,code=p.code,detail=p.detail,hex=p.encode().hex()))
    (ROOT/'comm/protocol/vectors.json').write_text(json.dumps(vectors,indent=2)+'\n',encoding='utf-8')
    cross=r'comm/sdk/tools/bin/compiler/riscv/cc_riscv32_musl_105/cc_riscv32_musl_win/bin/riscv32-linux-musl-gcc.exe'
    cross_env=os.environ.copy()
    cross_env['PATH']='D:/hispark_studio/HiSpark Studio/tools/Windows/cc_riscv32_win_env'+os.pathsep+cross_env.get('PATH','')
    cross_run=subprocess.run([str(ROOT/cross),'-std=c99','-Wall','-Wextra','-Werror','-O2','-c',
                              str(ROOT/'comm/protocol/eye_event.c'),'-o',str(out/'eye_event_riscv.o')],
                             capture_output=True,text=True,env=cross_env)
    (out/'riscv_compile.log').write_text(cross_run.stdout+cross_run.stderr,encoding='utf-8')
    if cross_run.returncode:raise RuntimeError('SDK RISC-V object compile failed: '+cross_run.stderr)
    result=dict(passed=True,riscv_object_compile_passed=True,compiler=args.cc,input_chunks=len(records),matched_responses=len(expected),
                decoded_deliveries=sum(line.endswith(' 1') for line in expected),
                rejected_crc_frames=decoder.bad_frames,embedded_or_radio_tested=False,
                sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted((ROOT/'comm/protocol').glob('*.[ch]'))})
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
