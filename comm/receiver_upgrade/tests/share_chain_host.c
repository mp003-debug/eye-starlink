/* Shared-library harness around actual packet, fanout and receiver code. */
#include "eye_endpoint.h"
#include "eye_fanout.h"
#include "eye_share.h"
#include <string.h>
static eye_fanout fan;
static eye_receiver nodes[3];
static eye_share_state shares[3];
static unsigned messages[3],care[3];
static eye_message last[3];
static int dropped=-1;
__declspec(dllexport) void chain_reset(void) {
    eye_fanout_reset(&fan,7);dropped=-1;
    memset(messages,0,sizeof(messages));memset(care,0,sizeof(care));
    for(unsigned i=0;i<3;i++) {eye_init(&nodes[i],1);eye_share_reset(&shares[i]);}
}
__declspec(dllexport) void chain_drop(int peer) {dropped=peer;}
__declspec(dllexport) unsigned chain_messages(unsigned peer) {return messages[peer];}
__declspec(dllexport) unsigned chain_care(unsigned peer) {return care[peer];}
__declspec(dllexport) unsigned chain_text(unsigned peer,uint8_t *out) {
    memcpy(out,last[peer].text,last[peer].length);return last[peer].length;
}
static int accept_text(const eye_message *m,void *context) {
    unsigned i=*(unsigned *)context;
    if(care[i])return EYE_SHARE_BLOCKED;
    last[i]=*m;++messages[i];return 1;
}
static int accept_care(const eye_packet *p,void *context) {
    unsigned i=*(unsigned *)context;
    if(p->code<=3) {care[i]=p->code;shares[i].active=0;}
    return 1;
}
static int test_only(const eye_packet *p,void *context) {(void)p;(void)context;return 1;}
__declspec(dllexport) int chain_exchange(const uint8_t *raw,uint64_t now,uint8_t *out) {
    eye_packet p,reply,aggregate;
    if(!eye_decode(raw,&p) || !eye_fanout_request(&fan,&p,now))return 0;
    if(eye_fanout_reply(&fan,now,&aggregate))return eye_encode(&aggregate,out);
    unsigned pending=eye_fanout_pending(&fan,now);
    for(unsigned i=0;i<3;i++)if(pending&(1u<<i)) {
        eye_fanout_sent(&fan,i);
        int received=p.version==2?eye_share_receive(&shares[i],&nodes[i],&p,now,&reply,accept_text,&i):
            eye_endpoint_receive(&nodes[i],&p,now,&reply,test_only,accept_care,&i);
        if(received>0 && (int)i!=dropped)eye_fanout_ack(&fan,i,&reply,now);
    }
    if(eye_fanout_reply(&fan,now,&aggregate))return eye_encode(&aggregate,out);
    return 0;
}
