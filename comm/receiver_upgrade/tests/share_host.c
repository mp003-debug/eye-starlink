#include <assert.h>
#include <string.h>
#include <stdio.h>
#include "eye_share.h"
#include "eye_endpoint.h"
#include "eye_fanout.h"
#include "eye_share_view.h"
static unsigned delivered,care;
static eye_message received;
static int accept(const eye_message *m,void *context) {
    (void)context;if(care)return EYE_SHARE_BLOCKED;received=*m;++delivered;return 1;
}
static int legacy(const eye_packet *p,void *c) {(void)p;(void)c;return 1;}
static eye_receiver receiver;
static eye_share_state sharing;
static unsigned sequence;
static uint64_t now;
static void start(unsigned test) {
    eye_init(&receiver,1);eye_share_reset(&sharing);sequence=0;now=1;
    eye_packet p={.kind=EYE_HELLO,.session=123,.detail=(uint8_t)test,.version=1},reply;
    assert(eye_endpoint_receive(&receiver,&p,now,&reply,legacy,legacy,NULL)==1 && reply.detail==0);
}
static eye_packet request(unsigned kind,unsigned code,unsigned detail,unsigned expected) {
    eye_packet p={.kind=(uint8_t)kind,.session=123,.sequence=++sequence,.code=(uint8_t)code,.detail=(uint8_t)detail,.version=2},reply;
    uint8_t frame[16];eye_packet decoded;
    assert(eye_encode(&p,frame) && eye_decode(frame,&decoded));
    assert(decoded.version==2 && decoded.code==code && decoded.detail==detail);
    assert(eye_share_receive(&sharing,&receiver,&decoded,++now,&reply,accept,NULL)==1);
    assert(reply.detail==expected);return p;
}
static eye_packet message(const uint8_t *text,unsigned length,unsigned category,unsigned expected) {
    request(EYE_SHARE_BEGIN,category,length,EYE_OK);
    for(unsigned i=0;i<length;i+=2)request(EYE_SHARE_DATA,text[i],i+1<length?text[i+1]:0,EYE_OK);
    uint16_t crc=eye_crc16(text,length);
    return request(EYE_SHARE_COMMIT,crc&255,crc>>8,expected);
}
int main(void) {
    const uint8_t hello[]={0xc4,0xe3,0xba,0xc3}; /* ni hao */
    start(0);request(EYE_SHARE_BEGIN,3,4,EYE_SHARE_UNSUPPORTED);
    request(EYE_CAPS,2,0,EYE_OK);
    eye_packet last=message(hello,4,3,EYE_OK),reply;
    assert(delivered==1 && received.length==4 && !memcmp(received.text,hello,4));
    assert(eye_share_receive(&sharing,&receiver,&last,++now,&reply,accept,NULL)==1 && reply.detail==EYE_DUPLICATE && delivered==1);
    /* Duplicate fragments cannot advance the buffer. */
    request(EYE_SHARE_BEGIN,3,4,EYE_OK);
    eye_packet data=request(EYE_SHARE_DATA,hello[0],hello[1],EYE_OK);
    assert(eye_share_receive(&sharing,&receiver,&data,++now,&reply,accept,NULL)==1 && reply.detail==EYE_DUPLICATE && sharing.received==2);
    request(EYE_SHARE_COMMIT,0,0,EYE_BAD_EVENT);assert(delivered==1);
    /* Maximum text and TEST isolation. */
    uint8_t full[128];for(unsigned i=0;i<128;i+=2) {full[i]=0xc4;full[i+1]=0xe3;}
    message(full,128,3,EYE_OK);assert(delivered==2);
    request(EYE_SHARE_BEGIN,3,129,EYE_BAD_EVENT);
    care=1;message(hello,4,3,EYE_SHARE_BLOCKED);assert(delivered==2);care=0;
    start(1);request(EYE_CAPS,2,1,EYE_OK);message(hello,4,3,EYE_OK);assert(delivered==2);
    /* Session expiry, assigned-character validation and fixed catalogue. */
    now+=2001;request(EYE_SHARE_BEGIN,3,4,EYE_NO_SESSION);
    start(0);request(EYE_CAPS,2,0,EYE_OK);
    const uint8_t injected[]={0x1b,'p'};message(injected,2,3,EYE_BAD_EVENT);
    message(hello,4,1,EYE_BAD_EVENT);
    /* Care cannot be replaced or revived after clear by an old mailbox. */
    eye_share_view view={0};eye_message m={.category=3,.length=4};memcpy(m.text,hello,4);
    assert(eye_share_publish(&view,&m,1)==EYE_SHARE_BLOCKED);
    assert(eye_share_publish(&view,&m,0)==1);eye_share_view_tick(&view,1,0);
    eye_share_view_tick(&view,0,1);assert(!view.visible);
    m.category=4;assert(eye_share_publish(&view,&m,0)==1);eye_share_view_tick(&view,0,5);
    eye_share_view_tick(&view,0,120005);assert(view.stale);
    /* Aggregator refuses a v1 ACK for a v2 request and requires all peers. */
    eye_fanout fan;eye_fanout_reset(&fan,7);last.kind=EYE_CAPS;last.sequence=55;last.code=2;
    assert(eye_fanout_request(&fan,&last,200));
    reply=last;reply.kind=EYE_ACK;reply.detail=0;
    for(unsigned i=0;i<3;i++)eye_fanout_sent(&fan,i);
    reply.version=1;assert(!eye_fanout_ack(&fan,0,&reply,201));reply.version=2;
    assert(!eye_fanout_ack(&fan,0,&reply,202));assert(!eye_fanout_ack(&fan,1,&reply,202));
    assert(eye_fanout_ack(&fan,2,&reply,202));assert(eye_fanout_reply(&fan,202,&last));
    puts("share host passed: v1/v2, capability, bounded atomic commit, dedup, TEST, priority, expiry and three-peer ACK");
    return 0;
}
