/* Host verification harness; NOT included in embedded firmware. */
#include "eye_event.h"
#include <stdio.h>
int main(void) {
    unsigned byte,i; unsigned long long now;
    eye_decoder decoder={0};eye_receiver receiver;eye_packet p,reply;
    uint8_t out[16];int deliver,result;
    eye_init(&receiver,1);
    while(scanf("%llu",&now)==1) {
        for(i=0;i<16;i++) {
            if(scanf("%2x",&byte)!=1) return 2;
            if(eye_feed(&decoder,(uint8_t)byte,&p)) {
                result=eye_receive(&receiver,&p,(uint64_t)now,&reply,&deliver);
                if(result!=1) {puts("none");continue;}
                if(!eye_encode(&reply,out)) return 3;
                for(byte=0;byte<16;byte++) printf("%02x",out[byte]);
                printf(" %d\n",deliver);
            }
        }
    }
    return 0;
}
