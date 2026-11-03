#ifndef BEARPI_CARE_HMI_H
#define BEARPI_CARE_HMI_H

#include <stdint.h>
#include "eye_link/eye_share.h"

/* B UART1 screen: LIVE eye events enter a bounded queue, then update the HMI. */
void care_hmi_init(void);
int care_hmi_accept_event(uint32_t session, uint32_t sequence, uint8_t code);
/* Legacy ASCII SLE path; not used when CONFIG_SAMPLE_SUPPORT_EYE_LINK=y. */
void care_hmi_on_sle_packet(const uint8_t *data, uint16_t length);

int care_hmi_accept_share(const eye_message *message);
#endif
