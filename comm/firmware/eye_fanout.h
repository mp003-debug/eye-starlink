/* Portable group acknowledgement; all required identities must reply. */
#ifndef EYE_FANOUT_H
#define EYE_FANOUT_H
#include "eye_event.h"
typedef struct {
    eye_packet request, reply;
    uint64_t first_ms;
    uint8_t required, acknowledged, sent, ok_seen;
    int has_request, complete;
} eye_fanout;
void eye_fanout_reset(eye_fanout *f, unsigned required);
/* Repeat renews send opportunity, never the original 600 ms deadline. */
int eye_fanout_request(eye_fanout *f, const eye_packet *p, uint64_t now);
unsigned eye_fanout_pending(const eye_fanout *f, uint64_t now);
void eye_fanout_sent(eye_fanout *f, unsigned peer);
int eye_fanout_ack(eye_fanout *f, unsigned peer, const eye_packet *p, uint64_t now);
int eye_fanout_reply(const eye_fanout *f, uint64_t now, eye_packet *p);
#endif
