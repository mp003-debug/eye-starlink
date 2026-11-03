/* Task-owned bridge and receiver logic, portable C99 for host verification. */
#ifndef EYE_ENDPOINT_H
#define EYE_ENDPOINT_H
#include "eye_event.h"
typedef int (*eye_accept_fn)(const eye_packet *event, void *context);
typedef struct {
    eye_packet request;
    uint64_t first_ms;
    int waiting, has_request;
} eye_bridge;
void eye_bridge_reset(eye_bridge *bridge);
/* Returns one only when request may be forwarded. Repeated UART requests are
 * forwarded so an ACK lost on the UART can be recovered by remote deduplication. */
int eye_bridge_request(eye_bridge *bridge, const eye_packet *request, uint64_t now);
int eye_bridge_ack(eye_bridge *bridge, const eye_packet *ack, uint64_t now);
/* Acceptance is transactional: rejected application handoff does not advance
 * sequence/dedup state. TEST and LIVE are separate handlers; NULL rejects. */
int eye_endpoint_receive(eye_receiver *receiver, const eye_packet *request,
    uint64_t now, eye_packet *reply, eye_accept_fn test, eye_accept_fn live, void *context);
#endif
