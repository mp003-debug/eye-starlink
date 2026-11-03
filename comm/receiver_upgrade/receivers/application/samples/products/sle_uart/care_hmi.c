#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include "soc_osal.h"
#include "pinctrl.h"
#include "uart.h"
#include "care_hmi.h"
#include "eye_link/eye_share_view.h"
#include "eye_link/eye_share_labels.h"
#include "tcxo.h"
#include <stdio.h>

#define CARE_HMI_UART            UART_BUS_1
#define CARE_HMI_TX_PIN          15
#define CARE_HMI_RX_PIN          16
#define CARE_HMI_BAUD            9600
#define CARE_HMI_QUEUE_LEN       8
#define CARE_HMI_TASK_STACK      0x1000
/* UART text rendering may take several hundred ms at 9600 baud. Let the
 * priority-28 radio task preempt it; care still owns this sole display writer. */
#define CARE_HMI_TASK_PRIO       30
#define CARE_HMI_TOUCH_DONE      0x01U
#define CARE_HMI_TOUCH_ACK       0x02U

typedef enum {
    CARE_EVENT_NONE = 0,
    CARE_EVENT_WATER = 1,
    CARE_EVENT_REST = 2,
    CARE_EVENT_HELP = 3,
    CARE_EVENT_CLEAR = 4
} care_event_t;

typedef struct {
    care_event_t kind;
    uint32_t session;
    uint32_t sequence;
    uint8_t code;
} queued_care_event_t;

static unsigned long g_care_queue_id;
static bool g_care_ready;
static uint8_t g_care_rx_buffer[64];
static uart_buffer_config_t g_care_uart_buffer = {
    .rx_buffer = g_care_rx_buffer,
    .rx_buffer_size = sizeof(g_care_rx_buffer)
};
static volatile uint32_t g_care_touch_flags;
static uint8_t g_care_touch_state;
static uint8_t g_care_level; /* 0=idle, 1=ordinary, 2=emergency */
static bool g_care_acknowledged;
static care_event_t g_care_request;
static eye_share_view g_share;

static void care_hmi_send(const uint8_t *command, uint32_t length)
{
    uint8_t packet[384];
    if (length + 3 > sizeof(packet)) {
        return;
    }
    (void)memcpy(packet, command, length);
    packet[length] = 0xFF;
    packet[length + 1] = 0xFF;
    packet[length + 2] = 0xFF;
    if (uapi_uart_write(CARE_HMI_UART, packet, length + 3, 0) != (int32_t)(length + 3)) {
        osal_printk("[care hmi] UART1 write failed\r\n");
    }
}

static void care_share_text(unsigned x,unsigned y,unsigned w,unsigned h,const uint8_t *raw,unsigned length,unsigned foreground,unsigned background)
{
    char command[376];
    int n=snprintf(command,sizeof(command),"xstr %u,%u,%u,%u,0,%u,%u,0,0,1,%c",x,y,w,h,foreground,background,34);
    if(n<0 || n>100)return;
    for(unsigned i=0;i<length && (unsigned)n+4<sizeof(command);i++) {
        if(raw[i]==34 || raw[i]==92)command[n++]=92;
        command[n++]=(char)raw[i];
    }
    command[n++]='"';care_hmi_send((const uint8_t *)command,(unsigned)n);
}
static void care_hmi_show_share(void)
{
    care_hmi_send((const uint8_t *)"fill 0,0,480,272,65535",sizeof("fill 0,0,480,272,65535")-1);
    care_hmi_send((const uint8_t *)"fill 0,0,480,52,6438",sizeof("fill 0,0,480,52,6438")-1);
    unsigned category=g_share.current.category-1;
    care_share_text(20,14,440,30,share_titles[category].text,share_titles[category].length,65535,6438);
    care_share_text(24,66,432,120,g_share.current.text,g_share.current.length,6438,65535);
    const uint8_t *state=g_share.stale?share_stale:g_share.acknowledged?share_read:share_wait;
    care_share_text(24,184,432,28,state,(unsigned)strlen((const char *)state),16936,65535);
    care_hmi_send((const uint8_t *)"fill 16,218,216,42,59197",sizeof("fill 16,218,216,42,59197")-1);
    care_hmi_send((const uint8_t *)"fill 248,218,216,42,59197",sizeof("fill 248,218,216,42,59197")-1);
    care_share_text(40,226,180,30,share_touch_ack,sizeof(share_touch_ack)-1,6438,59197);
    care_share_text(270,226,180,30,share_touch_done,sizeof(share_touch_done)-1,6438,59197);
}
static void care_hmi_show(void)
{
    /* IDs 3..9 are compiled from hmi/assets into eye_care_upgrade.HMI.
     * Both hotspots stay on page0; refreshing a picture cannot replay a touch
     * or redraw an obsolete button label. Only the local display task writes. */
    if(!g_care_level && g_share.visible) {care_hmi_show_share();return;}
    uint8_t picture = 3;
    if (g_care_request == CARE_EVENT_WATER) picture = g_care_acknowledged ? 5 : 4;
    else if (g_care_request == CARE_EVENT_REST) picture = g_care_acknowledged ? 7 : 6;
    else if (g_care_request == CARE_EVENT_HELP) picture = g_care_acknowledged ? 9 : 8;
    uint8_t command[] = "pic 0,0,3";
    command[8] = (uint8_t)('0' + picture);
    care_hmi_send(command, sizeof(command) - 1);
}

