"""Python sender -> actual C bridge -> three C endpoints, entirely offline."""
from pathlib import Path
import ctypes,json,subprocess,sys,os
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from eye_tracker.share_link import SharingEventLink
from eye_tracker.share_protocol import TEXT
from eye_tracker.interaction import Action
LINK=ROOT/'comm/receiver_upgrade/receivers/application/samples/products/sle_uart/eye_link'
OUT=(ROOT/os.environ.get('EYE_SHARING_CHECK_OUTPUT','build/receiver_sharing_20261102/host')).resolve()
if (ROOT/'build').resolve() not in OUT.parents:raise ValueError('check output must stay in upgrade build')
OUT.mkdir(parents=True,exist_ok=True)
GCC=__import__('os').environ.get('CC','gcc')
target=OUT/'sharing_chain.dll'
subprocess.run([GCC,'-std=c99','-Wall','-Werror','-shared','-I'+str(LINK),
    str(ROOT/'comm/receiver_upgrade/tests/share_chain_host.c')]+[str(LINK/n) for n in
    ('eye_event.c','eye_endpoint.c','eye_fanout.c','eye_share.c')]+['-o',str(target)],check=True)
lib=ctypes.CDLL(str(target));lib.chain_exchange.argtypes=[ctypes.c_char_p,ctypes.c_uint64,ctypes.c_void_p]
class Wire:
    def __init__(self):self.reply=b'';self.now=0
    def reset(self):self.reply=b''
    def read(self):raw=self.reply;self.reply=b'';return raw
    def try_write(self,raw):
        out=ctypes.create_string_buffer(16)
        if lib.chain_exchange(raw,int(self.now),out):self.reply=out.raw
        return True
def ready(test=False):
    lib.chain_reset();wire=Wire();link=SharingEventLink(wire,wire_test=test,session_factory=iter(range(1,100)).__next__)
    for now in range(0,200,10):wire.now=now;link.service(now)
    assert link.capable_session==link.session
    return wire,link
def tick(w,l,start,end,step=100):
    for now in range(start,end,step):w.now=now;l.service(now)
cases=[]
for test in (False,True):
    w,l=ready(test);body='你'*63+'完'
    assert l.submit_share(Action('tool_slot_0','','live',200),TEXT,body,200)
    tick(w,l,200,8000)
    assert l.counts['share_accepted']==1 and l.transfer is None
    for peer in range(3):
        assert lib.chain_messages(peer)==(0 if test else 1)
        if not test:
            raw=ctypes.create_string_buffer(128);n=lib.chain_text(peer,raw)
            assert raw.raw[:n].decode('gb2312')==body
    cases.append('64 characters with three receivers, '+('TEST no display' if test else 'LIVE model'))
for body in ('是','你'*63+'完'):
    w,l=ready()
    assert l.submit_share(Action('tool_slot_0','','live',200),TEXT,body,200)
    w.now=200;l.service(200)
    for now in range(300,8200,100):
        w.now=now;l.service(now,enabled=False)
    assert l.counts['share_accepted']==1 and l.transfer is None
    for peer in range(3):
        assert lib.chain_messages(peer)==1
        raw=ctypes.create_string_buffer(128);n=lib.chain_text(peer,raw)
        assert raw.raw[:n].decode('gb2312')==body
    cases.append(str(len(body))+' characters finish once during prolonged unknown gaze after explicit confirmation')
w,l=ready();lib.chain_drop(2)
assert l.submit_share(Action('tool_slot_0','','live',200),TEXT,'你好',200)
tick(w,l,200,900,50)
assert l.counts['share_accepted']==0 and all(lib.chain_messages(i)==0 for i in range(3))
cases.append('missing third receiver ACK cannot commit or report success')
w,l=ready();assert l.submit_share(Action('tool_slot_0','','live',200),TEXT,'你好'*32,200)
tick(w,l,200,600,50)
w.now=600;l.service(600,allow_heartbeat=False)
assert l.submit(Action('help','','live',600),600)
tick(w,l,600,800,20)
assert l.counts['remote_accepted']==1
assert all(lib.chain_care(i)==3 and lib.chain_messages(i)==0 for i in range(3))
cases.append('real v1 help preempts an unfinished v2 message through bridge')
assert l.submit_share(Action('tool_slot_0','','live',800),TEXT,'你好',800)
tick(w,l,800,1400,50)
assert l.counts['share_accepted']==0 and all(lib.chain_care(i)==3 for i in range(3))
cases.append('ordinary message cannot replace pending care')
result=dict(passed=True,cases=cases,hardware_tested=False)
(OUT/'chain_result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
