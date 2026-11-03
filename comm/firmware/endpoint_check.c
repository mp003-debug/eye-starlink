#include "eye_endpoint.h"
#include <stdio.h>
#include <stdlib.h>
static unsigned checks,tests,live;
#define CHECK(expr) do { ++checks; if(!(expr)) { fprintf(stderr,"line %d: %s\n",__LINE__,#expr); exit(1); } } while(0)
static int accept_test(const eye_packet *p,void *ctx) { (void)ctx; CHECK(p->detail==EYE_TEST); ++tests; return 1; }
static int accept_live(const eye_packet *p,void *ctx) { CHECK(p->detail==0); ++live; return *(int *)ctx; }
static eye_packet wire(const eye_packet *p) { uint8_t bytes[16]; eye_packet q; CHECK(eye_encode(p,bytes)); CHECK(eye_decode(bytes,&q)); return q; }
int main(void) {
    eye_receiver receiver; eye_bridge bridge; eye_packet ack,request;
    eye_init(&receiver,1); eye_bridge_reset(&bridge); int allow=0;
    request=(eye_packet){.kind=EYE_HELLO,.session=123,.detail=EYE_TEST};
    CHECK(eye_bridge_request(&bridge,&request,0));
    request=wire(&request);
    CHECK(eye_endpoint_receive(&receiver,&request,0,&ack,accept_test,accept_live,&allow)==1);
    CHECK(ack.detail==EYE_OK); CHECK(eye_bridge_ack(&bridge,&ack,2));
    CHECK(!eye_bridge_ack(&bridge,&ack,3)); /* duplicate ACK must not overrun PYNQ FIFO */
    for(unsigned i=1;i<=5;++i) {
        request=(eye_packet){.kind=EYE_EVENT,.session=123,.sequence=i,.code=i,.detail=EYE_TEST};
        uint64_t now=10+i*500;
        CHECK(eye_bridge_request(&bridge,&request,now)); request=wire(&request);
        CHECK(eye_endpoint_receive(&receiver,&request,now,&ack,accept_test,accept_live,&allow)==1);
        CHECK(ack.detail==EYE_OK); /* simulate dropping first application ACK */
        CHECK(eye_bridge_request(&bridge,&request,now+180));
        CHECK(eye_endpoint_receive(&receiver,&request,now+180,&ack,accept_test,accept_live,&allow)==1);
        CHECK(ack.detail==EYE_DUPLICATE); CHECK(tests==i); CHECK(live==0);
        eye_packet wrong=ack; ++wrong.session; CHECK(!eye_bridge_ack(&bridge,&wrong,now+181));
        wrong=ack; ++wrong.sequence; CHECK(!eye_bridge_ack(&bridge,&wrong,now+181));
        wrong=ack; ++wrong.code; CHECK(!eye_bridge_ack(&bridge,&wrong,now+181));
        CHECK(eye_bridge_ack(&bridge,&ack,now+182)); CHECK(!eye_bridge_ack(&bridge,&ack,now+183));
        CHECK(!eye_bridge_request(&bridge,&request,now+601));
    }
    /* Dropped ACK plus disconnect: old pending event cannot execute again. */
    eye_disconnect(&receiver); eye_bridge_reset(&bridge);
    CHECK(!eye_bridge_ack(&bridge,&ack,3000));
    CHECK(eye_endpoint_receive(&receiver,&request,3000,&ack,accept_test,accept_live,&allow)==1);
    CHECK(ack.detail==EYE_NO_SESSION); CHECK(tests==5);
    request=(eye_packet){.kind=EYE_HELLO,.session=456};
    CHECK(eye_endpoint_receive(&receiver,&request,3100,&ack,accept_test,accept_live,&allow)==1);
    CHECK(ack.detail==EYE_OK);
    request=(eye_packet){.kind=EYE_EVENT,.session=456,.sequence=1,.code=EYE_HELP};
    CHECK(eye_endpoint_receive(&receiver,&request,3110,&ack,accept_test,accept_live,&allow)==1);
    CHECK(ack.detail==EYE_BUSY); CHECK(receiver.last.sequence==0); CHECK(live==1);
    allow=1;
    CHECK(eye_endpoint_receive(&receiver,&request,3120,&ack,accept_test,accept_live,&allow)==1);
    CHECK(ack.detail==EYE_OK); CHECK(receiver.last.sequence==1); CHECK(live==2);
    CHECK(eye_endpoint_receive(&receiver,&request,3130,&ack,accept_test,accept_live,&allow)==1);
    CHECK(ack.detail==EYE_DUPLICATE); CHECK(live==2);
    ++request.sequence;
    CHECK(eye_endpoint_receive(&receiver,&request,3140,&ack,NULL,NULL,&allow)==1);
    CHECK(ack.detail==EYE_BUSY); CHECK(receiver.last.sequence==1);
    /* Session timeout and backwards clock fail closed. */
    CHECK(eye_endpoint_receive(&receiver,&request,5200,&ack,accept_test,accept_live,&allow)==1);
    CHECK(ack.detail==EYE_NO_SESSION); CHECK(live==2);
    CHECK(eye_endpoint_receive(&receiver,&request,100,&ack,accept_test,accept_live,&allow)==-1);
    CHECK(receiver.session==0);
    request.kind=EYE_ACK; CHECK(!eye_bridge_request(&bridge,&request,5300));
    CHECK(!eye_endpoint_receive(&receiver,&request,5300,&ack,accept_test,accept_live,&allow));
    printf("{\"passed\":true,\"checks\":%u,\"test_deliveries\":%u,\"live_handler_calls\":%u}\n",checks,tests,live);
    return 0;
}
