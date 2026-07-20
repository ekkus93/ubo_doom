// Ubo Doom: weapon-cycle selection logic. See ubo_weapon.h.
#include "ubo_weapon.h"

int ubo_next_owned_weapon(int cur, int n, const int* owned)
{
    int i;
    int w;

    // Start at cur+1 so we advance to a *different* weapon; only wrap back to
    // cur (at i == n) when it is the sole owned weapon.
    for (i = 1; i <= n; i++)
    {
        w = (cur + i) % n;
        if (owned[w])
            return w;
    }
    return cur;   /* nothing owned */
}
