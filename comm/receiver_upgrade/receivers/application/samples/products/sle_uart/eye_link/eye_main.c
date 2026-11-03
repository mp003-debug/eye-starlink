/* BearPi task glue. Only UART1 carries binary protocol; UART0 remains console.
 * SDK API declarations are from the pinned BearPi WS63 release. */
#include <string.h>
#include "soc_osal.h"
#include "app_init.h"
#include "pinctrl.h"
#include "uart.h"
#include "tcxo.h"
#include "eye_radio.h"
#include "eye_endpoint.h"
#include "eye_fanout.h"
#include "eye_app.h"
#include "care_hmi.h"
#include "wearable_epd.h"
#define QUEUE_COUNT 8
#define CHUNK_SIZE 32
#define MAX_AGE_MS 100
#define UART_BUS 1
#define UART_TX_GPIO 15
#define UART_RX_GPIO 16
static int test_event(const eye_packet *p,void *ctx) {
    (void)ctx;
    osal_printk("EYE TEST node=%u session=%u seq=%u code=%u\r\n",EYE_NODE_ID,p->session,p->sequence,p->code);
    return 1;
}
static int live_share(const eye_message *m,void *ctx) {
    (void)ctx;return eye_accept_share(m);
}
static int live_event(const eye_packet *p,void *ctx) {
    (void)ctx;
    return eye_accept_button(p);
}
#if EYE_IS_BRIDGE
typedef struct {uint64_t time; uint32_t epoch; uint16_t length; uint8_t bytes[CHUNK_SIZE];} uart_chunk;
static uart_chunk rx_queue[QUEUE_COUNT];
static uint8_t rx_storage[128],tx_storage[16];
static unsigned head,tail,count;
static volatile unsigned uart_fault;
static volatile int tx_busy;
static volatile unsigned diag_rx_calls,diag_rx_bytes,diag_tx_done;
static unsigned diag_decoded,diag_radio_sent,diag_radio_rx,diag_ack,diag_uart_tx;
static unsigned diag_tx_error;
static void uart_diagnostics(uint64_t now) {
    static uint64_t last;
    static unsigned previous[10];
    unsigned values[10],key;
    if(now-last<1000)return;
    last=now;key=osal_irq_lock();
    values[0]=diag_rx_calls;values[1]=diag_rx_bytes;values[2]=uart_fault;
    values[3]=diag_decoded;values[4]=diag_radio_sent;values[5]=diag_radio_rx;
    values[6]=diag_ack;values[7]=diag_uart_tx;values[8]=diag_tx_done;values[9]=diag_tx_error;
    osal_irq_restore(key);
    if(!memcmp(previous,values,sizeof(values)))return;
    memcpy(previous,values,sizeof(values));
    osal_printk("EYE UART rx_calls=%u bytes=%u fault=%u decoded=%u radio_tx=%u radio_rx=%u ack=%u uart_tx=%u done=%u txerr=0x%x\r\n",
      values[0],values[1],values[2],values[3],values[4],values[5],values[6],values[7],values[8],values[9]);
}
/* WS63 UART driver routes overrun to RX error=true; the separate overrun
 * registration declared in uart.h has no linked implementation in this SDK. */
