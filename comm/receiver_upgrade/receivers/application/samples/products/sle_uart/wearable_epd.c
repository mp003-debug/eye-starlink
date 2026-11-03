/* BearPi H3863 boards 3/4: SLE care-event receiver and SSD1677 display.
 * Wiring and SSD1677 register sequence are from the verified epaper_test.c.
 * Full refresh runs outside the SLE callback; control/LED polling stays live.
 */
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include "soc_osal.h"
#include "pinctrl.h"
#include "gpio.h"
#include "wearable_epd.h"
#include "wearable_ui_assets.h"
#include "eye_link/eye_share_view.h"
#include "tcxo.h"
#include "eye_link/eye_build_config.h"

#define EPD_CS 0
#define EPD_BUSY 5
#define EPD_SCK 7
#define EPD_MOSI 8
#define EPD_DC 10
#define EPD_RST 12
#define KEY_ACK 13
#define KEY_DONE 14
#define ALERT_LED 2
#define FRAME_BYTES 48000U
#define BUSY_TIMEOUT_MS 45000U
#define EVENT_QUEUE_LEN 8

typedef enum { EVENT_NONE, EVENT_WATER, EVENT_REST, EVENT_HELP, EVENT_CLEAR } event_t;
typedef struct {
    event_t kind;
    uint32_t session;
    uint32_t sequence;
    uint8_t code;
} queued_event_t;
typedef enum { PAGE_IDLE, PAGE_WATER, PAGE_WATER_ACK, PAGE_REST, PAGE_REST_ACK,
               PAGE_HELP, PAGE_HELP_ACK, PAGE_SHARE } page_t;

static unsigned long g_event_queue;
static volatile bool g_ready;
static volatile page_t g_desired_page = PAGE_IDLE;
static volatile uint8_t g_request; /* 0 idle, 1 water, 2 rest, 3 help */
static bool g_acknowledged;
static eye_share_view g_share;
static uint8_t g_share_frame[FRAME_BYTES];

static inline void pin(uint8_t number, gpio_level_t level)
{
    (void)uapi_gpio_set_val(number, level);
}

static void spi_byte(uint8_t value)
{
    for (uint8_t mask = 0x80U; mask != 0; mask >>= 1) {
        pin(EPD_SCK, GPIO_LEVEL_LOW);
        pin(EPD_MOSI, (value & mask) ? GPIO_LEVEL_HIGH : GPIO_LEVEL_LOW);
        pin(EPD_SCK, GPIO_LEVEL_HIGH);
    }
    pin(EPD_SCK, GPIO_LEVEL_LOW);
}

static void command(uint8_t value)
{
    pin(EPD_DC, GPIO_LEVEL_LOW);
    pin(EPD_CS, GPIO_LEVEL_LOW);
    spi_byte(value);
    pin(EPD_CS, GPIO_LEVEL_HIGH);
}

static void data_byte(uint8_t value)
{
    pin(EPD_DC, GPIO_LEVEL_HIGH);
    pin(EPD_CS, GPIO_LEVEL_LOW);
    spi_byte(value);
    pin(EPD_CS, GPIO_LEVEL_HIGH);
}

static bool wait_ready(const char *stage)
{
    for (uint32_t elapsed = 0; elapsed < BUSY_TIMEOUT_MS; elapsed += 10U) {
        if (uapi_gpio_get_val(EPD_BUSY) == GPIO_LEVEL_LOW) {
            osal_printk("[wearable epd] %s ready after %u ms\r\n", stage, (unsigned)elapsed);
            return true;
        }
        osal_msleep(10);
    }
    osal_printk("[wearable epd] ERROR: BUSY timeout at %s\r\n", stage);
    return false;
}

static bool configure_panel(void)
{
    pin(EPD_RST, GPIO_LEVEL_HIGH); osal_msleep(20);
    pin(EPD_RST, GPIO_LEVEL_LOW); osal_msleep(20);
    pin(EPD_RST, GPIO_LEVEL_HIGH); osal_msleep(20);
    command(0x12); osal_msleep(10);
    if (!wait_ready("reset")) return false;
    command(0x18); data_byte(0x80);
    command(0x0C);
    data_byte(0xAE); data_byte(0xC7); data_byte(0xC3); data_byte(0xC0); data_byte(0x80);
    command(0x01); data_byte(0xDF); data_byte(0x01); data_byte(0x02);
    command(0x3C); data_byte(0x01);
    command(0x11); data_byte(0x01);
    command(0x44);
    data_byte(0x00); data_byte(0x00); data_byte(0x1F); data_byte(0x03);
    command(0x45);
    data_byte(0xDF); data_byte(0x01); data_byte(0x00); data_byte(0x00);
    return true;
}

