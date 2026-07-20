// Ubo Doom: stable-key-enum -> linuxdoom-keycode mapping.
//
// Split out of doom_api.c so it can be unit-tested in isolation: this unit
// pulls in NO engine state (no globals, no zone heap) -- only the ubo_key_t
// enum (doom_api.h) and the KEY_* constants (doomkeys.h).
#ifndef UBO_KEYMAP_H
#define UBO_KEYMAP_H

#include "doom_api.h"   /* ubo_key_t */

// Map a stable UBO key enum to a linuxdoom key code (see doomkeys.h).
// Pure function. Returns 0 for keys with no direct doom keycode
// (unknown values and UBO_KEY_WEAPON_NEXT, which is synthesized elsewhere).
int ubo_map_key(ubo_key_t key);

#endif // UBO_KEYMAP_H
