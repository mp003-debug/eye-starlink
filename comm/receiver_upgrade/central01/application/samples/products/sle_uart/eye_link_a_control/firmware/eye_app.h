#ifndef EYE_APP_H
#define EYE_APP_H
#include "eye_event.h"
/* Teammate extension point. Called in eye task, never an IRQ. Return 1 only if
 * copied into a bounded application queue; return 0 for unavailable/full.
 * Do not block, retain the pointer, or execute a long actuator operation here.
 * Default weak implementation rejects LIVE events. TEST never calls this hook.
 * Deduplication covers one powered session only, not a durable transaction. */
int eye_accept_button(const eye_packet *event);
#endif
