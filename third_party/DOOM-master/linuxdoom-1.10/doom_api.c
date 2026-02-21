#include "doom_api.h"

#include <stdlib.h>
#include <string.h>

#include "doomdef.h"
#include "doomstat.h"
#include "d_event.h"
#include "doomkeys.h"
#include "d_main.h"
#include "d_net.h"
#include "m_argv.h"
#include "i_system.h"
#include "i_sound.h"
#include "i_video.h"
#include "s_sound.h"

int ubo_library_mode = 0;

// Filled by i_video_ubo.c via extern.
uint8_t ubo_rgba[320 * 200 * 4];

static int g_inited = 0;

// Keep argv storage alive for the lifetime of the process.
static char* g_argv[8];
static int g_argc = 0;
static char g_prog[] = "ubodoom";

static int map_ubo_key(ubo_key_t key)
{
    switch (key)
    {
        case UBO_KEY_UP: return KEY_UPARROW;
        case UBO_KEY_DOWN: return KEY_DOWNARROW;
        case UBO_KEY_LEFT: return KEY_LEFTARROW;
        case UBO_KEY_RIGHT: return KEY_RIGHTARROW;
        case UBO_KEY_FIRE: return KEY_RCTRL;
        case UBO_KEY_USE: return ' ';
        case UBO_KEY_ESCAPE: return KEY_ESCAPE;
        default: return 0;
    }
}

int doom_init(const char* iwad_path)
{
    if (g_inited) return 0;
    if (!iwad_path) return -1;

    ubo_library_mode = 1;

    // Build a minimal argv: [ubodoom, -iwad, <path>]
    g_argc = 0;
    g_argv[g_argc++] = g_prog;
    g_argv[g_argc++] = (char*)"-iwad";
    g_argv[g_argc++] = strdup(iwad_path);

    myargc = g_argc;
    myargv = g_argv;

    // D_DoomMain will call I_Init(), initialize sound/video, and then return (because ubo_library_mode=1).
    D_DoomMain();

    // In the original program, I_InitGraphics() is called at the start of D_DoomLoop().
    // Our i_video_ubo backend doesn't need it, but keeping the call preserves expected init sequencing.
    I_InitGraphics();

    g_inited = 1;
    return 0;
}

void doom_tick(void)
{
    if (!g_inited) return;

    // One "outer loop" iteration of D_DoomLoop().
    I_StartFrame();
    TryRunTics();

    // Position-based audio update.
    if (players[consoleplayer].mo)
        S_UpdateSounds(players[consoleplayer].mo);
    else
        S_UpdateSounds(NULL);

    D_Display();

#ifdef SNDINTR
    I_UpdateSound();
#endif
    I_SubmitSound();
}

void doom_shutdown(void)
{
    if (!g_inited) return;

    // Do NOT call I_Quit() (it exits the process). Just shut down sound.
    I_ShutdownSound();
    g_inited = 0;
}

void doom_key_down(ubo_key_t key)
{
    event_t ev;
    ev.type = ev_keydown;
    ev.data1 = map_ubo_key(key);
    ev.data2 = 0;
    ev.data3 = 0;
    D_PostEvent(&ev);
}

void doom_key_up(ubo_key_t key)
{
    event_t ev;
    ev.type = ev_keyup;
    ev.data1 = map_ubo_key(key);
    ev.data2 = 0;
    ev.data3 = 0;
    D_PostEvent(&ev);
}

const uint8_t* doom_get_rgba_ptr(void) { return ubo_rgba; }
int doom_get_rgba_width(void) { return 320; }
int doom_get_rgba_height(void) { return 200; }
