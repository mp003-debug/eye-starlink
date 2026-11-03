/* File-only pcaudiolib ABI adapter for eSpeak NG's WAV mode.
 * No hardware, audio server, allocation or network operations are permitted.
 * The real PCM output is delivered exclusively by the eye-control main loop.
 */
#include <stddef.h>
#include <stdint.h>
#include <errno.h>
struct audio_object;
struct audio_object *create_audio_device_object(const char *device,
        const char *application_name, const char *description) {
    (void)device; (void)application_name; (void)description; return NULL;
}
int audio_object_open(struct audio_object *object, int format, uint32_t rate,
        uint8_t channels) {
    (void)object; (void)format; (void)rate; (void)channels; return ENODEV;
}
int audio_object_write(struct audio_object *object, const void *data, size_t bytes) {
    (void)object; (void)data; (void)bytes; return ENODEV;
}
int audio_object_drain(struct audio_object *object) { (void)object; return ENODEV; }
int audio_object_flush(struct audio_object *object) { (void)object; return ENODEV; }
void audio_object_close(struct audio_object *object) { (void)object; }
void audio_object_destroy(struct audio_object *object) { (void)object; }
const char *audio_object_strerror(struct audio_object *object, int error) {
    (void)object; (void)error; return "File-only synthesis; device output is disabled";
}
