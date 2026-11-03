/* Black-box callback/transport harness; not a wireless implementation. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include "eye_radio.h"
#include "sle_device_discovery.h"
#include "sle_connection_manager.h"
#include "sle_ssap_client.h"
#include "sle_ssap_server.h"
#include "tcxo.h"
#if EYE_NODE_ID != 0
#define SERVER 1
#else
#define SERVER 0
#endif
static unsigned assertions,irq_level,inside_callback;
#define CHECK(x) do {++assertions;if(!(x)){fprintf(stderr,"FAIL %s:%d: %s\n",__FILE__,__LINE__,#x);exit(2);}}while(0)
#define CALL(fn,...) do {inside_callback=1;fn(__VA_ARGS__);inside_callback=0;}while(0)
static uint64_t clock_ms=1000;
static unsigned enables,announces,scans,stop_scans,connects,pairs,exchanges,finds,writes,notifies,responses,disconnects;
static unsigned fail_enable,fail_tx,last_status,last_write_type,last_length;
static const uint8_t *stack_payload;
static uint8_t saved_payload[16];
static const uint8_t *payload_by_conn[64];
static unsigned sends_by_conn[64];
static sle_announce_seek_callbacks_t discovery;
static sle_connection_callbacks_t connections;
static ssaps_callbacks_t servers;
static ssapc_callbacks_t clients;
static sle_addr_t remote={.type=0,.addr={0xe1,0x59,0,0,0,1}};
static void task_api(void){CHECK(!inside_callback);CHECK(!irq_level);}
unsigned int osal_irq_lock(void){unsigned old=irq_level;++irq_level;return old;}
void osal_irq_restore(unsigned int old){CHECK(irq_level>old);irq_level=old;}
int osal_printk(const char *format,...){(void)format;return 0;}
uint64_t uapi_tcxo_get_ms(void){return clock_ms;}
errcode_t enable_sle(void){task_api();++enables;return fail_enable;}
errcode_t sle_announce_seek_register_callbacks(sle_announce_seek_callbacks_t *p){task_api();discovery=*p;return 0;}
errcode_t sle_connection_register_callbacks(sle_connection_callbacks_t *p){task_api();connections=*p;return 0;}
errcode_t ssaps_register_callbacks(ssaps_callbacks_t *p){task_api();servers=*p;return 0;}
errcode_t ssapc_register_callbacks(ssapc_callbacks_t *p){task_api();clients=*p;return 0;}
errcode_t sle_set_local_addr(sle_addr_t *p){task_api();CHECK(p->addr[5]>=1&&p->addr[5]<=4);return 0;}
errcode_t sle_set_seek_param(sle_seek_param_t *p){task_api();CHECK(p->seek_type[0]==SLE_SEEK_ACTIVE);return 0;}
errcode_t sle_start_seek(void){task_api();++scans;return 0;}
errcode_t sle_stop_seek(void){task_api();++stop_scans;return 0;}
errcode_t sle_remove_paired_remote_device(const sle_addr_t *p){task_api();CHECK(p->addr[5]>=1&&p->addr[5]<=4);return 0;}
errcode_t sle_connect_remote_device(const sle_addr_t *p){task_api();CHECK(p->addr[5]>=1&&p->addr[5]<=4);++connects;return 0;}
errcode_t sle_disconnect_remote_device(const sle_addr_t *p){task_api();(void)p;++disconnects;return 0;}
errcode_t sle_pair_remote_device(const sle_addr_t *p){task_api();CHECK(p->addr[5]>=1&&p->addr[5]<=4);++pairs;return 0;}
errcode_t ssaps_register_server(sle_uuid_t *p,uint8_t *id){task_api();CHECK(p->len==2);*id=3;return 0;}
errcode_t ssaps_add_service_sync(uint8_t id,sle_uuid_t *p,bool primary,uint16_t *handle){task_api();CHECK(id==3&&primary&&p->len==2);*handle=0x20;return 0;}
errcode_t ssaps_add_property_sync(uint8_t id,uint16_t service,ssaps_property_info_t *p,uint16_t *handle){
 task_api();CHECK(id==3&&service==0x20&&p->value_len==16);CHECK(p->operate_indication&SSAP_OPERATE_INDICATION_BIT_WRITE);
 CHECK(p->operate_indication&SSAP_OPERATE_INDICATION_BIT_INDICATE);*handle=0x21;return 0;}
errcode_t ssaps_add_descriptor_sync(uint8_t id,uint16_t service,uint16_t property,ssaps_desc_info_t *p){
 task_api();CHECK(id==3&&service==0x20&&property==0x21);CHECK(p->type==SSAP_DESCRIPTOR_CLIENT_CONFIGURATION);
 CHECK(p->value_len==2&&p->value[0]==0&&p->value[1]==0);return 0;}
errcode_t ssaps_start_service(uint8_t id,uint16_t handle){task_api();CHECK(id==3&&handle==0x20);return 0;}
errcode_t ssaps_set_info(uint8_t id,ssap_exchange_info_t *p){task_api();CHECK(id==3&&p->mtu_size>=251&&p->mtu_size<=1500);return 0;}
errcode_t sle_set_announce_param(uint8_t id,const sle_announce_param_t *p){task_api();CHECK(id==1&&p->own_addr.addr[5]==EYE_NODE_ID+1);return 0;}
errcode_t sle_set_announce_data(uint8_t id,const sle_announce_data_t *p){
 static const uint8_t adv[]={1,2,1,2,2,0};task_api();CHECK(id==1);CHECK(p->announce_data_len==sizeof(adv));
 CHECK(!memcmp(p->announce_data,adv,sizeof(adv)));CHECK(p->seek_rsp_data_len==14);
 CHECK(p->seek_rsp_data[0]==13&&p->seek_rsp_data[1]==0x0b);CHECK(!memcmp(p->seek_rsp_data+2,"eye_event_v2",12));return 0;}
errcode_t sle_start_announce(uint8_t id){task_api();CHECK(id==1);++announces;return 0;}
errcode_t ssapc_exchange_info_req(uint8_t id,uint16_t conn,ssap_exchange_info_t *p){task_api();CHECK(id==0&&conn<64&&p->mtu_size>=251&&p->mtu_size<=1500);++exchanges;return 0;}
errcode_t ssapc_find_structure(uint8_t id,uint16_t conn,ssapc_find_structure_param_t *p){task_api();CHECK(id==0&&conn<64&&p->type==SSAP_FIND_TYPE_PROPERTY);++finds;return 0;}
errcode_t ssapc_write_req(uint8_t id,uint16_t conn,ssapc_write_param_t *p){
 task_api();CHECK(id==0&&conn<64&&p->handle==0x21);++writes;payload_by_conn[conn]=p->data;++sends_by_conn[conn];last_write_type=p->type;last_length=p->data_len;
 stack_payload=p->data;CHECK(p->data_len<=16);memcpy(saved_payload,p->data,p->data_len);return fail_tx;}
errcode_t ssaps_notify_indicate(uint8_t id,uint16_t conn,ssaps_ntf_ind_t *p){
 task_api();CHECK(id==3&&conn<64&&p->handle==0x21&&p->value_len==16);++notifies;payload_by_conn[conn]=p->value;++sends_by_conn[conn];
 stack_payload=p->value;memcpy(saved_payload,p->value,16);return fail_tx;}
errcode_t ssaps_send_response(uint8_t id,uint16_t conn,ssaps_send_rsp_t *p){task_api();CHECK(id==3&&conn<64);++responses;last_status=p->status;return 0;}
static void poll(void){eye_radio_poll(clock_ms);CHECK(!irq_level);}
static void start(void){
 remote.addr[5]=SERVER?1:2;
 CHECK(eye_radio_init()==0);CHECK(enables==1);CHECK(!eye_radio_ready());CHECK(eye_radio_init()==-1);CHECK(enables==1);
 CALL(discovery.sle_enable_cb,0);CHECK(!(announces||scans));poll();CHECK(SERVER?announces==1:scans==1);}
static void connect_before_subscription(void){
 if(!SERVER){uint8_t data[]={13,0x0b,'e','y','e','_','e','v','e','n','t','_','v','2'};
  sle_seek_result_info_t result={0};result.addr=remote;result.data=data;result.data_length=sizeof(data);
  CALL(discovery.seek_result_cb,&result);poll();CHECK(stop_scans==1);
  CALL(discovery.seek_disable_cb,0);poll();CHECK(connects==1);}
 CALL(connections.connect_state_changed_cb,7,&remote,SLE_ACB_STATE_CONNECTED,SLE_PAIR_NONE,SLE_DISCONNECT_BY_REMOTE);
 CHECK(!eye_radio_ready());poll();if(!SERVER)CHECK(pairs==1);
 CALL(connections.pair_complete_cb,7,&remote,0);poll();if(!SERVER)CHECK(exchanges==1);
 {ssap_exchange_info_t info={.mtu_size=520,.version=1};
  if(SERVER){CALL(servers.mtu_changed_cb,3,7,&info,0);}else{CALL(clients.exchange_info_cb,0,7,&info,0);}poll();}
 CHECK(!eye_radio_ready());if(!SERVER)CHECK(finds==1);
}
static void discover_property(unsigned wrong_uuid){
 /* SDK declares a trailing zero-sized descriptor array; provide one byte. */
 union {uint64_t align;uint8_t bytes[sizeof(ssapc_find_property_result_t)+1];} storage;
 ssapc_find_property_result_t *p=(ssapc_find_property_result_t *)storage.bytes;
 memset(&storage,0,sizeof(storage));p->handle=0x21;p->uuid.len=2;p->uuid.uuid[14]=wrong_uuid?0x03:0x02;p->uuid.uuid[15]=0xe1;
 p->operate_indication=SSAP_OPERATE_INDICATION_BIT_WRITE|SSAP_OPERATE_INDICATION_BIT_INDICATE;
 p->descriptors_count=1;p->descriptors_type[0]=SSAP_DESCRIPTOR_CLIENT_CONFIGURATION;
 CALL(clients.ssapc_find_property_cbk,0,7,p,0);poll();
 {ssapc_find_structure_result_t result={0};CALL(clients.find_structure_cmp_cb,0,7,&result,0);poll();}
}
static void subscribe(unsigned bad){
 if(SERVER){uint8_t data[2]={bad?1:2,0};ssaps_req_write_cb_t p={0};
  p.handle=0x21;p.type=SSAP_DESCRIPTOR_CLIENT_CONFIGURATION;p.need_rsp=true;p.request_id=13;p.length=2;p.value=data;
  CALL(servers.write_request_cb,3,7,&p,0);CHECK(!eye_radio_ready());poll();CHECK(last_status==(bad?0x0e:0));
 }else{ssapc_write_result_t result={.handle=0x21,.type=SSAP_DESCRIPTOR_CLIENT_CONFIGURATION};
  discover_property(0);CHECK(!eye_radio_ready());CHECK(writes==1&&last_write_type==SSAP_DESCRIPTOR_CLIENT_CONFIGURATION);
  CHECK(last_length==2&&stack_payload[0]==2&&stack_payload[1]==0);
  CALL(clients.write_cfm_cb,0,7,&result,bad?1:0);CHECK(!eye_radio_ready());poll();}
 CHECK(eye_radio_ready()==!bad);
}
static void bootstrap(void){start();connect_before_subscription();subscribe(0);}
static void confirm(unsigned bad,unsigned wrong_handle){
 if(SERVER){CALL(servers.indicate_cfm_cb,3,wrong_handle?8:7,bad?SLE_INDICATION_CFM_FAIL:SLE_INDICATION_CFM_SUCESS,0);}
 else{ssapc_write_result_t p={.handle=wrong_handle?0x22:0x21,.type=SSAP_PROPERTY_TYPE_VALUE};CALL(clients.write_cfm_cb,0,7,&p,bad?1:0);}
}
static void incoming(uint8_t *data,unsigned len,unsigned wrong_handle,unsigned bad){
 if(SERVER){ssaps_req_write_cb_t p={0};p.handle=wrong_handle?0x22:0x21;p.type=SSAP_PROPERTY_TYPE_VALUE;
  p.request_id=14;p.need_rsp=true;p.length=(uint16_t)len;p.value=data;CALL(servers.write_request_cb,3,7,&p,bad?1:0);}
 else{ssapc_handle_value_t p={.handle=wrong_handle?0x22:0x21,.type=SSAP_PROPERTY_TYPE_VALUE,.data_len=(uint16_t)len,.data=data};CALL(clients.indication_cb,0,7,&p,bad?1:0);}
}
static int receive(uint8_t *data){uint32_t epoch;uint64_t ms;unsigned peer;int result=eye_radio_receive_from(&peer,data,&epoch,&ms);
 if(result){CHECK(epoch==eye_radio_epoch());CHECK(ms<=clock_ms);}return result;}
