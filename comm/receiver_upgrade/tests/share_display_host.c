#include <stdio.h>
#include <stdint.h>
static FILE *commands;
static void observe(const uint8_t *p,unsigned n) {
    if(commands) {fwrite(p,1,n-3,commands);fputc('\n',commands);}
}
#define TEST_UART_OBSERVER observe
#include "../receivers/application/samples/products/sle_uart/care_hmi.c"
static void frame(const char *name,const eye_message *m,int ack,int stale) {
    static uint8_t bits[48000];
    eye_share_render(m,3,ack,stale,bits);
    FILE *f=fopen(name,"wb");assert(f);assert(fwrite(bits,1,sizeof(bits),f)==sizeof(bits));fclose(f);
}
int main(void) {
    care_hmi_init();
    eye_message m={.category=3,.length=128};
    /* 64 Chinese characters, including the final END marker in the preview. */
    for(unsigned i=0;i<64;i++) {m.text[2*i]=0xc4;m.text[2*i+1]=0xe3;}
    m.text[126]=0xcd;m.text[127]=0xea;
    assert(care_hmi_accept_share(&m)==1);
    assert(!g_share.visible);eye_share_view_tick(&g_share,0,1000);
    commands=fopen("hmi_64.gb2312.txt","wb");assert(commands);care_hmi_show();fclose(commands);commands=NULL;
    frame("epd_64.bin",&m,0,0);
    unsigned old=write_calls;care_hmi_handle_touch(CARE_HMI_TOUCH_ACK);
    assert(g_share.acknowledged && write_calls>old);frame("epd_read.bin",&m,1,0);
    care_hmi_handle_touch(CARE_HMI_TOUCH_DONE);assert(!g_share.visible && captured[8]=='3');
    m.length=4;memcpy(m.text,"a\"\\;",4);
    care_share_text(24,66,432,120,m.text,m.length,6438,65535);
    const char *escaped="a\\\"\\\\;\"";
    assert(memcmp(captured+captured_size-3-strlen(escaped),escaped,strlen(escaped))==0);
    commands=fopen("hmi_escape.gb2312.txt","wb");assert(commands);
    care_share_text(24,66,432,120,m.text,m.length,6438,65535);fclose(commands);commands=NULL;
    care_hmi_handle_event(CARE_EVENT_HELP);
    assert(care_hmi_accept_share(&m)==EYE_SHARE_BLOCKED && !g_share.visible);
    care_hmi_handle_event(CARE_EVENT_CLEAR);assert(!g_share.visible);
    m.category=2;m.length=6;memcpy(m.text,"\xce\xd2\xcf\xeb\xc4\xe3",6);
    assert(care_hmi_accept_share(&m)==1);eye_share_view_tick(&g_share,0,2000);
    commands=fopen("hmi_emotion.gb2312.txt","wb");assert(commands);care_hmi_show();fclose(commands);commands=NULL;
    frame("epd_emotion.bin",&m,0,0);
    m.category=4;m.length=6;memcpy(m.text,"\xcc\xfd\xd2\xf4\xc0\xd6",6);
    assert(care_hmi_accept_share(&m)==EYE_SHARE_BLOCKED);eye_share_hide(&g_share);
    assert(care_hmi_accept_share(&m)==1);eye_share_view_tick(&g_share,0,3000);
    eye_share_view_tick(&g_share,0,123000);assert(g_share.stale);
    commands=fopen("hmi_activity.gb2312.txt","wb");assert(commands);care_hmi_show();fclose(commands);commands=NULL;
    frame("epd_activity.bin",&m,0,1);
    puts("Sharing display host passed: 64 characters, quoting, read/clear, care priority, no resurrection, stale activity and native frame output");
    return 0;
}
