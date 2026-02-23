#include "doom_api.h"

#include <setjmp.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <execinfo.h>

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

// D_DoomLoop checks advancedemo each iteration; since we drive ticks manually
// we need to mirror that check ourselves.
extern boolean advancedemo;
void D_DoAdvanceDemo(void);

// maketic lives in d_net.c and isn't exported from d_net.h; reset it in
// doom_reset() to avoid the NetUpdate: numtics > BACKUPTICS error on re-init.
extern int maketic;
extern int gametic;
extern ticcmd_t netcmds[MAXPLAYERS][BACKUPTICS];

// D_ProcessEvents, G_BuildTiccmd, M_Ticker, G_Ticker for the singletics path.
void D_ProcessEvents(void);
void G_BuildTiccmd(ticcmd_t* cmd);
void G_Ticker(void);
void M_Ticker(void);
void D_Display(void);

int ubo_library_mode = 0;

// Jump buffer used by I_Error in library mode to avoid calling exit().
jmp_buf ubo_error_jmp;
int ubo_error_jmp_valid = 0;

// Filled by i_video_ubo.c via extern.
uint8_t ubo_rgba[320 * 200 * 4];

static int g_inited = 0;  // 0=not started, 1=ok, -1=failed

// Signal-based crash catch — catches SIGSEGV/SIGBUS during doom_init so that
// a crash in R_Init* (or anywhere else in D_DoomMain) is converted to a clean
// -1 return rather than killing the host process (ubo_app).
static sigjmp_buf g_crash_jmp;
static volatile sig_atomic_t g_crash_jmp_valid = 0;

static void doom_crash_handler(int sig)
{
    // Print a backtrace before longjmping — this is async-signal-safe enough
    // for debugging purposes (backtrace/backtrace_symbols_fd use no malloc).
    void *bt[32];
    int n = backtrace(bt, 32);
    fprintf(stderr, "[doom] SIGNAL %d — backtrace (%d frames):\n", sig, n);
    backtrace_symbols_fd(bt, n, 2);  // fd 2 = stderr
    fflush(stderr);
    (void)sig;
    if (g_crash_jmp_valid) {
        g_crash_jmp_valid = 0;
        siglongjmp(g_crash_jmp, 1);
    }
    // Not in a protected region — restore default and re-raise.
    signal(sig, SIG_DFL);
    raise(sig);
}

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
    if (g_inited == 1) return 0;
    if (g_inited == -1) return -1;  /* previous init failed; DOOM globals are dirty */
    if (!iwad_path) return -1;

    ubo_library_mode = 1;

    // Build a minimal argv: [ubodoom, -iwad, <path>]
    // Zone heap size is controlled by mb_used in m_misc.c defaults (set to 32 MB).
    g_argc = 0;
    g_argv[g_argc++] = g_prog;
    g_argv[g_argc++] = (char*)"-iwad";
    g_argv[g_argc++] = strdup(iwad_path);

    myargc = g_argc;
    myargv = g_argv;

    // Install crash handlers for SIGSEGV and SIGBUS so that a crash inside
    // D_DoomMain (e.g. in R_GenerateLookup with a bad WAD texture) is caught
    // and returned as -1 instead of killing the host process.
    struct sigaction sa, sa_old_segv, sa_old_bus;
    sa.sa_handler = doom_crash_handler;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = SA_RESETHAND;  // auto-restore default after first delivery
    sigaction(SIGSEGV, &sa, &sa_old_segv);
    sigaction(SIGBUS,  &sa, &sa_old_bus);

    g_crash_jmp_valid = 1;
    if (sigsetjmp(g_crash_jmp, 1) != 0) {
        // SIGSEGV or SIGBUS during init — restore handlers and abort cleanly.
        g_crash_jmp_valid = 0;
        ubo_error_jmp_valid = 0;
        sigaction(SIGSEGV, &sa_old_segv, NULL);
        sigaction(SIGBUS,  &sa_old_bus,  NULL);
        g_inited = -1;
        fprintf(stderr, "[doom] doom_init aborted via signal (SIGSEGV/SIGBUS)\n");
        return -1;
    }

    // Catch I_Error calls (which would otherwise call exit()) via longjmp.
    ubo_error_jmp_valid = 1;
    if (setjmp(ubo_error_jmp) != 0) {
        // I_Error fired during init — abort cleanly without killing the process.
        g_crash_jmp_valid = 0;
        ubo_error_jmp_valid = 0;
        sigaction(SIGSEGV, &sa_old_segv, NULL);
        sigaction(SIGBUS,  &sa_old_bus,  NULL);
        g_inited = -1;
        fprintf(stderr, "[doom] doom_init aborted via I_Error longjmp\n");
        return -1;
    }

    // D_DoomMain will call I_Init(), initialize sound/video, and then return (because ubo_library_mode=1).
    D_DoomMain();

    // In the original program, I_InitGraphics() is called at the start of D_DoomLoop().
    // Our i_video_ubo backend doesn't need it, but keeping the call preserves expected init sequencing.
    I_InitGraphics();

    g_crash_jmp_valid = 0;
    ubo_error_jmp_valid = 0;
    sigaction(SIGSEGV, &sa_old_segv, NULL);
    sigaction(SIGBUS,  &sa_old_bus,  NULL);
    g_inited = 1;

    // Re-install the crash handler permanently (without SA_RESETHAND) so that
    // SIGSEGV/SIGBUS during doom_tick are also caught instead of killing ubo_app.
    sa.sa_flags = 0;  // persistent, not one-shot
    sigaction(SIGSEGV, &sa, NULL);
    sigaction(SIGBUS,  &sa, NULL);

    // In library mode we drive ticks manually (singletics path), so set the
    // singletics flag.  This makes every NetUpdate() call in the engine
    // (r_main.c, d_main.c, d_net.c) return immediately, preventing the
    // "netbuffer->numtics > BACKUPTICS" I_Error after ~12 rendered frames.
    extern boolean singletics;
    singletics = true;

    // Force key bindings to known-good values after M_LoadDefaults has run
    // (as part of D_DoomMain above).  This overrides any stale/zeroed entries
    // in ~/.doomrc such as key_right=0 and key_left=0 which would break turning.
    // Also locks key_fire to KEY_RCTRL — KEY_ENTER is stolen by HU_MSGREFRESH
    // (hu_stuff.h) and would be eaten before reaching G_Responder.
    extern int key_fire, key_right, key_left, key_up, key_down;
    key_fire  = KEY_RCTRL;
    key_right = KEY_RIGHTARROW;
    key_left  = KEY_LEFTARROW;
    key_up    = KEY_UPARROW;
    key_down  = KEY_DOWNARROW;

    return 0;
}

