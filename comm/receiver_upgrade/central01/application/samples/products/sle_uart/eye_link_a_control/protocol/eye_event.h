/* Portable C99 wire/receiver reference; no radio or actuator implementation.
 * Integrator supplies monotonic ms and calls eye_disconnect on SLE disconnect.
 * Frames must be validated before enqueueing an actuator request, then ACKed.
 */
#ifndef EYE_EVENT_H
#define EYE_EVENT_H
#include <stdint.h>
#include <stddef.h>
#define EYE_FRAME_SIZE 16
#define EYE_HELLO 1
#define EYE_PING 2
#define EYE_EVENT 16
#define EYE_ACK 128
#define EYE_TEST 1
#define EYE_WATER 1
#define EYE_REST 2
#define EYE_HELP 3
#define EYE_MORE 4
#define EYE_BACK 5
enum { EYE_OK, EYE_DUPLICATE, EYE_NO_SESSION, EYE_OLD_SEQUENCE, EYE_BAD_EVENT, EYE_BAD_MODE, EYE_BUSY };
typedef struct {uint32_t session, sequence; uint8_t kind, code, detail, version;} eye_packet;
typedef struct {uint8_t data[EYE_FRAME_SIZE]; size_t used; uint32_t bad_frames;} eye_decoder;
typedef struct {
    uint32_t session; uint8_t mode, allow_test, has_last, has_time;
    uint64_t last_ms; eye_packet last;
} eye_receiver;
uint16_t eye_crc16(const uint8_t *data, size_t size);
int eye_encode(const eye_packet *p, uint8_t out[EYE_FRAME_SIZE]);
int eye_decode(const uint8_t raw[EYE_FRAME_SIZE], eye_packet *p);
int eye_feed(eye_decoder *d, uint8_t byte, eye_packet *p);
void eye_init(eye_receiver *r, int allow_test);
void eye_disconnect(eye_receiver *r);
/* Returns 1 for reply, 0 for incoming ACK (no reply), -1 for clock fault.
 * deliver is 1 only once per accepted EVENT. TEST is passed through in p.detail.
 * Test-mode receivers must route to logging/test handlers, never real actuators.
 */
int eye_receive(eye_receiver *r, const eye_packet *p, uint64_t now_ms,
                eye_packet *reply, int *deliver);
#endif
