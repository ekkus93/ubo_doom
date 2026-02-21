#include "doom_api.h"

#include <stdlib.h>
#include <string.h>

#include "doomdef.h"
#include "i_system.h"
#include "i_video.h"
#include "v_video.h"
#include "w_wad.h"
#include "z_zone.h"

// Headless video backend:
// - No X11, no input polling here.
// - Converts Doom's 8-bit paletted screen (screens[0]) into a 320x200 RGBA8888 buffer (ubo_rgba).

static int g_inited = 0;
static byte* g_palette = NULL;   // 256 * 3 RGB

void I_InitGraphics(void)
{
    if (g_inited) return;

    // Load PLAYPAL palette lump (first palette only).
    g_palette = (byte*)W_CacheLumpName("PLAYPAL", PU_STATIC);
    g_inited = 1;
}

void I_ShutdownGraphics(void)
{
    // Nothing to free (WAD cache owns PLAYPAL; ubo_rgba is static).
}

void I_SetPalette(byte* palette)
{
    // Doom will call this when palette changes (e.g., damage).
    // The argument points to 256*3 bytes.
    g_palette = palette;
}

void I_UpdateNoBlit(void) { }

void I_StartFrame(void) { }
void I_StartTic(void) { }
void I_ReadScreen(byte* scr) { memcpy(scr, screens[0], SCREENWIDTH*SCREENHEIGHT); }

void I_FinishUpdate(void)
{
    if (!g_inited) I_InitGraphics();
    if (!g_palette) return;

    // Convert 8-bit indexed pixels to RGBA (alpha=255).
    const byte* src = screens[0];
    uint8_t* dst = ubo_rgba;

    for (int i = 0; i < SCREENWIDTH * SCREENHEIGHT; i++)
    {
        int idx = src[i] * 3;
        dst[i*4 + 0] = g_palette[idx + 0];
        dst[i*4 + 1] = g_palette[idx + 1];
        dst[i*4 + 2] = g_palette[idx + 2];
        dst[i*4 + 3] = 255;
    }
}
