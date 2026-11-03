#ifndef EYE_SHARE_VIEW_H
#define EYE_SHARE_VIEW_H
#include "eye_share.h"
#include <string.h>
/* Call mailbox functions under the board's short IRQ lock; no rendering or
 * serial/SPI operations occur there. Care and local keys own presentation. */
typedef struct {
    eye_message pending, current;
    unsigned revision;
    uint64_t received_ms;
    uint8_t has_pending, visible, acknowledged, stale;
} eye_share_view;
static inline int eye_share_publish(eye_share_view *v,const eye_message *m,int care) {
    if(care || (m->category==4 && v->visible && v->current.category!=4))return EYE_SHARE_BLOCKED;
    if(v->has_pending)return 0;
    v->pending=*m;v->has_pending=1;return 1;
}
static inline void eye_share_hide(eye_share_view *v) {
    if(v->visible || v->has_pending)++v->revision;
    v->visible=v->has_pending=0;
}
static inline void eye_share_view_tick(eye_share_view *v,int care,uint64_t now) {
    if(care) {eye_share_hide(v);return;}
    if(v->has_pending) {
        v->current=v->pending;v->has_pending=0;v->visible=1;
        v->acknowledged=v->stale=0;v->received_ms=now;++v->revision;
    }
    if(v->visible && v->current.category==4 && !v->stale &&
       (now<v->received_ms || now-v->received_ms>=120000)) {v->stale=1;++v->revision;}
}
static inline void eye_share_read(eye_share_view *v) {
    if(v->visible && !v->acknowledged) {v->acknowledged=1;++v->revision;}
}
void eye_share_render(const eye_message *message,unsigned node,int acknowledged,int stale,uint8_t frame[48000]);
/* Font validation also rejects unassigned GB2312 byte pairs. */
int eye_share_glyph_supported(uint8_t first,uint8_t second);
#endif
