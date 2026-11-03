"""Create a local-only care-screen package, verifying actual ELF image bytes."""
from pathlib import Path
import hashlib,json,re,struct,zipfile
ROOT=Path(__file__).resolve().parents[1]
STAGE=ROOT/'build/receiver_upgrade_20261102'
SOURCE=ROOT/'comm/receiver_upgrade'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def symbols(path):
    raw=path.read_bytes();assert raw[:6]==b'\x7fELF\x01\x01'
    offset=struct.unpack_from('<I',raw,32)[0]
    size,count=struct.unpack_from('<HH',raw,46)
    sections=[struct.unpack_from('<10I',raw,offset+i*size) for i in range(count)]
    found={}
    for section in sections:
        if section[1]!=2:continue
        strings=sections[section[6]];names=raw[strings[4]:strings[4]+strings[5]]
        for pos in range(section[4],section[4]+section[5],section[9]):
            name,value,length,info,other,index=struct.unpack_from('<IIIBBH',raw,pos)
            key=names[name:names.find(b'\0',name)].decode('ascii',errors='replace')
            if key.startswith('ui_') and index<len(sections):
                data=sections[index];start=data[4]+value-data[3]
                found[key]=raw[start:start+length]
    return found
def main():
    software=json.loads((ROOT/'build/software/result.json').read_text())
    host=json.loads((STAGE/'host/result.json').read_text())
    assert software['passed'] and software['tests']==488 and host['host']=='passed'
    builds={};files={};elf_images={}
    def add(p,name=None):
        p=Path(p);files[name or p.relative_to(ROOT).as_posix()]=p
    for node in ('02','03','04'):
        directory=STAGE/'firmware'/f'{node}_care_ui_final'
        result=json.loads((directory/'result.json').read_text())
        assert result['build']=='passed' and not result['flashed']
        app=SOURCE/'receivers/application/samples/products/sle_uart'
        assert result['sources']=={p.relative_to(app).as_posix():sha(p) for p in app.rglob('*') if p.is_file()}
        builds[node]=result
        if node!='02':
            actual=symbols(directory/'ws63-liteos-app.elf')
            header=(app/f'wearable_ui_assets_{node}.h').read_text()
            arrays=re.findall(r'static const uint8_t (ui_\w+)\[\] = \{(.*?)\};',header,re.S)
            assert len(arrays)==7
            for name,values in arrays:
                expected=bytes(int(x) for x in re.findall(r'\d+',values))
                assert actual[name]==expected,(node,name)
            elf_images[node]=dict(images=7,exact_bytes_match=True)
        for row in result['artifacts']:
            p=directory/row['path'];assert sha(p)==row['sha256']
            if p.suffix in ('.fwpkg','.h','.config'):add(p,'install/'+node+'/'+p.name)
        add(directory/'result.json','install/'+node+'/build_result.json')
        rollback=ROOT/'imports/Eye_Wireless_Upgrade_Handoff_20261101/bearpi/firmware'/node/'ws63-liteos-app_all.fwpkg'
        add(rollback,'rollback/'+node+'/'+rollback.name)
    for p in SOURCE.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:add(p)
    baseline_hmi=Path('D:/Eye_tracker_system/comm/integration/four_board_20261030/received/02_serial_screen/bearpi_care_screen_v6.HMI')
    assert sha(baseline_hmi)==sha(SOURCE/'hmi/baseline_v6.HMI')
    rollback_tft=SOURCE/'hmi/baseline_v6.tft'
    assert rollback_tft.stat().st_size==2043240
    add(SOURCE/'hmi/eye_care_upgrade.tft','install/02/eye_care_upgrade.tft')
    add(rollback_tft,'rollback/02/baseline_v6.tft')
    for n in ('prepare_receiver_upgrade','build_receiver_assets','build_receiver_firmware','verify_receiver_ui','package_receiver_ui'):
        add(ROOT/'tools'/f'{n}.py')
    add(ROOT/'docs/receiver_displays.md','README.md')
    add(STAGE/'assets/care_preview.png','preview.png')
    add(STAGE/'host/result.json','evidence/host_result.json')
    add(ROOT/'build/software/result.json','evidence/software_result.json')
    hashes={n:sha(p) for n,p in files.items()}
    package=STAGE/'receiver_care_ui_local_ready.zip'
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
        for n,p in files.items():z.write(p,n)
        z.writestr('MANIFEST.json',json.dumps(hashes,indent=2))
    with zipfile.ZipFile(package) as z:
        assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in hashes.items())
    result=dict(stage='receiver care display, phase 1',state='local_ready_hardware_pending',
                software=software,host=host,elf_image_verification=elf_images,
                builds={n:{'directory':str(STAGE/'firmware'/f'{n}_care_ui_final'),'artifacts':r['artifacts']} for n,r in builds.items()},
                package=dict(path=str(package),sha256=sha(package),bytes=package.stat().st_size,verified_entries=len(hashes)),
                hmi_compiler=dict(version='1.68.1',model='TJC4827T143_011',errors=0,warnings=0,bytes=2372852),
                rollback_hmi=dict(original_source_sha256=sha(baseline_hmi),source_copy_identical=True,
                                  tft_sha256=sha(rollback_tft),bytes=2043240,rebuilt_not_flash_readback=True),
                hmi_simulator=dict(picture_ids_reviewed=[3,4,5,6,7,8,9],ack_hex='A5 02 5A',done_hex='A5 01 5A',connected_to_device=False),
                checkpoint=json.loads((STAGE/'preparation.json').read_text()),
                board_connected=False,flashed_nodes=[],pynq_changed=False,baseline_written=False,
                pending=['Establish ownership and identify COM-to-node mapping',
                         'Confirm serial-screen update adapter or spare screen TF card',
                         'Staged 03 then 04 then 02 display/firmware validation with rollback',
                         'HELLO/TEST then real-eye LIVE and mixed functionality',
                         'Phase 2 fixed expressions/emotions and phase 3 explicit text/opt-in activity sharing'])
    (STAGE/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(state=result['state'],elf_images=elf_images,package=result['package']),ensure_ascii=False))
if __name__=='__main__':main()
