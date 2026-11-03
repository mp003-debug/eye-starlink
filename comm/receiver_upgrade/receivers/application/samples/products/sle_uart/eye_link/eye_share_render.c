#include "eye_share_view.h"
#include "eye_share_font.h"
#include "eye_share_labels.h"
/* Native panel bytes are the logical 480x800 portrait rotated clockwise. */
static void dot(uint8_t *frame,int x,int y,int black) {
    if(x<0 || x>=480 || y<0 || y>=800)return;
    unsigned bit=(unsigned)x*800+(799-(unsigned)y);
    if(black)frame[bit/8]&=(uint8_t)~(0x80u>>(bit%8));
    else frame[bit/8]|=(uint8_t)(0x80u>>(bit%8));
}
static void box(uint8_t *f,int x,int y,int w,int h,int black) {
    for(int yy=y;yy<y+h;yy++)for(int xx=x;xx<x+w;xx++)dot(f,xx,yy,black);
}
static void text(uint8_t *f,const uint8_t *s,unsigned length,int x,int y,int columns,int scale,int black) {
    unsigned i=0,n=0;
    while(i<length) {
        unsigned b=s[i++],index=b-32;
        if(b>=0xa1 && i<length)index=95+(b-0xa1)*94+(s[i++]-0xa1);
        if(index>=95+87*94)continue;
        const uint8_t *g=share_font+index*72;
        int left=x+(int)(n%(unsigned)columns)*24*scale,top=y+(int)(n/(unsigned)columns)*32*scale;
        for(int yy=0;yy<24;yy++)for(int xx=0;xx<24;xx++)
            if(g[yy*3+xx/8]&(0x80>>(xx%8)))box(f,left+xx*scale,top+yy*scale,scale,scale,black);
        ++n;
    }
}
void eye_share_render(const eye_message *m,unsigned node,int acknowledged,int stale,uint8_t frame[48000]) {
    memset(frame,255,48000);
    box(frame,0,0,480,116,1);
    text(frame,share_titles[m->category-1].text,share_titles[m->category-1].length,32,42,16,1,0);
    uint8_t identity[2]={'0',(uint8_t)('0'+node)};text(frame,identity,2,396,42,2,1,0);
    box(frame,28,145,424,3,1);box(frame,28,548,424,3,1);
    unsigned chars=0;
    for(unsigned i=0;i<m->length;i++) {++chars;if(m->text[i]>=0xa1)++i;}
    int scale=chars<=16?2:1;
    text(frame,m->text,m->length,48,228,scale==2?8:16,scale,1);
    const unsigned char *state=stale?share_stale:acknowledged?share_read:share_wait;
    text(frame,state,(unsigned)strlen((const char *)state),40,580,16,1,1);
    text(frame,share_key_ack,sizeof(share_key_ack)-1,40,656,16,1,1);
    text(frame,share_key_done,sizeof(share_key_done)-1,40,704,16,1,1);
    text(frame,share_local_only,sizeof(share_local_only)-1,40,756,17,1,1);
}
