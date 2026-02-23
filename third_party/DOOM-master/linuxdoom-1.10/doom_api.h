#ifndef UBO_DOOM_API_H
#define UBO_DOOM_API_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// When non-zero, D_DoomMain will return after initialization (instead of entering D_DoomLoop).
extern int ubo_library_mode;

// Framebuffer produced by i_video_ubo.c (320x200 RGBA8888)
extern uint8_t ubo_rgba[320 * 200 * 4];

// Minimal embedded API.
int doom_init(const char* iwad_path);
void doom_tick(void);
void doom_shutdown(void);

// Input (a tiny stable enum that we map to doomkeys.h internally).
typedef enum ubo_key_e {
    UBO_KEY_UP = 1,
    UBO_KEY_DOWN = 2,
    UBO_KEY_LEFT = 3,
    UBO_KEY_RIGHT = 4,
    UBO_KEY_FIRE = 5,     // maps to KEY_RCTRL (Ctrl) — KEY_ENTER avoided: stolen by HU_MSGREFRESH
    UBO_KEY_USE = 6,      // maps to Space
    UBO_KEY_ESCAPE = 7,   // maps to Esc
} ubo_key_t;

void doom_key_down(ubo_key_t key);
void doom_key_up(ubo_key_t key);

// Accessors for ctypes.
const uint8_t* doom_get_rgba_ptr(void);
int doom_get_rgba_width(void);
int doom_get_rgba_height(void);

// Returns 1 if the engine is healthy, 0 otherwise (init failed or died mid-tick).
int doom_is_alive(void);

// Reset engine state so doom_init() can be called again after a mid-tick crash.
// NOTE: leaks the old zone heap allocation — acceptable for a crash recovery path.
void doom_reset(void);

#ifdef __cplusplus
}
#endif

#endif // UBO_DOOM_API_H
