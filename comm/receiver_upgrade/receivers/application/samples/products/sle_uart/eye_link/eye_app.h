#ifndef EYE_APP_H
#define EYE_APP_H
#include "eye_event.h"
#include "eye_share.h"
/* Teammate extension point. Called in eye task, never an IRQ. Return 1 only if
 * copied into a bounded application queue; return 0 for unavailable/full.
 * Do not block, retain the pointer, or execute a long actuator operation here.
 * This build links the wearable queue implementation. TEST never calls this hook.
 * Deduplication covers one powered session only, not a durable transaction. */
int eye_accept_button(const eye_packet *event);
int eye_accept_share(const eye_message *message);
#endif
