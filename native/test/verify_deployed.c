/* Verify a BUILT/DEPLOYED libubodoom.so by dlopen'ing the actual .so file (not
 * a rebuild from objects) and exercising the death -> respawn behaviour through
 * its exported symbols. Use this to confirm the shipped artifact on the device:
 * point it at the file the service loads (UBO_DOOM_LIB) and it starts a real
 * game, kills the player, and drives the real key path.
 *
 * Complements the other native tests:
 *   - test_ubo_units.c : pure logic, links nothing (fast, hermetic).
 *   - death_repro.c    : links freshly built engine .o files (tests the source).
 *   - verify_deployed.c: dlopen's a finished .so (tests the shipped binary).
 *
 * Built and run by native/scripts/run_verify_deployed.sh.
 *   Usage: verify_deployed [so] [iwad]
 *   so   defaults to $UBO_DOOM_LIB, iwad to $UBO_DOOM_IWAD.
 * Exit code is the number of failed checks (0 == all passed).
 */
#include <stdio.h>
#include <stdlib.h>
#include <dlfcn.h>

#include "doomdef.h"      /* skill_t (sk_medium) */
#include "m_fixed.h"      /* FRACUNIT */
#include "d_event.h"      /* BT_USE, BT_ATTACK */
#include "d_player.h"     /* player_t, PST_* */
#include "doom_api.h"     /* ubo_key_t */

/* Resolved from the deployed .so at runtime. */
static int   (*p_doom_init)(const char*);
static void  (*p_doom_tick)(void);
static void  (*p_doom_key_down)(int);
static void  (*p_doom_key_up)(int);
static void  (*p_doom_shutdown)(void);
static int   (*p_doom_is_alive)(void);
static void  (*p_G_DeferedInitNew)(int, int, int);
static void  (*p_P_DamageMobj)(void*, void*, void*, int);

static player_t* g_players;
static int*      g_consoleplayer;
static int*      g_usergame;      /* boolean is int-sized */
static int*      g_advancedemo;

static int failures = 0;

static void run(int n) { int i; for (i = 0; i < n; i++) p_doom_tick(); }
static void tap(int key) { p_doom_key_down(key); run(2); p_doom_key_up(key); }

static const char* pstate(int s)
{
    if (s == PST_LIVE)   return "PST_LIVE";
    if (s == PST_DEAD)   return "PST_DEAD";
    if (s == PST_REBORN) return "PST_REBORN";
    return "?";
}

static void check(int cond, const char* msg)
{
    printf(cond ? "  ok    %s\n" : "  FAIL  %s\n", msg);
    if (!cond) failures++;
}

static void* need(void* h, const char* name)
{
    void* s = dlsym(h, name);
    if (!s) { fprintf(stderr, "[verify] missing symbol: %s\n", name); exit(2); }
    return s;
}

int main(int argc, char** argv)
{
    const char* so   = (argc > 1) ? argv[1] : getenv("UBO_DOOM_LIB");
    const char* iwad = (argc > 2) ? argv[2] : getenv("UBO_DOOM_IWAD");
    void* h;
    player_t* p;
    int i;

    if (!so || !so[0]) { fprintf(stderr, "usage: %s <so> <iwad>  (or set UBO_DOOM_LIB/UBO_DOOM_IWAD)\n", argv[0]); return 2; }
    if (!iwad || !iwad[0]) { fprintf(stderr, "no IWAD (arg2 or UBO_DOOM_IWAD)\n"); return 2; }

    h = dlopen(so, RTLD_NOW | RTLD_GLOBAL);
    if (!h) { fprintf(stderr, "[verify] dlopen failed: %s\n", dlerror()); return 2; }
    printf("verifying deployed library: %s\n", so);

    p_doom_init        = need(h, "doom_init");
    p_doom_tick        = need(h, "doom_tick");
    p_doom_key_down    = need(h, "doom_key_down");
    p_doom_key_up      = need(h, "doom_key_up");
    p_doom_shutdown    = need(h, "doom_shutdown");
    p_doom_is_alive    = need(h, "doom_is_alive");
    p_G_DeferedInitNew = need(h, "G_DeferedInitNew");
    p_P_DamageMobj     = need(h, "P_DamageMobj");
    g_players          = need(h, "players");
    g_consoleplayer    = need(h, "consoleplayer");
    g_usergame         = need(h, "usergame");
    g_advancedemo      = need(h, "advancedemo");

    if (p_doom_init(iwad) != 0) { fprintf(stderr, "[verify] doom_init failed\n"); return 2; }

    /* Start a real single-player game; suppress the attract demo until it takes. */
    for (i = 0; i < 60 && !*g_usergame; i++) {
        *g_advancedemo = 0;
        p_G_DeferedInitNew(sk_medium, 1, 1);
        p_doom_tick();
    }
    run(15);

    p = &g_players[*g_consoleplayer];
    printf("game start: usergame=%d pstate=%s health=%d\n",
           *g_usergame, pstate(p->playerstate), p->health);
    if (!*g_usergame || !p->mo) { fprintf(stderr, "[verify] could not start a game\n"); return 2; }

    /* Die. */
    p_P_DamageMobj(p->mo, NULL, NULL, 10000);
    run(1);
    check(p->playerstate == PST_DEAD, "player dies from lethal damage");
    run(3);
    check(p_doom_is_alive(), "engine keeps ticking while dead (no hang)");

    /* Delay: FIRE while the view is still sinking must NOT respawn. */
    check(p->viewheight > 6 * FRACUNIT, "death view still sinking");
    tap(UBO_KEY_FIRE); run(1);
    check(p->playerstate == PST_DEAD, "FIRE while sinking does NOT respawn (delay holds)");

    /* After the view sinks, FIRE respawns (the fix). */
    run(45);
    check(p->viewheight <= 6 * FRACUNIT, "death view has sunk to the floor");
    tap(UBO_KEY_FIRE); run(25);
    check(p->playerstate == PST_LIVE && p->health > 0, "FIRE after view sunk RESPAWNS");

    /* USE still respawns. */
    p_P_DamageMobj(p->mo, NULL, NULL, 10000);
    run(50);
    check(p->playerstate == PST_DEAD, "player dies again");
    tap(UBO_KEY_USE); run(25);
    check(p->playerstate == PST_LIVE && p->health > 0, "USE after view sunk RESPAWNS");

    p_doom_shutdown();
    printf("\n");
    if (failures == 0) { printf("PASS: deployed library respawns correctly after death\n"); return 0; }
    printf("FAIL: %d check(s) failed\n", failures);
    return 1;
}