static void cursor(void)
{
    command(0x4E); data_byte(0x00); data_byte(0x00);
    command(0x4F); data_byte(0xDF); data_byte(0x01);
}

static void white_frame(uint8_t register_id)
{
    cursor(); command(register_id);
    pin(EPD_DC, GPIO_LEVEL_HIGH);
    pin(EPD_CS, GPIO_LEVEL_LOW);
    for (uint32_t i = 0; i < FRAME_BYTES; i++) {
        spi_byte(0xFF);
        if ((i % 3200U) == 3199U) osal_msleep(1);
    }
    pin(EPD_CS, GPIO_LEVEL_HIGH);
}

static bool image_frame(const uint8_t *rle, uint32_t length)
{
    uint32_t total = 0;
    cursor(); command(0x24);
    pin(EPD_DC, GPIO_LEVEL_HIGH);
    pin(EPD_CS, GPIO_LEVEL_LOW);
    for (uint32_t i = 0; i + 1U < length; i += 2U) {
        uint8_t count = rle[i];
        uint8_t value = rle[i + 1U];
        if (count == 0 || total + count > FRAME_BYTES) {
            pin(EPD_CS, GPIO_LEVEL_HIGH);
            osal_printk("[wearable epd] ERROR: corrupt RLE at %u\r\n", (unsigned)i);
            return false;
        }
        for (uint8_t j = 0; j < count; j++) spi_byte(value);
        total += count;
        if ((i & 0xFFU) == 0xFEU) osal_msleep(1);
    }
    pin(EPD_CS, GPIO_LEVEL_HIGH);
    if (total != FRAME_BYTES) {
        osal_printk("[wearable epd] ERROR: frame length %u\r\n", (unsigned)total);
        return false;
    }
    return true;
}

static const uint8_t *page_image(page_t page, uint32_t *length)
{
#define PAGE_ASSET(name) do { *length = sizeof(ui_##name); return ui_##name; } while (0)
    switch (page) {
        case PAGE_WATER: PAGE_ASSET(water);
        case PAGE_WATER_ACK: PAGE_ASSET(water_ack);
        case PAGE_REST: PAGE_ASSET(rest);
        case PAGE_REST_ACK: PAGE_ASSET(rest_ack);
        case PAGE_HELP: PAGE_ASSET(help);
        case PAGE_HELP_ACK: PAGE_ASSET(help_ack);
        default: PAGE_ASSET(idle);
    }
#undef PAGE_ASSET
}

static bool share_image_frame(void) {
    cursor();command(0x24);pin(EPD_DC,GPIO_LEVEL_HIGH);pin(EPD_CS,GPIO_LEVEL_LOW);
    for(unsigned i=0;i<FRAME_BYTES;i++) {spi_byte(g_share_frame[i]);if(i%3200==3199)osal_msleep(1);}
    pin(EPD_CS,GPIO_LEVEL_HIGH);return true;
}
static bool refresh(page_t page)
{
    uint32_t length = 0;
    const uint8_t *rle = page_image(page, &length);
    if (!configure_panel()) return false;
    white_frame(0x26);
    if (!(page==PAGE_SHARE?share_image_frame():image_frame(rle, length))) return false;
    command(0x21); data_byte(0x40); data_byte(0x00);
    command(0x22); data_byte(0xF7);
    command(0x20);
    if (!wait_ready("refresh")) return false;
    osal_printk("[wearable epd] page %u displayed\r\n", (unsigned)page);
    return true;
}

static page_t current_page(void)
{
    if (g_request == 1) return g_acknowledged ? PAGE_WATER_ACK : PAGE_WATER;
    if (g_request == 2) return g_acknowledged ? PAGE_REST_ACK : PAGE_REST;
    if (g_request == 3) return g_acknowledged ? PAGE_HELP_ACK : PAGE_HELP;
    return PAGE_IDLE;
}

static void set_event(event_t event)
{
    if(event!=EVENT_NONE) {unsigned key=osal_irq_lock();eye_share_hide(&g_share);osal_irq_restore(key);}
    if (event == EVENT_CLEAR) {
        g_request = 0;
        g_acknowledged = false;
    } else if (event == EVENT_HELP) {
        /* Deduplication already happened in the eye receiver. A newly queued
         * request must alert again even when its code matches the last one. */
        g_acknowledged = false;
        g_request = 3;
    } else if (g_request != 3 && (event == EVENT_WATER || event == EVENT_REST)) {
        uint8_t next = (event == EVENT_WATER) ? 1U : 2U;
        g_acknowledged = false;
        g_request = next;
    }
    g_desired_page = current_page();
    osal_printk("[wearable epd] event %u, request %u, page %u\r\n",
                (unsigned)event, (unsigned)g_request, (unsigned)g_desired_page);
}

