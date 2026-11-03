"""Generate learned-network golden vectors and run a fresh AXI/RTL simulation."""
from pathlib import Path
import hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import numpy as np
from eye_tracker.neural import NeuralModel,quantize
from eye_tracker.neural_accel import packed_weights
OUT=ROOT/'build/neural_upgrade_20261103/rtl'
BIN=Path('D:/AMDDesignTools/2026.1/Vivado/bin')

def vectors():
    OUT.mkdir(parents=True,exist_ok=True)
    model=NeuralModel(OUT.parent/'model/model.npz');weights,blocks=packed_weights(model)
    lines=[]
    def op(code,address=0,data=0,response=0,strobe=15):lines.append(f'{code:x} {address:x} {int(data)&0xffffffff:08x} {response:x} {strobe:x}')
    def wr(a,d,r=0,s=15):op(0,a,d,r,s)
    def rd(a,d,r=0):op(1,a,d,r)
    rd(0,0x4e4e3332);rd(4,0x10000);rd(0x2000,0,2)
    wr(8,1,2);wr(0x10,0,2);wr(0x10,2049,2);wr(0x18,33,2)
    wr(0x10001,3,2);wr(0x10000,3,2,3);wr(0x10004,3,2)
    wr(0x1004,3,2);rd(0x30000,0,2);rd(1,0,2)
    for i,w in enumerate(np.frombuffer(weights.tobytes(),'<u4')):wr(0x10000+4*i,w)
    rd(0x1c,len(weights))
    features=np.load(OUT.parent/'evaluation_features.npz')['features']
    cases=0;compares=0
    for f in features:
        x=f.astype(np.float64)*2-1
        for layer in range(3):
            q=quantize(x,model.ascale[layer]);gold=q.astype(np.int32)@model.qweights[layer].astype(np.int32)
            for i,w in enumerate(np.frombuffer(q.tobytes(),'<u4')):wr(0x1000+4*i,w)
            first=0
            for base,n,count in blocks[layer]:
                wr(0x10,n);wr(0x14,base);wr(0x18,count);wr(8,1)
                if cases==0:
                    wr(0x10000,0,2);wr(0x1000,0,2);wr(0x10,12,2);wr(8,1,2);rd(0x2000,0,2)
                op(2)
                rd(0x24,n+2)
                for j in range(count):rd(0x2000+4*j,gold[first+j]);compares+=1
                rd(0x2000+4*count,0,2);first+=count;cases+=1
            x=gold.astype(np.float64)*model.ascale[layer]*model.wscale[layer]+model.biases[layer]
            if layer<2:x=np.maximum(x,0)
    # Abort an in-flight long layer, reject stale outputs, clear requires reload.
    for i in range(288):wr(0x1000+i*4,0x7f817f81)
    wr(0x10,1152);wr(0x14,0);wr(0x18,32);wr(8,1);wr(8,2)
    rd(0xc,4);rd(0x2000,0,2);wr(8,1,2);wr(8,4);wr(8,1,2)
    # Extreme int8 arithmetic including -128, ragged length 7, tail 5 outputs.
    q=np.array([-128,127,-1,0,1,-127,126,0],np.int8)
    w=np.tile(np.array([-128,127,-1,1,0,126,-127],np.int8)[:,None],(1,32))
    for i,a in enumerate(np.frombuffer(w.tobytes(),'<u4')):wr(0x10000+4*i,a)
    for i,a in enumerate(np.frombuffer(q.tobytes(),'<u4')):wr(0x1000+4*i,a)
    wr(0x10,7);wr(0x14,0);wr(0x18,5);wr(8,1);op(2)
    golden=int(q[:7].astype(np.int32)@w[:,0].astype(np.int32))
    for j in range(5):rd(0x2000+4*j,golden)
    rd(0x2014,0,2)
    # AXI reset must drop residency and pending transactions.
    op(4);rd(0x1c,0);rd(0x20,0);wr(8,1,2);rd(0x2000,0,2)
    # Long input cannot start with too few initialized weight rows.
    wr(0x10,2048);wr(0x18,32);wr(0x14,4095);wr(8,1,2)
    # Rebuild a long operation for watchdog fault injection and reset while busy.
    for i in range(1152*8):wr(0x10000+4*i,0x81818181)
    for i in range(288):wr(0x1000+4*i,0x7f7f7f7f)
    wr(0x14,0);wr(0x10,1152);wr(8,1);op(5);rd(0xc,4);rd(0x2000,0,2)
    op(4);rd(0xc,0)
    # Fill the entire addressable weight RAM, exercise last row and max length.
    for i in range(4096*8):wr(0x10000+4*i,0x80808080)
    rd(0x1c,4096)
    for i in range(512):wr(0x1000+4*i,0x80808080)
    wr(0x10,2048);wr(0x14,2048);wr(0x18,32);wr(8,1);op(2);rd(0x24,2050)
    for i in range(32):rd(0x2000+4*i,2048*128*128)
    wr(0x10,1);wr(0x14,4095);wr(8,1);op(2)
    for i in range(32):rd(0x2000+4*i,128*128)
    # Reset during active MAC execution drops busy, pending AW, and residency.
    wr(0x10,2048);wr(0x14,0);wr(8,1);op(4)
    rd(0xc,0);rd(0x1c,0);rd(0x2000,0,2)
    (OUT/'commands.hex').write_text('\n'.join(lines)+'\n')
    return dict(model_sha256=model.sha256,network_frames=len(features),learned_blocks=cases,
                learned_dot_comparisons=compares,edge_dot_comparisons=69,commands=len(lines),
                full_network_core_cycles=2408,clock_hz=50000000)

def main():
    meta=vectors();stamp=OUT/'PASS.txt'
    if stamp.exists():stamp.unlink()
    sources=[ROOT/'fpga/rtl/neural_mac_axi.v',ROOT/'fpga/sim/tb_neural_mac.sv']
    for args in [['xvlog.bat','--sv',*[str(p) for p in sources]],['xelab.bat','tb_neural_mac','-s','nn_snapshot'],['xsim.bat','nn_snapshot','-runall']]:
        name=args[0];args[0]=str(BIN/name)
        with (OUT/(name+'.log')).open('w') as f:
            p=subprocess.run(args,cwd=OUT,stdout=f,stderr=subprocess.STDOUT)
        if p.returncode:raise RuntimeError(name+' failed')
    if not stamp.exists() or stamp.read_text().strip()!='PASS':raise RuntimeError('fresh_RTL_PASS_required')
    meta.update(passed=True,board_tested=False,sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    (OUT/'result.json').write_text(json.dumps(meta,indent=2));print(json.dumps(meta))

if __name__=='__main__':main()
