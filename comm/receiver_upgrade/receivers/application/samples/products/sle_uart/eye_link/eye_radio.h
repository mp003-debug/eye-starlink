/* Task-owned SLE transport. SDK callbacks only copy bounded messages.
 * node 0=A (central/client), 1=B, 2=C, 3=D (peripheral/server).
 * Fixed bench addresses are not authentication. */
#ifndef EYE_RADIO_H
#define EYE_RADIO_H
#include <stdint.h>
#include <stdbool.h>
#ifndef EYE_NODE_ID
#include <eye_build_config.h>
#endif
#ifndef EYE_REQUIRED_MASK
#define EYE_REQUIRED_MASK 7
#endif
#if EYE_NODE_ID < 0 || EYE_NODE_ID > 3 || EYE_REQUIRED_MASK < 1 || EYE_REQUIRED_MASK > 7
#error Invalid eye network configuration
#endif
#define EYE_IS_BRIDGE (EYE_NODE_ID == 0)
int eye_radio_init(void);
void eye_radio_poll(uint64_t now_ms);
bool eye_radio_ready(void);
uint8_t eye_radio_ready_mask(void);
uint32_t eye_radio_epoch(void);
/* A peer 0/1/2 means B/C/D. Receiver peer must be zero (A).
 * Accepted by stack is not application delivery. */
bool eye_radio_send_to(unsigned peer, const uint8_t data[16]);
bool eye_radio_receive_from(unsigned *peer, uint8_t data[16], uint32_t *epoch, uint64_t *received_ms);
#endif
