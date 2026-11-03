#include "eye_app.h"
#include "care_hmi.h"

/* B's LIVE hook only copies into the bounded HMI work queue. */
int eye_accept_button(const eye_packet *event)
{
    if (event == NULL) return 0;
    return care_hmi_accept_event(event->session, event->sequence, event->code);
}

int eye_accept_share(const eye_message *message) { return care_hmi_accept_share(message); }
