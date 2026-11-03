#include "eye_app.h"
#include "wearable_epd.h"

/* Strong implementation of the teammate's nonblocking application hook. */
int eye_accept_button(const eye_packet *event)
{
    if (event == NULL) return 0;
    return wearable_epd_accept_event(event->session, event->sequence, event->code);
}

int eye_accept_share(const eye_message *message) { return wearable_epd_accept_share(message); }