static void care_hmi_rx_callback(const void *buffer, uint16_t length, bool error)
{
    if (error || buffer == NULL) {
        return;
    }
    const uint8_t *bytes = (const uint8_t *)buffer;
    for (uint16_t i = 0; i < length; i++) {
        uint8_t b = bytes[i];
        switch (g_care_touch_state) {
            case 0:
                g_care_touch_state = (b == 0xA5) ? 1 : 0;
                break;
            case 1:
                if (b >= 1 && b <= 3) {
                    g_care_touch_state = (uint8_t)(b + 1);
                } else {
                    g_care_touch_state = (b == 0xA5) ? 1 : 0;
                }
                break;
            default:
                if (b == 0x5A) {
                    unsigned key = osal_irq_lock();
                    if (g_care_touch_state == 3) { /* A5 02 5A */
                        g_care_touch_flags |= CARE_HMI_TOUCH_ACK;
                    } else { /* A5 01 5A or A5 03 5A */
                        g_care_touch_flags |= CARE_HMI_TOUCH_DONE;
                    }
                    osal_irq_restore(key);
                }
                g_care_touch_state = (b == 0xA5) ? 1 : 0;
                break;
        }
    }
}

static void care_hmi_handle_event(care_event_t event)
{
    if(event!=CARE_EVENT_NONE) {unsigned key=osal_irq_lock();eye_share_hide(&g_share);osal_irq_restore(key);}
    if (event == CARE_EVENT_HELP || event == CARE_EVENT_CLEAR ||
        (g_care_level != 2 && (event == CARE_EVENT_WATER || event == CARE_EVENT_REST))) {
        unsigned key = osal_irq_lock();
        g_care_touch_flags = 0; /* Discard touches captured for the previous request. */
        osal_irq_restore(key);
    }
    if (event == CARE_EVENT_HELP) {
        g_care_level = 2;
        g_care_request = event;
        g_care_acknowledged = false;
        care_hmi_show();
        osal_printk("[care hmi] HELP\r\n");
    } else if (event == CARE_EVENT_CLEAR) {
        g_care_level = 0;
        g_care_request = CARE_EVENT_NONE;
        g_care_acknowledged = false;
        care_hmi_show();
        osal_printk("[care hmi] CLEAR\r\n");
    } else if (g_care_level != 2 && (event == CARE_EVENT_WATER || event == CARE_EVENT_REST)) {
        g_care_level = 1;
        g_care_request = event;
        g_care_acknowledged = false;
        care_hmi_show();
        if (event == CARE_EVENT_WATER) {
            osal_printk("[care hmi] WATER\r\n");
        } else if (event == CARE_EVENT_REST) {
            osal_printk("[care hmi] REST\r\n");
        }
    }
}

static void care_hmi_handle_touch(uint32_t touches)
{
    if(!g_care_level && g_share.visible) {
        unsigned key=osal_irq_lock();
        if(touches&CARE_HMI_TOUCH_ACK)eye_share_read(&g_share);
        if(touches&CARE_HMI_TOUCH_DONE)eye_share_hide(&g_share);
        osal_irq_restore(key);
        if(touches)care_hmi_show();
        return;
    }
    if ((touches & CARE_HMI_TOUCH_ACK) != 0 && g_care_level != 0 && !g_care_acknowledged) {
        g_care_acknowledged = true;
        care_hmi_show();
        osal_printk("[care hmi] acknowledged locally\r\n");
    }
    if ((touches & CARE_HMI_TOUCH_DONE) != 0 && g_care_level != 0) {
        care_hmi_handle_event(CARE_EVENT_CLEAR);
        osal_printk("[care hmi] completed locally\r\n");
    }
}

static void *care_hmi_task(const char *arg)
{
    (void)arg;
    osal_msleep(1000); /* Give the display time to boot. */
    care_hmi_send((const uint8_t *)"page page0", 10);
    osal_msleep(150);
    care_hmi_show();
    while (1) {
        /* Apply previously captured touches before a newly queued request.
         * A clear captured for the old picture must not erase the new event. */
        unsigned key = osal_irq_lock();
        uint32_t touches = g_care_touch_flags;
        g_care_touch_flags &= ~touches;
        osal_irq_restore(key);
        care_hmi_handle_touch(touches);
        queued_care_event_t event = {0};
        uint32_t size = sizeof(event);
        if (osal_msg_queue_read_copy(g_care_queue_id, &event, &size, 50) == OSAL_SUCCESS &&
            size == sizeof(event)) {
            if (event.session != 0) {
                osal_printk("[care hmi] accepted session=%u seq=%u code=%u\r\n",
                    (unsigned)event.session, (unsigned)event.sequence, (unsigned)event.code);
            }
            if (event.kind != CARE_EVENT_NONE) care_hmi_handle_event(event.kind);
        }
        unsigned revision=g_share.revision;
        key=osal_irq_lock();eye_share_view_tick(&g_share,g_care_level!=0,uapi_tcxo_get_ms());osal_irq_restore(key);
        if(revision!=g_share.revision)care_hmi_show();
    }
    return NULL;
}

