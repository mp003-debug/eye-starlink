"""Verify source/build/loader identity and package this private candidate only."""
from pathlib import Path
import hashlib,json,re,struct,zipfile
ROOT=Path(__file__).resolve().parents[1];STAGE=ROOT/'build/receiver_sharing_20261102'
SOURCE=ROOT/'comm/receiver_upgrade';PREV=ROOT/'build/receiver_upgrade_20261102'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def segments(path):
    raw=path.read_bytes();magic,crc,count,total=struct.unpack_from('<IHHI',raw)
    assert magic==0xefbeaddf and total==len(raw) and count==7
    result=[]
    for i in range(count):
        name,start,size,address,capacity,kind=struct.unpack_from('<32sIIIII',raw,12+i*52)
        assert start+size<=len(raw) and size<=capacity
        result.append(dict(name=name.rstrip(b'\0').decode(),bytes=size,address=address,capacity=capacity,
            kind=kind,sha256=hashlib.sha256(raw[start:start+size]).hexdigest()))
    return result
def elf_symbols(path):
    raw=path.read_bytes();assert raw[:6]==b'\x7fELF\x01\x01'
    offset=struct.unpack_from('<I',raw,32)[0];size,count=struct.unpack_from('<HH',raw,46)
    sections=[struct.unpack_from('<10I',raw,offset+i*size) for i in range(count)];found={}
    for section in sections:
        if section[1]!=2:continue
        strings=sections[section[6]];names=raw[strings[4]:strings[4]+strings[5]]
        for pos in range(section[4],section[4]+section[5],section[9]):
            name,value,length,info,other,index=struct.unpack_from('<IIIBBH',raw,pos)
            key=names[name:names.find(b'\0',name)].decode('ascii',errors='replace')
            if (key.startswith('ui_') or key=='share_font') and index<len(sections):
                data=sections[index];start=data[4]+value-data[3];found[key]=raw[start:start+length]
    return found
