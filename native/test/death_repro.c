/* Death / respawn regression harness for libubodoom.
 *
 * The user reported "after I die, the game locks up." It is NOT an engine hang:
 * vanilla single-player respawn triggers only on BT_USE (p_user.c P_DeathThink),
 * and in the Ubo turn-and-shoot scheme USE is buried in the DOWN mode-cycle, so
 * a dead player mashing FIRE gets nothing and the corpse view sits there. The
 * fix makes P_DeathThink respawn on FIRE *or* USE once the death view has sunk
 * to the floor (~1s). This harness locks that behavior down.
 *
 * Unlike harness.c (which only drives attract demos), this starts a REAL game
 * via G_DeferedInitNew, kills the player with P_DamageMobj, and drives the real
 * key path -- so it links engine internals, not just the public doom_api.h.
 *
 * Built and run by native/scripts/run_death_repro.sh. Usage: death_repro <iwad>
 * Exit code is the number of failed checks (0 == all passed).
 */
#include <stdio.h>
#include <stdlib.h>

#include "doomdef.h"
#include "m_fixed.h"
#include "doomstat.h"
#include "d_player.h"
#include "d_event.h"
#include "g_game.h"
#include "p_local.h"
#include "doom_api.h"

extern boolean advancedemo;

static int failures = 0;

static void run(int n) { int i; for (i = 0; i < n; i++) doom_tick(); }

static const char* pstate(int s)
{
    if (s == PST_LIVE)   return "PST_LIVE";
    if (s == PST_DEAD)   return "PST_DEAD";
    if (s == PST_REBORN) return "PST_REBORN";
    return "?";
}

static void check(int cond, const char* msg)
{
    if (cond) {
        printf("  ok    %s\n", msg);
    } else {
        printf("  FAIL  %s\n", msg);
        failures++;
    }
}

/* Tap a key for a couple of tics, then release. */
static void tap(ubo_key_t key)
{
    doom_key_down(key); run(2); doom_key_up(key);
}

int main(int argc, char** argv)
{
    const char* iwad;
    player_t* p;
    int i;

    iwad = (argc > 1) ? argv[1] : getenv("UBO_DOOM_IWAD");
    if (!iwad || !iwad[0]) { fprintf(stderr, "usage: %s <iwad>\n", argv[0]); return 2; }
    if (doom_init(iwad) != 0) { fprintf(stderr, "[death] doom_init failed\n"); return 2; }

    /* Start a real single-player game on map 1, skill medium. Re-assert
       ga_newgame and suppress the attract demo each tick until it takes, so
       D_DoAdvanceDemo can't steal gameaction. */
    for (i = 0; i < 60 && !usergame; i++) {
        advancedemo = false;
        G_DeferedInitNew(sk_medium, 1, 1);
        doom_tick();
    }
    run(15);   /* let P_SetupLevel settle */

    p = &players[consoleplayer];
    printf("death/respawn: usergame=%d gamestate=%d pstate=%s health=%d\n",
           usergame, (int)gamestate, pstate(p->playerstate), p->health);
    if (!usergame || !p->mo) {
        fprintf(stderr, "[death] could not start a real game; aborting\n");
        return 2;
    }

    /* Kill the player outright. */
    P_DamageMobj(p->mo, NULL, NULL, 10000);
    run(1);
    check(p->playerstate == PST_DEAD, "player dies from lethal damage");

    /* (1) The engine keeps ticking while dead -- no hang, stays alive. */
    run(3);
    check(doom_is_alive(), "engine keeps ticking while dead (no hang)");

    /* (2) DELAY: FIRE while the view is still sinking must NOT respawn, so the
       death view stays visible instead of respawning on a held fire key. */
    check(p->viewheight > 6 * FRACUNIT, "death view still sinking after a few tics");
    tap(UBO_KEY_FIRE); run(1);
    check(p->playerstate == PST_DEAD, "FIRE while view sinking does NOT respawn (delay holds)");

    /* (3) After the view has sunk, FIRE respawns (the natural action button). */
    run(45);
    check(p->viewheight <= 6 * FRACUNIT, "death view has sunk to the floor");
    tap(UBO_KEY_FIRE);
    run(25);   /* let ga_loadlevel run and respawn the player */
    check(p->playerstate == PST_LIVE && p->health > 0, "FIRE after view sunk respawns");

    /* (4) USE must still respawn: kill again, let the view sink, press USE. */
    P_DamageMobj(p->mo, NULL, NULL, 10000);
    run(50);   /* die + let the view sink */
    check(p->playerstate == PST_DEAD, "player dies again");
    tap(UBO_KEY_USE);
    run(25);
    check(p->playerstate == PST_LIVE && p->health > 0, "USE after view sunk respawns");

    doom_shutdown();

    printf("\n");
    if (failures == 0) {
        printf("PASS: death/respawn behaves as expected\n");
        return 0;
    }
    printf("FAIL: %d death/respawn check(s) failed\n", failures);
    return 1;
}
