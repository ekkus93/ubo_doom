/* Pure-logic unit tests for Ubo Doom's C seams.
 *
 * These exercise the two Ubo-authored bits of logic that are easy to get wrong
 * and expensive to catch on-device:
 *   - ubo_map_key()          (ubo_keymap.c) -- the stable-key -> doomkey table
 *   - ubo_next_owned_weapon()(ubo_weapon.c) -- the cyclic weapon-cycle scan
 *
 * They link ONLY those two translation units -- no engine objects, no zone
 * heap, no IWAD, no device. Built/run by native/scripts/run_unit_tests.sh
 * (or `make test-units` in the linuxdoom-1.10 tree). No test framework: plain
 * assert-style checks and a failure count as the exit code.
 */
#include <stdio.h>

#include "doom_api.h"     /* ubo_key_t */
#include "doomkeys.h"     /* KEY_* */
#include "ubo_keymap.h"
#include "ubo_weapon.h"

static int failures = 0;

#define CHECK_EQ(got, want, msg)                                              \
    do {                                                                      \
        long g_ = (long)(got);                                                \
        long w_ = (long)(want);                                               \
        if (g_ == w_) {                                                       \
            printf("  ok    %s\n", (msg));                                    \
        } else {                                                              \
            printf("  FAIL  %s: got %ld, want %ld  (%s:%d)\n",                \
                   (msg), g_, w_, __FILE__, __LINE__);                        \
            failures++;                                                       \
        }                                                                     \
    } while (0)

#define CHECK(cond, msg)                                                      \
    do {                                                                      \
        if (cond) {                                                           \
            printf("  ok    %s\n", (msg));                                    \
        } else {                                                              \
            printf("  FAIL  %s  (%s:%d)\n", (msg), __FILE__, __LINE__);       \
            failures++;                                                       \
        }                                                                     \
    } while (0)

/* --- ubo_map_key ------------------------------------------------------- */

static void test_keymap(void)
{
    printf("ubo_map_key:\n");

    /* USE must be Space: it is what produces BT_USE, which opens doors and,
       critically, triggers respawn from the death screen (p_user.c). */
    CHECK_EQ(ubo_map_key(UBO_KEY_USE), ' ', "USE -> space (respawn/use path)");

    /* FIRE must be RCTRL, never ENTER -- ENTER is eaten by HU_MSGREFRESH
       before it reaches G_Responder, so firing would silently break. */
    CHECK_EQ(ubo_map_key(UBO_KEY_FIRE), KEY_RCTRL, "FIRE -> KEY_RCTRL");
    CHECK(ubo_map_key(UBO_KEY_FIRE) != KEY_ENTER, "FIRE is not KEY_ENTER");

    CHECK_EQ(ubo_map_key(UBO_KEY_MENU_SELECT), KEY_ENTER, "MENU_SELECT -> KEY_ENTER");
    CHECK_EQ(ubo_map_key(UBO_KEY_ESCAPE), KEY_ESCAPE, "ESCAPE -> KEY_ESCAPE");
    CHECK_EQ(ubo_map_key(UBO_KEY_UP), KEY_UPARROW, "UP -> KEY_UPARROW");
    CHECK_EQ(ubo_map_key(UBO_KEY_DOWN), KEY_DOWNARROW, "DOWN -> KEY_DOWNARROW");
    CHECK_EQ(ubo_map_key(UBO_KEY_LEFT), KEY_LEFTARROW, "LEFT -> KEY_LEFTARROW");
    CHECK_EQ(ubo_map_key(UBO_KEY_RIGHT), KEY_RIGHTARROW, "RIGHT -> KEY_RIGHTARROW");

    /* WEAPON_NEXT is synthesized in doom_key_down(), not a real key, and an
       out-of-range value must not fall through to a bogus keycode. */
    CHECK_EQ(ubo_map_key(UBO_KEY_WEAPON_NEXT), 0, "WEAPON_NEXT -> 0 (not a keycode)");
    CHECK_EQ(ubo_map_key((ubo_key_t)0), 0, "unknown key -> 0");

    /* No two live actions may collide, or one would shadow the other. */
    CHECK(ubo_map_key(UBO_KEY_FIRE) != ubo_map_key(UBO_KEY_USE),
          "FIRE and USE map to distinct keys");
    CHECK(ubo_map_key(UBO_KEY_UP) != ubo_map_key(UBO_KEY_DOWN),
          "UP and DOWN map to distinct keys");
    CHECK(ubo_map_key(UBO_KEY_LEFT) != ubo_map_key(UBO_KEY_RIGHT),
          "LEFT and RIGHT map to distinct keys");
}

/* --- ubo_next_owned_weapon --------------------------------------------- */

/* Weapon indices (doomdef.h): fist=0 pistol=1 shotgun=2 chaingun=3 missile=4
   plasma=5 bfg=6 chainsaw=7 supershotgun=8. NUMWEAPONS was 9 when written;
   the function is generic over n, and the tests pass n explicitly. */
#define NW 9

static void test_weapon_cycle(void)
{
    int all[NW];
    int sparse[NW];
    int one[NW];
    int none[NW];
    int i;

    printf("ubo_next_owned_weapon:\n");

    for (i = 0; i < NW; i++) {
        all[i] = 1;
        sparse[i] = 0;
        one[i] = 0;
        none[i] = 0;
    }
    sparse[0] = 1;  /* fist    */
    sparse[3] = 1;  /* chaingun */
    one[1] = 1;     /* pistol only */

    /* Sequential advance when everything is owned. */
    CHECK_EQ(ubo_next_owned_weapon(1, NW, all), 2, "all owned: pistol -> shotgun");
    CHECK(ubo_next_owned_weapon(1, NW, all) != 1, "all owned: advances off current");

    /* Wrap past the last slot back to the first. */
    CHECK_EQ(ubo_next_owned_weapon(8, NW, all), 0, "all owned: supershotgun wraps to fist");

    /* Skip unowned slots in both directions of the wrap. */
    CHECK_EQ(ubo_next_owned_weapon(0, NW, sparse), 3, "sparse: fist -> chaingun (skips 1,2)");
    CHECK_EQ(ubo_next_owned_weapon(3, NW, sparse), 0, "sparse: chaingun wraps to fist (skips 4-8)");

    /* Only the current weapon owned -> stays put (full loop finds only itself). */
    CHECK_EQ(ubo_next_owned_weapon(1, NW, one), 1, "single owned: stays on pistol");

    /* Nothing owned -> returns cur unchanged (caller then leaves it alone). */
    CHECK_EQ(ubo_next_owned_weapon(4, NW, none), 4, "none owned: returns cur");
}

int main(void)
{
    test_keymap();
    test_weapon_cycle();

    printf("\n");
    if (failures == 0) {
        printf("PASS: all Ubo unit checks passed\n");
        return 0;
    }
    printf("FAIL: %d Ubo unit check(s) failed\n", failures);
    return 1;
}