def main():
    software=json.loads((ROOT/'build/software/result.json').read_text())
    assert software['passed'] and software['tests']>=502
    host=json.loads((STAGE/'host/result.json').read_text());chain=json.loads((STAGE/'host/chain_result.json').read_text())
    assert host['passed'] and chain['passed']
    files={};builds={};checks={}
    def add(p,name=None):files[name or p.relative_to(ROOT).as_posix()]=p
    for node in ('01','02','03','04'):
        directory=STAGE/'firmware'/(node+('_final' if node=='01' else '_candidate'))
        r=json.loads((directory/'result.json').read_text());assert r['build']=='passed' and not r['flashed']
        app=SOURCE/('central01' if node=='01' else 'receivers')/'application/samples/products/sle_uart'
        assert r['sources']=={p.relative_to(app).as_posix():sha(p) for p in app.rglob('*') if p.is_file()},node
        fw=directory/'ws63-liteos-app_all.fwpkg'
        old=(ROOT/'imports/Eye_Wireless_Upgrade_Handoff_20261101/bearpi/firmware/01/ws63-liteos-app_all.fwpkg'
            if node=='01' else PREV/'firmware'/(node+'_care_ui_final')/fw.name)
        new_segments=segments(fw);old_segments=segments(old)
        assert new_segments[:4]==old_segments[:4],node+' boot loaders changed'
        assert [(x['address'],x['kind']) for x in new_segments]==[(x['address'],x['kind']) for x in old_segments]
        assert new_segments[-1]['address']==0x230000 and new_segments[-1]['bytes']<=0x230000
        images=0;font_bytes=0
        if node in ('03','04'):
            symbols=elf_symbols(directory/'ws63-liteos-app.elf')
            header=(app/f'wearable_ui_assets_{node}.h').read_text()
            for name,data in re.findall(r'static const uint8_t (ui_\w+)\[\] = \{(.*?)\};',header,re.S):
                assert symbols[name]==bytes(int(x) for x in re.findall(r'\d+',data));images+=1
            font=(app/'eye_link/eye_share_font.h').read_text().split('{',1)[1].split('}',1)[0]
            expected=bytes(int(x) for x in re.findall(r'\d+',font));assert symbols['share_font']==expected
            font_bytes=len(expected);assert images==7 and font_bytes==595656
        for row in r['artifacts']:
            p=directory/row['path'];assert sha(p)==row['sha256']
            if p.suffix in ('.fwpkg','.h','.config'):add(p,'install/'+node+'/'+p.name)
        add(directory/'result.json','install/'+node+'/build_result.json');add(old,'rollback/'+node+'/'+old.name)
        builds[node]=dict(directory=directory.relative_to(ROOT).as_posix(),artifacts=r['artifacts'])
        checks[node]=dict(segments=new_segments,first_four_loader_segments_unchanged=True,care_images=images,font_bytes=font_bytes)
    # Compare the accepted runtime package; only the reviewed integration files
    # and the new UI glyph atlas may differ from the accepted 146-file runtime.
    allowed={'src/eye_tracker/'+n+'.py' for n in ('appearance_trial','board','daily_tools','event_link','launch','trial_events','visual_theme')}
    allowed.add('assets/typing/glyphs.npz')
    with zipfile.ZipFile(PREV/'eye_tracker_upgrade_receiver_care_verified.zip') as z:
        manifest=json.loads(z.read('upgrade_manifest.json'))['files']
        changed=[n for n,row in manifest.items() if sha(ROOT/n)!=row['sha256']]
    assert set(changed)<=allowed,changed
    for p in SOURCE.rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts:add(p)
    # No HMI rewrite: the accepted TFT and its compile project remain exact.
    with zipfile.ZipFile(PREV/'receiver_care_ui_verified.zip') as z:
        for n in ('eye_care_upgrade.HMI','eye_care_upgrade.tft'):
            key='comm/receiver_upgrade/hmi/'+n
            assert hashlib.sha256(z.read(key)).hexdigest()==sha(SOURCE/'hmi'/n)
    for n in ('build_receiver_firmware','build_share_font','verify_receiver_sharing','verify_sharing_chain','preview_receiver_sharing','package_receiver_sharing'):
        add(ROOT/'tools'/(n+'.py'))
    add(ROOT/'tools/flash_receiver_sharing.ps1')
    for p in (STAGE/'previews').glob('*.png'):add(p,'previews/'+p.name)
    add(ROOT/'docs/receiver_sharing.md','README.md')
    add(STAGE/'host/result.json','evidence/host.json');add(STAGE/'host/chain_result.json','evidence/offline_chain.json')
    add(ROOT/'build/software/result.json','evidence/software.json')
    add(ROOT/'build/software/tests.txt','evidence/software_tests.txt')
    hashes={n:sha(p) for n,p in files.items()};package=STAGE/'receiver_sharing_candidate.zip'
    assert not package.exists(),'preserve existing package; choose an explicit new candidate name'
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
        for n,p in files.items():z.write(p,n)
        z.writestr('MANIFEST.json',json.dumps(hashes,indent=2))
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in hashes.items())
    result=dict(stage='receiver sharing phases 2+3',state='local_ready_hardware_pending',software=software,
        host=host,offline_chain=chain,builds=builds,firmware_checks=checks,
        runtime_protection=dict(previous_files=len(manifest),unchanged=len(manifest)-len(changed),reviewed_changed=changed,
            private_favorites_volume_bookmarks_excluded_from_deployment=True),
        hmi=dict(existing_tft_unchanged=True,simulator_version='1.68.1',font0_height=24,
            reviewed=['64 characters with final marker','quoted text and backslash'],hardware_connected=False),
        checkpoint_sha256=sha(STAGE/'before_sharing.zip'),
        package=dict(path=package.relative_to(ROOT).as_posix(),sha256=sha(package),bytes=package.stat().st_size,entries=len(hashes)),
        board_connected=False,flashed_nodes=[],baseline_written=False,
        pending=['current exclusive ownership and node identity','update four nodes; receivers before bridge',
                 'silent v1/v2 TEST then unified real-eye operation and mixed media checks',
                 'per-node dropout recovery and actual screen latency'])
    (STAGE/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('state','runtime_protection','package')},ensure_ascii=False))
if __name__=='__main__':main()