void care_hmi_init(void)
{
    uart_attr_t attr = {
        .baud_rate = CARE_HMI_BAUD,
        .data_bits = UART_DATA_BIT_8,
        .stop_bits = UART_STOP_BIT_1,
        .parity = UART_PARITY_NONE
    };
    uart_pin_config_t pins = {
        .tx_pin = CARE_HMI_TX_PIN,
        .rx_pin = CARE_HMI_RX_PIN,
        .cts_pin = PIN_NONE,
        .rts_pin = PIN_NONE
    };
    uapi_pin_set_mode(CARE_HMI_TX_PIN, PIN_MODE_1);
    uapi_pin_set_mode(CARE_HMI_RX_PIN, PIN_MODE_1);
    uapi_uart_deinit(CARE_HMI_UART);
    if (uapi_uart_init(CARE_HMI_UART, &pins, &attr, NULL, &g_care_uart_buffer) != ERRCODE_SUCC) {
        osal_printk("[care hmi] UART1 init failed\r\n");
        return;
    }
    if (uapi_uart_register_rx_callback(CARE_HMI_UART,
        UART_RX_CONDITION_FULL_OR_SUFFICIENT_DATA_OR_IDLE, 1, care_hmi_rx_callback) != ERRCODE_SUCC) {
        osal_printk("[care hmi] UART1 RX callback failed\r\n");
        return;
    }
    if (osal_msg_queue_create("care_hmi_queue", CARE_HMI_QUEUE_LEN, &g_care_queue_id, 0,
        sizeof(queued_care_event_t)) != OSAL_SUCCESS) {
        osal_printk("[care hmi] queue creation failed\r\n");
        return;
    }
    osal_kthread_lock();
    osal_task *task = osal_kthread_create((osal_kthread_handler)care_hmi_task, 0,
        "CareHmiTask", CARE_HMI_TASK_STACK);
    if (task == NULL) {
        osal_kthread_unlock();
        osal_printk("[care hmi] task creation failed\r\n");
        return;
    }
    osal_kthread_set_priority(task, CARE_HMI_TASK_PRIO);
    g_care_ready = true;
    osal_kthread_unlock();
    osal_printk("[care hmi] UART1 ready at 9600 baud\r\n");
}

void care_hmi_on_sle_packet(const uint8_t *data, uint16_t length)
{
    if (!g_care_ready || data == NULL || length == 0) {
        return;
    }
    while (length > 0 && (data[length - 1] == '\n' || data[length - 1] == '\r' || data[length - 1] == ' ')) {
        length--;
    }
    queued_care_event_t event = {0};
    if (length == 5 && memcmp(data, "WATER", 5) == 0) {
        event.kind = CARE_EVENT_WATER;
    } else if (length == 4 && memcmp(data, "REST", 4) == 0) {
        event.kind = CARE_EVENT_REST;
    } else if (length == 4 && memcmp(data, "HELP", 4) == 0) {
        event.kind = CARE_EVENT_HELP;
    } else if (length == 5 && memcmp(data, "CLEAR", 5) == 0) {
        event.kind = CARE_EVENT_CLEAR;
    }
    if (event.kind != CARE_EVENT_NONE && osal_msg_queue_write_copy(g_care_queue_id, &event,
        sizeof(event), 0) != OSAL_SUCCESS) {
        osal_printk("[care hmi] event queue full\r\n");
    }
}

int care_hmi_accept_event(uint32_t session, uint32_t sequence, uint8_t code)
{
    if (!g_care_ready || session == 0) return 0;
    queued_care_event_t event = {.session = session, .sequence = sequence, .code = code};
    if (code == 1) event.kind = CARE_EVENT_WATER;
    else if (code == 2) event.kind = CARE_EVENT_REST;
    else if (code == 3) event.kind = CARE_EVENT_HELP;
    else if (code == 4 || code == 5) event.kind = CARE_EVENT_NONE;
    else return 0;
    return osal_msg_queue_write_copy(g_care_queue_id, &event, sizeof(event), 0) == OSAL_SUCCESS;
}

int care_hmi_accept_share(const eye_message *message) {
    if(!g_care_ready || !message)return 0;
    unsigned key=osal_irq_lock();int result=eye_share_publish(&g_share,message,g_care_level!=0);osal_irq_restore(key);
    return result;
}
