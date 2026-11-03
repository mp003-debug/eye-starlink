#ifndef EYE_SHARE_H
#define EYE_SHARE_H
#include "eye_event.h"
#define EYE_CAPS 32
#define EYE_SHARE_BEGIN 33
#define EYE_SHARE_DATA 34
#define EYE_SHARE_COMMIT 35
#define EYE_SHARE_BLOCKED 7
#define EYE_SHARE_UNSUPPORTED 8
#define EYE_SHARE_MAX 128
typedef struct {
    uint8_t category, length;
    uint8_t text[EYE_SHARE_MAX + 1]; /* GB2312, validated and NUL terminated. */
} eye_message;
typedef struct {
    uint32_t session;
    uint8_t capable, active, received;
    uint64_t started;
    eye_message message;
} eye_share_state;
typedef int (*eye_share_accept_fn)(const eye_message *, void *);
void eye_share_reset(eye_share_state *state);
/* Same v1 session/sequence, with a distinct version byte. Return codes 7/8
 * describe blocked/unsupported sharing, never upstream caregiver status. */
int eye_share_receive(eye_share_state *state, eye_receiver *receiver,
    const eye_packet *packet, uint64_t now, eye_packet *reply,
    eye_share_accept_fn accept, void *context);
int eye_share_validate(const eye_message *message);
#endif
