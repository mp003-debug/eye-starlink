#include <stdio.h>
#include "../receivers/application/samples/products/sle_uart/care_hmi.c"
#include "eye_endpoint.h"
static void picture(unsigned id) {
    assert(captured_size==12 && memcmp(captured,"pic 0,0,",8)==0);
    assert(captured[8]=='0'+id);
    assert(captured[9]==255 && captured[10]==255 && captured[11]==255);
}
static void drain(void) {
    queued_care_event_t p;unsigned size=sizeof(p);
    assert(osal_msg_queue_read_copy(1,&p,&size,0)==0);
    if(p.kind!=CARE_EVENT_NONE)care_hmi_handle_event(p.kind);
}
static int test_accept(const eye_packet *p,void *ctx) { (void)p;(*(unsigned *)ctx)++;return 1; }
static int live_accept(const eye_packet *p,void *ctx) { (void)ctx;return care_hmi_accept_event(p->session,p->sequence,p->code); }
int main(void) {
    care_hmi_init();assert(g_care_ready);
    care_hmi_show();picture(3);
    for(unsigned code=1;code<=3;code++) {
        care_hmi_handle_event(CARE_EVENT_CLEAR);
        assert(care_hmi_accept_event(99,code,(uint8_t)code));drain();picture(2*code+2);
        care_hmi_handle_touch(CARE_HMI_TOUCH_ACK);picture(2*code+3);
        unsigned old=write_calls;care_hmi_handle_touch(CARE_HMI_TOUCH_ACK);assert(write_calls==old);
        assert(g_care_request==(care_event_t)code && g_care_acknowledged);
        care_hmi_handle_touch(CARE_HMI_TOUCH_DONE);picture(3);assert(!g_care_level);
    }
    care_hmi_handle_event(CARE_EVENT_HELP);picture(8);
    care_hmi_handle_touch(CARE_HMI_TOUCH_ACK);picture(9);
    unsigned old=write_calls;
    care_hmi_handle_event(CARE_EVENT_WATER);care_hmi_handle_event(CARE_EVENT_REST);
    assert(write_calls==old && g_care_request==CARE_EVENT_HELP && g_care_acknowledged);
    for(unsigned code=4;code<=5;code++) {assert(care_hmi_accept_event(99,code,(uint8_t)code));drain();assert(write_calls==old);}
    assert(!care_hmi_accept_event(0,1,1));assert(!care_hmi_accept_event(99,1,6));
    queue_busy=1;assert(!care_hmi_accept_event(99,7,3));queue_busy=0;
    /* Split UART touch frames, noise, malformed endings, error callback. */
    uint8_t ack[]={0xA5,2,0x5A},done[]={0xA5,1,0x5A},noise[]={0,0xA5,7,0x5A};
    g_care_touch_flags=0;care_hmi_rx_callback(noise,sizeof(noise),false);assert(!g_care_touch_flags);
    for(unsigned i=0;i<3;i++)care_hmi_rx_callback(ack+i,1,false);
    assert(g_care_touch_flags==CARE_HMI_TOUCH_ACK);
    care_hmi_handle_event(CARE_EVENT_HELP);assert(!g_care_touch_flags && !g_care_acknowledged);picture(8);
    care_hmi_rx_callback(done,3,true);assert(!g_care_touch_flags);
    care_hmi_rx_callback(done,3,false);assert(g_care_touch_flags==CARE_HMI_TOUCH_DONE);
    care_hmi_handle_touch(g_care_touch_flags);picture(3);
    /* Actual protocol endpoint: TEST is accepted without entering the UI queue;
       LIVE retries do not replay, and a full UI queue reports BUSY. */
    for(unsigned mode=0;mode<2;mode++) {
        eye_receiver r;eye_packet reply,p={.session=200+mode,.kind=EYE_HELLO,.detail=(uint8_t)mode};unsigned tests=0;
        eye_init(&r,1);assert(eye_endpoint_receive(&r,&p,0,&reply,test_accept,live_accept,&tests)==1);
        assert(reply.detail==EYE_OK);p.kind=EYE_EVENT;p.sequence=1;p.code=3;
        old=write_calls;queued_size=0;
        assert(eye_endpoint_receive(&r,&p,10,&reply,test_accept,live_accept,&tests)==1);
        assert(reply.detail==EYE_OK && write_calls==old);
        if(mode)assert(tests==1 && !queued_size);else {assert(queued_size);drain();picture(8);}
        queued_size=0;
        eye_endpoint_receive(&r,&p,20,&reply,test_accept,live_accept,&tests);
        assert(reply.detail==EYE_DUPLICATE && !queued_size);
        if(!mode) {
            p.sequence=2;queue_busy=1;eye_endpoint_receive(&r,&p,30,&reply,test_accept,live_accept,&tests);
            assert(reply.detail==EYE_BUSY && r.last.sequence==1);queue_busy=0;
            eye_endpoint_receive(&r,&p,40,&reply,test_accept,live_accept,&tests);
            assert(reply.detail==EYE_OK && queued_size);drain();
        }
    }
    puts("HMI host scenarios passed: pages, local ACK/DONE, help priority, navigation, UART parsing, TEST isolation, dedup, BUSY retry");
    return 0;
}
