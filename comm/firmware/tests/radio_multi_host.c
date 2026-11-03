/* Actual production adapter driven by three independent mocked peers. */
#define main single_peer_main
#include "radio_host.c"
#undef main
static const unsigned cid[3]={17,4,29};
static sle_addr_t addr(unsigned peer){sle_addr_t a={.type=0,.addr={0xe1,0x59,0,0,0,0}};a.addr[5]=(uint8_t)(peer+2);return a;}
static void discover(unsigned peer){
 sle_addr_t a=addr(peer);uint8_t data[]={13,0x0b,'e','y','e','_','e','v','e','n','t','_','v','2'};
 sle_seek_result_info_t p={0};p.addr=a;p.data=data;p.data_length=sizeof(data);
 CALL(discovery.seek_result_cb,&p);poll();CALL(discovery.seek_disable_cb,0);poll();
 CALL(connections.connect_state_changed_cb,cid[peer],&a,SLE_ACB_STATE_CONNECTED,SLE_PAIR_NONE,SLE_DISCONNECT_BY_REMOTE);poll();
 CALL(connections.pair_complete_cb,cid[peer],&a,0);poll();
 ssap_exchange_info_t mt={.mtu_size=520,.version=1};CALL(clients.exchange_info_cb,0,cid[peer],&mt,0);poll();
}
static void subscription(unsigned peer){
 union {uint64_t align;uint8_t bytes[sizeof(ssapc_find_property_result_t)+1];} store;
 ssapc_find_property_result_t *p=(ssapc_find_property_result_t*)store.bytes;memset(&store,0,sizeof(store));
 p->handle=0x21;p->uuid.len=2;p->uuid.uuid[14]=2;p->uuid.uuid[15]=0xe1;
 p->operate_indication=SSAP_OPERATE_INDICATION_BIT_WRITE|SSAP_OPERATE_INDICATION_BIT_INDICATE;
 p->descriptors_count=1;p->descriptors_type[0]=SSAP_DESCRIPTOR_CLIENT_CONFIGURATION;
 CALL(clients.ssapc_find_property_cbk,0,cid[peer],p,0);poll();
 ssapc_find_structure_result_t result={0};CALL(clients.find_structure_cmp_cb,0,cid[peer],&result,0);poll();
 ssapc_write_result_t done={.handle=0x21,.type=SSAP_DESCRIPTOR_CLIENT_CONFIGURATION};
 CALL(clients.write_cfm_cb,0,cid[peer],&done,0);poll();
}
static void cfm(unsigned peer){ssapc_write_result_t p={.handle=0x21,.type=SSAP_PROPERTY_TYPE_VALUE};CALL(clients.write_cfm_cb,0,cid[peer],&p,0);}
static void rx(unsigned peer,uint8_t *data){ssapc_handle_value_t p={.handle=0x21,.type=SSAP_PROPERTY_TYPE_VALUE,.data_len=16,.data=data};CALL(clients.indication_cb,0,cid[peer],&p,0);}
int main(int argc,char **argv){
 uint8_t data[16]={1},out[16];unsigned peer;uint32_t epoch;uint64_t ms;
 CHECK(argc==2);start();discover(2);subscription(2);CHECK(eye_radio_ready_mask()==4);CHECK(!eye_radio_ready());CHECK(!eye_radio_send_to(2,data));
 discover(0);subscription(0);CHECK(eye_radio_ready_mask()==5);CHECK(!eye_radio_ready());
 discover(1);
 if(!strcmp(argv[1],"partial_setup")){clock_ms+=8001;poll();CHECK(!eye_radio_ready());CHECK(disconnects==1);}
 else {subscription(1);CHECK(eye_radio_ready());CHECK(eye_radio_ready_mask()==7);
  if(!strcmp(argv[1],"group")){
   for(unsigned i=0;i<3;i++){data[0]=(uint8_t)(i+10);CHECK(eye_radio_send_to(i,data));}
   CHECK(payload_by_conn[cid[0]]!=payload_by_conn[cid[1]]);CHECK(payload_by_conn[cid[1]]!=payload_by_conn[cid[2]]);
   CHECK(!eye_radio_send_to(3,data));
   for(unsigned i=0;i<3;i++){CHECK(payload_by_conn[cid[i]][0]==i+10);cfm(i);data[0]=(uint8_t)i;rx(i,data);}
   memset(data,99,16);poll();
   for(unsigned i=0;i<3;i++){CHECK(eye_radio_receive_from(&peer,out,&epoch,&ms));CHECK(peer==i&&out[0]==i);}
   CHECK(!eye_radio_receive_from(&peer,out,&epoch,&ms));
  }else if(!strcmp(argv[1],"reconnect")){
   CHECK(eye_radio_send_to(1,data));rx(0,data);poll();uint32_t old=eye_radio_epoch();
   sle_addr_t a=addr(1);CALL(connections.connect_state_changed_cb,cid[1],&a,SLE_ACB_STATE_DISCONNECTED,SLE_PAIR_NONE,SLE_DISCONNECT_BY_REMOTE);
   CHECK(!eye_radio_ready());CHECK(eye_radio_epoch()!=old);CHECK(!eye_radio_send_to(0,data));poll();
   CHECK(eye_radio_ready_mask()==5);CHECK(!eye_radio_receive_from(&peer,out,&epoch,&ms));
   cfm(1);poll();discover(1);subscription(1);CHECK(eye_radio_ready());
   CHECK(!eye_radio_receive_from(&peer,out,&epoch,&ms));CHECK(eye_radio_send_to(1,data));
  }else if(!strcmp(argv[1],"unknown_peer")){
   unsigned n=connects;sle_addr_t a=addr(2);a.addr[5]=99;
   CALL(connections.connect_state_changed_cb,44,&a,SLE_ACB_STATE_CONNECTED,SLE_PAIR_NONE,SLE_DISCONNECT_BY_REMOTE);poll();
   CHECK(disconnects==1&&connects==n);CHECK(eye_radio_ready());
  }else if(!strcmp(argv[1],"buffer_isolation")){
   CHECK(eye_radio_send_to(0,data));cfm(1);poll();CHECK(!eye_radio_send_to(0,data));
   CHECK(eye_radio_send_to(1,data));cfm(0);poll();data[0]=42;CHECK(eye_radio_send_to(0,data));
   CHECK(payload_by_conn[cid[1]][0]==1);clock_ms+=501;poll();CHECK(!eye_radio_ready());CHECK(disconnects==2);
  }else return 3;
 }
 printf("{\"role\":\"group\",\"scenario\":\"%s\",\"assertions\":%u,\"passed\":true}\n",argv[1],assertions);return 0;
}
