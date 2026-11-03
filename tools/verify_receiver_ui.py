"""Compile production receiver drivers with a fake HAL; never connects hardware."""
from pathlib import Path
import hashlib,json,subprocess
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'comm/receiver_upgrade'
STAGE=ROOT/'build/receiver_upgrade_20261102'
GCC=Path(__import__('os').environ.get('CC','gcc'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    out=STAGE/'host';out.mkdir(parents=True,exist_ok=True)
    link=SOURCE/'receivers/application/samples/products/sle_uart/eye_link'
    results=[]
    for name in ('hmi','epd','epd04'):
        exe=out/(name+'.exe')
        command=[str(GCC),'-std=c99','-Wall','-Wextra','-Werror','-Wno-unused-function',
                 '-Wno-unused-variable','-I'+str(SOURCE/'tests'),'-I'+str(link),
                 str(SOURCE/'tests'/f'{"epd" if name=="epd04" else name}_host.c')]
        if name=='epd04':command+=['-DCONFIG_EYE_LINK_NODE_D=1']
        if name=='hmi':command += [str(link/'eye_event.c'),str(link/'eye_endpoint.c')]
        subprocess.run(command+['-o',str(exe)],check=True,cwd=ROOT)
        result=subprocess.run([str(exe)],check=True,cwd=ROOT,text=True,capture_output=True)
        results.append(result.stdout.strip());print(result.stdout.strip())
    before=json.loads((STAGE/'before_hashes.json').read_text(encoding='utf-8'))
    protected={k:v for k,v in before.items() if k.startswith(('src/eye_tracker/','assets/','config/','data/private/'))}
    changed=[k for k,v in protected.items() if sha(ROOT/k)!=v]
    assert not changed,changed
    # Radio/transport/protocol and physical pin/display timing are unchanged.
    base=ROOT/'imports/Eye_Wireless_Upgrade_Handoff_20261101/bearpi/receivers/application/samples/products/sle_uart'
    app=SOURCE/'receivers/application/samples/products/sle_uart'
    for p in (base/'eye_link').glob('*'):
        if p.is_file():assert sha(p)==sha(app/'eye_link'/p.name),p.name
    assert sha(base/'wearable_epd.c')==sha(app/'wearable_epd.c')
    for p in (STAGE/'assets').glob('epd_*.png'):
        im=Image.open(p);assert im.size==(480,800) and im.mode=='1'
    for p in (SOURCE/'hmi/assets').glob('*.png'):assert Image.open(p).size==(480,272)
    tft=SOURCE/'hmi/eye_care_upgrade.tft';assert 0<tft.stat().st_size<8*1024*1024
    result=dict(host='passed',scenarios=results,protected_files=len(protected),protected_changed=changed,
                transport_protocol_unchanged=True,epd_driver_and_pins_unchanged=True,
                tft_bytes=tft.stat().st_size,tft_sha256=sha(tft),board_tested=False)
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
