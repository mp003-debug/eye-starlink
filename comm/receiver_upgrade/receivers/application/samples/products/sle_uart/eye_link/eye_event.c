#include "eye_event.h"
#include <string.h>
static uint32_t get32(const uint8_t *p) {
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static void put32(uint8_t *p, uint32_t v) {
    unsigned i; for(i=0;i<4;i++) p[i]=(uint8_t)(v>>(8*i));
}
uint16_t eye_crc16(const uint8_t *data,size_t size) {
    uint16_t crc=0xffff;size_t i;unsigned b;
    for(i=0;i<size;i++) {
        crc^=(uint16_t)((uint16_t)data[i]<<8);
        for(b=0;b<8;b++) crc=(uint16_t)((crc<<1)^((crc&0x8000)?0x1021:0));
    }
    return crc;
}
static int valid(const eye_packet *p) {
    if(p->version==2) return p->session && (p->kind==32 || p->kind==33 || p->kind==34 || p->kind==35 || p->kind==EYE_ACK);
    if(p->version>1)return 0;
    return p->session && (p->kind==EYE_HELLO || p->kind==EYE_PING || p->kind==EYE_EVENT || p->kind==EYE_ACK);
}
int eye_encode(const eye_packet *p,uint8_t out[16]) {
    uint16_t crc;
    if(!valid(p)) return 0;
    out[0]=0xa5;out[1]=0x5a;out[2]=p->version==2?2:1;out[3]=p->kind;
    put32(out+4,p->session);put32(out+8,p->sequence);
    out[12]=p->code;out[13]=p->detail;crc=eye_crc16(out,14);
    out[14]=(uint8_t)crc;out[15]=(uint8_t)(crc>>8);return 1;
}
int eye_decode(const uint8_t raw[16],eye_packet *p) {
    if(raw[0]!=0xa5 || raw[1]!=0x5a || (raw[2]!=1 && raw[2]!=2) ||
       eye_crc16(raw,14)!=((uint16_t)raw[14]|((uint16_t)raw[15]<<8))) return 0;
    p->version=raw[2];p->kind=raw[3];p->session=get32(raw+4);p->sequence=get32(raw+8);
    p->code=raw[12];p->detail=raw[13];return valid(p);
}
int eye_feed(eye_decoder *d,uint8_t byte,eye_packet *p) {
    d->data[d->used++]=byte;
    while(d->used>=2 && (d->data[0]!=0xa5 || d->data[1]!=0x5a)) {
        --d->used;memmove(d->data,d->data+1,d->used);
    }
    if(d->used==16) {
        if(eye_decode(d->data,p)) {d->used=0;return 1;}
        ++d->bad_frames;--d->used;memmove(d->data,d->data+1,d->used);
    }
    return 0;
}
void eye_init(eye_receiver *r,int allow_test) {memset(r,0,sizeof(*r));r->allow_test=(uint8_t)(allow_test!=0);}
void eye_disconnect(eye_receiver *r) {r->session=0;r->has_last=0;}
static int same(const eye_packet *a,const eye_packet *b) {
    return (a->version==2)==(b->version==2) && a->kind==b->kind && a->session==b->session && a->sequence==b->sequence && a->code==b->code && a->detail==b->detail;
}
int eye_receive(eye_receiver *r,const eye_packet *p,uint64_t now,eye_packet *reply,int *deliver) {
    uint8_t status=EYE_OK;*deliver=0;
    if(p->version==2)return 0;
    if(r->has_time && now<r->last_ms) return -1;
    if(r->has_time && now-r->last_ms>2000) eye_disconnect(r);
    if(p->kind==EYE_ACK) return 0;
    if(p->kind==EYE_HELLO) {
        if(p->sequence || p->code || p->detail>1) status=EYE_BAD_EVENT;
        else if(p->detail==EYE_TEST && !r->allow_test) status=EYE_BAD_MODE;
        else if(p->session==r->session) {
            if(p->detail!=r->mode) status=EYE_BAD_MODE;
        } else {r->session=p->session;r->mode=p->detail;r->last=*p;r->has_last=1;}
    } else if(r->session!=p->session) status=EYE_NO_SESSION;
    else if(p->detail!=r->mode) status=EYE_BAD_MODE;
    else if(p->kind==EYE_EVENT && (p->code<1 || p->code>5)) status=EYE_BAD_EVENT;
    else if(p->kind==EYE_PING && p->code) status=EYE_BAD_EVENT;
    else if(!p->sequence) status=EYE_OLD_SEQUENCE;
    else if(r->has_last && p->sequence<=r->last.sequence) status=same(p,&r->last)?EYE_DUPLICATE:EYE_OLD_SEQUENCE;
    else {r->last=*p;r->has_last=1;*deliver=p->kind==EYE_EVENT;}
    if(status==EYE_OK || status==EYE_DUPLICATE) {r->last_ms=now;r->has_time=1;}
    *reply=*p;reply->kind=EYE_ACK;reply->detail=status;return 1;
}
