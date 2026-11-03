#include <stdio.h>
#include "../receivers/application/samples/products/sle_uart/wearable_epd.c"
int main(void) {
    wearable_epd_init();assert(g_ready);
    for(unsigned request=1;request<=3;request++) {
        set_event(EVENT_CLEAR);set_event((event_t)request);
        assert(g_desired_page==2*request-1 && !g_acknowledged);
        g_acknowledged=true;assert(current_page()==2*request);
        set_event((event_t)request);assert(!g_acknowledged);
    }
    g_acknowledged=true;set_event(EVENT_WATER);set_event(EVENT_REST);
    assert(g_request==3 && g_acknowledged && current_page()==PAGE_HELP_ACK);
    set_event(EVENT_CLEAR);assert(g_request==0 && current_page()==PAGE_IDLE);
    uint8_t count=0;bool latch=false;gpio_values[KEY_ACK]=GPIO_LEVEL_LOW;
    assert(!key_pressed(KEY_ACK,&count,&latch));assert(!key_pressed(KEY_ACK,&count,&latch));
    assert(key_pressed(KEY_ACK,&count,&latch));assert(!key_pressed(KEY_ACK,&count,&latch));
    gpio_values[KEY_ACK]=GPIO_LEVEL_HIGH;assert(!key_pressed(KEY_ACK,&count,&latch));assert(!latch && !count);
    for(unsigned code=4;code<=5;code++) {
        assert(wearable_epd_accept_event(99,code,(uint8_t)code));
        queued_event_t q;memcpy(&q,queued,sizeof(q));assert(q.kind==EVENT_NONE);
    }
    for(unsigned page=0;page<=6;page++) {
        uint32_t length=0,total=0;const uint8_t *v=page_image((page_t)page,&length);
        assert(length%2==0);
        for(unsigned i=0;i<length;i+=2) {assert(v[i]);total+=v[i];assert(total<=FRAME_BYTES);}
        assert(total==FRAME_BYTES);
    }
    puts("EPD host scenarios passed: page mapping, repeated requests, help priority, clear, debounce, navigation, seven RLE frames");
    return 0;
}
