#include "eye_fanout.h"
#include "eye_endpoint.h"
#include <stdio.h>
#include <stdlib.h>
static unsigned checks,calls[3];
#define CHECK(x) do{++checks;if(!(x)){fprintf(stderr,"line %d: %s\n",__LINE__,#x);exit(2);}}while(0)
static int accept(const eye_packet *p,void *ctx){CHECK(p->detail==EYE_TEST);++calls[*(unsigned*)ctx];return 1;}
int main(void){
 eye_receiver receivers[3];eye_fanout f;eye_packet ack,out,p={.kind=EYE_HELLO,.session=123,.detail=EYE_TEST};
 for(unsigned i=0;i<3;i++)eye_init(&receivers[i],1);
 eye_fanout_reset(&f,7);CHECK(eye_fanout_request(&f,&p,100));CHECK(eye_fanout_pending(&f,100)==7);
 for(unsigned i=0;i<3;i++){
  eye_fanout_sent(&f,i);CHECK(eye_endpoint_receive(&receivers[i],&p,110,&ack,accept,NULL,&i)==1);
  CHECK(eye_fanout_ack(&f,i,&ack,111)==(i==2));
  CHECK(!eye_fanout_ack(&f,i,&ack,111)); /* repeated peer cannot count twice */
 }
 CHECK(eye_fanout_reply(&f,112,&out)&&out.detail==EYE_OK);CHECK(!eye_fanout_pending(&f,112));
 for(unsigned code=1;code<=5;code++){
  uint64_t now=200+code*300;p.kind=EYE_EVENT;p.code=code;p.sequence=code;
  CHECK(eye_fanout_request(&f,&p,now));
  for(unsigned i=0;i<3;i++){
   eye_fanout_sent(&f,i);CHECK(eye_endpoint_receive(&receivers[i],&p,now+10,&ack,accept,NULL,&i)==1);
   if(i!=1)CHECK(eye_fanout_ack(&f,i,&ack,now+11)==0); /* C ACK lost */
  }
  CHECK(!eye_fanout_reply(&f,now+12,&out));CHECK(f.acknowledged==5);
  CHECK(eye_fanout_request(&f,&p,now+180));CHECK(eye_fanout_pending(&f,now+180)==2);
  unsigned i=1;eye_fanout_sent(&f,i);CHECK(eye_endpoint_receive(&receivers[i],&p,now+190,&ack,accept,NULL,&i)==1);
  CHECK(ack.detail==EYE_DUPLICATE);eye_packet wrong=ack;++wrong.sequence;
  CHECK(!eye_fanout_ack(&f,i,&wrong,now+191));CHECK(!eye_fanout_ack(&f,9,&ack,now+191));
  CHECK(eye_fanout_ack(&f,i,&ack,now+191));CHECK(eye_fanout_reply(&f,now+192,&out)&&out.detail==EYE_OK);
  CHECK(eye_fanout_request(&f,&p,now+360));CHECK(!eye_fanout_pending(&f,now+360));
  CHECK(eye_fanout_reply(&f,now+360,&out)); /* UART ACK loss uses cached aggregate */
  for(i=0;i<3;i++)CHECK(calls[i]==code);
  CHECK(!eye_fanout_request(&f,&p,now+601));CHECK(!eye_fanout_pending(&f,now+601));CHECK(!eye_fanout_reply(&f,now+601,&out));
 }
 /* One missing/rejecting receiver must never produce a success aggregate. */
 ++p.sequence;CHECK(eye_fanout_request(&f,&p,2200));
 ack=p;ack.kind=EYE_ACK;ack.detail=EYE_OK;
 eye_fanout_sent(&f,0);CHECK(!eye_fanout_ack(&f,0,&ack,2210));
 CHECK(!eye_fanout_ack(&f,1,&ack,2211)); /* not actually sent */
 eye_fanout_sent(&f,1);ack.detail=EYE_BUSY;CHECK(eye_fanout_ack(&f,1,&ack,2212));
 CHECK(eye_fanout_reply(&f,2213,&out)&&out.detail==EYE_BUSY&&f.acknowledged==1);
 CHECK(!eye_fanout_pending(&f,2213)); /* partial outcome is retained, not rollback */
 eye_fanout_reset(&f,7);CHECK(!eye_fanout_pending(&f,2300));CHECK(!eye_fanout_reply(&f,2300,&out));CHECK(!eye_fanout_ack(&f,1,&ack,2300));
 /* New connection: old events cannot bootstrap a receiver session. */
 eye_disconnect(&receivers[2]);unsigned i=2;CHECK(eye_endpoint_receive(&receivers[2],&p,2310,&ack,accept,NULL,&i)==1);
 CHECK(ack.detail==EYE_NO_SESSION);CHECK(calls[2]==5);
 CHECK(eye_fanout_request(&f,&p,2400));CHECK(!eye_fanout_pending(&f,2399));CHECK(!eye_fanout_request(&f,&p,3001));
 eye_fanout_reset(&f,7);p.kind=EYE_ACK;CHECK(!eye_fanout_request(&f,&p,3100));
 printf("{\"passed\":true,\"checks\":%u,\"accepted_per_receiver\":[%u,%u,%u]}\n",checks,calls[0],calls[1],calls[2]);
 return 0;
}
