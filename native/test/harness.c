/* Headless concurrency/memory stress harness for libubodoom.
 *
 * Drives the engine through many ticks. The attract-loop demos shoot and spawn
 * monsters, so S_StartSound -> I_StartSound -> addsfx runs on THIS (game) thread
 * while the dedicated audio thread's mixer (I_UpdateSound) reads/advances the
 * same low-level channel arrays. That is exactly the cross-thread interaction we
 * want ThreadSanitizer to inspect, and whose fixed-size global arrays we want
 * AddressSanitizer to bounds-check.
 *
 * Built and run by native/scripts/run_sanitizers.sh, which links it against
 * sanitizer-instrumented Doom objects. Usage: harness <iwad> [ticks]
 */
#include <stdio.h>
#include <stdlib.h>
#include "doom_api.h"

int main(int argc, char** argv)
{
    const char* iwad;
    int ticks;
    int i;
    int rc;

    iwad = (argc > 1) ? argv[1] : getenv("UBO_DOOM_IWAD");
    ticks = (argc > 2) ? atoi(argv[2]) : 2000;
    if (!iwad || !iwad[0]) {
        fprintf(stderr, "usage: %s <iwad> [ticks]\n", argv[0]);
        return 2;
    }

    rc = doom_init(iwad);
    fprintf(stderr, "[harness] doom_init(%s) -> %d\n", iwad, rc);
    if (rc != 0)
        return 1;

    for (i = 0; i < ticks; i++) {
        doom_tick();
        if (!doom_is_alive()) {
            fprintf(stderr, "[harness] engine reported not-alive at tick %d\n", i);
            break;
        }
        /* Poke the input path too. Ignored during demo playback, exercised if a
         * game is started; harmless either way, adds event-path activity. */
        if ((i % 40) == 0)
            doom_key_down(UBO_KEY_FIRE);
        else if ((i % 40) == 8)
            doom_key_up(UBO_KEY_FIRE);
        else if ((i % 40) == 16)
            doom_key_down(UBO_KEY_WEAPON_NEXT);
    }

    fprintf(stderr, "[harness] ran %d ticks; shutting down\n", i);
    doom_shutdown();
    fprintf(stderr, "[harness] clean shutdown\n");
    return 0;
}
