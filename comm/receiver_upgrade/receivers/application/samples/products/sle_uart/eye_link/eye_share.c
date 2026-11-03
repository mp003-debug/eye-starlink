#include "eye_share.h"
#include "eye_share_catalog.h"
#include "eye_share_valid.h"
#include <string.h>

void eye_share_reset(eye_share_state *s) { memset(s,0,sizeof(*s)); }
static int same(const eye_packet *a,const eye_packet *b) {
    return a->version==b->version && a->kind==b->kind && a->session==b->session &&
        a->sequence==b->sequence && a->code==b->code && a->detail==b->detail;
}
int eye_share_glyph_supported(uint8_t first,uint8_t second) {
    if(first>=32 && first<=126)return 1;
    if(first<0xa1 || first>0xf7 || second<0xa1 || second>0xfe)return 0;
    return share_glyph_valid[95+(first-0xa1)*94+(second-0xa1)]!=0;
}
int eye_share_validate(const eye_message *m) {
    unsigned i=0,characters=0;
    if(m->category<1 || m->category>4 || !m->length || m->length>EYE_SHARE_MAX)return 0;
    while(i<m->length) {
        unsigned b=m->text[i++];
        if(b>=0x20 && b<=0x7e) { /* ASCII printable; renderer escapes quotes. */ }
        else if(b>=0xa1 && b<=0xf7 && i<m->length && m->text[i]>=0xa1 && m->text[i]<=0xfe && eye_share_glyph_supported((uint8_t)b,m->text[i])) {++i;}
        else return 0;
        if(++characters>64)return 0;
    }
    if(m->category==3)return 1;
    for(unsigned n=0;n<sizeof(share_catalog)/sizeof(share_catalog[0]);n++)
        if(share_catalog[n].category==m->category && share_catalog[n].length==m->length &&
           !memcmp(share_catalog[n].text,m->text,m->length))return 1;
    return 0;
}
int eye_share_receive(eye_share_state *s,eye_receiver *r,const eye_packet *p,uint64_t now,
                      eye_packet *reply,eye_share_accept_fn accept,void *context) {
    unsigned status=EYE_OK;
    if(p->version!=2 || p->kind==EYE_ACK)return 0;
    *reply=*p;reply->kind=EYE_ACK;
    if(r->has_time && (now<r->last_ms || now-r->last_ms>2000)) {
        eye_disconnect(r);eye_share_reset(s);
    }
    if(s->session!=r->session)eye_share_reset(s);
    if(s->active && (now<s->started || now-s->started>20000))s->active=0;
    if(!r->session || r->session!=p->session)status=EYE_NO_SESSION;
    else if(!p->sequence)status=EYE_OLD_SEQUENCE;
    else if(r->has_last && p->sequence<=r->last.sequence)
        status=same(p,&r->last)?EYE_DUPLICATE:EYE_OLD_SEQUENCE;
    else if(p->kind==EYE_CAPS) {
        if(p->code!=2 || p->detail!=r->mode)status=EYE_BAD_MODE;
        else {eye_share_reset(s);s->session=r->session;s->capable=1;}
    } else if(!s->capable || s->session!=r->session)status=EYE_SHARE_UNSUPPORTED;
    else if(p->kind==EYE_SHARE_BEGIN) {
        if(p->code<1 || p->code>4 || !p->detail || p->detail>EYE_SHARE_MAX)status=EYE_BAD_EVENT;
        else {
            memset(&s->message,0,sizeof(s->message));s->message.category=p->code;
            s->message.length=p->detail;s->received=0;s->active=1;s->started=now;
        }
    } else if(p->kind==EYE_SHARE_DATA) {
        if(!s->active || s->received>=s->message.length)status=EYE_BAD_EVENT;
        else {
            unsigned remain=s->message.length-s->received;
            if(remain==1 && p->detail)status=EYE_BAD_EVENT;
            else {
                s->message.text[s->received++]=p->code;
                if(remain>1)s->message.text[s->received++]=p->detail;
            }
        }
    } else if(p->kind==EYE_SHARE_COMMIT) {
        uint16_t checksum=(uint16_t)p->code|((uint16_t)p->detail<<8);
        if(!s->active || s->received!=s->message.length ||
           eye_crc16(s->message.text,s->message.length)!=checksum || !eye_share_validate(&s->message))status=EYE_BAD_EVENT;
        else if(r->mode!=EYE_TEST) {
            int accepted=accept?accept(&s->message,context):0;
            if(accepted!=1)status=accepted==EYE_SHARE_BLOCKED?EYE_SHARE_BLOCKED:EYE_BUSY;
        }
        if(status==EYE_OK)s->active=0;
    } else status=EYE_BAD_EVENT;
    if(status==EYE_OK) {r->last=*p;r->has_last=1;}
    if(status==EYE_OK || status==EYE_DUPLICATE) {r->last_ms=now;r->has_time=1;}
    reply->detail=(uint8_t)status;
    return 1;
}
