#include "eye_endpoint.h"
#include <string.h>
static int equal_request(const eye_packet *a, const eye_packet *b) {
    return a->kind==b->kind && a->session==b->session && a->sequence==b->sequence &&
           a->code==b->code && a->detail==b->detail;
}
void eye_bridge_reset(eye_bridge *b) { memset(b,0,sizeof(*b)); }
int eye_bridge_request(eye_bridge *b,const eye_packet *p,uint64_t now) {
    if(p->kind==EYE_ACK) return 0;
    if(!b->has_request || !equal_request(p,&b->request)) {
        b->request=*p; b->first_ms=now; b->has_request=1;
    }
    /* A continuous repeat of the same old request is not a new button action. */
    if(now<b->first_ms || now-b->first_ms>600) { b->waiting=0; return 0; }
    b->waiting=1; return 1;
}
int eye_bridge_ack(eye_bridge *b,const eye_packet *p,uint64_t now) {
    if(!b->waiting || p->kind!=EYE_ACK || now<b->first_ms || now-b->first_ms>600 ||
       p->session!=b->request.session || p->sequence!=b->request.sequence ||
       p->code!=b->request.code) return 0;
    b->waiting=0; return 1;
}
int eye_endpoint_receive(eye_receiver *r,const eye_packet *p,uint64_t now,eye_packet *reply,
                         eye_accept_fn test,eye_accept_fn live,void *context) {
    eye_receiver candidate=*r;
    int deliver=0, result=eye_receive(&candidate,p,now,reply,&deliver);
    if(result<0) { eye_disconnect(r); return result; }
    if(!result) return result;
    if(deliver) {
        eye_accept_fn accept=p->detail==EYE_TEST?test:live;
        if(!accept || !accept(p,context)) { reply->detail=EYE_BUSY; return 1; }
    }
    *r=candidate;
    return 1;
}