/* Three 25 ms samples suppress contact bounce; each press fires once. */
static bool key_pressed(uint8_t gpio, uint8_t *low_count, bool *latched)
{
    if (uapi_gpio_get_val(gpio) == GPIO_LEVEL_LOW) {
        if (*low_count < 3) ++*low_count;
        if (*low_count == 3 && !*latched) {
            *latched = true;
            return true;
        }
    } else {
        *low_count = 0;
        *latched = false;
    }
    return false;
}

static void *control_task(const char *arg)
{
    (void)arg;
    uint8_t ack_low = 0, done_low = 0;
    bool ack_latched = false, done_latched = false;
    uint32_t tick = 0;
    while (1) {
        queued_event_t event = {0};
        uint32_t size = sizeof(event);
        if (osal_msg_queue_read_copy(g_event_queue, &event, &size, 25) == OSAL_SUCCESS &&
            size == sizeof(event)) {
            osal_printk("[wearable epd] accepted session=%u seq=%u code=%u\r\n",
                (unsigned)event.session, (unsigned)event.sequence, (unsigned)event.code);
            if (event.kind != EVENT_NONE) set_event(event.kind);
        }
        bool ack=key_pressed(KEY_ACK, &ack_low, &ack_latched);
        bool done=key_pressed(KEY_DONE, &done_low, &done_latched);
        unsigned share_key=osal_irq_lock();
        eye_share_view_tick(&g_share,g_request!=0,uapi_tcxo_get_ms());
        if(!g_request && g_share.visible) {
            if(ack)eye_share_read(&g_share);
            if(done)eye_share_hide(&g_share);
        }
        if(!g_request)g_desired_page=g_share.visible?PAGE_SHARE:PAGE_IDLE;
        osal_irq_restore(share_key);
        if (ack && g_request != 0 && !g_acknowledged) {
            g_acknowledged = true;
            g_desired_page = current_page();
            osal_printk("[wearable epd] acknowledged\r\n");
        }
        if (done && g_request != 0) {
            set_event(EVENT_CLEAR);
            osal_printk("[wearable epd] completed locally\r\n");
        }
        /* 25 ms ticks: ordinary 400 ms ON / 1600 ms OFF; urgent 200/200. */
        uint32_t phase = (g_request == 3) ? (tick % 16U) : (tick % 80U);
        bool on = (g_request == 3) ? (phase < 8U) : (g_request != 0 && phase < 16U);
        pin(ALERT_LED, on ? GPIO_LEVEL_HIGH : GPIO_LEVEL_LOW);
        ++tick;
    }
    return NULL;
}

static void *display_task(const char *arg)
{
    (void)arg;
    int last_page = -1;
    unsigned last_share_revision=0;
    osal_msleep(300);
    while (1) {
        page_t desired = g_desired_page;
        unsigned key=osal_irq_lock();
        unsigned revision=g_share.revision;
        eye_message message=g_share.current;
        int acknowledged=g_share.acknowledged,stale=g_share.stale;
        osal_irq_restore(key);
        if ((int)desired != last_page || (desired==PAGE_SHARE && revision!=last_share_revision)) {
            if(desired==PAGE_SHARE)eye_share_render(&message,EYE_NODE_ID+1,acknowledged,stale,g_share_frame);
            if (refresh(desired)) {last_page = (int)desired;last_share_revision=revision;}
            else osal_msleep(1000);
        } else {
            osal_msleep(100);
        }
    }
    return NULL;
}