static void uart_rx(const void *buf,uint16_t len,bool error) {
    const uint8_t *src=buf;
    unsigned key=osal_irq_lock();
    ++diag_rx_calls;diag_rx_bytes+=len;
    if(error || !src || len>CHUNK_SIZE*(QUEUE_COUNT-count)) {
        ++uart_fault; head=tail=count=0;
    } else if(eye_radio_ready()) {
        uint32_t epoch=eye_radio_epoch();
        uint64_t now=uapi_tcxo_get_ms();
        while(len) {
            uart_chunk *q=&rx_queue[head];
            unsigned n=len>CHUNK_SIZE?CHUNK_SIZE:len;
            q->time=now; q->epoch=epoch; q->length=n; memcpy(q->bytes,src,n);
            head=(head+1)%QUEUE_COUNT; ++count; src+=n; len-=n;
        }
    }
    osal_irq_restore(key);
}
static void uart_error(uint32_t *info,uint32_t len) {
    unsigned key=osal_irq_lock(); (void)info; (void)len;
    ++uart_fault; head=tail=count=0;
    osal_irq_restore(key);
}
static void uart_done(const void *buf,uint32_t len,const void *param) {
    (void)buf; (void)len; (void)param; ++diag_tx_done;tx_busy=0;
}
static void uart_flush(void) {
    unsigned key=osal_irq_lock(); head=tail=count=0; osal_irq_restore(key);
}
static int uart_pop(uart_chunk *q) {
    int found=0; unsigned key=osal_irq_lock();
    if(count) { *q=rx_queue[tail]; tail=(tail+1)%QUEUE_COUNT; --count; found=1; }
    osal_irq_restore(key); return found;
}
static int uart_start(void) {
    uart_pin_config_t pins={.tx_pin=UART_TX_GPIO,.rx_pin=UART_RX_GPIO,.cts_pin=PIN_NONE,.rts_pin=PIN_NONE};
    uart_attr_t attr={.baud_rate=115200,.data_bits=UART_DATA_BIT_8,.stop_bits=UART_STOP_BIT_1,.parity=UART_PARITY_NONE};
    uart_buffer_config_t buffers={.rx_buffer=rx_storage,.rx_buffer_size=sizeof(rx_storage)};
    if(uapi_pin_set_mode(UART_TX_GPIO,PIN_MODE_1) || uapi_pin_set_mode(UART_RX_GPIO,PIN_MODE_1)) return 0;
    uapi_uart_deinit(UART_BUS);
    if(uapi_uart_init(UART_BUS,&pins,&attr,NULL,&buffers)) return 0;
    /* WS63 RX FIFO IRQ drains a complete 16-byte frame before idle can fire.
     * Dispatch on sufficient data too; FULL_OR_IDLE alone accumulated 128 bytes
     * in live testing, mixing expired requests before application timestamps. */
    if(uapi_uart_register_rx_callback(UART_BUS,UART_RX_CONDITION_FULL_OR_SUFFICIENT_DATA_OR_IDLE,1,uart_rx) ||
       uapi_uart_register_frame_error_callback(UART_BUS,uart_error) ||
       uapi_uart_register_parity_error_callback(UART_BUS,uart_error)) return 0;
    return 1;
}
static void uart_reply(const eye_packet *p) {
    if(tx_busy || !eye_encode(p,tx_storage)) return;
    tx_busy=1;
    unsigned result=uapi_uart_write_int(UART_BUS,tx_storage,sizeof(tx_storage),NULL,uart_done);
    if(result) {diag_tx_error=result;tx_busy=0;} else ++diag_uart_tx;
}
#endif
static void *eye_task(const char *arg) {
    (void)arg;
#if !EYE_IS_BRIDGE
    /* App init callbacks run in the system Init phase. Initialize B's HMI or
     * C/D's e-paper from this running task before starting the radio. */
#if EYE_NODE_ID == 1
    care_hmi_init();
#else
    wearable_epd_init();
#endif
#endif
    eye_receiver receiver;
    eye_share_state sharing={0};
    eye_fanout bridge;
    eye_decoder decoder={0};
    uint32_t epoch=0;
    int was_ready=0;
    uint64_t last_poll=0;
#if EYE_IS_BRIDGE
    uint64_t partial_since=0;
    unsigned seen_fault=0;
    if(!uart_start()) { osal_printk("EYE UART1 INIT FAILED\r\n"); return NULL; }
#endif
    eye_init(&receiver,1); eye_fanout_reset(&bridge,EYE_REQUIRED_MASK);
    /* The SDK's boot-time SLE core initialization finishes asynchronously. */
    osal_msleep(5000);
    if(eye_radio_init()!=0) { osal_printk("EYE RADIO INIT FAILED\r\n"); return NULL; }
    osal_printk("EYE role=%s node=%u required=0x%x TEST=log LIVE=application-hook\r\n",EYE_IS_BRIDGE?"bridge":"receiver",EYE_NODE_ID,EYE_REQUIRED_MASK);
    for(;;) {
        uint8_t raw[16]; uint64_t received_ms;
        uint32_t received_epoch; unsigned received_peer;
        uint64_t now=uapi_tcxo_get_ms();
        eye_radio_poll(now);
        int ready=eye_radio_ready();
        uint32_t current_epoch=eye_radio_epoch();
        if(epoch!=current_epoch || !ready || (last_poll && (now<last_poll || now-last_poll>250))) {
            eye_disconnect(&receiver); eye_share_reset(&sharing); eye_fanout_reset(&bridge,EYE_REQUIRED_MASK); memset(&decoder,0,sizeof(decoder));
#if EYE_IS_BRIDGE
            uart_flush(); partial_since=0;
#endif
            epoch=current_epoch;
        }
        if(ready!=was_ready) { osal_printk("EYE link=%s epoch=%u\r\n",ready?"READY":"DOWN",epoch); was_ready=ready; }
        last_poll=now;
#if EYE_IS_BRIDGE
        if(seen_fault!=uart_fault) {
            seen_fault=uart_fault; memset(&decoder,0,sizeof(decoder)); eye_fanout_reset(&bridge,EYE_REQUIRED_MASK);
        }
        uart_chunk q={0};
        for(unsigned n=0;n<QUEUE_COUNT && uart_pop(&q);++n) {
            now=uapi_tcxo_get_ms();
            if(!eye_radio_ready() || q.epoch!=eye_radio_epoch() || now<q.time || now-q.time>MAX_AGE_MS) {
                memset(&decoder,0,sizeof(decoder)); continue;
            }
            if(decoder.used && (q.time<partial_since || q.time-partial_since>30)) memset(&decoder,0,sizeof(decoder));
            if(!decoder.used) partial_since=q.time;
            for(unsigned i=0;i<q.length;++i) {
                eye_packet p;
                if(eye_feed(&decoder,q.bytes[i],&p) && (++diag_decoded,eye_fanout_request(&bridge,&p,now))) {
                    eye_packet cached;
                    if(eye_fanout_reply(&bridge,now,&cached))uart_reply(&cached);
                }
            }
        }
        /* A stack-busy link may accept on a later poll, only within this request's
         * original deadline. No queue survives group epoch changes. */
        if(epoch==eye_radio_epoch()&&eye_radio_ready()) {
            unsigned pending=eye_fanout_pending(&bridge,now);
            if(pending)eye_encode(&bridge.request,raw);
            for(unsigned i=0;i<3;i++)if((pending&(1u<<i))&&eye_radio_send_to(i,raw)) {
                eye_fanout_sent(&bridge,i);++diag_radio_sent;
            }
        }
#endif
        for(unsigned n=0;n<QUEUE_COUNT && eye_radio_receive_from(&received_peer,raw,&received_epoch,&received_ms);++n) {
            eye_packet p,reply;
            now=uapi_tcxo_get_ms();
            if(!eye_radio_ready() || received_epoch!=eye_radio_epoch() || received_epoch!=epoch ||
               now<received_ms || now-received_ms>MAX_AGE_MS || !eye_decode(raw,&p)) continue;
#if EYE_IS_BRIDGE
            ++diag_radio_rx;
            if(eye_fanout_ack(&bridge,received_peer,&p,now)&&eye_fanout_reply(&bridge,now,&reply)) {
                ++diag_ack;uart_reply(&reply);
                if(bridge.request.kind==EYE_EVENT)
                    osal_printk("EYE GROUP session=%u seq=%u code=%u accepted=0x%x required=0x%x status=%u\r\n",
                      p.session,p.sequence,p.code,bridge.acknowledged,bridge.required,reply.detail);
            }
#else
            if(p.version!=2 && p.kind==EYE_HELLO && p.session!=receiver.session)eye_share_reset(&sharing);
            if(p.version!=2 && p.kind==EYE_EVENT && p.code<=3)sharing.active=0;
            int handled=p.version==2 ? eye_share_receive(&sharing,&receiver,&p,now,&reply,live_share,NULL) :
                eye_endpoint_receive(&receiver,&p,now,&reply,test_event,live_event,NULL);
            if(p.version==2 && handled>0)osal_printk("EYE SHARE node=%u session=%u seq=%u kind=%u status=%u mode=%u\r\n",
                EYE_NODE_ID,p.session,p.sequence,p.kind,reply.detail,receiver.mode);
            if(handled>0 &&
               received_epoch==eye_radio_epoch() && eye_radio_ready()) {
                eye_encode(&reply,raw); (void)eye_radio_send_to(0,raw);
            }
#endif
        }
#if EYE_IS_BRIDGE
        uart_diagnostics(uapi_tcxo_get_ms());
#endif
        osal_msleep(5);
    }
    return NULL;
}
static void eye_entry(void) {
    /* eye_task initializes the application queue before starting the radio. */
    osal_kthread_lock();
    osal_task *task=osal_kthread_create((osal_kthread_handler)eye_task,0,"EyeEvent",0x1800);
    if(task) osal_kthread_set_priority(task,28);
    osal_kthread_unlock();
}
app_run(eye_entry);