static void disconnect(void){uint32_t old=eye_radio_epoch();
 CALL(connections.connect_state_changed_cb,7,&remote,SLE_ACB_STATE_DISCONNECTED,SLE_PAIR_NONE,SLE_DISCONNECT_BY_REMOTE);
 CHECK(!eye_radio_ready());CHECK(eye_radio_epoch()!=old);poll();CHECK(SERVER?announces==2:scans==2);}
int main(int argc,char **argv){uint8_t a[16],b[16];unsigned i;CHECK(argc==2);for(i=0;i<16;i++)a[i]=(uint8_t)(i+10);
 if(!strcmp(argv[1],"init_failure")){fail_enable=1;CHECK(eye_radio_init()==-1);CHECK(enables==1);CHECK(!eye_radio_ready());}
 else if(!strcmp(argv[1],"enable_callback_failure")){CHECK(eye_radio_init()==0);CALL(discovery.sle_enable_cb,1);poll();CHECK(!eye_radio_ready());CHECK(!(scans||announces));}
 else if(!strcmp(argv[1],"bad_subscription")){start();connect_before_subscription();subscribe(1);}
 else if(!strcmp(argv[1],"wrong_property")){CHECK(!SERVER);start();connect_before_subscription();discover_property(1);CHECK(!eye_radio_ready());CHECK(disconnects==1);}
 else{bootstrap();
  if(!strcmp(argv[1],"flow")){
   CHECK(eye_radio_send_to(0,a));CHECK(stack_payload!=a);memset(a,0,16);CHECK(!memcmp(stack_payload,saved_payload,16));
   CHECK(!eye_radio_send_to(0,a));confirm(0,0);CHECK(!eye_radio_send_to(0,a));poll();CHECK(eye_radio_send_to(0,a));confirm(0,0);poll();
   for(i=0;i<16;i++){a[i]=(uint8_t)(i+1);}incoming(a,16,0,0);memset(a,99,16);CHECK(!receive(b));poll();CHECK(receive(b));
   for(i=0;i<16;i++)CHECK(b[i]==i+1);CHECK(!receive(b));
   incoming(a,16,1,0);poll();CHECK(!receive(b));incoming(a,15,0,0);poll();CHECK(!receive(b));incoming(a,16,0,1);poll();CHECK(!receive(b));
   incoming(a,16,0,0);clock_ms+=101;poll();CHECK(!receive(b));
   incoming(a,16,0,0);poll();incoming(a,16,0,0);disconnect();CHECK(!receive(b));CHECK(!eye_radio_send_to(0,a));
  }else if(!strcmp(argv[1],"tx_timeout")){CHECK(eye_radio_send_to(0,a));clock_ms+=501;poll();CHECK(!eye_radio_ready());CHECK(disconnects==1);}
  else if(!strcmp(argv[1],"tx_call_failure")){fail_tx=1;CHECK(!eye_radio_send_to(0,a));CHECK(!eye_radio_ready());poll();CHECK(disconnects==1);}
  else if(!strcmp(argv[1],"tx_confirm_failure")){CHECK(eye_radio_send_to(0,a));confirm(1,0);poll();CHECK(!eye_radio_ready());CHECK(disconnects==1);}
  else if(!strcmp(argv[1],"wrong_confirmation")){CHECK(eye_radio_send_to(0,a));confirm(0,1);poll();
   if(SERVER){CHECK(eye_radio_ready());CHECK(!eye_radio_send_to(0,a));confirm(0,0);poll();CHECK(eye_radio_send_to(0,a));}
   else{CHECK(!eye_radio_ready());CHECK(disconnects==1);}}
  else if(!strcmp(argv[1],"callback_overflow")){uint32_t old=eye_radio_epoch();for(i=0;i<33;i++)incoming(a,16,0,0);
   CHECK(!eye_radio_ready());CHECK(eye_radio_epoch()!=old);poll();CHECK(disconnects==1);CHECK(!receive(b));}
  else if(!strcmp(argv[1],"rx_overflow")){uint32_t old=eye_radio_epoch();for(i=0;i<9;i++)incoming(a,16,0,0);
   poll();CHECK(!eye_radio_ready());CHECK(eye_radio_epoch()!=old);CHECK(disconnects==1);CHECK(!receive(b));}
  else if(!strcmp(argv[1],"clock_regression")){clock_ms--;poll();CHECK(!eye_radio_ready());}
  else{fprintf(stderr,"Unknown scenario\n");return 3;}
 }
 printf("{\"role\":\"%s\",\"scenario\":\"%s\",\"assertions\":%u,\"passed\":true}\n",SERVER?"bridge":"receiver",argv[1],assertions);return 0;
}
