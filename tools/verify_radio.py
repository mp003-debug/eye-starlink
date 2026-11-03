"""Host test real radio C adapter against pinned SDK declarations and mocked stack.

This checks state transitions/callback ownership, never RF, pairing interoperability
or real scheduling. Each scenario gets a fresh process, as firmware gets a fresh boot.
"""
import argparse,hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cc',default=__import__('os').environ.get('CC','gcc'))
    args=parser.parse_args()
    out=ROOT/'comm/build/radio_host';out.mkdir(parents=True,exist_ok=True)
    tests=ROOT/'comm/firmware/tests';sdk=ROOT/'comm/sdk/include'
    env=os.environ.copy();env['PATH']=str(Path(args.cc).parent)+os.pathsep+env.get('PATH','')
    includes=[tests,ROOT/'comm/firmware',sdk,sdk/'driver',sdk/'middleware/services/bts/sle']
    sources=[ROOT/'comm/firmware/eye_radio.c',tests/'radio_host.c']
    scenarios=['init_failure','enable_callback_failure','bad_subscription','flow','tx_timeout','tx_call_failure',
               'tx_confirm_failure','wrong_confirmation','callback_overflow','rx_overflow','clock_regression']
    results=[];failures=[]
    for role,node,mask,harness in [('bridge_single',0,1,'radio_host.c'),('receiver_B',1,7,'radio_host.c'),('receiver_C',2,7,'radio_host.c'),('receiver_D',3,7,'radio_host.c'),('bridge_group',0,7,'radio_multi_host.c')]:
        sources=[ROOT/'comm/firmware/eye_radio.c',tests/harness]
        exe=out/(role+'.exe')
        command=[args.cc,'-std=c99','-Wall','-Wextra','-Werror','-O2','-DEYE_NODE_ID='+str(node),'-DEYE_REQUIRED_MASK='+str(mask)]
        command.extend('-I'+str(p) for p in includes)
        command.extend(str(p) for p in sources);command.extend(['-o',str(exe)])
        run=subprocess.run(command,capture_output=True,text=True,env=env)
        (out/(role+'_compile.log')).write_text(run.stdout+run.stderr,encoding='utf-8')
        if run.returncode:
            failures.append(dict(role=role,stage='compile',details=run.stderr));continue
        for scenario in (['group','reconnect','partial_setup','unknown_peer','buffer_isolation'] if role=='bridge_group' else scenarios+(['wrong_property'] if node==0 else [])):
            run=subprocess.run([str(exe),scenario],capture_output=True,text=True,env=env,timeout=5)
            (out/(role+'_'+scenario+'.log')).write_text(run.stdout+run.stderr,encoding='utf-8')
            if run.returncode:failures.append(dict(role=role,stage=scenario,details=run.stderr))
            else:
                row=json.loads(run.stdout.strip().splitlines()[-1]);row.update(role=role,node=node,required_mask=mask);results.append(row)
    result=dict(passed=not failures,scenarios=len(results),assertions=sum(p['assertions'] for p in results),
                checks=results,failures=failures,radio_or_board_tested=False,
                scope='Real C adapter + real SDK API declarations, mocked stack callbacks; no RF/interoperability claim',
                sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in [ROOT/'comm/firmware/eye_radio.c',tests/'radio_host.c',tests/'radio_multi_host.c',ROOT/'comm/firmware/eye_radio.h',tests/'soc_osal.h',Path(__file__)]})
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if failures:raise SystemExit(1)
if __name__=='__main__':main()
