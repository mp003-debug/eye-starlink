/* Host-only substitute for OSAL IRQ/time-independent declarations.
 * All SLE structures and API signatures come from the real pinned SDK. */
#ifndef EYE_TEST_SOC_OSAL_H
#define EYE_TEST_SOC_OSAL_H
unsigned int osal_irq_lock(void);
void osal_irq_restore(unsigned int state);
int osal_printk(const char *format, ...);
#endif
