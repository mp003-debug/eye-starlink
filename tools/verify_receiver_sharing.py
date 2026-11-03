"""Compile actual C receiver logic with fake HAL; no hardware connection."""
import subprocess,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
APP=ROOT/'comm/receiver_upgrade/receivers/application/samples/products/sle_uart'
LINK=APP/'eye_link';TEST=ROOT/'comm/receiver_upgrade/tests'
OUT=ROOT/'build/receiver_sharing_20261102/host';OUT.mkdir(parents=True,exist_ok=True)
GCC=Path(__import__('os').environ.get('CC','gcc'))
results=[]
for name in ('share','hmi','epd','epd04','share_display'):
    source=TEST/('epd_host.c' if name=='epd04' else name+'_host.c')
    command=[str(GCC),'-std=c99','-Wall','-Wextra','-Werror','-Wno-unused-function',
        '-Wno-unused-variable','-Wno-missing-field-initializers','-I'+str(TEST),'-I'+str(LINK),'-I'+str(APP),str(source)]
    if name=='share':command += [str(LINK/n) for n in ('eye_event.c','eye_share.c','eye_endpoint.c','eye_fanout.c')]
    elif name=='hmi':command += [str(LINK/n) for n in ('eye_event.c','eye_endpoint.c')]
    else:command += [str(LINK/'eye_share_render.c')]
    if name=='epd04':command+=['-DCONFIG_EYE_LINK_NODE_D=1']
    if name=='epd':command+=['-DCONFIG_EYE_LINK_NODE_C=1']
    exe=OUT/(name+'.exe')
    subprocess.run(command+['-o',str(exe)],check=True,cwd=ROOT)
    result=subprocess.check_output([str(exe)],text=True,cwd=OUT).strip();print(result);results.append(result)
(OUT/'result.json').write_text(json.dumps(dict(passed=True,scenarios=results,hardware_tested=False),indent=2),encoding='utf-8')
