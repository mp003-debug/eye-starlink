#ifndef RECEIVER_FAKE_HAL_H
#define RECEIVER_FAKE_HAL_H
/* Host-only HAL. The production drivers themselves are included by each test. */
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <assert.h>
#define OSAL_SUCCESS 0
#define ERRCODE_SUCC 0
#define UART_BUS_1 1
#define UART_DATA_BIT_8 8
#define UART_STOP_BIT_1 1
#define UART_PARITY_NONE 0
#define UART_RX_CONDITION_FULL_OR_SUFFICIENT_DATA_OR_IDLE 0
#define PIN_NONE (-1)
#define PIN_MODE_0 0
#define PIN_MODE_1 1
#define PIN_MODE_4 4
#define PIN_PULL_TYPE_UP 1
#define GPIO_DIRECTION_INPUT 0
#define GPIO_DIRECTION_OUTPUT 1
typedef enum { GPIO_LEVEL_LOW, GPIO_LEVEL_HIGH } gpio_level_t;
typedef struct { uint8_t *rx_buffer; unsigned rx_buffer_size; } uart_buffer_config_t;
typedef struct { unsigned baud_rate, data_bits, stop_bits, parity; } uart_attr_t;
typedef struct { int tx_pin, rx_pin, cts_pin, rts_pin; } uart_pin_config_t;
typedef struct { int unused; } osal_task;
typedef void *(*osal_kthread_handler)(const char *);
static uint8_t captured[2048], queued[256];
static unsigned captured_size, queued_size, write_calls;
static int queue_busy;
static gpio_level_t gpio_values[32];
static inline unsigned osal_irq_lock(void) { return 0; }
static inline void osal_irq_restore(unsigned key) { (void)key; }
static inline void osal_msleep(unsigned ms) { (void)ms; }
static inline void osal_printk(const char *fmt, ...) { (void)fmt; }
static inline void osal_kthread_lock(void) {}
static inline void osal_kthread_unlock(void) {}
static inline osal_task *osal_kthread_create(osal_kthread_handler f, int a, const char *s, unsigned n) {
    static osal_task task; (void)f;(void)a;(void)s;(void)n;return &task;
}
static inline void osal_kthread_set_priority(osal_task *t, unsigned p) { (void)t;(void)p; }
static inline int osal_msg_queue_create(const char *n, unsigned c, unsigned long *q, int flags, unsigned size) {
    (void)n;(void)c;(void)flags;(void)size;*q=1;return 0;
}
static inline int osal_msg_queue_write_copy(unsigned long q,const void *p,unsigned size,unsigned wait) {
    (void)q;(void)wait;if(queue_busy)return -1;assert(size<=sizeof(queued));memcpy(queued,p,size);queued_size=size;return 0;
}
static inline int osal_msg_queue_read_copy(unsigned long q,void *p,unsigned *size,unsigned wait) {
    (void)q;(void)wait;if(!queued_size)return -1;assert(*size>=queued_size);memcpy(p,queued,queued_size);*size=queued_size;queued_size=0;return 0;
}
static inline int32_t uapi_uart_write(int bus,const uint8_t *p,unsigned size,int timeout) {
#ifdef TEST_UART_OBSERVER
    TEST_UART_OBSERVER(p,size);
#endif
    assert(bus==1);(void)timeout;assert(size<=sizeof(captured));memcpy(captured,p,size);captured_size=size;++write_calls;return (int32_t)size;
}
static inline void uapi_uart_deinit(int bus) {(void)bus;}
static inline int uapi_uart_init(int bus,const uart_pin_config_t *p,const uart_attr_t *a,void *flow,const uart_buffer_config_t *b) {
    (void)bus;(void)p;(void)a;(void)flow;(void)b;return 0;
}
static inline int uapi_uart_register_rx_callback(int bus,int cond,int size,void (*cb)(const void *,uint16_t,bool)) {
    (void)bus;(void)cond;(void)size;(void)cb;return 0;
}
static inline int uapi_pin_set_mode(unsigned p,unsigned m) {(void)p;(void)m;return 0;}
static inline int uapi_pin_set_pull(unsigned p,unsigned m) {(void)p;(void)m;return 0;}
static inline int uapi_gpio_set_dir(unsigned p,unsigned m) {(void)p;(void)m;return 0;}
static inline int uapi_gpio_set_val(unsigned p,gpio_level_t v) {gpio_values[p]=v;return 0;}
static inline gpio_level_t uapi_gpio_get_val(unsigned p) {return gpio_values[p];}
static inline void uapi_pin_init(void) {}
static inline void uapi_gpio_init(void) {}
#endif
