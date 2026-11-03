#ifndef WEARABLE_EPD_H
#define WEARABLE_EPD_H
#include <stdint.h>
#include "eye_link/eye_share.h"
void wearable_epd_init(void);
void wearable_epd_on_sle_packet(const uint8_t *data, uint16_t length);
/* Returns 1 only after a LIVE event has been copied into the bounded queue. */
int wearable_epd_accept_event(uint32_t session, uint32_t sequence, uint8_t code);
int wearable_epd_accept_share(const eye_message *message);
#endif
