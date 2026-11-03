/* WS63 SLE: A is the central/client, B/C/D are peripheral/servers.
 * Follows the pinned SDK one-to-many connection direction. All stack calls run
 * in the task; callbacks copy messages and immediately invalidate group input.
 * One missing required receiver disables new group requests. */
#include "eye_radio.h"
#include <string.h>
#include "soc_osal.h"
#include "tcxo.h"
#include "sle_device_discovery.h"
#include "sle_connection_manager.h"
#include "sle_ssap_client.h"
#include "sle_ssap_server.h"
#include "sle_errcode.h"
#define QSIZE 32
#define RSIZE 8
#define MTU 520
#define MAX_AGE 100
#define TX_TIMEOUT 500
#define SETUP_TIMEOUT 8000
#define LINK_COUNT (EYE_IS_BRIDGE?3:1)
static const uint8_t address_prefix[5]={0xe1,0x59,0,0,0};
static const char radio_name[]="eye_event_v2";
enum { ENABLE=1,CONNECT,DISCONNECT,PAIR,EXCHANGE,SCAN,SCAN_STOP,PROPERTY,FOUND,
       WRITE_CFM,WRITE,READ,IND_CFM,DATA,ADV };
typedef struct {
    uint8_t kind,type,need_rsp,len,flag;
    uint16_t conn,handle,request;
    uint32_t epoch,status,diag_value;
    uint64_t time;
    sle_addr_t addr;
    uint8_t data[16];
} message;
typedef struct {
    bool connected,ready,bad,disconnect_sent,tx_busy,subscribing,exchange,find;
    uint16_t conn,property;
    uint32_t born;
    /* Diagnostic metadata only; never participates in protocol decisions. */
    uint32_t diag_status,diag_value;
    uint16_t diag_handle;
    uint8_t diag_kind,diag_flag,diag_type,diag_len;
    uint64_t since,tx_since;
    sle_addr_t addr;
    uint8_t tx[16],cccd[2];
} link_state;
static link_state links[3];
static message queue[QSIZE],received[RSIZE];
static volatile unsigned qhead,qcount,rhead,rcount;
static volatile uint32_t generation=1;
static volatile uint8_t ready_mask;
static volatile bool fatal;
/* First fault is latched without printing from stack/IRQ callbacks. */
static const char *fatal_reason;
static volatile uint32_t fatal_status,fatal_line;
static volatile uint64_t fatal_time;
static void mark_fault_locked(const char *reason,uint32_t status,unsigned line) {
    if(!fatal){fatal_reason=reason;fatal_status=status;fatal_line=line;fatal_time=uapi_tcxo_get_ms();}
}
static bool initialized,enabled,scanning,stopping,services_added,fault_reported;
static int seeking=-1;
static sle_addr_t candidate;
static uint64_t started,last_now,connect_since;
static uint8_t server_id,property_value[16],descriptor_value[2];
static uint16_t service_handle,property_handle;
static sle_announce_seek_callbacks_t discovery;
static sle_connection_callbacks_t connections;
static ssaps_callbacks_t servers;
static ssapc_callbacks_t clients;
static void bump_locked(void) {
    if(++generation==0)generation=1;
    ready_mask=0;rhead=rcount=0;
}
static void bump(void) {unsigned key=osal_irq_lock();bump_locked();osal_irq_restore(key);}
static void fault_at(const char *reason,uint32_t status,unsigned line) {
    unsigned key=osal_irq_lock();mark_fault_locked(reason,status,line);
    bump_locked();fatal=true;osal_irq_restore(key);
}
#define FAULT(reason,status) fault_at(reason,(uint32_t)(status),__LINE__)
static void report_fault(uint64_t now) {
    if(fatal&&!fault_reported){
        fault_reported=true;
        osal_printk("EYE radio fatal; reset required reason=%s status=0x%08x line=%u at_ms=%u poll_ms=%u seeking=%d scan=%u stop=%u q=%u\r\n",
                    fatal_reason?fatal_reason:"unknown",(unsigned)fatal_status,(unsigned)fatal_line,
                    (unsigned)fatal_time,(unsigned)now,seeking,(unsigned)scanning,(unsigned)stopping,(unsigned)qcount);
    }
}
static void push(message *m) {
    unsigned key;m->time=uapi_tcxo_get_ms();key=osal_irq_lock();m->epoch=generation;
    if(qcount==QSIZE){mark_fault_locked("callback_queue_full",m->kind,__LINE__);bump_locked();fatal=true;}
    else {queue[(qhead+qcount)%QSIZE]=*m;++qcount;}
    osal_irq_restore(key);
}
static bool pop(message *m) {
    unsigned key=osal_irq_lock();bool ok=qcount!=0;
    if(ok){*m=queue[qhead];qhead=(qhead+1)%QSIZE;--qcount;}
    osal_irq_restore(key);return ok;
}
uint32_t eye_radio_epoch(void) {
    unsigned key=osal_irq_lock();uint32_t g=generation;osal_irq_restore(key);return g;
}
uint8_t eye_radio_ready_mask(void) {
    unsigned key=osal_irq_lock();uint8_t mask=fatal?0:ready_mask;osal_irq_restore(key);return mask;
}
bool eye_radio_ready(void) {
    unsigned required=EYE_IS_BRIDGE?EYE_REQUIRED_MASK:1;
    return (eye_radio_ready_mask()&required)==required;
}
static bool expected(const sle_addr_t *addr,unsigned node) {
    return addr->type==0&&!memcmp(addr->addr,address_prefix,5)&&addr->addr[5]==node+1;
}
static int node_for(const sle_addr_t *addr) {
    if(!EYE_IS_BRIDGE)return expected(addr,0)?0:-1;
    for(unsigned i=0;i<3;i++)if((EYE_REQUIRED_MASK&(1u<<i))&&expected(addr,i+1))return (int)i;
    return -1;
}
static int by_conn(uint16_t conn) {
    for(unsigned i=0;i<LINK_COUNT;i++)if(links[i].connected&&links[i].conn==conn)return (int)i;
    return -1;
}
static void bad_link_at(link_state *l,const char *reason,uint32_t status,unsigned line) {
    if(!l->bad){
        l->bad=true;l->ready=false;bump();
        osal_printk("EYE PEERFAULT suffix=%02x conn=%u reason=%s status=0x%08x line=%u ms=%u since=%u tx_since=%u property=%u subscribing=%u tx_busy=%u exchange=%u find=%u last_kind=%u last_status=0x%08x last_flag=%u last_handle=%u last_type=%u last_len=%u last_value=0x%08x\r\n",
                    l->addr.addr[5],l->conn,reason,(unsigned)status,line,(unsigned)uapi_tcxo_get_ms(),
                    (unsigned)l->since,(unsigned)l->tx_since,l->property,(unsigned)l->subscribing,
                    (unsigned)l->tx_busy,(unsigned)l->exchange,(unsigned)l->find,l->diag_kind,
                    (unsigned)l->diag_status,l->diag_flag,l->diag_handle,l->diag_type,l->diag_len,(unsigned)l->diag_value);
    }
}
#define BAD_LINK(link,reason,status) bad_link_at(link,reason,(uint32_t)(status),__LINE__)
static void link_api(link_state *l,const char *reason,errcode_t status) {
    if(status)BAD_LINK(l,reason,status);
}
static sle_uuid_t uuid(uint16_t value) {
    sle_uuid_t u={0};const uint8_t b[16]={0x37,0xbe,0xa8,0x80,0xfc,0x70,0x11,0xea,0xb7,0x20,0,0,0,0,0,0};
    memcpy(u.uuid,b,16);u.len=2;u.uuid[14]=(uint8_t)value;u.uuid[15]=(uint8_t)(value>>8);return u;
}
static void enable_cb(errcode_t status){message m={0};m.kind=ENABLE;m.status=status;push(&m);}
static void connection_cb(uint16_t conn,const sle_addr_t *addr,sle_acb_state_t state,
                          sle_pair_state_t pair,sle_disc_reason_t reason) {
    message m={0};if(!addr)return;
    m.type=(uint8_t)state;m.status=(uint32_t)reason;
    if(state==SLE_ACB_STATE_CONNECTED)m.kind=CONNECT;
    else if(state==SLE_ACB_STATE_DISCONNECTED||state==SLE_ACB_STATE_NONE)m.kind=DISCONNECT;
    else return;
    m.conn=conn;m.addr=*addr;m.flag=(uint8_t)pair;
    /* Invalidate UART/data immediately, before task processes disconnect. */
    if(node_for(addr)>=0)bump();
    push(&m);
}
static void pair_cb(uint16_t conn,const sle_addr_t *addr,errcode_t status) {
    message m={0};(void)addr;m.kind=PAIR;m.conn=conn;m.status=status;push(&m);
}
static void mtu_cb(uint8_t id,uint16_t conn,ssap_exchange_info_t *p,errcode_t status) {
    message m={0};(void)id;m.kind=EXCHANGE;m.conn=conn;m.status=status;m.flag=p&&p->mtu_size>=20;m.diag_value=p?p->mtu_size:0;push(&m);
}
static void scan_cb(sle_seek_result_info_t *p) {
    message m={0};size_t n=sizeof(radio_name)-1;
    if(!p||!p->data||node_for(&p->addr)<0||p->data_length<n)return;
    for(size_t i=0;i+n<=p->data_length;i++)if(!memcmp(p->data+i,radio_name,n)){
        m.kind=SCAN;m.addr=p->addr;push(&m);return;
    }
}
static void scan_stop_cb(errcode_t status){message m={0};m.kind=SCAN_STOP;m.status=status;push(&m);}
static void scan_enable_cb(errcode_t status){if(status)FAULT("seek_enable_callback",status);}
static void adv_cb(uint32_t id,errcode_t status){message m={0};(void)id;m.kind=ADV;m.status=status;push(&m);}
static void property_cb(uint8_t id,uint16_t conn,ssapc_find_property_result_t *p,errcode_t status) {
    message m={0};(void)id;
    if(!p||p->uuid.len!=2||p->uuid.uuid[14]!=2||p->uuid.uuid[15]!=0xe1)return;
    m.kind=PROPERTY;m.conn=conn;m.handle=p->handle;m.status=status;
    m.diag_value=p->operate_indication;m.len=p->descriptors_count;
    if((p->operate_indication&(SSAP_OPERATE_INDICATION_BIT_WRITE|SSAP_OPERATE_INDICATION_BIT_INDICATE))==
       (SSAP_OPERATE_INDICATION_BIT_WRITE|SSAP_OPERATE_INDICATION_BIT_INDICATE))
        for(unsigned i=0;i<p->descriptors_count;i++)if(p->descriptors_type[i]==SSAP_DESCRIPTOR_CLIENT_CONFIGURATION)m.flag=1;
    push(&m);
}
static void found_cb(uint8_t id,uint16_t conn,ssapc_find_structure_result_t *p,errcode_t status) {
    message m={0};(void)id;(void)p;m.kind=FOUND;m.conn=conn;m.status=status;push(&m);
}
static void write_cfm_cb(uint8_t id,uint16_t conn,ssapc_write_result_t *p,errcode_t status) {
    message m={0};(void)id;m.kind=WRITE_CFM;m.conn=conn;m.status=status;
    if(p){m.handle=p->handle;m.type=p->type;}else m.status=1;push(&m);
}
static void data_cb(uint8_t id,uint16_t conn,ssapc_handle_value_t *p,errcode_t status) {
    message m={0};(void)id;if(status||!p||!p->data||p->data_len!=16)return;
    m.kind=DATA;m.conn=conn;m.handle=p->handle;m.type=p->type;m.len=16;memcpy(m.data,p->data,16);push(&m);
}
static void write_cb(uint8_t id,uint16_t conn,ssaps_req_write_cb_t *p,errcode_t status) {
    message m={0};(void)id;if(!p)return;
    m.kind=WRITE;m.conn=conn;m.handle=p->handle;m.type=p->type;m.status=status;
    m.request=p->request_id;m.need_rsp=p->need_rsp;
    if(p->value&&p->length<=16){m.len=(uint8_t)p->length;memcpy(m.data,p->value,p->length);}push(&m);
}
static void read_cb(uint8_t id,uint16_t conn,ssaps_req_read_cb_t *p,errcode_t status) {
    message m={0};(void)id;if(!p)return;
    m.kind=READ;m.conn=conn;m.handle=p->handle;m.type=p->type;m.status=status;
    m.request=p->request_id;m.need_rsp=p->need_rsp;push(&m);
}
static void ind_cb(uint8_t id,uint16_t conn,sle_indication_cfm_result_t result,errcode_t status) {
    message m={0};(void)id;m.kind=IND_CFM;m.conn=conn;m.status=status;m.flag=result==SLE_INDICATION_CFM_SUCESS;push(&m);
}
static int start_scan(void) {
    sle_seek_param_t p={0};p.own_addr_type=0;p.filter_duplicates=1;p.seek_phys=1;
    p.seek_type[0]=SLE_SEEK_ACTIVE;p.seek_interval[0]=100;p.seek_window[0]=100;
    errcode_t status=sle_set_seek_param(&p);
    osal_printk("EYE DIAG seek_param status=0x%08x ms=%u\r\n",(unsigned)status,(unsigned)uapi_tcxo_get_ms());
    if(status){FAULT("seek_param_api",status);return -1;}
    status=sle_start_seek();
    osal_printk("EYE DIAG seek_start status=0x%08x ms=%u\r\n",(unsigned)status,(unsigned)uapi_tcxo_get_ms());
    if(status){FAULT("seek_start_api",status);return -1;}
    scanning=true;return 0;
}
static int start_server(void) {
    sle_announce_param_t a={0};sle_announce_data_t d={0};ssap_exchange_info_t info={0};
    static uint8_t adv[]={1,2,1,2,2,0},scan[2+sizeof(radio_name)-1];
    if(!services_added) {
        sle_uuid_t app=uuid(0xe100),service=uuid(0xe101);
        ssaps_property_info_t p={0};ssaps_desc_info_t c={0};
        if(ssaps_register_server(&app,&server_id)||ssaps_add_service_sync(server_id,&service,1,&service_handle))return -1;
        p.uuid=uuid(0xe102);p.permissions=SSAP_PERMISSION_READ|SSAP_PERMISSION_WRITE;
        p.operate_indication=SSAP_OPERATE_INDICATION_BIT_READ|SSAP_OPERATE_INDICATION_BIT_WRITE|SSAP_OPERATE_INDICATION_BIT_INDICATE;
        p.value=property_value;p.value_len=16;
        if(ssaps_add_property_sync(server_id,service_handle,&p,&property_handle))return -1;
        c.type=SSAP_DESCRIPTOR_CLIENT_CONFIGURATION;c.permissions=SSAP_PERMISSION_READ|SSAP_PERMISSION_WRITE;
        c.operate_indication=SSAP_OPERATE_INDICATION_BIT_READ|SSAP_OPERATE_INDICATION_BIT_WRITE;
        c.value=descriptor_value;c.value_len=2;
        if(ssaps_add_descriptor_sync(server_id,service_handle,property_handle,&c)||ssaps_start_service(server_id,service_handle))return -1;
        services_added=true;
    }
    info.mtu_size=MTU;info.version=1;if(ssaps_set_info(server_id,&info))return -1;
    a.announce_handle=1;a.announce_mode=SLE_ANNOUNCE_MODE_CONNECTABLE_SCANABLE;
    a.announce_gt_role=SLE_ANNOUNCE_ROLE_T_CAN_NEGO;a.announce_level=SLE_ANNOUNCE_LEVEL_NORMAL;
    a.announce_channel_map=7;a.announce_interval_min=0xc8;a.announce_interval_max=0xc8;
    a.conn_interval_min=0x64;a.conn_interval_max=0x64;a.conn_supervision_timeout=200;
    a.announce_tx_power=0;a.own_addr.type=0;memcpy(a.own_addr.addr,address_prefix,5);a.own_addr.addr[5]=EYE_NODE_ID+1;
    scan[0]=(uint8_t)sizeof(radio_name);scan[1]=0x0b;memcpy(scan+2,radio_name,sizeof(radio_name)-1);
    d.announce_data=adv;d.announce_data_len=sizeof(adv);d.seek_rsp_data=scan;d.seek_rsp_data_len=sizeof(scan);
    return sle_set_announce_param(1,&a)||sle_set_announce_data(1,&d)||sle_start_announce(1)?-1:0;
}
static void exchange(link_state *l) {
    ssap_exchange_info_t p={0};if(!EYE_IS_BRIDGE||l->exchange)return;
    l->exchange=true;p.mtu_size=MTU;p.version=1;
    link_api(l,"exchange_request_api",ssapc_exchange_info_req(0,l->conn,&p));
}
static void respond(const message *m,link_state *l,uint8_t status,uint8_t *data,uint16_t len) {
    ssaps_send_rsp_t p={0};if(!m->need_rsp)return;
    p.request_id=m->request;p.status=status;p.value=data;p.value_len=len;
    link_api(l,"send_response_api",ssaps_send_response(server_id,m->conn,&p));
}
static bool receive_data(const message *m,link_state *l,uint64_t now) {
    unsigned key;bool ok=false;
    if(!l->ready||l->bad||m->len!=16||now<m->time||now-m->time>MAX_AGE)return false;
    key=osal_irq_lock();
    if(m->epoch==generation&&!fatal) {
        if(rcount<RSIZE){received[(rhead+rcount)%RSIZE]=*m;++rcount;ok=true;}
        else {mark_fault_locked("receive_queue_full",rcount,__LINE__);bump_locked();fatal=true;}
    }
    osal_irq_restore(key);return ok;
}
int eye_radio_init(void) {
    if(initialized)return -1;
    initialized=true;started=last_now=uapi_tcxo_get_ms();
    osal_printk("EYE radio diag=20261030-peerdiag-v2\r\n");
    discovery.sle_enable_cb=enable_cb;discovery.seek_result_cb=scan_cb;discovery.seek_disable_cb=scan_stop_cb;
    discovery.seek_enable_cb=scan_enable_cb;discovery.announce_enable_cb=adv_cb;
    connections.connect_state_changed_cb=connection_cb;connections.pair_complete_cb=pair_cb;
    if(sle_announce_seek_register_callbacks(&discovery)||sle_connection_register_callbacks(&connections))return -1;
    if(EYE_IS_BRIDGE) {
        clients.exchange_info_cb=mtu_cb;clients.ssapc_find_property_cbk=property_cb;
        clients.find_structure_cmp_cb=found_cb;clients.write_cfm_cb=write_cfm_cb;
        clients.notification_cb=data_cb;clients.indication_cb=data_cb;
        if(ssapc_register_callbacks(&clients))return -1;
    } else {
        servers.read_request_cb=read_cb;servers.write_request_cb=write_cb;
        servers.mtu_changed_cb=mtu_cb;servers.indicate_cfm_cb=ind_cb;
        if(ssaps_register_callbacks(&servers))return -1;
    }
    return enable_sle()? -1:0;
}
void eye_radio_poll(uint64_t now) {
    message m;unsigned budget=QSIZE;
    if(now<last_now){FAULT("poll_clock_regressed",(uint32_t)(last_now-now));report_fault(now);return;}last_now=now;
    while(budget--&&pop(&m)) {
        int index=by_conn(m.conn);link_state *l=index>=0?&links[index]:NULL;
        if(m.kind==CONNECT||m.kind==DISCONNECT)
            osal_printk("EYE DIAG connection_cb suffix=%02x conn=%u state=%u pair=%u reason=0x%08x callback_ms=%u poll_ms=%u\r\n",
                        m.addr.addr[5],m.conn,m.type,m.flag,(unsigned)m.status,(unsigned)m.time,(unsigned)now);
        if(fatal)break;
        switch(m.kind) {
        case ENABLE:
            if(m.status){FAULT("enable_callback",m.status);break;}enabled=true;
            if(EYE_IS_BRIDGE) {
                sle_addr_t local={0};memcpy(local.addr,address_prefix,5);local.addr[5]=1;
                errcode_t status=sle_set_local_addr(&local);
                osal_printk("EYE DIAG local_addr status=0x%08x\r\n",(unsigned)status);
                if(status)FAULT("local_addr_api",status);else if(start_scan())FAULT("initial_scan",0);
            }else if(start_server())FAULT("initial_server",0);
            break;
        case CONNECT: {
            int slot=node_for(&m.addr);
            if(slot<0){(void)sle_disconnect_remote_device(&m.addr);break;}
            l=&links[slot];
            if(l->connected){BAD_LINK(l,"duplicate_connect",m.conn);(void)sle_disconnect_remote_device(&m.addr);break;}
            memset(l,0,sizeof(*l));l->connected=true;l->conn=m.conn;l->addr=m.addr;l->since=now;l->born=m.epoch;
            if(EYE_IS_BRIDGE) {
                if(seeking!=slot){BAD_LINK(l,"unexpected_connect_slot",seeking);break;}
                if(m.flag==SLE_PAIR_PAIRED)exchange(l);
                else if(m.flag==SLE_PAIR_NONE)link_api(l,"pair_request_api",sle_pair_remote_device(&l->addr));
            }else l->property=property_handle;
            osal_printk("EYE peer=%u CONNECT conn=%u epoch=%u\r\n",(unsigned)slot+1,m.conn,(unsigned)generation);
            break;
        }
        case DISCONNECT: {
            int slot=node_for(&m.addr);
            if(slot<0)break;
            l=&links[slot];
            if(l->connected&&l->conn!=m.conn)break;
            memset(l,0,sizeof(*l));
            if(seeking==slot){seeking=-1;stopping=false;}
            if(!EYE_IS_BRIDGE&&enabled&&start_server())FAULT("restart_server",0);
            osal_printk("EYE peer=%u DOWN epoch=%u\r\n",(unsigned)slot+1,(unsigned)generation);
            break;
        }
        case SCAN: {
            int slot=node_for(&m.addr);
            if(EYE_IS_BRIDGE&&scanning&&!stopping&&seeking<0&&slot>=0&&!links[slot].connected) {
                seeking=slot;candidate=m.addr;stopping=true;connect_since=now;
                errcode_t status=sle_stop_seek();
                osal_printk("EYE DIAG seek_stop suffix=%02x status=0x%08x ms=%u\r\n",candidate.addr[5],(unsigned)status,(unsigned)uapi_tcxo_get_ms());
                if(status)FAULT("seek_stop_api",status);
            }break;
        }
        case SCAN_STOP:
            osal_printk("EYE DIAG seek_stop_callback status=0x%08x callback_ms=%u poll_ms=%u\r\n",(unsigned)m.status,(unsigned)m.time,(unsigned)now);
            if(m.status){FAULT("seek_stop_callback",m.status);break;}
            if(EYE_IS_BRIDGE&&stopping&&seeking>=0) {
                stopping=false;scanning=false;connect_since=now;
                errcode_t removed=sle_remove_paired_remote_device(&candidate);
                errcode_t status=sle_connect_remote_device(&candidate);
                osal_printk("EYE DIAG connect_request suffix=%02x remove_status=0x%08x connect_status=0x%08x ms=%u\r\n",
                            candidate.addr[5],(unsigned)removed,(unsigned)status,(unsigned)uapi_tcxo_get_ms());
                if(status) {seeking=-1;bump();}
            }break;
        case ADV:if(m.status)FAULT("announce_callback",m.status);break;
        default:
            /* Queued events from a former incarnation of a reused conn id drop. */
            if(!l||l->bad||m.epoch<l->born)break;
            l->diag_kind=m.kind;l->diag_status=m.status;l->diag_flag=m.flag;
            l->diag_handle=m.handle;l->diag_type=m.type;l->diag_len=m.len;l->diag_value=m.diag_value;
            switch(m.kind) {
            case PAIR:if(m.status)BAD_LINK(l,"pair_callback",m.status);else exchange(l);break;
            case EXCHANGE:
                if(m.status||!m.flag){BAD_LINK(l,m.status?"exchange_callback_status":"exchange_invalid_mtu",m.status);break;}
                if(EYE_IS_BRIDGE&&!l->find){ssapc_find_structure_param_t p={0};l->find=true;
                    p.type=SSAP_FIND_TYPE_PROPERTY;p.start_hdl=1;p.end_hdl=0xffff;
                    link_api(l,"find_structure_api",ssapc_find_structure(0,l->conn,&p));
                }break;
            case PROPERTY:
                if(m.status||!m.flag||(l->property&&l->property!=m.handle))BAD_LINK(l,m.status?"property_callback_status":(!m.flag?"property_missing_operations_or_descriptor":"property_handle_conflict"),m.status);
                else l->property=m.handle;
                break;
            case FOUND:
                if(m.status||!l->property){BAD_LINK(l,m.status?"find_complete_status":"find_complete_no_property",m.status);break;}
                if(!l->subscribing&&!l->ready){ssapc_write_param_t p={0};
                    l->cccd[0]=2;l->cccd[1]=0;l->subscribing=true;l->tx_since=now;
                    p.handle=l->property;p.type=SSAP_DESCRIPTOR_CLIENT_CONFIGURATION;p.data=l->cccd;p.data_len=2;
                    link_api(l,"subscribe_write_api",ssapc_write_req(0,l->conn,&p));
                }break;
            case WRITE_CFM:
                if(m.status||m.handle!=l->property){BAD_LINK(l,m.status?"write_confirmation_status":"write_confirmation_handle",m.status);break;}
                if(m.type==SSAP_DESCRIPTOR_CLIENT_CONFIGURATION&&l->subscribing){
                    l->subscribing=false;l->ready=true;if(seeking==index)seeking=-1;
                }else if(m.type==SSAP_PROPERTY_TYPE_VALUE)l->tx_busy=false;
                break;
            case IND_CFM:if(m.status||!m.flag)BAD_LINK(l,"indication_confirmation",m.status);else l->tx_busy=false;break;
            case DATA:
                if(EYE_IS_BRIDGE&&m.handle==l->property&&m.type==SSAP_PROPERTY_TYPE_VALUE)(void)receive_data(&m,l,now);
                break;
            case WRITE:
                if(!EYE_IS_BRIDGE){uint8_t status=0;
                    if(m.status||m.handle!=l->property)status=(uint8_t)ERRCODE_SSAP_INVALID_HANDLE;
                    else if(m.type==SSAP_DESCRIPTOR_CLIENT_CONFIGURATION){
                        if(m.len!=2||m.data[0]!=2||m.data[1]!=0)status=(uint8_t)ERRCODE_SSAP_INCORRECT_DATA_VALUE;
                        else {l->cccd[0]=2;l->ready=true;}
                    }else if(m.type!=SSAP_PROPERTY_TYPE_VALUE||!receive_data(&m,l,now))status=(uint8_t)ERRCODE_SSAP_INSUFFICIENT_RESOURCES;
                    respond(&m,l,status,NULL,0);
                }break;
            case READ:
                if(!EYE_IS_BRIDGE){
                    if(!m.status&&m.handle==l->property&&m.type==SSAP_DESCRIPTOR_CLIENT_CONFIGURATION)respond(&m,l,0,l->cccd,2);
                    else respond(&m,l,(uint8_t)ERRCODE_SSAP_PROHIBIT_READING,NULL,0);
                }break;
            default:break;
            }
        }
    }
    for(unsigned i=0;i<LINK_COUNT;i++) {
        link_state *l=&links[i];
        if(l->connected&&((!l->ready&&now-l->since>SETUP_TIMEOUT)||
           ((l->tx_busy||l->subscribing)&&now-l->tx_since>TX_TIMEOUT)))
            BAD_LINK(l,(!l->ready&&now-l->since>SETUP_TIMEOUT)?"setup_timeout":(l->subscribing?"subscribe_confirmation_timeout":"data_confirmation_timeout"),
                     (!l->ready&&now-l->since>SETUP_TIMEOUT)?(uint32_t)(now-l->since):(uint32_t)(now-l->tx_since));
        if(l->connected&&(l->bad||fatal)&&!l->disconnect_sent){
            l->disconnect_sent=true;(void)sle_disconnect_remote_device(&l->addr);
            osal_printk("EYE peer=%u FAULT; disconnect requested\r\n",i+1);
        }
    }
    if(EYE_IS_BRIDGE&&seeking>=0&&!links[seeking].connected&&now-connect_since>SETUP_TIMEOUT){
        /* A missing connect completion cannot safely overlap another attempt. */
        FAULT("connect_completion_timeout",(uint32_t)(now-connect_since));(void)sle_disconnect_remote_device(&candidate);
    }
    if(!enabled&&now-started>SETUP_TIMEOUT)FAULT("enable_timeout",(uint32_t)(now-started));
    report_fault(now);
    if(!fatal){
        uint8_t mask=0;unsigned key;uint32_t before=eye_radio_epoch();
        for(unsigned i=0;i<LINK_COUNT;i++)if(links[i].connected&&links[i].ready&&!links[i].bad)mask|=(uint8_t)(1u<<i);
        key=osal_irq_lock();if(before==generation&&!qcount)ready_mask=mask;osal_irq_restore(key);
        if(EYE_IS_BRIDGE&&enabled&&!scanning&&!stopping&&seeking<0&&
           (mask&EYE_REQUIRED_MASK)!=EYE_REQUIRED_MASK&&start_scan())FAULT("next_scan",0);
    }
}
bool eye_radio_send_to(unsigned slot,const uint8_t data[16]) {
    link_state *l;errcode_t status;uint32_t epoch;
    if(slot>=LINK_COUNT||!data||!eye_radio_ready())return false;
    l=&links[slot];if(!l->ready||l->bad||l->tx_busy||l->subscribing)return false;
    epoch=eye_radio_epoch();memcpy(l->tx,data,16);l->tx_busy=true;l->tx_since=uapi_tcxo_get_ms();
    if(EYE_IS_BRIDGE){ssapc_write_param_t p={0};p.handle=l->property;p.type=SSAP_PROPERTY_TYPE_VALUE;
        p.data=l->tx;p.data_len=16;status=ssapc_write_req(0,l->conn,&p);
    }else{ssaps_ntf_ind_t p={0};p.handle=l->property;p.type=SSAP_PROPERTY_TYPE_VALUE;
        p.value=l->tx;p.value_len=16;status=ssaps_notify_indicate(server_id,l->conn,&p);
    }
    if(status){BAD_LINK(l,"send_data_api",status);return false;}
    return epoch==eye_radio_epoch()&&eye_radio_ready();
}
bool eye_radio_receive_from(unsigned *slot,uint8_t data[16],uint32_t *epoch,uint64_t *received_ms) {
    if(!slot||!data||!epoch||!received_ms)return false;
    for(;;){message m;unsigned key=osal_irq_lock();
        if(!rcount){osal_irq_restore(key);return false;}
        m=received[rhead];rhead=(rhead+1)%RSIZE;--rcount;osal_irq_restore(key);
        int i=by_conn(m.conn);
        if(i>=0&&eye_radio_ready()&&m.epoch==eye_radio_epoch()&&last_now>=m.time&&last_now-m.time<=MAX_AGE){
            *slot=(unsigned)i;memcpy(data,m.data,16);*epoch=m.epoch;*received_ms=m.time;return true;
        }
    }
}