void wearable_epd_init(void)
{
    uapi_pin_init();
    uapi_gpio_init();
    if (uapi_pin_set_mode(EPD_BUSY, PIN_MODE_4) != ERRCODE_SUCC ||
        uapi_pin_set_mode(EPD_CS, PIN_MODE_0) != ERRCODE_SUCC ||
        uapi_pin_set_mode(EPD_SCK, PIN_MODE_0) != ERRCODE_SUCC ||
        uapi_pin_set_mode(EPD_MOSI, PIN_MODE_0) != ERRCODE_SUCC ||
        uapi_pin_set_mode(EPD_DC, PIN_MODE_0) != ERRCODE_SUCC ||
        uapi_pin_set_mode(EPD_RST, PIN_MODE_0) != ERRCODE_SUCC ||
        uapi_pin_set_mode(KEY_ACK, PIN_MODE_0) != ERRCODE_SUCC ||
        uapi_pin_set_mode(KEY_DONE, PIN_MODE_0) != ERRCODE_SUCC ||
        uapi_pin_set_mode(ALERT_LED, PIN_MODE_0) != ERRCODE_SUCC ||
        uapi_pin_set_pull(KEY_ACK, PIN_PULL_TYPE_UP) != ERRCODE_SUCC ||
        uapi_pin_set_pull(KEY_DONE, PIN_PULL_TYPE_UP) != ERRCODE_SUCC ||
        uapi_gpio_set_dir(EPD_BUSY, GPIO_DIRECTION_INPUT) != ERRCODE_SUCC ||
        uapi_gpio_set_dir(EPD_CS, GPIO_DIRECTION_OUTPUT) != ERRCODE_SUCC ||
        uapi_gpio_set_dir(EPD_SCK, GPIO_DIRECTION_OUTPUT) != ERRCODE_SUCC ||
        uapi_gpio_set_dir(EPD_MOSI, GPIO_DIRECTION_OUTPUT) != ERRCODE_SUCC ||
        uapi_gpio_set_dir(EPD_DC, GPIO_DIRECTION_OUTPUT) != ERRCODE_SUCC ||
        uapi_gpio_set_dir(EPD_RST, GPIO_DIRECTION_OUTPUT) != ERRCODE_SUCC ||
        uapi_gpio_set_dir(KEY_ACK, GPIO_DIRECTION_INPUT) != ERRCODE_SUCC ||
        uapi_gpio_set_dir(KEY_DONE, GPIO_DIRECTION_INPUT) != ERRCODE_SUCC ||
        uapi_gpio_set_dir(ALERT_LED, GPIO_DIRECTION_OUTPUT) != ERRCODE_SUCC) {
        osal_printk("[wearable epd] ERROR: GPIO init failed\r\n");
        return;
    }
    pin(EPD_CS, GPIO_LEVEL_HIGH);
    pin(EPD_SCK, GPIO_LEVEL_LOW);
    pin(EPD_MOSI, GPIO_LEVEL_LOW);
    pin(EPD_DC, GPIO_LEVEL_LOW);
    pin(EPD_RST, GPIO_LEVEL_HIGH);
    pin(ALERT_LED, GPIO_LEVEL_LOW);
    if (osal_msg_queue_create("wearable_events", EVENT_QUEUE_LEN, &g_event_queue, 0,
        sizeof(queued_event_t)) != OSAL_SUCCESS) {
        osal_printk("[wearable epd] ERROR: queue creation failed\r\n");
        return;
    }
    /* Newly created LiteOS tasks start at the default priority. Keep either
     * task from running until both priorities and queue readiness are set. */
    osal_kthread_lock();
    osal_task *control = osal_kthread_create((osal_kthread_handler)control_task, 0,
        "CareControl", 0x1000);
    osal_task *display = osal_kthread_create((osal_kthread_handler)display_task, 0,
        "CareDisplay", 0x1800);
    if (control == NULL || display == NULL) {
        osal_kthread_unlock();
        osal_printk("[wearable epd] ERROR: task creation failed\r\n");
        return;
    }
    osal_kthread_set_priority(control, 27);
    osal_kthread_set_priority(display, 25);
    g_ready = true;
    osal_kthread_unlock();
    osal_printk("[wearable epd] ready; event queue and ACK/DONE keys\r\n");
}

void wearable_epd_on_sle_packet(const uint8_t *bytes, uint16_t length)
{
    if (!g_ready || bytes == NULL || length == 0) return;
    while (length && (bytes[length - 1] == '\r' || bytes[length - 1] == '\n' ||
                      bytes[length - 1] == ' ')) --length;
    event_t event = EVENT_NONE;
    if (length == 5 && memcmp(bytes, "WATER", 5) == 0) event = EVENT_WATER;
    else if (length == 4 && memcmp(bytes, "REST", 4) == 0) event = EVENT_REST;
    else if (length == 4 && memcmp(bytes, "HELP", 4) == 0) event = EVENT_HELP;
    else if (length == 5 && memcmp(bytes, "CLEAR", 5) == 0) event = EVENT_CLEAR;
    queued_event_t queued = {.kind = event};
    if (event != EVENT_NONE && osal_msg_queue_write_copy(g_event_queue, &queued,
        sizeof(queued), 0) != OSAL_SUCCESS) {
        osal_printk("[wearable epd] ERROR: event queue full\r\n");
    }
}

int wearable_epd_accept_event(uint32_t session, uint32_t sequence, uint8_t code)
{
    if (!g_ready) return 0;
    queued_event_t queued = {.session = session, .sequence = sequence, .code = code};
    if (code == 1) queued.kind = EVENT_WATER;
    else if (code == 2) queued.kind = EVENT_REST;
    else if (code == 3) queued.kind = EVENT_HELP;
    else if (code == 4 || code == 5) queued.kind = EVENT_NONE;
    else return 0;
    return osal_msg_queue_write_copy(g_event_queue, &queued, sizeof(queued), 0) == OSAL_SUCCESS;
}

int wearable_epd_accept_share(const eye_message *message) {
    if(!g_ready || !message)return 0;
    unsigned key=osal_irq_lock();int result=eye_share_publish(&g_share,message,g_request!=0);osal_irq_restore(key);
    return result;
}