void doom_tick(void)
{
    if (g_inited != 1) return;

    // Arm the crash jump so SIGSEGV/SIGBUS and I_Error during the tick are
    // caught here rather than killing the host process (ubo_app).
    ubo_error_jmp_valid = 1;
    g_crash_jmp_valid = 1;

    if (sigsetjmp(g_crash_jmp, 1) != 0) {
        // SIGSEGV or SIGBUS mid-tick.
        g_crash_jmp_valid = 0;
        ubo_error_jmp_valid = 0;
        g_inited = -1;
        fprintf(stderr, "[doom] doom_tick aborted via signal (SIGSEGV/SIGBUS)\n");
        return;
    }

    if (setjmp(ubo_error_jmp) != 0) {
        // I_Error mid-tick (e.g. Z_Malloc failure during level load).
        g_crash_jmp_valid = 0;
        ubo_error_jmp_valid = 0;
        g_inited = -1;
        fprintf(stderr, "[doom] doom_tick aborted via I_Error\n");
        return;
    }

    // One "outer loop" iteration of D_DoomLoop(), singletics path.
    // This mirrors d_main.c's singletics branch exactly: run 1 tic per
    // doom_tick call with no spin-waits, so the Kivy main thread is never
    // blocked waiting for real-time tics to accumulate.
    I_StartFrame();
    I_StartTic();
    D_ProcessEvents();
    G_BuildTiccmd(&netcmds[consoleplayer][maketic%BACKUPTICS]);
    if (advancedemo)
        D_DoAdvanceDemo();
    M_Ticker();
    G_Ticker();
    gametic++;
    maketic++;

    // Position-based audio update.
    if (players[consoleplayer].mo)
        S_UpdateSounds(players[consoleplayer].mo);
    else
        S_UpdateSounds(NULL);

    D_Display();

    I_UpdateSound();
    I_SubmitSound();

    g_crash_jmp_valid = 0;
    ubo_error_jmp_valid = 0;
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
    int doom_key = map_ubo_key(key);
    fprintf(stderr, "[doom] doom_key_down: ubo_key=%d -> doom_key=%d\n", (int)key, doom_key);
    event_t ev;
    ev.type = ev_keydown;
    ev.data1 = doom_key;
    ev.data2 = 0;
    ev.data3 = 0;
    D_PostEvent(&ev);
}

void doom_key_up(ubo_key_t key)
{
    int doom_key = map_ubo_key(key);
    fprintf(stderr, "[doom] doom_key_up:   ubo_key=%d -> doom_key=%d\n", (int)key, doom_key);
    event_t ev;
    ev.type = ev_keyup;
    ev.data1 = doom_key;
    ev.data2 = 0;
    ev.data3 = 0;
    D_PostEvent(&ev);
}

const uint8_t* doom_get_rgba_ptr(void) { return ubo_rgba; }
int doom_get_rgba_width(void) { return 320; }
int doom_get_rgba_height(void) { return 200; }
int doom_is_alive(void) { return g_inited == 1; }

void doom_reset(void)
{
    // Allow doom_init() to run again after a mid-tick crash.
    // The old zone heap leaks but all other globals will be re-initialised
    // by the next D_DoomMain() call.
    g_inited = 0;
    ubo_error_jmp_valid = 0;
    g_crash_jmp_valid = 0;

    // Clear the WAD file list so D_AddFile() starts from index 0 on the next
    // init — without this, each re-init appends the IWAD again and again,
    // causing duplicate lump registrations.
    memset(wadfiles, 0, sizeof(wadfiles));

    // Reset tic counters to avoid NetUpdate: netbuffer->numtics > BACKUPTICS.
    // gametic and maketic carry over from the crashed session and cause the
    // net tic buffer difference check to immediately fire on the next run.
    gametic = 0;
    maketic = 0;

    fprintf(stderr, "[doom] doom_reset: engine state cleared, ready for re-init\n");
}
