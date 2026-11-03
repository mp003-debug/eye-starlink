#include "eye_fanout.h"
#include <string.h>
static int fresh(const eye_fanout *f,uint64_t now) {
    return f->has_request && now>=f->first_ms && now-f->first_ms<=600;
}
static int same(const eye_packet *a,const eye_packet *b) {
    return (a->version==2)==(b->version==2) && a->kind==b->kind && a->session==b->session && a->sequence==b->sequence &&
        a->code==b->code && a->detail==b->detail;
}
void eye_fanout_reset(eye_fanout *f,unsigned required) {
    memset(f,0,sizeof(*f)); f->required=(uint8_t)(required&7);
}
int eye_fanout_request(eye_fanout *f,const eye_packet *p,uint64_t now) {
    if(!f->required || (p->kind!=EYE_HELLO && p->kind!=EYE_PING && p->kind!=EYE_EVENT && !(p->version==2 && p->kind>=32 && p->kind<=35)))return 0;
    if(!f->has_request || !same(&f->request,p)) {
        unsigned mask=f->required; eye_fanout_reset(f,mask);
        f->has_request=1;f->first_ms=now;f->request=*p;
    }
    if(!fresh(f,now))return 0;
    /* Only outstanding peers may be retried; a completed aggregate is cached. */
    f->sent=f->acknowledged;
    return 1;
}
unsigned eye_fanout_pending(const eye_fanout *f,uint64_t now) {
    return fresh(f,now)&&!f->complete ? f->required&~f->sent : 0;
}
void eye_fanout_sent(eye_fanout *f,unsigned peer) {
    if(peer<3) f->sent|=(uint8_t)(1u<<peer);
}
int eye_fanout_ack(eye_fanout *f,unsigned peer,const eye_packet *p,uint64_t now) {
    unsigned bit=peer<3?1u<<peer:0;
    if(!fresh(f,now)||f->complete||!(f->required&bit)||!(f->sent&bit)||
       (f->acknowledged&bit)||p->kind!=EYE_ACK||(p->version==2)!=(f->request.version==2)||p->session!=f->request.session||
       p->sequence!=f->request.sequence||p->code!=f->request.code)return 0;
    f->reply=*p;
    if(p->detail!=EYE_OK && p->detail!=EYE_DUPLICATE) {
        /* Some other peers may already have accepted: failure is not rollback. */
        f->complete=1;return 1;
    }
    f->acknowledged|=(uint8_t)bit;if(p->detail==EYE_OK)f->ok_seen=1;
    if(f->acknowledged==f->required) {
        f->reply.detail=f->ok_seen?EYE_OK:EYE_DUPLICATE;f->complete=1;return 1;
    }
    return 0;
}
int eye_fanout_reply(const eye_fanout *f,uint64_t now,eye_packet *p) {
    if(!fresh(f,now)||!f->complete)return 0;
    *p=f->reply;return 1;
}
